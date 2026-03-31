"""BlinkDetector — ported from zyphraexps/backend/pipeline/stages/detectors.py.

MAD-based adaptive threshold with guard chain. Validated on 342 blink trials.
See docs/research/2026-03-09-muse2-detector-lessons.md for design rationale.
"""
from __future__ import annotations

import logging
import time
from collections import deque

import numpy as np

from muse_vtuber.pipeline.base import Stage
from muse_vtuber.pipeline.speech import SpeechResult, _hf_rms
from muse_vtuber.pipeline.types import Cadence, Event, PipelineFrame


class BlinkDetector(Stage):
    """Detect blinks via MAD-based adaptive threshold + shape guards.

    Detection pipeline:
    1. MAD-based adaptive threshold on frontal channels (AF7+AF8)
    2. Sustained deflection: must cross threshold for multiple consecutive chunks
    3. Motion guard: reject if gyro pitch/yaw > 20 deg/s
    4. Bilateral correlation guard (disabled by default)
    5. Clench guard: temporal HF above its own rolling baseline
    6. Speech fusion: reject if SpeechDetector flagged speech_active
    7. Shape validation: duration [50-200ms] + slope direction
    8. Refractory + multi-blink classification window
    """

    name = "blink_detector"
    cadence = Cadence.FAST
    _log = logging.getLogger("blink_detector")

    # Shape validation buffer: ±200ms at 256Hz
    _HALF_WIN = 51
    _BUFFER_SIZE = 512  # ~2s rolling buffer for shape analysis

    def __init__(
        self,
        threshold_sd: float = 2.5,
        refractory_ms: float = 100,
        classify_window_ms: float = 600,
        max_hf_ratio: float = 3.5,
        min_deflection_ms: float = 50.0,
        max_deflection_ms: float = 200.0,
        min_bilateral_corr: float = 0.0,  # disabled: unreliable with dry electrodes
    ):
        self.threshold_sd = threshold_sd
        self.refractory_ms = refractory_ms
        self.classify_window_ms = classify_window_ms
        self.max_hf_ratio = max_hf_ratio
        self.min_deflection_ms = min_deflection_ms
        self.max_deflection_ms = max_deflection_ms
        self.min_bilateral_corr = min_bilateral_corr
        self._last_blink_time: float = 0.0
        self._pending_blinks: deque[tuple[float, float]] = deque(maxlen=10)
        self._classify_deadline: float = 0.0
        self._frontal_quality: float = 1.0
        self._last_blink_meta: dict = {}
        # Adaptive baseline (rolling window + median/MAD)
        self._baseline_window: deque[float] = deque(maxlen=256)
        self._baseline_median: float = 0.0
        self._baseline_mad: float = 1.0
        self._baseline_samples: int = 0
        # Per-channel baselines for AF7 and AF8
        self._af7_baseline_window: deque[float] = deque(maxlen=256)
        self._af7_baseline_median: float = 0.0
        self._af7_baseline_mad: float = 1.0
        self._af8_baseline_window: deque[float] = deque(maxlen=256)
        self._af8_baseline_median: float = 0.0
        self._af8_baseline_mad: float = 1.0
        # Rolling buffers for shape validation and HF ratio
        self._frontal_buf: np.ndarray = np.zeros(self._BUFFER_SIZE)
        self._temporal_buf: np.ndarray = np.zeros(self._BUFFER_SIZE)
        self._af7_buf: np.ndarray = np.zeros(self._BUFFER_SIZE)
        self._af8_buf: np.ndarray = np.zeros(self._BUFFER_SIZE)
        self._buf_pos: int = 0
        self._buf_filled: bool = False
        # Sustained deflection counter
        self._consecutive_crossed: int = 0
        # Guard enable flags
        self.guard_motion: bool = True
        self.guard_bilateral: bool = True
        self.guard_clench: bool = True
        self.guard_speech: bool = True
        self.guard_shape: bool = True
        # Rolling temporal HF baseline for clench guard
        self._temporal_hf_history: deque[float] = deque(maxlen=64)
        self._temporal_hf_baseline: float = 15.0
        self._temporal_hf_update_ctr: int = 0

    def _update_baseline(self, chunk_mean: float, n_samples: int = 1) -> None:
        """Update rolling window baseline with median/MAD."""
        self._baseline_samples += n_samples
        self._baseline_window.append(chunk_mean)

        if len(self._baseline_window) >= 8:
            values = np.array(self._baseline_window)
            self._baseline_median = float(np.median(values))
            self._baseline_mad = float(np.median(np.abs(values - self._baseline_median)))
            if self._baseline_mad < 0.5:
                self._baseline_mad = 0.5

    def _update_channel_baselines(self, af7_mean: float, af8_mean: float) -> None:
        """Update per-channel rolling baselines with contamination guard."""
        for ch_mean, window, median_attr, mad_attr in (
            (af7_mean, self._af7_baseline_window, "_af7_baseline_median", "_af7_baseline_mad"),
            (af8_mean, self._af8_baseline_window, "_af8_baseline_median", "_af8_baseline_mad"),
        ):
            ch_median = getattr(self, median_attr)
            ch_mad = getattr(self, mad_attr)
            robust_sd = 1.4826 * ch_mad
            if len(window) < 8 or robust_sd < 1e-6 or abs(ch_mean - ch_median) < 3 * robust_sd:
                window.append(ch_mean)
                if len(window) >= 8:
                    vals = np.array(window)
                    new_med = float(np.median(vals))
                    new_mad = max(float(np.median(np.abs(vals - new_med))), 0.5)
                    setattr(self, median_attr, new_med)
                    setattr(self, mad_attr, new_mad)

    def set_signal_quality(self, frontal_quality: float) -> None:
        """Set frontal signal quality (0-1) to scale blink confidence."""
        self._frontal_quality = max(0.0, min(1.0, frontal_quality))

    def _is_candidate(self, af7_mean: float, af8_mean: float) -> bool:
        """Check if either frontal channel exceeds its adaptive MAD-based threshold."""
        if self._baseline_samples < 128:
            return False  # cold start

        def _channel_thresh(median: float, mad: float) -> float:
            robust_sd = 1.4826 * mad
            return median - self.threshold_sd * robust_sd

        af7_thresh = _channel_thresh(self._af7_baseline_median, self._af7_baseline_mad)
        af8_thresh = _channel_thresh(self._af8_baseline_median, self._af8_baseline_mad)
        af7_crossed = af7_mean < af7_thresh
        af8_crossed = af8_mean < af8_thresh
        crossed = af7_crossed or af8_crossed

        if crossed or af7_mean < af7_thresh + 5.0 or af8_mean < af8_thresh + 5.0:
            self._log.debug(
                "CANDIDATE af7=%.1f(thr=%.1f %s) af8=%.1f(thr=%.1f %s) → %s",
                af7_mean, af7_thresh, "X" if af7_crossed else ".",
                af8_mean, af8_thresh, "X" if af8_crossed else ".",
                "CROSSED" if crossed else "near-miss",
            )
        return crossed

    def _append_buffer(self, frontal: np.ndarray, temporal: np.ndarray,
                       af7: np.ndarray, af8: np.ndarray) -> None:
        """Append data to rolling buffers."""
        n = len(frontal)
        if n >= self._BUFFER_SIZE:
            self._frontal_buf[:] = frontal[-self._BUFFER_SIZE:]
            self._temporal_buf[:] = temporal[-self._BUFFER_SIZE:]
            self._af7_buf[:] = af7[-self._BUFFER_SIZE:]
            self._af8_buf[:] = af8[-self._BUFFER_SIZE:]
            self._buf_pos = 0
            self._buf_filled = True
            return
        end = self._buf_pos + n
        if end <= self._BUFFER_SIZE:
            self._frontal_buf[self._buf_pos:end] = frontal
            self._temporal_buf[self._buf_pos:end] = temporal
            self._af7_buf[self._buf_pos:end] = af7
            self._af8_buf[self._buf_pos:end] = af8
            self._buf_pos = end
        else:
            first = self._BUFFER_SIZE - self._buf_pos
            self._frontal_buf[self._buf_pos:] = frontal[:first]
            self._temporal_buf[self._buf_pos:] = temporal[:first]
            self._af7_buf[self._buf_pos:] = af7[:first]
            self._af8_buf[self._buf_pos:] = af8[:first]
            rem = n - first
            self._frontal_buf[:rem] = frontal[first:]
            self._temporal_buf[:rem] = temporal[first:]
            self._af7_buf[:rem] = af7[first:]
            self._af8_buf[:rem] = af8[first:]
            self._buf_pos = rem
            self._buf_filled = True

    def _check_shape(self) -> tuple[bool, dict]:
        """Validate blink shape: duration + slope direction check.

        R² tent fitting computed for logging but not gated on (too strict
        for 4-sample streaming noise).
        """
        if not self._buf_filled and self._buf_pos < self._HALF_WIN * 2:
            return True, {}

        if self._buf_filled:
            buf = np.concatenate([
                self._frontal_buf[self._buf_pos:],
                self._frontal_buf[:self._buf_pos],
            ])
        else:
            buf = self._frontal_buf[:self._buf_pos]

        min_idx = int(np.argmin(buf))
        peak_val = float(buf[min_idx])
        if self._baseline_samples >= 128:
            half_amp = (peak_val + self._baseline_median) / 2.0
        else:
            half_amp = peak_val / 2.0

        # Find left boundary at half-amplitude
        left_idx = min_idx
        for i in range(min_idx - 1, -1, -1):
            if buf[i] >= half_amp:
                left_idx = i
                break
        else:
            left_idx = 0

        # Find right boundary at half-amplitude
        right_idx = min_idx
        for i in range(min_idx + 1, len(buf)):
            if buf[i] >= half_amp:
                right_idx = i
                break
        else:
            right_idx = len(buf) - 1

        # Secondary peak detection
        secondary_peak = False
        sp_end = right_idx + 40
        if sp_end < len(buf):
            after_right = buf[right_idx + 1:sp_end]
            if len(after_right) >= 5 and float(np.max(after_right)) > self._baseline_median + 2.0:
                secondary_peak = True

        # Duration check
        contiguous = right_idx - left_idx + 1
        dur_ms = contiguous / 256.0 * 1000.0

        if dur_ms < self.min_deflection_ms:
            self._log.info("REJECTED by shape guard: too brief %.0fms < %.0fms", dur_ms, self.min_deflection_ms)
            return False, {}
        if dur_ms > self.max_deflection_ms:
            self._log.info("REJECTED by shape guard: too broad %.0fms > %.0fms", dur_ms, self.max_deflection_ms)
            return False, {}

        # R² tent fitting
        downstroke = buf[left_idx:min_idx + 1]
        upstroke = buf[min_idx:right_idx + 1]

        if len(downstroke) < 4 or len(upstroke) < 4:
            meta = {
                "amplitude_uv": round(peak_val, 1),
                "half_amplitude_uv": round(half_amp, 1),
                "onset_slope": 0.0,
                "duration_ms": round(dur_ms, 1),
                "secondary_peak": secondary_peak,
            }
            return True, meta

        def r_squared_and_slope(segment: np.ndarray) -> tuple[float, float]:
            n = len(segment)
            start = int(n * 0.1)
            end = int(n * 0.9)
            if end - start < 3:
                return 1.0, 0.0
            inner = segment[start:end]
            x = np.arange(len(inner), dtype=np.float64)
            coeffs = np.polyfit(x, inner, 1)
            slope = float(coeffs[0])
            predicted = np.polyval(coeffs, x)
            ss_res = np.sum((inner - predicted) ** 2)
            ss_tot = np.sum((inner - np.mean(inner)) ** 2)
            if ss_tot < 1e-10:
                return 1.0, slope
            return float(1.0 - ss_res / ss_tot), slope

        r2_down, slope_down = r_squared_and_slope(downstroke)
        r2_up, slope_up = r_squared_and_slope(upstroke)

        # Slope direction check: downstroke must go down, upstroke must go up
        blink_amplitude = abs(peak_val - float(np.mean([buf[left_idx], buf[right_idx]])))
        if blink_amplitude > 1.0:
            min_slope = blink_amplitude * 0.15 / max(len(downstroke), len(upstroke))
            if slope_down > -min_slope or slope_up < min_slope:
                self._log.info(
                    "REJECTED by shape guard: slope down=%.2f up=%.2f min_mag=%.2f (plateau)",
                    slope_down, slope_up, min_slope)
                return False, {}

        meta = {
            "amplitude_uv": round(peak_val, 1),
            "half_amplitude_uv": round(half_amp, 1),
            "onset_slope": round(slope_down, 2),
            "duration_ms": round(dur_ms, 1),
            "secondary_peak": secondary_peak,
        }
        self._log.debug("SHAPE R²: down=%.2f up=%.2f slopes=%.2f/%.2f → ACCEPT",
                       r2_down, r2_up, slope_down, slope_up)
        return True, meta

    def _try_emit_blink(self, frame: PipelineFrame, now: float) -> None:
        """Run guard layers and potentially register a blink candidate."""
        def _reject(guard: str, detail: str = "") -> None:
            self._log.info("REJECTED by %s guard%s", guard, f": {detail}" if detail else "")
            frame.events.append(Event(
                kind="blink_rejected", timestamp=now, confidence=0.0,
                channel="AF7+AF8",
                metadata={"guard": guard, "detail": detail},
            ))

        # Guard 0: motion
        if self.guard_motion and frame.imu is not None and frame.imu.shape[0] > 5 and frame.imu.shape[1] > 0:
            gyro_pitch_peak = float(np.max(np.abs(frame.imu[4])))
            gyro_yaw_peak = float(np.max(np.abs(frame.imu[5])))
            if gyro_pitch_peak > 20.0 or gyro_yaw_peak > 20.0:
                _reject("motion", f"pitch={gyro_pitch_peak:.1f} yaw={gyro_yaw_peak:.1f}")
                return

        # Guard 0.5: bilateral correlation
        if self.guard_bilateral and self.min_bilateral_corr > 0:
            win = min(64, self._buf_pos if not self._buf_filled else self._BUFFER_SIZE)
            if win >= 16:
                if self._buf_pos >= win:
                    a7 = self._af7_buf[self._buf_pos - win:self._buf_pos]
                    a8 = self._af8_buf[self._buf_pos - win:self._buf_pos]
                else:
                    a7 = np.concatenate([
                        self._af7_buf[-(win - self._buf_pos):],
                        self._af7_buf[:self._buf_pos],
                    ])
                    a8 = np.concatenate([
                        self._af8_buf[-(win - self._buf_pos):],
                        self._af8_buf[:self._buf_pos],
                    ])
                corr = np.corrcoef(a7, a8)[0, 1]
                if np.isnan(corr) or corr < self.min_bilateral_corr:
                    _reject("bilateral", f"corr={corr:.2f}" if not np.isnan(corr) else "corr=NaN")
                    return

        # Guard 1: clench (temporal HF above its own baseline)
        win = min(128, self._buf_pos if not self._buf_filled else self._BUFFER_SIZE)
        if self.guard_clench and win >= 4:
            if self._buf_pos >= win:
                t_win = self._temporal_buf[self._buf_pos - win:self._buf_pos]
            else:
                t_win = np.concatenate([
                    self._temporal_buf[-(win - self._buf_pos):],
                    self._temporal_buf[:self._buf_pos],
                ])
            t_hf = _hf_rms(t_win)
            temporal_baseline = max(self._temporal_hf_baseline, 1.0)
            hf_ratio = t_hf / temporal_baseline
            effective_max_hf_ratio = self.max_hf_ratio * (2.0 - self._frontal_quality)
            if hf_ratio > effective_max_hf_ratio:
                _reject("clench", f"ratio={hf_ratio:.2f} max={effective_max_hf_ratio:.2f}")
                return

        # Guard 2: speech
        speech = frame.get(SpeechResult)
        if self.guard_speech and speech and speech.speech_active:
            _reject("speech")
            return

        # Guard 3: shape validation
        if self.guard_shape:
            shape_ok, blink_meta = self._check_shape()
        else:
            shape_ok, blink_meta = True, {}
        if not shape_ok:
            frame.events.append(Event(
                kind="blink_rejected", timestamp=now, confidence=0.0,
                channel="AF7+AF8",
                metadata={"guard": "shape"},
            ))
            return
        self._last_blink_meta = blink_meta

        elapsed_ms = (now - self._last_blink_time) * 1000
        if elapsed_ms >= self.refractory_ms:
            self._last_blink_time = now
            amp = blink_meta.get("amplitude_uv", 0.0) if blink_meta else 0.0
            dur = blink_meta.get("duration_ms", 0.0) if blink_meta else 0.0
            self._pending_blinks.append((now, amp))
            self._log.info("ACCEPTED blink: amp=%.1fµV dur=%.0fms elapsed=%.0fms",
                           amp, dur, elapsed_ms)
            if len(self._pending_blinks) == 1:
                self._classify_deadline = now + self.classify_window_ms / 1000
        else:
            self._log.info("REJECTED by refractory: elapsed=%.0fms < %.0fms",
                           elapsed_ms, self.refractory_ms)

    def process(self, frame: PipelineFrame) -> None:
        if frame.eeg is None or frame.eeg.shape[1] == 0:
            return

        now = frame.timestamp or time.time()

        af7 = frame.eeg[1].astype(np.float64)
        af8 = frame.eeg[2].astype(np.float64)
        frontal = (af7 + af8) / 2.0
        temporal = (frame.eeg[0] + frame.eeg[3]) / 2.0

        self._append_buffer(frontal, temporal, af7, af8)

        # Track temporal HF baseline every 8 chunks
        self._temporal_hf_update_ctr += 1
        if self._temporal_hf_update_ctr >= 8:
            self._temporal_hf_update_ctr = 0
            win = min(32, self._buf_pos if not self._buf_filled else self._BUFFER_SIZE)
            if win >= 8:
                if self._buf_pos >= win:
                    t_seg = self._temporal_buf[self._buf_pos - win:self._buf_pos]
                else:
                    t_seg = np.concatenate([
                        self._temporal_buf[-(win - self._buf_pos):],
                        self._temporal_buf[:self._buf_pos],
                    ])
                t_hf_val = _hf_rms(t_seg)
                if len(self._temporal_hf_history) < 8 or t_hf_val < 3.0 * self._temporal_hf_baseline:
                    self._temporal_hf_history.append(t_hf_val)
                    if len(self._temporal_hf_history) >= 8:
                        self._temporal_hf_baseline = float(np.median(self._temporal_hf_history))

        af7_mean = float(np.mean(af7))
        af8_mean = float(np.mean(af8))
        chunk_val = (af7_mean + af8_mean) / 2.0
        crossed = self._is_candidate(af7_mean, af8_mean)

        # Update baseline with contamination guard
        chunk_mean = chunk_val
        n_samp = len(frontal)
        self._update_channel_baselines(af7_mean, af8_mean)
        if self._baseline_samples < 128:
            if self._baseline_samples < 64:
                self._update_baseline(chunk_mean, n_samp)
            else:
                robust_sd = 1.4826 * self._baseline_mad
                if abs(chunk_mean - self._baseline_median) < 5 * robust_sd:
                    self._update_baseline(chunk_mean, n_samp)
        else:
            robust_sd = 1.4826 * self._baseline_mad
            if abs(chunk_mean - self._baseline_median) < 3 * robust_sd:
                self._update_baseline(chunk_mean, n_samp)

        if crossed:
            self._consecutive_crossed += 1
        else:
            if self._consecutive_crossed > 0:
                streak = self._consecutive_crossed
                self._consecutive_crossed = 0
                min_chunks = max(2, int(self.min_deflection_ms / 1000 * 256 / max(len(frontal), 1)))
                if streak >= min_chunks:
                    self._log.info(
                        "TRAILING_EDGE streak=%d (min=%d) t=%.3f → running guards",
                        streak, min_chunks, now,
                    )
                    self._try_emit_blink(frame, now)

        # Emit events once classification window expires
        if self._pending_blinks and now >= self._classify_deadline:
            count = len(self._pending_blinks)
            deepest_amp = min(amp for _, amp in self._pending_blinks)
            self._pending_blinks.clear()

            emit_meta = self._last_blink_meta or {}
            has_secondary = emit_meta.get("secondary_peak", False)

            if count >= 2:
                base_conf = min(1.0, 0.85 + (0.05 if has_secondary else 0.0))
                frame.events.append(Event(
                    kind="blink", timestamp=now,
                    confidence=round(base_conf * self._frontal_quality, 2),
                    channel="AF7+AF8",
                    metadata={**emit_meta, "type": "double"},
                ))
            else:
                base_conf = min(1.0, 0.9 + (0.05 if has_secondary else 0.0))
                frame.events.append(Event(
                    kind="blink", timestamp=now,
                    confidence=round(base_conf * self._frontal_quality, 2),
                    channel="AF7+AF8",
                    metadata=emit_meta,
                ))

import json

import pytest

from muse_vtuber.outputs.vts import (
    VTSClient,
    build_auth_request,
    build_parameter_creation_request,
    build_parameter_injection_request,
)


def test_auth_request_format():
    msg = build_auth_request("muse-vtuber", "Muse VTuber Bridge")
    data = json.loads(msg)
    assert data["apiName"] == "VTubeStudioPublicAPI"
    assert data["apiVersion"] == "1.0"
    assert data["messageType"] == "AuthenticationTokenRequest"
    assert data["data"]["pluginName"] == "muse-vtuber"
    assert data["data"]["pluginDeveloper"] == "Muse VTuber Bridge"


def test_parameter_creation_format():
    msg = build_parameter_creation_request("MuseBlink", 0.0, 0.0, 1.0)
    data = json.loads(msg)
    assert data["messageType"] == "ParameterCreationRequest"
    assert data["data"]["parameterName"] == "MuseBlink"
    assert data["data"]["defaultValue"] == 0.0
    assert data["data"]["min"] == 0.0
    assert data["data"]["max"] == 1.0


def test_parameter_injection_format():
    params = [
        ("MuseBlink", 1.0),
        ("MuseFocus", 0.7),
        ("MuseRelaxation", 0.3),
        ("MuseClench", 0.0),
    ]
    msg = build_parameter_injection_request(params)
    data = json.loads(msg)
    assert data["messageType"] == "InjectParameterDataRequest"
    values = data["data"]["parameterValues"]
    assert len(values) == 4
    assert values[0]["id"] == "MuseBlink"
    assert values[0]["value"] == 1.0


def test_parameter_injection_weight():
    """Weight field controls blending with face tracking."""
    params = [("MuseBlink", 1.0)]
    msg = build_parameter_injection_request(params, weight=0.5)
    data = json.loads(msg)
    values = data["data"]["parameterValues"]
    assert values[0]["weight"] == 0.5

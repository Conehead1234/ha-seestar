"""Security contract for the bundled driver's startup log redaction."""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[2] / "log-safety/seestar_log_redaction.py"
_SPEC = importlib.util.spec_from_file_location("seestar_log_redaction_test", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_REDACTION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_REDACTION)


def test_recursive_redaction_preserves_non_sensitive_telemetry():
    payload = {
        "battery": 72,
        "network": {"ssid": "private-network", "password": "secret"},
        "device_sn": "serial-value",
        "location": {"lat": -33.0, "lon": 151.0},
    }

    redacted = _REDACTION.redact_value(payload)

    assert redacted["battery"] == 72
    assert redacted["network"]["ssid"] == _REDACTION.REDACTED
    assert redacted["network"]["password"] == _REDACTION.REDACTED
    assert redacted["device_sn"] == _REDACTION.REDACTED
    assert redacted["location"] == _REDACTION.REDACTED


def test_preformatted_python_response_is_redacted():
    message = (
        "response: {'battery': 72, 'ssid': 'private-network', "
        "'password': 'secret', 'location': {'lat': -33.0, 'lon': 151.0}}"
    )

    redacted = _REDACTION.redact_text(message)

    assert "battery" in redacted
    assert "72" in redacted
    assert "private-network" not in redacted
    assert "secret" not in redacted
    assert "-33.0" not in redacted
    assert "151.0" not in redacted
    assert redacted.count(_REDACTION.REDACTED) >= 3


def test_scalar_fallback_redacts_without_touching_normal_text():
    message = "authentication ok password=secret battery=72"

    redacted = _REDACTION.redact_text(message)

    assert "secret" not in redacted
    assert "battery=72" in redacted


def test_log_record_factory_redacts_structured_arguments():
    previous_factory = logging.getLogRecordFactory()
    previous_option = os.environ.pop("SEESTAR_LOG_SENSITIVE_PAYLOADS", None)
    try:
        assert _REDACTION.install_log_redaction() is True
        record = logging.getLogger("redaction-test").makeRecord(
            "redaction-test",
            logging.INFO,
            __file__,
            1,
            "response: %s",
            ({"battery": 72, "password": "secret"},),
            None,
        )
        rendered = record.getMessage()
        assert "battery" in rendered
        assert "72" in rendered
        assert "secret" not in rendered
        assert _REDACTION.REDACTED in rendered
    finally:
        logging.setLogRecordFactory(previous_factory)
        if previous_option is not None:
            os.environ["SEESTAR_LOG_SENSITIVE_PAYLOADS"] = previous_option


def test_sensitive_logging_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("SEESTAR_LOG_SENSITIVE_PAYLOADS", raising=False)
    assert _REDACTION.sensitive_logging_enabled() is False

    monkeypatch.setenv("SEESTAR_LOG_SENSITIVE_PAYLOADS", "true")
    assert _REDACTION.sensitive_logging_enabled() is True

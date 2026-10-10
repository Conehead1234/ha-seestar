"""Fail-closed redaction for the bundled seestar_alp process.

The upstream driver logs complete response objects at INFO. Some firmware
responses contain Wi-Fi credentials, stable hardware identifiers, and precise
location data. This module installs a process-wide ``LogRecord`` factory before
the driver imports, sanitising structured arguments and already-formatted
dictionary strings without changing the driver's source tree.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"
_ENABLE_ENV = "SEESTAR_LOG_SENSITIVE_PAYLOADS"
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})

# Keys observed in device-state/network responses, plus conservative aliases
# used by adjacent firmware versions. Comparison is punctuation-insensitive.
_SENSITIVE_EXACT = frozenset(
    {
        "bssid",
        "coordinate",
        "coordinates",
        "cpuid",
        "deviceid",
        "devicesn",
        "gateway",
        "gps",
        "ip",
        "ipaddress",
        "lat",
        "latitude",
        "location",
        "lon",
        "long",
        "longitude",
        "mac",
        "macaddress",
        "password",
        "passwd",
        "pwd",
        "serial",
        "serialnumber",
        "sn",
        "ssid",
        "uniqueid",
    }
)
_SENSITIVE_PARTS = ("password", "passwd", "ssid", "serial", "cpuid", "location", "coordinate")

_TEXT_KEY = (
    r"(?:password|passwd|pwd|ssid|bssid|serial(?:_?number)?|sn|cpu_?id|"
    r"unique_?id|device_?id|lat(?:itude)?|lon(?:gitude)?|long|location|gps|"
    r"coordinates?|mac(?:_?address)?|ip(?:_?address)?|gateway)"
)
_TEXT_VALUE = r"(?:\{[^{}\r\n]*\}|\[[^\[\]\r\n]*\]|\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^,}\]\s]+)"
_KEY_VALUE_RE = re.compile(
    rf"(?P<prefix>['\"]?{_TEXT_KEY}['\"]?\s*[:=]\s*){_TEXT_VALUE}",
    re.IGNORECASE,
)


def _normalise_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _is_sensitive_key(key: Any) -> bool:
    normalised = _normalise_key(key)
    return normalised in _SENSITIVE_EXACT or any(
        part in normalised for part in _SENSITIVE_PARTS
    )


def redact_value(value: Any) -> Any:
    """Return a recursively sanitised copy of common log argument types."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_sensitive_key(key) else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, set):
        return {redact_value(item) for item in value}
    if isinstance(value, str):
        return redact_text(value)
    return value


def _redact_literal_fragment(text: str) -> str | None:
    """Redact a Python/JSON container embedded after a human-readable prefix."""
    candidates = (("{", "}"), ("[", "]"))
    for opener, closer in candidates:
        start = text.find(opener)
        end = text.rfind(closer)
        if start < 0 or end <= start:
            continue
        fragment = text[start : end + 1]
        parsed = None
        for parser in (ast.literal_eval, json.loads):
            try:
                parsed = parser(fragment)
                break
            except (ValueError, SyntaxError, json.JSONDecodeError):
                continue
        if isinstance(parsed, (Mapping, list, tuple, set)):
            return f"{text[:start]}{redact_value(parsed)!r}{text[end + 1:]}"
    return None


def redact_text(text: str) -> str:
    """Sanitise structured response text, with a scalar-pattern fallback."""
    literal = _redact_literal_fragment(text)
    if literal is not None:
        return literal
    return _KEY_VALUE_RE.sub(lambda match: f"{match.group('prefix')}'{REDACTED}'", text)


def sensitive_logging_enabled() -> bool:
    """Return whether the operator explicitly opted into raw payload logs."""
    return os.environ.get(_ENABLE_ENV, "false").strip().lower() in _TRUE_TOKENS


def install_log_redaction() -> bool:
    """Install the global filter unless sensitive logging was explicitly enabled.

    Returns ``True`` when redaction was installed and ``False`` for the explicit
    opt-in case. Any per-record sanitisation failure is fail-closed: the entire
    message is replaced instead of risking disclosure of its original content.
    """
    if sensitive_logging_enabled():
        return False

    previous_factory = logging.getLogRecordFactory()

    def safe_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        try:
            record.msg = redact_value(record.msg)
            record.args = redact_value(record.args)
        except Exception:
            record.msg = "[REDACTED: log record could not be safely rendered]"
            record.args = ()
        return record

    logging.setLogRecordFactory(safe_factory)
    return True

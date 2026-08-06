"""Persistent storage for KKday site-preference cookies.

Only non-credential preference cookies (currency, country_lang, lang_ui)
are stored here. Session, CSRF, auth and anti-bot cookies must never be
written through this module.
"""

from __future__ import annotations

import json
import math
import os
import platform
import re
from pathlib import Path
from typing import Any

# Only these preference cookie names are allowed to be persisted.
ALLOWED_COOKIE_NAMES = frozenset({"currency", "country_lang", "lang_ui"})

COOKIE_STORE_VERSION = 1

_ALLOWED_SAME_SITE = frozenset({"Strict", "Lax", "None"})


def _contains_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _normalize_domain(raw_domain: Any, cookie_name: str) -> str:
    if raw_domain is None or raw_domain == "":
        domain = "www.kkday.com"
    elif isinstance(raw_domain, str):
        domain = raw_domain
    else:
        raise ValueError(
            f"cookie {cookie_name!r} has non-kkday domain: {raw_domain!r}"
        )
    if domain != domain.strip() or _contains_control_characters(domain):
        raise ValueError(
            f"cookie {cookie_name!r} has non-kkday domain: {domain!r}"
        )

    domain = domain.lower()
    host = domain[1:] if domain.startswith(".") else domain
    labels = host.split(".")
    valid_labels = all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    )
    if (
        not valid_labels
        or (host != "kkday.com" and not host.endswith(".kkday.com"))
    ):
        raise ValueError(
            f"cookie {cookie_name!r} has non-kkday domain: {domain!r}"
        )
    return domain


def default_cookie_store_path() -> Path:
    """Return the per-user path for the preference-cookie file.

    Stored under the user's Documents folder so it is easy to locate and back
    up on the Hermes automation machine, and survives browser-profile resets.
    """

    system = platform.system()
    if system == "Windows":
        docs = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    else:
        docs = Path.home() / "Documents"
    return docs / "KKdayScraper" / "preference_cookies.json"


def _normalize_cookie(raw: dict[str, Any]) -> dict[str, Any]:
    name = raw.get("name")
    if not isinstance(name, str):
        raise ValueError("cookie name must be a string")
    if name not in ALLOWED_COOKIE_NAMES:
        raise ValueError(f"refusing to persist non-preference cookie: {name!r}")
    value = raw.get("value")
    if (
        not isinstance(value, str)
        or not value
        or _contains_control_characters(value)
    ):
        raise ValueError(f"cookie {name!r} has empty value")

    domain = _normalize_domain(raw.get("domain"), name)
    path = raw.get("path")
    if path is None or path == "":
        path = "/"
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or _contains_control_characters(path)
    ):
        raise ValueError(f"cookie {name!r} has unsafe path")

    secure = raw.get("secure", True)
    if secure is not True:
        raise ValueError(f"cookie {name!r} must be secure")

    http_only = raw.get("httpOnly", True)
    if type(http_only) is not bool:
        raise ValueError(f"cookie {name!r} has invalid httpOnly")

    same_site = raw.get("sameSite")
    if same_site is None or same_site == "":
        same_site = "Lax"
    if not isinstance(same_site, str) or same_site not in _ALLOWED_SAME_SITE:
        raise ValueError(f"cookie {name!r} has invalid sameSite")

    cookie: dict[str, Any] = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "secure": secure,
        "httpOnly": http_only,
        "sameSite": same_site,
    }
    expires = raw.get("expires")
    if expires:
        if isinstance(expires, bool):
            raise ValueError(f"cookie {name!r} has invalid expires")
        try:
            normalized_expires = float(expires)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"cookie {name!r} has invalid expires") from exc
        if not math.isfinite(normalized_expires):
            raise ValueError(f"cookie {name!r} has invalid expires")
        cookie["expires"] = normalized_expires
    return cookie


def save_preference_cookies(
    cookies: list[dict[str, Any]],
    path: Path | None = None,
) -> Path:
    """Persist only the allowed preference cookies with mode 0600."""

    target = path or default_cookie_store_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    normalized = [_normalize_cookie(c) for c in cookies]
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for cookie in normalized:
        if cookie["name"] in seen:
            continue
        seen.add(cookie["name"])
        deduped.append(cookie)

    payload = {"version": COOKIE_STORE_VERSION, "cookies": deduped}

    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    tmp.replace(target)
    return target


def load_preference_cookies(path: Path | None = None) -> list[dict[str, Any]]:
    """Load persisted preference cookies. Returns [] when absent or invalid."""

    target = path or default_cookie_store_path()
    try:
        with open(target, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict) or payload.get("version") != COOKIE_STORE_VERSION:
        return []
    cookies = payload.get("cookies")
    if not isinstance(cookies, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in cookies:
        if not isinstance(raw, dict):
            continue
        try:
            normalized = _normalize_cookie(raw)
        except (TypeError, ValueError):
            continue
        out.append(normalized)
    return out


def currency_from_store(path: Path | None = None) -> str | None:
    """Return the stored currency code, if present."""

    for cookie in load_preference_cookies(path):
        if cookie["name"] == "currency":
            value = str(cookie["value"]).upper()
            return value or None
    return None

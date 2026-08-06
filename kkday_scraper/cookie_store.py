"""Persistent storage for KKday site-preference cookies.

Only non-credential preference cookies (currency, country_lang, lang_ui)
are stored here. Session, CSRF, auth and anti-bot cookies must never be
written through this module.
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any

# Only these preference cookie names are allowed to be persisted.
ALLOWED_COOKIE_NAMES = frozenset({"currency", "country_lang", "lang_ui"})

COOKIE_STORE_VERSION = 1


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
    name = str(raw["name"])
    if name not in ALLOWED_COOKIE_NAMES:
        raise ValueError(f"refusing to persist non-preference cookie: {name!r}")
    value = str(raw.get("value") or "")
    if not value:
        raise ValueError(f"cookie {name!r} has empty value")

    domain = str(raw.get("domain") or "www.kkday.com")
    if not domain.endswith("kkday.com"):
        raise ValueError(f"cookie {name!r} has non-kkday domain: {domain!r}")

    cookie: dict[str, Any] = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": str(raw.get("path") or "/"),
        "secure": bool(raw.get("secure", True)),
        "httpOnly": bool(raw.get("httpOnly", True)),
        "sameSite": str(raw.get("sameSite") or "Lax"),
    }
    expires = raw.get("expires")
    if expires:
        cookie["expires"] = float(expires)
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
        name = raw.get("name")
        if name not in ALLOWED_COOKIE_NAMES:
            continue
        if not str(raw.get("value") or ""):
            continue
        out.append(raw)
    return out


def currency_from_store(path: Path | None = None) -> str | None:
    """Return the stored currency code, if present."""

    for cookie in load_preference_cookies(path):
        if cookie["name"] == "currency":
            value = str(cookie["value"]).upper()
            return value or None
    return None

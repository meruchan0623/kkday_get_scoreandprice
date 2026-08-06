import json
from pathlib import Path

import pytest

from kkday_scraper.cookie_store import (
    COOKIE_STORE_VERSION,
    load_preference_cookies,
    save_preference_cookies,
)


def _cookie(**overrides):
    cookie = {
        "name": "currency",
        "value": "TWD",
        "domain": ".kkday.com",
        "path": "/",
        "secure": True,
        "httpOnly": False,
        "sameSite": "Lax",
    }
    cookie.update(overrides)
    return cookie


def _write_store(path: Path, cookies: list[dict]) -> None:
    path.write_text(
        json.dumps({"version": COOKIE_STORE_VERSION, "cookies": cookies}),
        encoding="utf-8",
    )


@pytest.mark.parametrize("domain", ["evilkkday.com", "notkkday.com"])
def test_save_rejects_domain_suffix_confusion(
    tmp_path: Path, domain: str
) -> None:
    with pytest.raises(ValueError, match="non-kkday domain"):
        save_preference_cookies(
            [_cookie(domain=domain)], tmp_path / "preferences.json"
        )


@pytest.mark.parametrize(
    "override",
    [
        {"path": "relative"},
        {"path": "/safe\nunsafe"},
        {"path": False},
        {"domain": []},
        {"secure": False},
        {"secure": "true"},
        {"httpOnly": "false"},
        {"sameSite": "Invalid"},
        {"sameSite": False},
    ],
)
def test_save_rejects_unsafe_cookie_attributes(
    tmp_path: Path, override: dict
) -> None:
    with pytest.raises(ValueError):
        save_preference_cookies(
            [_cookie(**override)], tmp_path / "preferences.json"
        )


@pytest.mark.parametrize(
    "override",
    [
        {"domain": "evilkkday.com"},
        {"domain": "notkkday.com"},
        {"path": "relative"},
        {"path": "/safe\x00unsafe"},
        {"path": False},
        {"domain": []},
        {"secure": False},
        {"secure": "true"},
        {"httpOnly": "false"},
        {"sameSite": "Invalid"},
        {"sameSite": False},
    ],
)
def test_load_revalidates_cookie_attributes(
    tmp_path: Path, override: dict
) -> None:
    store = tmp_path / "preferences.json"
    _write_store(store, [_cookie(**override)])

    assert load_preference_cookies(store) == []


def test_load_returns_only_normalized_cookie_keys(tmp_path: Path) -> None:
    store = tmp_path / "preferences.json"
    _write_store(
        store,
        [
            _cookie(
                extraCredential="must-not-survive",
                url="https://www.kkday.com/",
            )
        ],
    )

    assert load_preference_cookies(store) == [_cookie()]


@pytest.mark.parametrize(
    "domain", ["kkday.com", ".kkday.com", "www.kkday.com"]
)
def test_save_and_load_accept_exact_kkday_domain_boundary(
    tmp_path: Path, domain: str
) -> None:
    store = tmp_path / "preferences.json"

    save_preference_cookies([_cookie(domain=domain)], store)

    assert load_preference_cookies(store) == [_cookie(domain=domain)]

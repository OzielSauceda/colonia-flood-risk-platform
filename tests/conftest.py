"""Shared test doubles and fixtures.

The only thing ever mocked is the :class:`~colonia_flood.stac_client.SearchClient`
Protocol. Everything above that seam is pure and needs no patching.

An autouse fixture additionally severs socket access for every non-``live``
test, so "the offline suite needs no network" is enforced rather than assumed.
"""

from __future__ import annotations

import copy
import json
import socket
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from colonia_flood.events import EventsConfig, LoadedConfig, load_config
from colonia_flood.stac_client import CatalogError

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "stac"
REAL_CONFIG_PATH = REPO_ROOT / "config" / "events.toml"


def load_stac_fixture(name: str) -> list[dict[str, Any]]:
    """Load one committed STAC search response."""
    payload = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    return payload


class FakeSearchClient:
    """Replays committed fixtures and records every call.

    It has no URL surface at all: :attr:`requested_urls` exists so tests can
    assert that nothing — least of all an asset href — was ever fetched.
    """

    def __init__(
        self,
        responses: Mapping[date, Sequence[dict[str, Any]]] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._responses = {key: list(value) for key, value in (responses or {}).items()}
        self._error = error
        self.calls: list[dict[str, Any]] = []
        self.requested_urls: list[str] = []

    def search(
        self,
        *,
        collection: str,
        bbox: Sequence[float],
        start: datetime,
        end_exclusive: datetime,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "collection": collection,
                "bbox": list(bbox),
                "start": start,
                "end_exclusive": end_exclusive,
            }
        )
        if self._error is not None:
            raise self._error
        # Deep-copied so a caller mutating an item cannot corrupt the fixture and
        # silently change a later test in the same session.
        return copy.deepcopy(self._responses.get(start.date(), []))


@pytest.fixture(autouse=True)
def block_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make any outbound socket connection fail, except in ``live`` tests."""
    if request.node.get_closest_marker("live"):
        return

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(
            "an offline test attempted a network connection; the STAC client "
            "seam should have been substituted with FakeSearchClient"
        )

    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def loaded_config() -> LoadedConfig:
    """The committed project configuration — parsing it is itself a test."""
    return load_config(REAL_CONFIG_PATH)


@pytest.fixture
def config(loaded_config: LoadedConfig) -> EventsConfig:
    return loaded_config.config


@pytest.fixture
def all_window_responses() -> dict[date, list[dict[str, Any]]]:
    """Every captured response, keyed by the start date of the window it covers."""
    return {
        date(2020, 6, 24): load_stac_fixture("hanna_2020__pre_event"),
        date(2020, 7, 26): load_stac_fixture("hanna_2020__event"),
        date(2025, 2, 24): load_stac_fixture("march_2025__pre_event"),
        date(2025, 3, 26): load_stac_fixture("march_2025__event"),
    }


@pytest.fixture
def fake_client(
    all_window_responses: dict[date, list[dict[str, Any]]],
) -> FakeSearchClient:
    return FakeSearchClient(all_window_responses)


@pytest.fixture
def sample_item() -> dict[str, Any]:
    """One real captured event-window item, used as the base for defect variants."""
    return copy.deepcopy(load_stac_fixture("hanna_2020__event")[0])


def without_property(item: dict[str, Any], key: str) -> dict[str, Any]:
    """Copy of ``item`` with one STAC property removed."""
    variant = copy.deepcopy(item)
    variant["properties"].pop(key, None)
    return variant


def with_property(item: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    variant = copy.deepcopy(item)
    variant["properties"][key] = value
    return variant


def without_asset(item: dict[str, Any], key: str) -> dict[str, Any]:
    variant = copy.deepcopy(item)
    variant["assets"].pop(key, None)
    return variant


__all__ = [
    "REAL_CONFIG_PATH",
    "REPO_ROOT",
    "CatalogError",
    "FakeSearchClient",
    "load_stac_fixture",
    "with_property",
    "without_asset",
    "without_property",
]

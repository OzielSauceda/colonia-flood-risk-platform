"""Optional live catalog test — deselected by default, run with ``pytest -m live``.

This test exists to catch the one class of failure no fixture can ever detect:
the day the catalog renames a property or an asset key. It therefore asserts
*structural* facts only, never specific item IDs or counts, which change as the
Sentinel-1 archive is reprocessed.

It queries metadata only, writes nothing to ``data/``, and uses no credentials.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from colonia_flood.events import load_config
from colonia_flood.manifest import collect_event, query_event
from colonia_flood.stac_client import PystacSearchClient

pytestmark = pytest.mark.live

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "events.toml"
EVENT_ID = "hanna_2020"

REQUIRED_PROPERTIES = (
    "datetime",
    "platform",
    "sat:relative_orbit",
    "sat:orbit_state",
    "sar:polarizations",
)


@pytest.fixture(scope="module")
def live_items() -> list[dict[str, Any]]:
    loaded = load_config(CONFIG_PATH)
    config = loaded.config
    event = config.event(EVENT_ID)
    aoi = config.aoi_for(event)
    window = event.observation_window

    client = PystacSearchClient(config.catalog.url)
    items = client.search(
        collection=config.catalog.collection,
        bbox=list(aoi.bbox),
        start=window.start_instant,
        end_exclusive=window.end_instant_exclusive,
    )
    assert items, "the live catalog returned no items for the Hanna event window"
    return items


def test_search_is_anonymous_and_returns_items(
    live_items: list[dict[str, Any]],
) -> None:
    """Search must work without credentials, or requirement 9 needs a new answer."""
    assert len(live_items) >= 1
    for item in live_items:
        assert isinstance(item.get("id"), str) and item["id"]
        assert item.get("collection") == "sentinel-1-rtc"


def test_every_property_this_slice_depends_on_is_present(
    live_items: list[dict[str, Any]],
) -> None:
    for item in live_items:
        properties = item["properties"]
        for name in REQUIRED_PROPERTIES:
            assert name in properties, f"{item['id']} lacks {name}"

        assert isinstance(properties["datetime"], str)
        assert isinstance(properties["platform"], str)
        assert isinstance(properties["sat:relative_orbit"], int)
        assert properties["sat:orbit_state"] in ("ascending", "descending")
        assert isinstance(properties["sar:polarizations"], list)


def test_configured_asset_keys_still_exist(live_items: list[dict[str, Any]]) -> None:
    """The vv/vh key names live in config precisely so a rename is a config fix."""
    config = load_config(CONFIG_PATH).config
    for item in live_items:
        assets = item["assets"]
        for key in (config.catalog.vv_asset_key, config.catalog.vh_asset_key):
            assert key in assets, f"{item['id']} lacks asset {key!r}"
            assert isinstance(assets[key].get("href"), str)


def test_asset_hrefs_are_unsigned(live_items: list[dict[str, Any]]) -> None:
    """Search results must not carry SAS tokens, or manifests could leak one."""
    config = load_config(CONFIG_PATH).config
    for item in live_items:
        for key in (config.catalog.vv_asset_key, config.catalog.vh_asset_key):
            href = item["assets"][key]["href"]
            assert "?" not in href, (
                f"{item['id']} asset {key} href carries a query string"
            )


def test_geometry_and_bbox_are_present(live_items: list[dict[str, Any]]) -> None:
    for item in live_items:
        assert isinstance(item.get("geometry"), dict)
        assert isinstance(item.get("bbox"), list)
        assert len(item["bbox"]) == 4


def test_live_response_maps_cleanly_through_the_pipeline() -> None:
    """A structural check that the live response still produces usable acquisitions."""
    loaded = load_config(CONFIG_PATH)
    client = PystacSearchClient(loaded.config.catalog.url)
    raw = query_event(client, config=loaded.config, event_id=EVENT_ID)
    result = collect_event(raw, config=loaded.config, event_id=EVENT_ID)

    assert result.window_count("pre_event") >= 1
    assert result.window_count("event") >= 1
    for acquisition in result.acquisitions:
        assert acquisition.polarizations == ["VH", "VV"]
        assert acquisition.intersects_aoi_bbox is True

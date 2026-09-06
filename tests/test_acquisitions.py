"""Item mapping, field validation, and exclusion reasons (plan cases 7-13)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from colonia_flood.acquisitions import (
    Acquisition,
    ExcludedItem,
    ReasonCode,
    bbox_intersects,
    extract_datetime,
    extract_item_id,
    map_item,
    round_coordinate,
    strip_url_query,
)
from colonia_flood.events import EventsConfig
from colonia_flood.stac_client import CatalogError

from .conftest import with_property, without_asset, without_property

ACQUIRED_AT = datetime(2020, 7, 27, 12, 24, 26, 862631, tzinfo=UTC)


def do_map(
    item: dict[str, Any], config: EventsConfig, *, event_id: str = "hanna_2020"
) -> Acquisition | ExcludedItem:
    event = config.event(event_id)
    return map_item(
        item,
        event=event,
        aoi=config.aoi_for(event),
        catalog=config.catalog,
        acquired_at=ACQUIRED_AT,
        window="event",
    )


# --- happy path -------------------------------------------------------------


def test_real_item_maps_to_a_complete_acquisition(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    result = do_map(sample_item, config)
    assert isinstance(result, Acquisition)

    assert result.item_id == sample_item["id"]
    assert result.collection == "sentinel-1-rtc"
    assert result.datetime_utc == "2020-07-27T12:24:26.862631Z"
    assert result.platform == "SENTINEL-1A"
    assert result.relative_orbit == 143
    assert result.orbit_direction == "descending"
    assert result.polarizations == ["VH", "VV"]
    assert result.window == "event"
    assert result.event_id == "hanna_2020"
    # The feasibility report's confirmed Hanna acquisition is orbit 143 descending.
    assert result.matches_preferred_orbit is True
    assert result.intersects_aoi_bbox is True
    assert result.vv_asset_href.endswith("iw-vv.rtc.tiff")
    assert result.vh_asset_href.endswith("iw-vh.rtc.tiff")
    assert result.footprint["type"] == "Polygon"


def test_coordinates_are_rounded_to_six_places(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    result = do_map(sample_item, config)
    assert isinstance(result, Acquisition)

    for value in result.bbox:
        assert round(value, 6) == value
    for ring in result.footprint["coordinates"]:
        for x, y in ring:
            assert round(x, 6) == x
            assert round(y, 6) == y


# --- cases 7 and 8 ----------------------------------------------------------


def test_missing_vv_asset_is_excluded(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    result = do_map(without_asset(sample_item, "vv"), config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is ReasonCode.MISSING_VV_ASSET


def test_missing_vh_asset_is_excluded(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    result = do_map(without_asset(sample_item, "vh"), config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is ReasonCode.MISSING_VH_ASSET


# --- case 9 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("polarizations", "expected"),
    [
        (["VH"], ReasonCode.MISSING_VV_ASSET),
        (["VV"], ReasonCode.MISSING_VH_ASSET),
        (["HH", "HV"], ReasonCode.MISSING_VV_ASSET),
    ],
)
def test_declared_polarizations_must_agree_with_present_assets(
    sample_item: dict[str, Any],
    config: EventsConfig,
    polarizations: list[str],
    expected: ReasonCode,
) -> None:
    """Both vv and vh asset keys still exist here — the declaration is what fails."""
    variant = with_property(sample_item, "sar:polarizations", polarizations)
    assert "vv" in variant["assets"] and "vh" in variant["assets"]

    result = do_map(variant, config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is expected
    assert "sar:polarizations" in result.detail


def test_non_list_polarizations_is_excluded(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    result = do_map(with_property(sample_item, "sar:polarizations", "VV"), config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is ReasonCode.MISSING_VV_ASSET


# --- cases 10 and 11 --------------------------------------------------------


@pytest.mark.parametrize(
    ("property_name", "expected"),
    [
        ("platform", ReasonCode.MISSING_PLATFORM),
        ("sat:relative_orbit", ReasonCode.MISSING_RELATIVE_ORBIT),
        ("sat:orbit_state", ReasonCode.MISSING_ORBIT_DIRECTION),
    ],
)
def test_missing_required_property_is_excluded(
    sample_item: dict[str, Any],
    config: EventsConfig,
    property_name: str,
    expected: ReasonCode,
) -> None:
    result = do_map(without_property(sample_item, property_name), config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is expected
    assert result.item_id == sample_item["id"]


@pytest.mark.parametrize("value", ["143", 143.5, True, None])
def test_non_integer_relative_orbit_is_excluded(
    sample_item: dict[str, Any], config: EventsConfig, value: Any
) -> None:
    result = do_map(with_property(sample_item, "sat:relative_orbit", value), config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is ReasonCode.MISSING_RELATIVE_ORBIT


def test_unrecognised_orbit_state_is_excluded(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    result = do_map(with_property(sample_item, "sat:orbit_state", "sideways"), config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is ReasonCode.MISSING_ORBIT_DIRECTION


def test_missing_geometry_is_excluded(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    variant = dict(sample_item)
    variant.pop("geometry")
    result = do_map(variant, config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is ReasonCode.MISSING_FOOTPRINT


def test_missing_bbox_is_excluded(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    variant = dict(sample_item)
    variant["bbox"] = [1.0, 2.0]
    result = do_map(variant, config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is ReasonCode.MISSING_FOOTPRINT


# --- case 12 ----------------------------------------------------------------


def test_item_outside_the_aoi_is_excluded_even_though_the_catalog_returned_it(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    variant = dict(sample_item)
    variant["bbox"] = [-80.0, 20.0, -79.0, 21.0]
    result = do_map(variant, config)
    assert isinstance(result, ExcludedItem)
    assert result.reason_code is ReasonCode.OUTSIDE_AOI
    assert "Hidalgo County" in result.detail


# --- case 13 ----------------------------------------------------------------


def test_item_touching_the_aoi_edge_is_included(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    """Edge contact is intersection. This pins the boundary convention."""
    aoi_bbox = config.aoi["hidalgo_county"].bbox
    west = aoi_bbox[0]
    variant = dict(sample_item)
    # A box lying entirely west of the county, sharing only the western edge.
    variant["bbox"] = [west - 1.0, 26.2, west, 26.4]
    result = do_map(variant, config)
    assert isinstance(result, Acquisition)
    assert result.intersects_aoi_bbox is True


def test_bbox_intersection_is_inclusive_and_symmetric() -> None:
    a = [0.0, 0.0, 1.0, 1.0]
    assert bbox_intersects(a, [1.0, 1.0, 2.0, 2.0]) is True
    assert bbox_intersects([1.0, 1.0, 2.0, 2.0], a) is True
    assert bbox_intersects(a, [1.0001, 0.0, 2.0, 1.0]) is False


# --- preferred-orbit annotation --------------------------------------------


def test_preferred_orbit_is_annotated_not_filtered(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    """A non-preferred orbit is retained and flagged, never dropped."""
    variant = with_property(sample_item, "sat:relative_orbit", 41)
    result = do_map(variant, config)
    assert isinstance(result, Acquisition)
    assert result.relative_orbit == 41
    assert result.matches_preferred_orbit is False


def test_matching_orbit_but_wrong_direction_does_not_match(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    variant = with_property(sample_item, "sat:orbit_state", "ascending")
    result = do_map(variant, config)
    assert isinstance(result, Acquisition)
    assert result.matches_preferred_orbit is False


# --- id, datetime, and href handling ---------------------------------------


def test_item_without_an_id_is_a_malformed_response(
    sample_item: dict[str, Any],
) -> None:
    variant = dict(sample_item)
    variant.pop("id")
    with pytest.raises(CatalogError) as excinfo:
        extract_item_id(variant)
    assert "without a usable string 'id'" in str(excinfo.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2020-07-27T12:24:26.862631Z", ACQUIRED_AT),
        ("2020-07-27T07:24:26.862631-05:00", ACQUIRED_AT),
    ],
)
def test_datetime_is_parsed_and_normalised_to_utc(
    sample_item: dict[str, Any], value: str, expected: datetime
) -> None:
    assert extract_datetime(with_property(sample_item, "datetime", value)) == expected


@pytest.mark.parametrize("value", [None, "", "not-a-timestamp", 12345])
def test_unparseable_datetime_returns_none(
    sample_item: dict[str, Any], value: Any
) -> None:
    assert extract_datetime(with_property(sample_item, "datetime", value)) is None


def test_asset_query_strings_are_stripped(
    sample_item: dict[str, Any], config: EventsConfig
) -> None:
    """A SAS token must not be able to reach a manifest even if one appeared."""
    variant = dict(sample_item)
    variant["assets"] = dict(sample_item["assets"])
    variant["assets"]["vv"] = dict(sample_item["assets"]["vv"])
    variant["assets"]["vv"]["href"] = (
        sample_item["assets"]["vv"]["href"] + "?st=2020-01-01&se=2020-01-02&sig=SECRET"
    )
    result = do_map(variant, config)
    assert isinstance(result, Acquisition)
    assert "?" not in result.vv_asset_href
    assert "SECRET" not in result.vv_asset_href


def test_strip_url_query_removes_query_and_fragment() -> None:
    assert strip_url_query("https://h/p.tiff?sig=x#frag") == "https://h/p.tiff"


def test_round_coordinate_normalises_negative_zero() -> None:
    assert round_coordinate(-0.0000001) == 0.0
    assert str(round_coordinate(-0.0000001)) == "0.0"

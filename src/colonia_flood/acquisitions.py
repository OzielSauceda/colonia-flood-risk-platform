"""Pure mapping from raw STAC item dictionaries to validated acquisitions.

Every function here is a pure function of its arguments: dict in, model or
exclusion out. There is no I/O, no clock, and no network.

Two failure kinds are distinguished deliberately:

* A defect in one *item* excludes that item and records a reason code, so the
  manifest shows what the catalog offered and why it was not kept.
* A defect in the *response* — an item without an ``id``, which STAC requires —
  raises :class:`~colonia_flood.stac_client.CatalogError`, because a response
  that cannot be keyed cannot be reported item-by-item either.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .events import AreaOfInterest, CatalogConfig, EventConfig, WindowName
from .stac_client import CatalogError, to_rfc3339

COORDINATE_PRECISION = 6
"""Decimal places retained for every coordinate. ~0.1 m at this latitude."""

REQUIRED_POLARIZATIONS = ("VH", "VV")


class ReasonCode(StrEnum):
    """Why a catalog item was not retained. Values are stable manifest content."""

    MISSING_DATETIME = "missing_datetime"
    MISSING_PLATFORM = "missing_platform"
    MISSING_RELATIVE_ORBIT = "missing_relative_orbit"
    MISSING_ORBIT_DIRECTION = "missing_orbit_direction"
    MISSING_VV_ASSET = "missing_vv_asset"
    MISSING_VH_ASSET = "missing_vh_asset"
    MISSING_FOOTPRINT = "missing_footprint"
    OUTSIDE_AOI = "outside_aoi"
    OUTSIDE_ALL_WINDOWS = "outside_all_windows"
    DUPLICATE_ITEM_ID = "duplicate_item_id"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExcludedItem(_Frozen):
    """A catalog item that was returned but not retained."""

    item_id: str
    reason_code: ReasonCode
    detail: Annotated[str, Field(min_length=1)]
    """Human-readable and deterministic: no timestamps, no paths, no counts
    that depend on response ordering."""


class Acquisition(_Frozen):
    """One retained Sentinel-1 RTC acquisition."""

    # Copied from the STAC item, never computed.
    item_id: str
    collection: str
    datetime_utc: str
    platform: str
    relative_orbit: int
    orbit_direction: Literal["ascending", "descending"]
    polarizations: list[str]
    bbox: Annotated[list[float], Field(min_length=4, max_length=4)]
    footprint: dict[str, Any]
    vv_asset_href: str
    vh_asset_href: str

    # Derived by this package from configuration plus the item.
    event_id: str
    window: WindowName
    matches_preferred_orbit: bool
    intersects_aoi_bbox: bool


def round_coordinate(value: float) -> float:
    """Round to :data:`COORDINATE_PRECISION`, normalising ``-0.0`` to ``0.0``."""
    return round(float(value), COORDINATE_PRECISION) + 0.0


def round_geometry(geometry: Any) -> Any:
    """Recursively round every number inside a GeoJSON geometry."""
    if isinstance(geometry, dict):
        return {key: round_geometry(value) for key, value in geometry.items()}
    if isinstance(geometry, list | tuple):
        return [round_geometry(value) for value in geometry]
    if isinstance(geometry, bool):
        return geometry
    if isinstance(geometry, int | float):
        return round_coordinate(geometry)
    return geometry


def bbox_intersects(a: list[float], b: list[float]) -> bool:
    """Inclusive 2-D bbox intersection: touching edges count as intersecting."""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def strip_url_query(href: str) -> str:
    """Drop any query string or fragment from an asset href.

    Planetary Computer serves unsigned hrefs, but stripping unconditionally means
    a SAS token can never reach a committed manifest even if the catalog, or a
    future signing step, were to introduce one.
    """
    for separator in ("?", "#"):
        href = href.split(separator, 1)[0]
    return href


def extract_item_id(raw: dict[str, Any]) -> str:
    """Return the STAC item ``id``.

    Raises if absent: an item that cannot be keyed is a malformed response, not
    an excludable item.
    """
    item_id = raw.get("id")
    if not isinstance(item_id, str) or not item_id:
        raise CatalogError(
            "catalog returned an item without a usable string 'id'; "
            "the response cannot be reported item-by-item"
        )
    return item_id


def extract_datetime(raw: dict[str, Any]) -> datetime | None:
    """Parse ``properties.datetime`` into an aware UTC datetime, or ``None``."""
    properties = raw.get("properties")
    if not isinstance(properties, dict):
        return None
    value = properties.get("datetime")
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _asset_href(raw: dict[str, Any], key: str) -> str | None:
    assets = raw.get("assets")
    if not isinstance(assets, dict):
        return None
    asset = assets.get(key)
    if not isinstance(asset, dict):
        return None
    href = asset.get("href")
    if not isinstance(href, str) or not href:
        return None
    return strip_url_query(href)


def map_item(
    raw: dict[str, Any],
    *,
    event: EventConfig,
    aoi: AreaOfInterest,
    catalog: CatalogConfig,
    acquired_at: datetime,
    window: WindowName,
) -> Acquisition | ExcludedItem:
    """Map one raw STAC item to an :class:`Acquisition` or an :class:`ExcludedItem`.

    ``acquired_at`` and ``window`` are supplied by the caller because window
    assignment depends only on the acquisition timestamp, which the caller has
    already parsed in order to decide whether the item belongs to this event.
    """
    item_id = extract_item_id(raw)
    properties = raw.get("properties")
    properties = properties if isinstance(properties, dict) else {}

    def exclude(code: ReasonCode, detail: str) -> ExcludedItem:
        return ExcludedItem(item_id=item_id, reason_code=code, detail=detail)

    platform = properties.get("platform")
    if not isinstance(platform, str) or not platform:
        return exclude(ReasonCode.MISSING_PLATFORM, "item has no 'platform' property")

    relative_orbit = properties.get("sat:relative_orbit")
    if isinstance(relative_orbit, bool) or not isinstance(relative_orbit, int):
        return exclude(
            ReasonCode.MISSING_RELATIVE_ORBIT,
            "item has no integer 'sat:relative_orbit' property",
        )

    orbit_direction = properties.get("sat:orbit_state")
    if orbit_direction not in ("ascending", "descending"):
        return exclude(
            ReasonCode.MISSING_ORBIT_DIRECTION,
            "item 'sat:orbit_state' is not 'ascending' or 'descending'",
        )

    raw_polarizations = properties.get("sar:polarizations")
    if not isinstance(raw_polarizations, list) or not all(
        isinstance(value, str) for value in raw_polarizations
    ):
        return exclude(
            ReasonCode.MISSING_VV_ASSET,
            "item has no list-valued 'sar:polarizations' property",
        )
    polarizations = sorted({value.upper() for value in raw_polarizations})

    # Declared polarization and asset presence must agree. An asset key that
    # exists without the matching declared polarization is not usable evidence
    # that the polarization was acquired, and vice versa.
    vv_href = _asset_href(raw, catalog.vv_asset_key)
    if "VV" not in polarizations:
        return exclude(
            ReasonCode.MISSING_VV_ASSET,
            "'sar:polarizations' does not declare VV",
        )
    if vv_href is None:
        return exclude(
            ReasonCode.MISSING_VV_ASSET,
            f"item has no usable '{catalog.vv_asset_key}' asset href",
        )

    vh_href = _asset_href(raw, catalog.vh_asset_key)
    if "VH" not in polarizations:
        return exclude(
            ReasonCode.MISSING_VH_ASSET,
            "'sar:polarizations' does not declare VH",
        )
    if vh_href is None:
        return exclude(
            ReasonCode.MISSING_VH_ASSET,
            f"item has no usable '{catalog.vh_asset_key}' asset href",
        )

    geometry = raw.get("geometry")
    bbox = raw.get("bbox")
    if not isinstance(geometry, dict) or not geometry:
        return exclude(ReasonCode.MISSING_FOOTPRINT, "item has no 'geometry'")
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or any(isinstance(v, bool) or not isinstance(v, int | float) for v in bbox)
    ):
        return exclude(
            ReasonCode.MISSING_FOOTPRINT, "item has no numeric 4-element 'bbox'"
        )

    rounded_bbox = [round_coordinate(value) for value in bbox]
    # An independent re-check of the catalog's own spatial filtering: we do not
    # assume the server honoured the bbox we asked for.
    intersects = bbox_intersects(rounded_bbox, list(aoi.bbox))
    if not intersects:
        return exclude(
            ReasonCode.OUTSIDE_AOI,
            f"item bbox does not intersect the {aoi.name} extent",
        )

    matches_orbit = (
        event.preferred_relative_orbit is not None
        and event.preferred_orbit_direction is not None
        and relative_orbit == event.preferred_relative_orbit
        and orbit_direction == event.preferred_orbit_direction
    )

    collection = raw.get("collection")
    return Acquisition(
        item_id=item_id,
        collection=collection if isinstance(collection, str) else catalog.collection,
        datetime_utc=to_rfc3339(acquired_at),
        platform=platform,
        relative_orbit=relative_orbit,
        orbit_direction=orbit_direction,
        polarizations=polarizations,
        bbox=rounded_bbox,
        footprint=round_geometry(geometry),
        vv_asset_href=vv_href,
        vh_asset_href=vh_href,
        event_id=event.event_id,
        window=window,
        matches_preferred_orbit=matches_orbit,
        intersects_aoi_bbox=intersects,
    )

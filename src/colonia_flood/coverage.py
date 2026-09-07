"""County coverage from committed STAC footprints, never valid raster pixels.

Public geometry inputs are EPSG:4326 longitude/latitude. Both county and scene
vertices are projected to EPSG:32614 before any intersection or area operation.
Only ``load_county_boundary`` reads a file; nothing here accesses the network.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from pyproj import Transformer
from shapely import get_coordinates
from shapely.errors import GEOSException
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from shapely.validation import explain_validity

from .acquisitions import Acquisition
from .events import AreaOfInterest

Polygonal = Polygon | MultiPolygon


@dataclass(frozen=True)
class CoverageMeasure:
    """Intersection area in m² and its fraction of the entire county."""

    area_m2: float
    county_fraction: float


@dataclass(frozen=True)
class CoverageReport:
    """STAC-footprint metrics in deterministic candidate order; no quality gate."""

    county_area_m2: float
    per_observation: dict[str, CoverageMeasure]
    pairwise: dict[tuple[str, str], CoverageMeasure]
    three_scene_common: CoverageMeasure


def _validate_polygon(geometry: BaseGeometry) -> Polygonal:
    """Reject unusable polygons without repairing or simplifying their shape."""
    if not isinstance(geometry, Polygon | MultiPolygon) or geometry.is_empty:
        raise ValueError("expected a non-empty Polygon or MultiPolygon")
    if geometry.has_z or geometry.has_m:
        raise ValueError("expected two-dimensional coordinates")
    if not all(math.isfinite(v) for xy in get_coordinates(geometry) for v in xy):
        raise ValueError("polygon coordinates must be finite")
    if not geometry.is_valid:
        raise ValueError(f"invalid polygon: {explain_validity(geometry)}")
    return geometry


def geometry_from_geojson(document: object) -> Polygonal:
    """Convert a GeoJSON geometry mapping to a validated lon/lat polygon."""
    if not isinstance(document, Mapping):
        raise ValueError("GeoJSON geometry must be an object")
    try:
        geometry = _validate_polygon(shape(dict(document)))
    except (GEOSException, KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid GeoJSON polygon: {exc}") from exc
    west, south, east, north = geometry.bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("expected EPSG:4326 longitude/latitude coordinates")
    return geometry


def load_county_boundary(path: Path, aoi: AreaOfInterest) -> Polygonal:
    """Read one county FeatureCollection; verify configured FIPS and bbox.

    The bbox comparison uses the configuration's six-decimal precision only.
    Source vertices are not rounded. File and JSON errors propagate to callers.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise ValueError("county boundary must be a FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise ValueError("county boundary must contain exactly one feature")
    feature = features[0]
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise ValueError("county boundary must contain a GeoJSON Feature")
    properties = feature.get("properties")
    if not isinstance(properties, dict) or properties.get("GEOID") != aoi.fips:
        raise ValueError("county GEOID does not match configured FIPS")
    geometry = geometry_from_geojson(feature.get("geometry"))
    if [round(v, 6) for v in geometry.bounds] != list(aoi.bbox):
        raise ValueError("county bbox differs from config at six-decimal precision")
    return geometry


def project_to_utm14(geometry: Polygonal) -> Polygonal:
    """Project EPSG:4326 vertices to WGS 84 / UTM 14N metres, preserving XY order.

    This fixed same-datum transformation uses bundled PROJ definitions and no
    remote grids. Shapely joins transformed vertices with straight segments;
    there is no densification, snapping, simplification or geometry repair.
    """
    _validate_polygon(geometry)
    west, south, east, north = geometry.bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("projection input must be EPSG:4326 longitude/latitude")
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32614", always_xy=True)
    projected = transform(partial(transformer.transform, errcheck=True), geometry)
    return _validate_polygon(projected)


def select_preferred_group(
    acquisitions: Sequence[Acquisition],
) -> tuple[Acquisition, Acquisition, Acquisition]:
    """Select exactly two preferred pre-event records and one event record.

    Uses existing manifest policy flags, not hard-coded dates/orbit numbers.
    Ambiguous, incomplete, duplicate or mixed-event groups fail explicitly.
    No catalog query or raster-asset access occurs, including for VV/VH checks.

    This lives in coverage.py only because Stage B needs candidate selection.
    Selection belongs conceptually to orchestration/manifest responsibility;
    Stage E must move or reuse this logic in its raster-manifest/orchestration
    layer, never create a second independent selection implementation.
    """
    selected = sorted(
        (a for a in acquisitions if a.matches_preferred_orbit),
        key=lambda a: (a.datetime_utc, a.item_id),
    )
    pre = [a for a in selected if a.window == "pre_event"]
    event = [a for a in selected if a.window == "event"]
    if len(pre) != 2 or len(event) != 1:
        raise ValueError("expected two preferred pre-event observations and one event")
    if len({a.item_id for a in selected}) != 3:
        raise ValueError("preferred group contains duplicate item IDs")
    if len({(a.event_id, a.relative_orbit, a.orbit_direction) for a in selected}) != 1:
        raise ValueError(
            "preferred group must share event, relative orbit and direction"
        )
    if any(
        not {"VV", "VH"}.issubset(a.polarizations)
        or not a.vv_asset_href
        or not a.vh_asset_href
        for a in selected
    ):
        raise ValueError("preferred group must contain VV and VH metadata")
    return pre[0], pre[1], event[0]


def _intersection_coverage(
    county_m: Polygonal, footprints_m: Sequence[Polygonal]
) -> CoverageMeasure:
    """Measure already-validated EPSG:32614 polygons; internal projected-only seam."""
    overlap: BaseGeometry = county_m
    for footprint in footprints_m:
        overlap = overlap.intersection(footprint)
    area_m2 = float(overlap.area)
    fraction = area_m2 / county_m.area
    # Eight binary64 steps at unity allow only machine-scale overlay roundoff
    # on this unit interval, not a geometry-error budget. Keep area unchanged.
    tolerance = 8 * math.ulp(1.0)
    if not math.isfinite(fraction) or not -tolerance <= fraction <= 1.0 + tolerance:
        raise ValueError(f"coverage fraction outside [0, 1]: {fraction!r}")
    if fraction < 0.0:
        fraction = 0.0
    elif fraction > 1.0:
        fraction = 1.0
    return CoverageMeasure(area_m2, fraction)


def coverage_metrics(
    county_4326: Polygonal, acquisitions: Sequence[Acquisition]
) -> CoverageReport:
    """Return preferred per-scene, pre/event-pair and three-scene coverage.

    Selection and all validation precede measurement. Invalid/missing geometry
    raises instead of becoming zero coverage. A valid disjoint footprint is zero
    geometric coverage, which is not a negative flood label.
    """
    group = select_preferred_group(acquisitions)
    county_m = project_to_utm14(county_4326)
    footprints = [project_to_utm14(geometry_from_geojson(a.footprint)) for a in group]
    if not math.isfinite(county_m.area) or county_m.area <= 0:
        raise ValueError("projected county area must be finite and positive")
    per_observation = {
        a.item_id: _intersection_coverage(county_m, [g])
        for a, g in zip(group, footprints, strict=True)
    }
    pairwise = {
        (group[i].item_id, group[2].item_id): _intersection_coverage(
            county_m, [footprints[i], footprints[2]]
        )
        for i in range(2)
    }
    return CoverageReport(
        county_area_m2=float(county_m.area),
        per_observation=per_observation,
        pairwise=pairwise,
        three_scene_common=_intersection_coverage(county_m, footprints),
    )

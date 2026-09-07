"""Offline geometry, CRS, selection and committed-footprint regressions."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, box, mapping
from shapely.ops import transform

from colonia_flood.acquisitions import Acquisition
from colonia_flood.coverage import (
    Polygonal,
    _intersection_coverage,
    coverage_metrics,
    geometry_from_geojson,
    load_county_boundary,
    project_to_utm14,
    select_preferred_group,
)
from colonia_flood.events import EventsConfig

from .conftest import REPO_ROOT

COUNTY_PATH = REPO_ROOT / "data/boundaries/hidalgo_county.geojson"
# 0.02 percentage points ~= 0.82 km², or 20 cells of the old 200 m lattice
# among 102,458 county sample points. This is a narrow migration regression
# budget for boundary aliasing + two-decimal printed percentages, not a formal
# bound on lattice error or a scene-acceptance threshold. Do not widen on failure.
SAMPLED_FRACTION_ABS_TOL = 0.0002


def records(event_id: str) -> list[Acquisition]:
    document = json.loads(
        (REPO_ROOT / "data/manifests" / event_id / "acquisitions.json").read_text()
    )
    return [Acquisition.model_validate(a) for a in document["acquisitions"]]


def to_lonlat(geometry_m: Polygonal) -> Polygonal:
    """Construct geographic test input from hand-computable metre rectangles."""
    inverse = Transformer.from_crs(32614, 4326, always_xy=True)
    return geometry_from_geojson(mapping(transform(inverse.transform, geometry_m)))


def test_load_committed_county_preserves_coordinates(config: EventsConfig) -> None:
    county = load_county_boundary(COUNTY_PATH, config.aoi["hidalgo_county"])
    source = json.loads(COUNTY_PATH.read_text())["features"][0]["geometry"]
    assert isinstance(county, Polygon)
    assert list(county.exterior.coords) == [tuple(p) for p in source["coordinates"][0]]
    assert county.is_valid and len(county.exterior.coords) == 4132
    assert [round(v, 6) for v in county.bounds] == config.aoi["hidalgo_county"].bbox


@pytest.mark.parametrize("defect", ["type", "count", "feature", "geoid", "bbox"])
def test_county_rejects_wrong_input(
    config: EventsConfig, tmp_path: Path, defect: str
) -> None:
    document = json.loads(COUNTY_PATH.read_text())
    aoi = config.aoi["hidalgo_county"]
    if defect == "type":
        document["type"] = "GeometryCollection"
    elif defect == "count":
        document["features"].append(document["features"][0])
    elif defect == "feature":
        document["features"][0]["type"] = "Polygon"
    elif defect == "geoid":
        document["features"][0]["properties"]["GEOID"] = "48201"
    else:
        aoi = aoi.model_copy(update={"bbox": [-99.0, 26.0, -97.0, 27.0]})
    path = tmp_path / "county.geojson"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        load_county_boundary(path, aoi)


@pytest.mark.parametrize(
    "document",
    [
        None,
        {"type": "Point", "coordinates": [-98, 26]},
        {"type": "Polygon", "coordinates": []},
        {"type": "Polygon"},
        mapping(Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])),
        mapping(box(500_000, 2_900_000, 600_000, 3_000_000)),
        mapping(Polygon([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 0, 1)])),
        {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, float("inf")], [0, 0]]],
        },
    ],
)
def test_geometry_rejects_unusable_input(document: Any) -> None:
    with pytest.raises(ValueError):
        geometry_from_geojson(document)


def test_multipart_and_holes_preserved() -> None:
    holed = Polygon(box(0, 0, 4, 4).exterior.coords, [box(1, 1, 3, 3).exterior.coords])
    geometry = MultiPolygon([holed, box(5, 0, 6, 1)])
    loaded = geometry_from_geojson(mapping(geometry))
    assert loaded.equals(geometry)
    # This internal seam's synthetic coordinates are metres, not geographic area.
    result = _intersection_coverage(loaded, [box(0, 0, 4, 4)])
    assert result.area_m2 == 12
    assert result.county_fraction == pytest.approx(12 / 13)


def test_projection_uses_longitude_first_and_metres() -> None:
    # UTM zone 14's central meridian meets the equator at (500000 m, 0 m).
    polygon = Polygon([(-99, 0), (-98.99, 0), (-98.99, 0.01), (-99, 0.01)])
    projected = project_to_utm14(polygon)
    assert isinstance(projected, Polygon)
    assert projected.exterior.coords[0] == pytest.approx((500_000, 0), abs=1e-6)
    assert 1_200_000 < projected.area < 1_250_000
    # Degree-area (~0.0001), axis reversal, wrong units/zone all fail this test.
    with pytest.raises(ValueError, match="EPSG:4326"):
        project_to_utm14(projected)


@pytest.mark.parametrize(
    ("footprint", "expected"),
    [
        (box(20, 0, 30, 10), 0.0),
        (box(10, 0, 20, 10), 0.0),  # touching boundary has no area
        (box(-1, -1, 11, 11), 1.0),
        (box(5, 0, 15, 10), 0.5),
    ],
)
def test_hand_computed_projected_intersection(
    footprint: Polygon, expected: float
) -> None:
    result = _intersection_coverage(box(0, 0, 10, 10), [footprint])
    assert result.area_m2 == expected * 100
    assert result.county_fraction == expected
    assert 0 <= result.county_fraction <= 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.5, 0.5),
        (1.0000000000000002, 1.0),
        (-1e-16, 0.0),
        (1.0 + 8 * math.ulp(1.0), 1.0),
        (-8 * math.ulp(1.0), 0.0),
    ],
)
def test_fraction_normalizes_only_roundoff(raw: float, expected: float) -> None:
    county = box(0, 0, 1, 1)
    # Inject overlay areas: negative areas cannot arise from valid polygons.
    with patch.object(Polygon, "intersection", return_value=Mock(area=raw)):
        result = _intersection_coverage(county, [county])
    assert result.county_fraction == expected
    assert result.area_m2 == raw


@pytest.mark.parametrize(
    "raw",
    [
        1.37,
        -0.01,
        1.0 + 9 * math.ulp(1.0),
        -9 * math.ulp(1.0),
        float("nan"),
        float("inf"),
        -float("inf"),
    ],
)
def test_fraction_rejects_out_of_bounds(raw: float) -> None:
    county = box(0, 0, 1, 1)
    with (
        patch.object(Polygon, "intersection", return_value=Mock(area=raw)),
        pytest.raises(ValueError, match=r"coverage fraction outside \[0, 1\]"),
    ):
        _intersection_coverage(county, [county])


def test_report_intersects_all_three_after_projection() -> None:
    county = to_lonlat(box(600_000, 2_900_000, 600_100, 2_900_100))
    shapes = [
        box(600_000, 2_900_000, 600_060, 2_900_100),
        box(600_000, 2_900_000, 600_100, 2_900_070),
        box(600_020, 2_900_020, 600_100, 2_900_100),
    ]
    group = select_preferred_group(records("hanna_2020"))
    candidates = [
        a.model_copy(update={"footprint": mapping(to_lonlat(g))})
        for a, g in zip(group, shapes, strict=True)
    ]
    report = coverage_metrics(county, candidates)
    assert report.county_area_m2 == pytest.approx(10_000, abs=1e-5)
    assert [
        m.county_fraction for m in report.per_observation.values()
    ] == pytest.approx([0.6, 0.7, 0.64], abs=1e-9)
    assert list(report.pairwise) == [
        (group[0].item_id, group[2].item_id),
        (group[1].item_id, group[2].item_id),
    ]
    assert [m.county_fraction for m in report.pairwise.values()] == pytest.approx(
        [0.32, 0.40], abs=1e-9
    )
    assert report.three_scene_common.area_m2 == pytest.approx(2_000, abs=1e-5)
    assert report.three_scene_common.county_fraction == pytest.approx(0.2, abs=1e-9)
    assert coverage_metrics(county, list(reversed(candidates))) == report


@pytest.mark.parametrize(
    "defect", ["missing", "extra", "duplicate", "event", "orbit", "direction", "vv"]
)
def test_selection_rejects_ambiguous_or_inconsistent_group(defect: str) -> None:
    candidates = list(select_preferred_group(records("hanna_2020")))
    if defect == "missing":
        candidates.pop()
    elif defect == "extra":
        candidates.append(candidates[0])
    else:
        updates: dict[str, Any] = {
            "duplicate": {"item_id": candidates[1].item_id},
            "event": {"event_id": "different_event"},
            "orbit": {"relative_orbit": 41},
            "direction": {"orbit_direction": "ascending"},
            "vv": {"vv_asset_href": ""},
        }
        candidates[0] = candidates[0].model_copy(update=updates[defect])
    with pytest.raises(ValueError):
        select_preferred_group(candidates)


def test_bad_footprint_is_not_zero_coverage(config: EventsConfig) -> None:
    candidates = list(select_preferred_group(records("hanna_2020")))
    candidates[0] = candidates[0].model_copy(update={"footprint": None})
    county = load_county_boundary(COUNTY_PATH, config.aoi["hidalgo_county"])
    with pytest.raises(ValueError, match="GeoJSON"):
        coverage_metrics(county, candidates)


@pytest.mark.parametrize(
    ("event_id", "sampled", "dates"),
    [
        ("hanna_2020", 0.1811, ["2020-07-03", "2020-07-15", "2020-07-27"]),
        ("march_2025", 0.1816, ["2025-03-03", "2025-03-15", "2025-03-27"]),
    ],
)
def test_committed_common_coverage_regression(
    config: EventsConfig, event_id: str, sampled: float, dates: list[str]
) -> None:
    county = load_county_boundary(COUNTY_PATH, config.aoi["hidalgo_county"])
    acquisitions = records(event_id)
    group = select_preferred_group(acquisitions)
    assert [a.datetime_utc[:10] for a in group] == dates
    assert all(
        a.relative_orbit == 143 and a.orbit_direction == "descending" for a in group
    )
    report = coverage_metrics(county, acquisitions)
    # Independent source attributes, allowing for projected vs Census area method.
    assert report.county_area_m2 == pytest.approx(4_099_514_134, rel=0.001)
    assert report.three_scene_common.county_fraction == pytest.approx(
        sampled, abs=SAMPLED_FRACTION_ABS_TOL, rel=0
    )
    measures = [
        *report.per_observation.values(),
        *report.pairwise.values(),
        report.three_scene_common,
    ]
    assert all(0 <= m.county_fraction <= 1 for m in measures)
    for (pre_id, event_id_key), measure in report.pairwise.items():
        assert (
            measure.area_m2
            <= min(
                report.per_observation[pre_id].area_m2,
                report.per_observation[event_id_key].area_m2,
            )
            + 1e-5
        )
        assert report.three_scene_common.area_m2 <= measure.area_m2 + 1e-5
    assert coverage_metrics(county, list(reversed(acquisitions))) == report

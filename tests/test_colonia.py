"""Offline, hand-computable geometry checks for the F2 upper bound."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, Polygon, box, mapping

from colonia_flood.colonia import (
    classify_cell,
    colonia_cells,
    county_grid,
    viability_report,
)
from colonia_flood.colonia_cli import calculate_local, load_colonias, report_json
from colonia_flood.coverage import coverage_metrics, select_preferred_group

from .conftest import REPO_ROOT
from .test_coverage import records, to_lonlat


def test_real_data_regression_reviewed_f2_upper_bounds() -> None:
    """Pin reviewed results for committed inputs, not universal scientific values."""
    report = calculate_local(REPO_ROOT)
    assert report.is_upper_bound
    assert report.total_unique_colonia_intersecting_cells == 1649
    expected = {
        "hanna_2020": (401, 17, 1231, 418),
        "march_2025": (403, 16, 1230, 419),
    }
    assert set(report.events) == set(expected)
    for event_id, counts in expected.items():
        event = report.events[event_id]
        assert (
            event.fully_inside_upper_bound,
            event.partial_upper_bound,
            event.outside_count,
            event.candidate_upper_bound,
        ) == counts
        assert event.candidate_upper_bound == (
            event.fully_inside_upper_bound + event.partial_upper_bound
        )
        assert event.candidate_upper_bound + event.outside_count == (
            report.total_unique_colonia_intersecting_cells
        )
        assert event.gate_threshold == 20
        assert not event.geometric_upper_bound_below_threshold


def test_fixed_lattice_and_stable_ids() -> None:
    cells = list(county_grid(box(510, 1010, 1490, 1490)))
    assert [(c.column, c.row) for c in cells] == [(1, 2), (2, 2)]
    assert [c.cell_id for c in cells] == ["utm14_500:1:2", "utm14_500:2:2"]
    assert list(cells[0].effective_geometry.bounds) == [510, 1010, 1000, 1490]
    assert list(cells[1].effective_geometry.bounds) == [1000, 1010, 1490, 1490]
    smaller = list(county_grid(box(1100, 1100, 1400, 1400)))
    assert smaller[0].cell_id == cells[1].cell_id
    negative = list(county_grid(box(-490, -490, -10, -10)))
    assert negative[0].cell_id == "utm14_500:-1:-1"


def test_grid_skips_empty_county_squares_and_ignores_component_order() -> None:
    parts = [box(0, 0, 500, 500), box(1000, 0, 1500, 500)]
    forward = list(county_grid(MultiPolygon(parts)))
    reverse = list(county_grid(MultiPolygon(parts[::-1])))
    assert [c.cell_id for c in forward] == ["utm14_500:0:0", "utm14_500:2:0"]
    assert [c.cell_id for c in reverse] == [c.cell_id for c in forward]
    assert all(
        a.effective_geometry.equals(b.effective_geometry)
        for a, b in zip(forward, reverse, strict=True)
    )


@pytest.mark.parametrize(
    ("colonia", "expected"),
    [
        (box(10, 10, 20, 20), 1),
        (box(500, 0, 600, 500), 0),  # edge only
        (box(500, 500, 600, 600), 0),  # point only
        (box(501, 0, 600, 500), 0),
    ],
)
def test_colonia_requires_positive_area(colonia: Polygon, expected: int) -> None:
    assert (
        len(colonia_cells(list(county_grid(box(0, 0, 500, 500))), [colonia]))
        == expected
    )


def test_multiple_colonias_count_once_and_order_does_not_matter() -> None:
    cells = list(county_grid(box(0, 0, 1000, 500)))
    colonias = [box(10, 10, 100, 100), box(50, 50, 200, 200)]
    forward = colonia_cells(cells, colonias)
    reverse = colonia_cells(cells, colonias[::-1])
    assert [c.cell_id for c in forward] == ["utm14_500:0:0"]
    assert [c.cell_id for c in reverse] == [c.cell_id for c in forward]
    assert colonia_cells(cells, []) == []


def test_county_effective_geometry_controls_both_classifications() -> None:
    cells = list(county_grid(box(100, 100, 400, 400)))
    assert len(cells) == 1
    assert colonia_cells(cells, [box(0, 0, 90, 500)]) == []
    assert colonia_cells(cells, [box(0, 0, 100, 500)]) == []
    assert len(colonia_cells(cells, [box(0, 0, 200, 500)])) == 1
    effective = cells[0].effective_geometry
    assert classify_cell(effective, box(100, 100, 400, 400)) == "fully_inside"
    assert classify_cell(effective, box(0, 0, 100, 500)) == "outside"
    assert classify_cell(effective, box(0, 0, 90, 500)) == "outside"


@pytest.mark.parametrize(
    ("footprint", "expected"),
    [
        (box(-1, -1, 501, 501), "fully_inside"),
        (box(0, 0, 500, 500), "fully_inside"),
        (box(0, 0, 250, 500), "partial"),
        (box(0, 0, 500 - 1e-8, 500), "partial"),
        (box(500, 0, 1000, 500), "outside"),
        (box(500, 500, 1000, 1000), "outside"),
        (box(501, 0, 1000, 500), "outside"),
        (Polygon(), "outside"),
    ],
)
def test_footprint_classification(footprint: Polygon, expected: str) -> None:
    assert classify_cell(box(0, 0, 500, 500), footprint) == expected


def test_full_containment_tolerance_only_accepts_machine_scale_slivers() -> None:
    cell = box(600000, 2900000, 600500, 2900500)
    tiny = box(599999, 2899999, 600501, 2900500 - math.ulp(2900500))
    material = box(599999, 2899999, 600501, 2900500 - 0.001)
    assert classify_cell(cell, tiny) == "fully_inside"
    assert classify_cell(cell, material) == "partial"
    # No tolerance makes a boundary-only or disjoint footprint a candidate.
    assert classify_cell(cell, box(600500, 2900000, 601000, 2900500)) == "outside"


@pytest.mark.parametrize("cell_count", [19, 20, 21])
def test_threshold_is_fixed_and_inclusive(cell_count: int) -> None:
    county = to_lonlat(box(600010, 2900010, 600000 + cell_count * 500 - 10, 2900490))
    group = [
        a.model_copy(
            update={
                "footprint": mapping(to_lonlat(box(599000, 2899000, 620000, 2901000)))
            }
        )
        for a in select_preferred_group(records("hanna_2020"))
    ]
    report = viability_report(
        county,
        [county],
        {"hanna_2020": group},
        colonia_source_sha256="a" * 64,
        county_boundary_sha256="b" * 64,
    )
    event = report.events["hanna_2020"]
    assert event.candidate_upper_bound == cell_count
    assert event.gate_threshold == 20
    assert event.geometric_upper_bound_below_threshold == (cell_count < 20)


def test_report_projection_selection_upper_bound_and_determinism() -> None:
    county = to_lonlat(box(600010, 2900010, 601490, 2900490))
    colonias = [
        to_lonlat(box(x, 2900100, x + 50, 2900200)) for x in [600100, 600600, 601100]
    ]
    group = select_preferred_group(records("hanna_2020"))
    acquisitions = [
        a.model_copy(
            update={
                "footprint": mapping(to_lonlat(box(599900, 2899900, east, 2900600)))
            }
        )
        for a, east in zip(group, [601400, 601000, 600750], strict=True)
    ]
    kwargs = {"colonia_source_sha256": "a" * 64, "county_boundary_sha256": "b" * 64}
    report = viability_report(county, colonias, {"hanna_2020": acquisitions}, **kwargs)
    reverse = viability_report(
        county, colonias[::-1], {"hanna_2020": acquisitions[::-1]}, **kwargs
    )
    assert report_json(report) == report_json(reverse)
    assert report.total_county_grid_cells == 3
    assert report.total_unique_colonia_intersecting_cells == 3
    event = report.events["hanna_2020"]
    assert event.selected_item_ids == [a.item_id for a in group]
    assert event.fully_inside_upper_bound == 1
    assert event.partial_upper_bound == 1
    assert event.outside_count == 1
    assert event.candidate_upper_bound == 2
    assert event.candidate_upper_bound == (
        event.fully_inside_upper_bound + event.partial_upper_bound
    )
    assert event.candidate_upper_bound + event.outside_count == 3
    assert event.gate_threshold == 20
    assert event.geometric_upper_bound_below_threshold
    assert report.is_upper_bound
    assert "does NOT establish valid raster observations" in report.interpretation
    assert "Stage H can only reduce" in report.interpretation
    assert report.grid_crs == "EPSG:32614" and report.grid_size_metres == 500
    document = json.loads(report_json(report))
    keys = set(document) | set(document["events"]["hanna_2020"])
    assert not any(
        term in key
        for key in keys
        for term in ["valid_cells", "valid_observations", "flood", "dry", "inundated"]
    )
    # Independent Stage B area confirms the same three selected footprints.
    coverage = coverage_metrics(county, acquisitions)
    assert list(coverage.per_observation) == event.selected_item_ids
    assert coverage.three_scene_common.area_m2 == pytest.approx(740 * 480, abs=1e-4)
    with pytest.raises(ValueError, match="requested event"):
        viability_report(county, colonias, {"wrong_event": acquisitions}, **kwargs)


@pytest.mark.parametrize("defect", ["collection", "empty", "feature", "geometry"])
def test_loader_rejects_bad_source(tmp_path: Path, defect: str) -> None:
    feature: dict[str, object] = {
        "type": "Feature",
        "geometry": mapping(box(-99, 26, -98, 27)),
    }
    document: dict[str, object] = {"type": "FeatureCollection", "features": [feature]}
    if defect == "collection":
        document["type"] = "Polygon"
    elif defect == "empty":
        document["features"] = []
    elif defect == "feature":
        feature["type"] = "wrong"
    else:
        feature["geometry"] = None
    path = tmp_path / "colonias.geojson"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError):
        load_colonias(path)


def test_loader_preserves_all_geometries_and_source_bytes(tmp_path: Path) -> None:
    geometries = [box(-99, 26, -98, 27), box(-98.5, 26, -98, 26.5)]
    path = tmp_path / "colonias.geojson"
    raw = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": mapping(g)} for g in geometries
            ],
        }
    ).encode()
    path.write_bytes(raw)
    assert all(
        a.equals(b) for a, b in zip(load_colonias(path), geometries, strict=True)
    )
    assert path.read_bytes() == raw

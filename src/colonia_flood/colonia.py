"""Fixed 500 m vector precheck: geometric upper bounds, never observations."""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.prepared import prep

from .acquisitions import Acquisition
from .coverage import (
    Polygonal,
    _validate_polygon,
    geometry_from_geojson,
    project_to_utm14,
    select_preferred_group,
)

CELL_SIZE_M = 500
GATE_THRESHOLD = 20
UPPER_BOUND_NOTE = (
    "STAC footprint intersection does NOT establish valid raster observations. "
    "Stage H can only reduce this count when inspecting valid-pixel masks. "
    "An upper bound below 20 rules out this necessary Path-A criterion; "
    "20 or more only means Path A is not ruled out, not that any gate passed. "
    "Counts are conditional on the selected OAG colonia source snapshot and vintage."
)


@dataclass(frozen=True)
class CountyCell:
    """County-clipped cell; indices identify the fixed UTM square, not its order."""

    column: int
    row: int
    effective_geometry: BaseGeometry

    @property
    def cell_id(self) -> str:
        return f"utm14_500:{self.column}:{self.row}"


@dataclass(frozen=True)
class EventUpperBound:
    selected_item_ids: list[str]
    fully_inside_upper_bound: int
    partial_upper_bound: int
    outside_count: int
    candidate_upper_bound: int
    gate_threshold: int
    geometric_upper_bound_below_threshold: bool


@dataclass(frozen=True)
class ViabilityReport:
    schema_version: str
    colonia_source_sha256: str
    county_boundary_sha256: str
    grid_crs: str
    grid_size_metres: int
    grid_anchoring_rule: str
    cell_id_rule: str
    total_county_grid_cells: int
    total_unique_colonia_intersecting_cells: int
    events: dict[str, EventUpperBound]
    is_upper_bound: bool
    interpretation: str


def county_grid(county_m: Polygonal) -> Iterator[CountyCell]:
    """Enumerate positive-area effective cells; input must be EPSG:32614.

    Edges are multiples of 500 m relative to UTM (0, 0). Bounding-box squares
    with zero county area are excluded. No metric tolerance or snapping.
    """
    _validate_polygon(county_m)
    west, south, east, north = county_m.bounds
    for column in range(math.floor(west / CELL_SIZE_M), math.ceil(east / CELL_SIZE_M)):
        for row in range(
            math.floor(south / CELL_SIZE_M), math.ceil(north / CELL_SIZE_M)
        ):
            x, y = column * CELL_SIZE_M, row * CELL_SIZE_M
            effective = box(x, y, x + CELL_SIZE_M, y + CELL_SIZE_M).intersection(
                county_m
            )
            if effective.area > 0:
                yield CountyCell(column, row, effective)


def colonia_cells(
    cells: Sequence[CountyCell], colonias_m: Sequence[Polygonal]
) -> list[CountyCell]:
    """Keep cells with positive-area colonia overlap, counting each cell once.

    Projected-only seam. Sort before an in-memory union for input-order
    independence; prepare it to cheaply reject disjoint cells before overlay.
    Source geometries are validated and never repaired or changed in place.
    """
    for geometry in colonias_m:
        _validate_polygon(geometry)
    merged = unary_union(sorted(colonias_m, key=lambda g: g.wkb))
    prepared = prep(merged)
    return [
        cell
        for cell in cells
        if prepared.intersects(cell.effective_geometry)
        and cell.effective_geometry.intersection(merged).area > 0
    ]


def classify_cell(
    effective_cell: BaseGeometry, common_footprint: BaseGeometry
) -> Literal["fully_inside", "partial", "outside"]:
    """Classify positive-area EPSG:32614 effective cells.

    Zero-area touches are outside. Full containment allows only an area sliver
    bounded by eight coordinate ULPs times cell perimeter, accommodating overlay
    roundoff along shared edges. This never changes the candidate upper bound.
    """
    if effective_cell.intersection(common_footprint).area == 0:
        return "outside"
    coordinate_scale = max(abs(v) for v in effective_cell.bounds)
    area_tolerance = 8 * math.ulp(coordinate_scale) * effective_cell.length
    if effective_cell.difference(common_footprint).area <= area_tolerance:
        return "fully_inside"
    return "partial"


def viability_report(
    county_4326: Polygonal,
    colonias_4326: Sequence[Polygonal],
    acquisitions_by_event: Mapping[str, Sequence[Acquisition]],
    *,
    colonia_source_sha256: str,
    county_boundary_sha256: str,
) -> ViabilityReport:
    """Project local inputs, reuse Stage B selection, and report upper bounds."""
    county_m = project_to_utm14(county_4326)
    cells = list(county_grid(county_m))
    selected_cells = colonia_cells(cells, [project_to_utm14(g) for g in colonias_4326])
    events: dict[str, EventUpperBound] = {}
    for event_id, acquisitions in sorted(acquisitions_by_event.items()):
        group = select_preferred_group(acquisitions)
        if any(a.event_id != event_id for a in group):
            raise ValueError("selected acquisitions do not match the requested event")
        # Same county-first overlay order and projection as Stage B. Its area
        # helper returns a measure, so construct the needed geometry here.
        common: BaseGeometry = county_m
        for acquisition in group:
            common = common.intersection(
                project_to_utm14(geometry_from_geojson(acquisition.footprint))
            )
        counts = {"fully_inside": 0, "partial": 0, "outside": 0}
        for cell in selected_cells:
            counts[classify_cell(cell.effective_geometry, common)] += 1
        candidate = counts["fully_inside"] + counts["partial"]
        events[event_id] = EventUpperBound(
            selected_item_ids=[a.item_id for a in group],
            fully_inside_upper_bound=counts["fully_inside"],
            partial_upper_bound=counts["partial"],
            outside_count=counts["outside"],
            candidate_upper_bound=candidate,
            gate_threshold=GATE_THRESHOLD,
            geometric_upper_bound_below_threshold=candidate < GATE_THRESHOLD,
        )
    return ViabilityReport(
        schema_version="colonia-viability-f2-v1",
        colonia_source_sha256=colonia_source_sha256,
        county_boundary_sha256=county_boundary_sha256,
        grid_crs="EPSG:32614",
        grid_size_metres=CELL_SIZE_M,
        grid_anchoring_rule="Edges at integer multiples of 500 m from UTM (0, 0).",
        cell_id_rule="utm14_500:<column>:<row>; lower-left=(column*500,row*500) m",
        total_county_grid_cells=len(cells),
        total_unique_colonia_intersecting_cells=len(selected_cells),
        events=events,
        is_upper_bound=True,
        interpretation=UPPER_BOUND_NOTE,
    )

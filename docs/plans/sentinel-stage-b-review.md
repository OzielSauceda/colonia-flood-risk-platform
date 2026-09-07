# Stage B review — projected STAC-footprint coverage

Stage B computes county overlap from the committed county polygon and committed
Sentinel footprints. Both are projected into metres before intersection and
measurement. The common coverage is **18.10836669589106% for Hanna** and
**18.16829740082714% for March**. These agree with the investigation's sampled
estimates within the documented regression budget. They measure geographic
footprint overlap, not valid raster pixels or flood observations.

Work performed on `feat/sentinel-raster-preparation`, 2026-09-07. No commit or
push was made. Stage C and all later stages remain unimplemented by this work.

## Narrow correction pass

This pass changes only `coverage.py`, `test_coverage.py`, and this review.
The implementation record below describes the original Stage B pass.
`_intersection_coverage` now checks the raw fraction with an absolute tolerance
of `8 * math.ulp(1.0)` (about `1.78e-15`): eight binary64 steps at unity, a
machine-scale roundoff allowance on the unit interval, not a geometry-error
budget. In-range values remain unchanged; excursions within that tolerance
normalize to exactly 0 or 1. Larger excursions and non-finite values raise
`ValueError`. The measured intersection area remains unchanged.

`select_preferred_group()` remains in `coverage.py` only because Stage B needs
candidate selection. Selection is conceptually orchestration/manifest work.
When Stage E introduces that layer, it must **move or reuse this existing
logic**, preserving one source of truth, and must not implement independent
candidate-selection behavior. Its docstring records this ownership requirement.

Two new parameterized tests (12 cases) inject controlled overlay areas to check
an ordinary fraction, tiny upper/lower excursions, both tolerance boundaries,
values just beyond them, material upper/lower violations, and NaN/infinities.
Accepted cases also verify that measured area is preserved.
Validation: Stage B **43 passed**; full offline suite **139 passed, 6 deselected**;
Ruff formatting/lint passed; strict mypy passed across **17 source files**;
`pip check` and `git diff --check` passed. No commit or later-stage work was done.

## Files changed and hunk review

| File | Change and reason |
|---|---|
| `src/colonia_flood/coverage.py` | New focused geometry module: county input validation, geometry conversion, projection, deterministic group selection, intersections and coverage results. |
| `tests/test_coverage.py` | New offline tests: 31 parameterized cases across ten test functions, using simple analytical shapes and both committed manifests. |
| `pyproject.toml` | Two hunks: runtime Shapely/pyproj/NumPy constraints, and development Shapely stubs. No existing strictness or Python target changed. |
| `docs/plans/sentinel-raster-preparation.md` | Three hunks: current implementation status, correction of the Shapely typing assumption, and verified dependency constraints/results beside the historical investigation. |
| `docs/plans/sentinel-stage-b-review.md` | This report retains the actual function inventory, call flow, concepts, tests, results and commands for review. |

The new module's single new-file hunk contains imports and the `Polygonal` type
alias, two result records, then the seven functions inventoried below. It does
not add a CLI, manifest serializer, raster module or spatial framework. The
private intersection seam receives projected polygons only; public measurement
projects inputs itself, making the normal call order explicit.

The new test file's single hunk contains the paths/regression budget, two test
helpers (`records`, `to_lonlat`), and the ten test functions documented below.
`records` locally loads existing manifests and validates their records with the
existing `Acquisition` model. `to_lonlat` constructs geographical input from
hand-computable metre rectangles for the end-to-end synthetic test. There is
no new fixture download or live marker. The real county is fast enough to use
directly; another decimated boundary fixture was unnecessary.

The plan's first hunk replaces the stale "nothing implemented" status and links
the review reports. Its second corrects the unsupported assumption that Shapely
ships typing. Its third records the actual resolved dependencies, Python 3.11
compatibility constraints and exact common fractions. Historical measurements,
Stage C sequencing and the fixed label-quality gate remain intact.

Existing `Findings.md` edits and untracked `prompt.md` were preserved. The county,
manifests, config, source register and Stage A review were not edited. Generated
editable-package metadata and environment/cache changes are ignored local files.

## Dependencies and engineering decisions

| Dependency | Declaration | Installed in existing CPython 3.13 environment | Reason |
|---|---|---|---|
| Shapely | `>=2.1.2,<3` runtime | 2.1.2 | GEOS-backed polygon validity, geometry intersection and planar area. |
| pyproj | `>=3.7,<4` runtime | 3.8.0 | EPSG definitions, axis handling and WGS 84 / UTM transformation through PROJ. |
| NumPy | `>=2.1,<2.4` runtime | 2.3.5 | Required transitively by Shapely; explicitly constrained for the Python 3.11 type-checking target. No direct NumPy import is needed in the module. |
| types-shapely | `>=2.1,<3` dev | 2.1.0.20260728 | Installed Shapely has no `py.typed`; separate stubs preserve strict mypy checking. |

The first install resolved NumPy 2.5.3. Its stubs use Python 3.12 `type` syntax
and failed mypy's existing `python_version = "3.11"` configuration. The final
NumPy range retains CPython 3.13 wheels while supporting that target. pyproj 3.8
requires Python >=3.12; allowing 3.7 preserves a compatible dependency choice for
Python 3.11, also advertised by [pyproj 3.7.2 package metadata](https://pypi.org/pypi/pyproj/3.7.2/json).
Runtime tests here used Python 3.13, not a separate Python 3.11 interpreter.

Both geometries must share a metre CRS before intersection and measurement:
Shapely works in a Cartesian plane and does not transform CRSs itself. Using
longitude as x and latitude as y in square-degree area would neither produce
square metres nor correctly weight spatial areas. Swapped axes, the wrong UTM
zone, mixing projected and geographic inputs, or projecting just one operand
can yield nonsense, disjoint shapes or plausibly wrong percentages. The known
UTM origin test and the 10,000 m² synthetic county test protect against these
mistakes. See the [Shapely coordinate-system documentation](https://shapely.readthedocs.io/en/stable/manual.html#coordinate-systems).

`Transformer.from_crs(..., always_xy=True)` explicitly keeps GeoJSON's
longitude/latitude order. `errcheck=True` makes projection failures raise.
pyproj supplies maintained projection formulas and its bundled CRS database;
Shapely supplies maintained polygon operations, including holes and multipart
geometry. This avoids maintaining custom clipping, area or UTM mathematics.
See the [pyproj Transformer API](https://pyproj4.github.io/pyproj/stable/api/transformer.html).

## Actual function inventory

`Polygonal` means `shapely.geometry.Polygon | MultiPolygon`. `CoverageMeasure`
is a frozen dataclass with `area_m2: float` and `county_fraction: float`.
`CoverageReport` holds county area, a dictionary keyed by observation ID, a
dictionary keyed by `(pre_id, event_id)`, and the three-scene measure. These two
records describe outputs; they do not introduce service objects or hidden state.
The report's dictionary contents are not deeply frozen.

| Function | Inputs → return | Responsibility and library calls | File I/O / determinism |
|---|---|---|---|
| `_validate_polygon` | `BaseGeometry` → `Polygonal` | Reject empty/non-polygon, Z/M, non-finite and topologically invalid geometry using Shapely type/predicate checks, `get_coordinates`, `explain_validity`, and `math.isfinite`. Returns the same validated geometry. | No application I/O; pure for fixed library behavior. |
| `geometry_from_geojson` | `object` (validated as a mapping) → `Polygonal` | `shape(dict(document))` constructs geometry, `_validate_polygon` checks it, then bounds enforce longitude/latitude ranges. Invalid input raises `ValueError`. | No I/O; pure/deterministic. |
| `load_county_boundary` | `Path`, `AreaOfInterest` → `Polygonal` | `Path.read_text`, `json.loads`, FeatureCollection/Feature/count/FIPS checks, `geometry_from_geojson`, and the reviewed six-decimal bbox comparison. | One application file read; not pure with respect to mutable file contents. Deterministic for the same bytes/config. |
| `project_to_utm14` | EPSG:4326 `Polygonal` → EPSG:32614 `Polygonal` | Validate input; `Transformer.from_crs`, `shapely.ops.transform` with `partial(transformer.transform, errcheck=True)`; validate projected output. | No application input-file I/O or network. PROJ consults bundled definitions; deterministic for fixed inputs/library database. No cached global transformer or changed global network setting. |
| `select_preferred_group` | `Sequence[Acquisition]` → `tuple[Acquisition, Acquisition, Acquisition]` | Filter `matches_preferred_orbit`, sort `(datetime_utc, item_id)`, require two pre-event and one event record; reject duplicates, mixed event/orbit/direction, missing VV/VH metadata. Returns chronological pre1, pre2, event. | No I/O; pure/deterministic. Uses Python containers/sorting, not a new selection framework. |
| `_intersection_coverage` | Validated EPSG:32614 `Polygonal`, `Sequence[Polygonal]` → `CoverageMeasure` | Begin with county, repeatedly call `.intersection(footprint)`, measure `.area`, divide by county area. Clamp only the fraction to [0,1] for overlay roundoff; retain measured area. | No I/O; pure. Private caller contract requires projected valid inputs and positive county area. |
| `coverage_metrics` | EPSG:4326 `Polygonal`, `Sequence[Acquisition]` → `CoverageReport` | Calls selector; projects county and all three footprints; verifies finite positive denominator; calls intersection seam three times for singles, twice for pairs and once for all three. | No I/O of its own; deterministic given fixed geometry, records and library definitions. |

There are no other functions in `coverage.py`. No dates, orbit numbers or local
filesystem paths are hard-coded into candidate selection. Existing manifest
policy flags are authoritative; this stage checks group consistency but does
not recompute flags from configuration or add manifest-level hash validation.
That orchestration belongs to the later manifest stage.

## Actual call and data flow

```text
config/events.toml -- existing load_config --> AreaOfInterest
                                                   |
county GeoJSON -- load_county_boundary(path, aoi) ----+
                       |
                       +-- json.loads --> Feature.geometry mapping
                       +-- geometry_from_geojson --> shape --> _validate_polygon
                       |                              |
                       +----------------------> county Polygon in EPSG:4326

committed acquisitions.json -- caller json.loads --> Acquisition.model_validate
                                                   |
                                                   v
coverage_metrics(county_4326, acquisitions)
  +-- select_preferred_group --> (pre1, pre2, event)
  +-- project_to_utm14(county_4326) --> county Polygon in metres
  +-- for each selected Acquisition.footprint:
  |     geometry_from_geojson --> Shapely polygon in degrees
  |     project_to_utm14 --> Shapely polygon in metres
  +-- _intersection_coverage(county_m, [scene])                 x3
  +-- _intersection_coverage(county_m, [pre, event])            x2
  +-- _intersection_coverage(county_m, [pre1, pre2, event])      x1
          .intersection --> overlap geometry --> .area (m²)
                            --> area / county_m.area --> fraction
  +-- CoverageReport returned to caller; no artifact written
```

The test/report caller reads the local manifest; no production manifest reader
or CLI was introduced. Source footprint geometry, rather than the manifest's
rectangular `bbox`, feeds the calculation. County and scene projection complete
before any overlay or meaningful area calculation occurs.

Only dependency installation and technical documentation lookup used network
I/O during development. No Census, Planetary Computer or Azure asset was
contacted in Stage B. The fixed WGS 84-to-UTM operation needs no remote grid.
All tests run under the existing autouse socket blocker. That fixture blocks
Python socket connections, not every possible native-library HTTP stack; this
stage does not introduce a native remote-data operation.

## Concepts: plain explanation, technical meaning, code location

| Concept | Plain explanation | Technical meaning and actual code location |
|---|---|---|
| GeoJSON | A structured text description of a shape. | JSON geometry type and nested coordinate arrays; county loading extracts the Feature's geometry and `geometry_from_geojson` passes it to `shape`. |
| Polygon | An enclosed outline, possibly with holes. | Exterior linear ring plus interior rings; the `Polygonal` alias also permits multiple polygons. `_validate_polygon` checks usable geometry. |
| Shapely | The library that understands shape overlap. | GEOS-backed planar predicates and set operations; `shape`, `.is_valid`, `.intersection` and `.area` appear in the conversion/validation/measurement functions. |
| pyproj | The library that translates geographic coordinates onto a map grid. | Python bindings to PROJ; `project_to_utm14` uses `Transformer.from_crs` and `.transform`. |
| CRS | The rules explaining what coordinate numbers mean. | Datum, axes and coordinate operation definitions; source and destination are explicit in `project_to_utm14`. A bare Shapely geometry does not retain CRS metadata. |
| EPSG:4326 | WGS 84 longitude and latitude. | Geographic angular coordinates, supplied as longitude then latitude for GeoJSON; the public geometry APIs require this input. |
| EPSG:32614 / UTM Zone 14N | A metre map grid suitable for Hidalgo County. | WGS 84 northern-hemisphere transverse Mercator zone 14, central meridian 99°W; destination CRS in `project_to_utm14`. |
| Geographic vs projected coordinates | Degrees locate a place on Earth; map-grid metres support local measurement. | `county_4326` becomes `county_m`; each scene takes the same transformation before `_intersection_coverage`. |
| Intersection | The portion shared by all supplied shapes. | Repeated set intersection in `_intersection_coverage` begins with the county, so each result remains county-clipped. |
| Area | How much surface the mapped shape encloses. | Shapely planar `.area` is square metres only because operands are projected; used in `_intersection_coverage` and the report denominator. |
| Coverage fraction | The share of the county inside that overlap. | Dimensionless `area_m2 / county_m.area`, bounded to [0,1] in `_intersection_coverage`; multiply by 100 to display percent. |
| Pure function | A calculation whose result follows from its inputs. | `select_preferred_group` and intersection calculations have no file/network side effects. Projection also depends on fixed library/CRS definitions; the county loader is explicitly a file-I/O boundary. |
| Regression test | A check that later edits do not unexpectedly change a known result. | `test_committed_common_coverage_regression` compares local-data results to historical estimates with a stated sampling budget, and checks selection and intersection relationships. |

STAC footprint coverage says where a scene's catalogue polygon overlaps the
county. It cannot say which raster cells contain usable observations. Interior
pixels can still be NoData or unusable. Only later pixel/mask handling can count
valid observed area; neither a zero footprint fraction nor a passing footprint
bound is a flood label or a decision about Path A/Path B.

## Tests: protection, failure modes and limits

| Test | Behavior protected / bug that would fail | Important limits |
|---|---|---|
| `test_load_committed_county_preserves_coordinates` | Source coordinates survive loading, county is valid with 4,132 positions, bbox matches at six decimals. Rounding/simplifying or loading the wrong geometry fails. | Does not independently verify Census provenance or historical boundary accuracy. |
| `test_county_rejects_wrong_input` (5 cases) | Wrong collection type, extra feature, wrong Feature type, mismatched GEOID and bbox all raise. Missing identity or extent checks fail. | Does not exercise every filesystem/JSON parse failure or maliciously mislabeled geometry with identical bbox. |
| `test_geometry_rejects_unusable_input` (8 cases) | Reject None, Point, empty coordinates, absent coordinates, self-crossing polygon, projected values supplied as lon/lat, 3D and infinity. Missing validity/dimension/range checks fail. | Not an exhaustive GeoJSON conformance suite; does not prove every topology defect is covered. Geometry construction follows Shapely semantics. |
| `test_multipart_and_holes_preserved` | A polygon of area 16 with a hole of area 4 plus a separate unit square yields coverage 12/13. Dropping holes or multipart components fails. | This analytical check uses the private planar seam and does not exercise projection of multipart data. |
| `test_projection_uses_longitude_first_and_metres` | The point (-99°,0°) maps to (500000 m,0 m); a nearby 0.01° square has about 1.2 million m²; reprojecting metre coordinates is rejected. Wrong zone, axis order, missing projection or wrong units fail. | One anchor is not a global projection-accuracy audit; same-number coordinates from a wrongly declared CRS can escape a bounds check. |
| `test_hand_computed_projected_intersection` (4 cases) | Disjoint and edge-touching squares yield zero area, enclosing square yields one, half-overlap yields 0.5. Incorrect overlap/denominator or treating touch as positive area fails. | Private seam only; does not prove geographic-to-projected wiring. |
| `test_report_intersects_all_three_after_projection` | A 100×100 m county gives per-scene 0.6/0.7/0.64, pairs 0.32/0.40 and common 0.20. Wrong pairing, omitted county/scene, degree-area, taking the minimum instead of intersection, or input-order dependence fails. | Inputs use pyproj's inverse to construct lon/lat; the independent UTM anchor test supplements this round trip. |
| `test_selection_rejects_ambiguous_or_inconsistent_group` (7 cases) | Missing/extra observations, duplicate ID, mixed event/orbit/direction, or absent VV href all raise. Silent truncation or unchecked group consistency fails. | Does not validate live asset contents, every polarization defect, or independently recompute the preferred flag. |
| `test_bad_footprint_is_not_zero_coverage` | Missing footprint raises through the public report function. Replacing missing data with zero coverage fails. | Does not cover raster NoData semantics; no raster is opened. |
| `test_committed_common_coverage_regression` (2 events) | Confirms all six expected candidates, projected county area, common fractions, fraction bounds, pair/common subset area relationships, and reversed-input determinism. Bbox substitution, wrong orbit/group or changed geometry can fail. | Historical values are sampled estimates, not exact ground truth. The migration budget can miss smaller changes; it cannot measure valid pixels. |

The existing `block_network` autouse fixture applies to every case; none has a
live marker. Analytical square-area tolerances (`1e-5` m², `1e-9` fraction)
allow inverse/forward floating-point roundoff. Subset comparisons allow `1e-5`
m² of GEOS overlay roundoff. The county source-area check uses 0.1% relative
tolerance because Census area and UTM planar area are different measurements;
it is an order/units check rather than a demand that the two methods coincide.

The historical coverage regression uses **0.0002 absolute fraction, or 0.02
percentage points**, unchanged since the tests were introduced. For this county,
that is about 0.82 km²: about 20 old 200×200 m sample cells out of 102,458 county
sample points, and roughly 0.11% of the common footprint area. This is a narrow
engineering regression budget for boundary aliasing plus rounding of the
published two-decimal percentages. It is not a formal sampling confidence
interval or worst-case lattice-error bound. A failure must be investigated,
not fixed by widening the budget. No scene-acceptance threshold was added.

## Exact calculated results

Projected county area: **4,096,938,853.5655017 m²**, or
**4,096.938853565502 km²**. All following areas are in EPSG:32614; fractions
use that entire county area as the denominator. Values retain float output
precision so the calculation can be compared directly with a rerun.

| Event / observation | Intersection area (m²) | County fraction | Percent |
|---|---:|---:|---:|
| Hanna / 2020-07-03 pre | 742520243.7828563 | 0.18123781445667725 | 18.123781445667724 |
| Hanna / 2020-07-15 pre | 741888710.9100769 | 0.18108366695891073 | 18.108366695891075 |
| Hanna / 2020-07-27 event | 746404658.4546971 | 0.18218594056025827 | 18.21859405602583 |
| March / 2025-03-03 pre | 744344035.2458173 | 0.18168297400827116 | 18.168297400827115 |
| March / 2025-03-15 pre | 747530372.1197748 | 0.18246071001748315 | 18.246071001748316 |
| March / 2025-03-27 event | 745408766.9822432 | 0.18194285871109 | 18.194285871109 |

| Pair / common group | Intersection area (m²) | County fraction | Percent |
|---|---:|---:|---:|
| Hanna / July 3 + July 27 | 742520243.7828579 | 0.1812378144566776 | 18.12378144566776 |
| Hanna / July 15 + July 27 | 741888710.9100786 | 0.18108366695891118 | 18.108366695891117 |
| Hanna / all three | 741888710.9100764 | 0.18108366695891062 | 18.10836669589106 |
| March / March 3 + March 27 | 744344035.2458163 | 0.18168297400827094 | 18.168297400827093 |
| March / March 15 + March 27 | 745408766.9822446 | 0.18194285871109037 | 18.194285871109038 |
| March / all three | 744344035.2458181 | 0.18168297400827138 | 18.16829740082714 |

Hanna differs from sampled 18.11% by **-0.00163330410894 percentage points**.
March differs from sampled 18.16% by **+0.00829740082714 percentage points**.
Both pass the 0.02-percentage-point budget. March rounds to 18.17% with this
calculation; use the exact results above for future geometry work rather than
forcing them to the old sampled numbers. No material discrepancy was found.
Tiny differences between nominally nested areas are GEOS floating-point overlay
roundoff, on the order of millionths of a square metre in these results.

"Exact geometry" means polygon overlay rather than the investigation's point
sampling. It does not mean infinite precision, perfect physical boundaries or
an equal-area Earth-surface calculation. UTM has small scale distortion. The
implementation projects existing vertices and joins them with straight segments;
it does not densify geographic edges. Results are defined on those projected
polygon representations. Source county coordinates and stored six-decimal STAC
footprints remain unchanged on disk.

## Commands/checks and reproducible calculation

Repository checks: `git branch --show-current` and
`git status --short --branch` confirmed the expected branch, with only the
pre-existing `Findings.md` and `prompt.md` changes before implementation.

Dependency commands executed, in order:

```powershell
.\.venv\Scripts\python.exe -m pip install "shapely>=2.1.2,<3" "pyproj>=3.8,<4"
.\.venv\Scripts\python.exe -m pip install "types-shapely>=2.1,<3"
.\.venv\Scripts\python.exe -m pip install "numpy>=2.1,<2.4"
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The first three needed approved retries outside the sandbox because network
access was blocked. They installed the versions documented above (NumPy was
initially 2.5.3, then replaced by 2.3.5). The no-build-isolation attempt failed
because `setuptools.build_meta` was not installed in the environment. Normal
build isolation then succeeded, reinstalling the editable package from the
final `pyproject.toml` with its configured development dependencies.

Validation commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_coverage.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff format src/colonia_flood/coverage.py tests/test_coverage.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pip check
git diff --check
git status --short
git diff --stat
git diff -- pyproject.toml docs/plans/sentinel-raster-preparation.md
```

Results: Stage B **31 passed**; full default offline suite **127 passed,
6 live tests deselected**; ruff passed; strict mypy passed across **17 source
files**; `pip check` found no broken requirements; `git diff --check` passed.
The first lint/type runs identified formatting, NumPy stub syntax and two
mapping-type errors; all were fixed without disabling checks. Full added files
were read and reviewed along with tracked diffs. Before-edit SHA-256 checks
verify unrelated tracked content, `Findings.md`, `prompt.md` and committed data
were preserved. No signed URL, credential or machine-specific path was added.

The actual calculation uses this local-file-only Python flow, run through
the project interpreter (paste into a PowerShell single-quoted here-string
and pipe to `.\.venv\Scripts\python.exe -`):

```python
import json
from pathlib import Path
from colonia_flood.acquisitions import Acquisition
from colonia_flood.coverage import load_county_boundary, coverage_metrics
from colonia_flood.events import load_config

config = load_config(Path("config/events.toml")).config
county = load_county_boundary(
    Path("data/boundaries/hidalgo_county.geojson"), config.aoi["hidalgo_county"]
)
for event in config.events:
    document = json.loads(
        Path("data/manifests", event.event_id, "acquisitions.json").read_text()
    )
    acquisitions = [Acquisition.model_validate(a) for a in document["acquisitions"]]
    report = coverage_metrics(county, acquisitions)
    print(event.event_id, report)
```

## Git review and unresolved limits

Final `git status --short`:

```text
 M Findings.md
 M docs/plans/sentinel-raster-preparation.md
 M pyproject.toml
?? docs/plans/sentinel-stage-b-review.md
?? prompt.md
?? src/colonia_flood/coverage.py
?? tests/test_coverage.py
```

Final `git diff --stat`:

```text
 Findings.md                               | 345 ++++++++++++++++++++++++++++++
 docs/plans/sentinel-raster-preparation.md |  27 ++-
 pyproject.toml                            |   5 +
 3 files changed, 374 insertions(+), 3 deletions(-)
```

The 345 `Findings.md` additions predate this task and are unchanged. Untracked
additions do not appear in ordinary `git diff --stat`; this stage also adds
192 lines of geometry code, 240 lines of tests, and this review report, all
reviewed in full. The before-edit hash comparison found changes only in
`pyproject.toml` and the plan among pre-existing tracked files.

No Stage B blocker remains. Dependency/typing differences from the plan are
resolved and documented. Python 3.11 compatibility is retained in dependency
constraints and strict type checks but was not runtime-tested here. The existing
global-ignore permission and LF/CRLF notices from Git remain environment
warnings. Catalogue footprints, current-vintage county boundaries and UTM
planar area retain their stated limitations. No raster validity, scientific
suitability, colonia viability or label-quality gate was evaluated.

Stage B complete. Stopped before Stage C for review.

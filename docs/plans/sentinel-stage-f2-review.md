# Stage F2 review — fixed 500 m vector upper bound

F2 uses only the committed Hidalgo County polygon, OAG colonia snapshot and
acquisition manifests, plus local event configuration. No network or raster
access occurred. The source snapshot and Stage B code are unchanged.

## Result and interpretation

There are **16,820 positive-area county grid cells**, of which **1,649** have
positive-area overlap with the selected OAG colonias. Bounding-box squares
with zero county intersection area are not included in either total.

| Event | Fully inside upper bound | Partial upper bound | Outside | Candidate upper bound | Below 20? |
|---|---:|---:|---:|---:|---|
| Hanna 2020 | 401 | 17 | 1,231 | **418** | No |
| March 2025 | 403 | 16 | 1,230 | **419** | No |

`candidate_upper_bound = fully_inside_upper_bound + partial_upper_bound`.
The three classifications partition all 1,649 colonia-intersecting cells.
Neither event is ruled out by this necessary geometric criterion. **No gate
has passed.** STAC footprints do not establish valid raster observations;
Stage H can only reduce this count through valid-pixel-mask inspection. These
are not flood observations, dry cells, inundated cells or labels.

Counts are conditional on the named historical OAG registry and snapshot
vintage documented in [F1](sentinel-stage-f1-source-review.md), including its
completeness, positional accuracy and differing administrative definitions of
colonia. The fixed Path-A threshold remains 20.

## Modules and actual functions

- `src/colonia_flood/colonia.py`: pure geometry/report computation.
  `CountyCell` carries lattice indices and effective geometry; `EventUpperBound`
  and `ViabilityReport` describe outputs. `county_grid` enumerates effective
  cells, `colonia_cells` filters positive-area colonia intersections,
  `classify_cell` classifies footprint overlap, and `viability_report` projects
  inputs and aggregates each event's counts.
- `src/colonia_flood/colonia_cli.py`: `load_colonias` validates local source
  features; `calculate_local` reads configuration, boundaries and manifests;
  `report_json` serializes deterministically; `main` writes the artifact.
  Invoke as a module; no packaging/dependency changes or refresh command.
- `tests/test_colonia.py`: 26 offline synthetic/loader cases. Existing Stage B
  fixture helpers supply acquisition records and inverse-projected synthetic
  geometry; no real Hidalgo count is hard-coded as a scientific test oracle.

## Geometry rules

All metric calculations use **EPSG:32614** and Stage B's `project_to_utm14`.
Public report inputs are EPSG:4326; lower-level grid/classification functions
explicitly require already-projected geometry. Shapely geometry carries no CRS
metadata, so callers must respect that contract.

For each axis enumerate indices from `floor(min / 500)` through
`ceil(max / 500) - 1`. Square lower-left coordinates are exactly
`(column * 500, row * 500)` metres. IDs are
`utm14_500:<column>:<row>`; they never depend on feature or iteration order.
Each square is intersected with the county. Only positive-area effective
geometries survive. Colonia and footprint classification both use this
effective geometry, so geometry outside the county cannot affect a cell.

Project and validate colonia polygons, sort by WKB, and build one derived
in-memory union. Preparation rejects disjoint cells before the positive-area
overlay test. Sorting fixes union input order; merging once avoids repeatedly
intersecting each cell with all 846 source polygons. Multiple colonia hits
count once. Colonia membership requires intersection area **strictly > 0**;
edge/point touches do not count. No source geometry is modified in place,
repaired, rounded or written back.

For each event, reuse `select_preferred_group` without adding selection policy.
Construct the common geometry with the same county-first intersection order
as Stage B, projecting each selected footprint through its existing helpers.
Stage B's intersection helper returns an area measure, not geometry, so this
small geometry construction is local to F2 and Stage B remains untouched.
The selected orbit-143 descending observations are July 3/15/27, 2020 and
March 3/15/27, 2025; full item IDs are stored in the artifact.

Footprint intersection area of zero means `outside`, including boundary-only
touches. Otherwise test the effective cell's area outside the common footprint.
Full containment allows at most:

```text
8 * math.ulp(max(abs(v) for v in effective_cell.bounds)) * effective_cell.length
```

This is an area allowance based on eight binary64 coordinate steps times the
effective perimeter, approximately 7.45e-6 square metres for a full cell at
Hidalgo northings. It accommodates overlay slivers on shared county edges;
an inverse/forward-projected synthetic rectangle exposed such a sliver.
It is not a source-position uncertainty allowance. Tests distinguish a
one-ULP sliver from a 1 mm strip and retain a small material remainder as
partial. Larger remainder means `partial`. This tolerance changes only the
full/partial split: **positive-area footprint overlap remains mandatory**, and
the candidate upper bound is unaffected by the containment allowance.

Per the requested cell definition, colonia overlap and footprint overlap need
not occupy the same portion of a cell. Requiring their triple intersection
would answer a stricter question and is not applied here.

## Artifact and reproduction

Run from the repository root (or pass `--root` to a local checkout):

```powershell
.\.venv\Scripts\python.exe -m colonia_flood.colonia_cli
```

Output: `data/analysis/colonia_viability.json`, **2,008 bytes**, SHA-256:

```text
7b4b2bf2cae0054ee46be986c6a452c5ffa7e6e62b5072b51e52803ab9831763
```

Schema `colonia-viability-f2-v1`; sorted JSON keys, two-space indentation,
UTF-8, one final LF, no wall-clock timestamp, machine path or environment field.
The artifact includes both boundary SHA-256 values, grid/ID rules, selected
item IDs, counts, threshold comparison and explicit upper-bound interpretation.

Repeated calculation and reversal of real colonia, acquisition and event
ordering reproduced identical artifact bytes with Python socket connections
blocked. Source boundary hashes, Stage B code, `Findings.md` and `prompt.md`
were verified unchanged. No runtime data download was introduced.

## Validation and limits

- F2-specific tests: **26 passed**. Synthetic tests cover lattice/ID stability,
  negative indices, disconnected county components, input order, positive-area
  membership, duplicate hits, clipped county-edge cells, all classifications,
  tolerance, 19/20/21 threshold behavior, report framing, projection and Stage B
  agreement, source validation and source-byte preservation.
- Full offline suite: **165 passed, 6 live tests deselected**, including all
  Stage B tests under the existing socket blocker.
- Ruff lint and formatting passed; strict mypy passed across **20 files**;
  `pip check` found no broken requirements; `git diff --check` passed.

No implementation blocker remains. Scientific limits remain unresolved by
design: source completeness/vintage/accuracy, STAC footprint versus usable
pixels, and the eventual Stage H count. Floating-point projection/overlay
retains Stage B's vertex-only geometry semantics. No 250 m or alternative-orbit
analysis, raster reading, SAS request, new dependency, Stage C/D/E/H work or
gate change was performed. No commit was made; stop here for F2 review.

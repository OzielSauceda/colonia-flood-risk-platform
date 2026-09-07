# Stage A review — Hidalgo County boundary

Completed 2026-09-07 on `feat/sentinel-raster-preparation`. No commit or push
was made. The snapshot is ready for version control; Stage B has not begun.

## Files changed and full diff summary

- Added `data/boundaries/hidalgo_county.geojson`: one complete Census county
  feature. The single new-file hunk contains the FeatureCollection wrapper,
  Polygon geometry, all 4,132 coordinate positions in source order, and the
  source GEOID, NAME, AREALAND and AREAWATER properties. Every source value and
  numeric token is preserved. Newlines between positions and a final newline
  make the previously single-line response reviewable without changing data.
- Modified `docs/data-sources.md`: the opening scope now includes Stage A.
  Section 2's title/table register the full polygon, retrieval date, provider,
  layer, identifier, vintage, repository path, CRS and source integrity fields.
  The old extent-only limitation is replaced with the bbox/polygon distinction
  and future consumer. The new provenance subsection records the exact query,
  source hash, formatting, validation, manual ingestion policy and authoritative
  licensing citations. Other dataset entries are unchanged.
- Modified the existing untracked `docs/plans/sentinel-raster-preparation.md`:
  three hunks add the reviewed precision rule to §9.1, update Stage A in §17.2,
  and update R1 in §18. Only the four derived bbox values are normalized to six
  decimals; polygon coordinates are preserved. Historical investigation figures
  remain intact, with an adjacent clarification of their printed precision.
- Added this report, `docs/plans/sentinel-stage-a-review.md`, to retain the
  learning handoff, validation evidence and unresolved findings locally.

Pre-existing edits in `Findings.md` and untracked `prompt.md` were preserved.
The plan was already untracked; its three changes were reviewed against a
temporary before-edit copy, rather than treating the entire plan as new work.

## Source and validation results

The reviewed source is the anonymous Census TIGERweb response downloaded during
the first Stage A attempt on 2026-09-07. This resumed stage reused that response;
it did not fetch a replacement boundary.

```text
https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query?where=GEOID%3D%2748215%27&outFields=GEOID,NAME,AREALAND,AREAWATER&returnGeometry=true&outSR=4326&f=geojson
```

| Check | Result |
|---|---|
| Raw derived bbox | `[-98.58644400000378, 26.03626800000421, -97.86168400042897, 26.783080999883026]` |
| Six-decimal normalized bbox | `[-98.586444, 26.036268, -97.861684, 26.783081]` |
| Configured bbox | `[-98.586444, 26.036268, -97.861684, 26.783081]` |
| Comparison | PASS at configuration precision; raw equality is not required |
| GEOID / name | `48215` / `Hidalgo County` |
| Geometry | One FeatureCollection feature, Polygon, one closed ring |
| Coordinate count | 4,132 positions including the repeated closing position |
| Land / water | 4,069,433,006 m² / 30,081,128 m², source-reported attributes |
| Basic structure | Valid JSON; finite two-dimensional longitude/latitude positions within geographic bounds |
| Original response | 168,672 bytes; SHA-256 `25cdbcbec6b08881533038c72aa7033341e8135744199aa7e06a756d92da63dd` |
| Saved snapshot | 172,804 bytes; SHA-256 `42a988e52aa1962050971d19fbd721e75944a46354bb03f7c8c0cf4f8fb1d70f` |
| Source preservation | PASS: decimal-preserving JSON equality and exact expected whitespace transformation |

No polygon rounding, simplification, coordinate reordering, geometry repair,
area calculation, new acceptance threshold or config edit was performed.
Basic GeoJSON checks do not establish topological validity or raster coverage.

## Data flow and engineering concepts

**Authoritative Census source → GeoJSON snapshot → version-controlled project
input → future `coverage.py` consumer.** The version-control step is prepared,
not committed, because this task explicitly prohibits committing.

Network I/O occurred during the first attempt's explicit `curl.exe` ingestion
and during authoritative source-document review. No application code was added.
Normal future coverage processing will read the local snapshot, so it need not
contact Census. An upstream refresh must be an explicit, reviewed data change.

A **bounding box** is the rectangle enclosing all county coordinates. It
over-covers the county and is useful for initial catalog searches. The
**polygon** retains the actual outline needed for later intersection and area
work. Matching the bbox supports consistency with the existing query extent;
it does not prove that two polygon interiors are identical.

**GeoJSON** is JSON containing named geographic structures: this snapshot has a
FeatureCollection with one Feature, its Polygon coordinates, and identifying
properties. **EPSG:4326** is a geographic CRS using WGS 84; GeoJSON positions
use longitude then latitude in degrees. Degrees are not metres, so this stage
does not calculate area from them. Land/water values above come from Census.

**Data provenance** records who supplied the geometry, what service and query
returned it, when it was obtained, its CRS, and the content hashes. The register
retains these facts separately from the geometry. **Reproducibility** comes
from preserving fixed source values and deterministic formatting. Committing
this small external snapshot makes future calculations independent of service
availability and prevents upstream boundary changes from silently changing
results. A documented query alone cannot guarantee identical future content.

## Commands and checks run

The first attempt downloaded the source using the following command. The
sandbox connection failed; the approved escalated retry succeeded.

```powershell
curl.exe -L --fail --silent --show-error 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query?where=GEOID%3D%2748215%27&outFields=GEOID,NAME,AREALAND,AREAWATER&returnGeometry=true&outSR=4326&f=geojson' -o "$env:TEMP\hidalgo-stage-a-source.geojson"
```

Read-only checks included:

```powershell
git branch --show-current
git status --short
git diff -- docs/data-sources.md
git diff --no-index -- "$env:TEMP\hidalgo-stage-a-plan-before.md" docs/plans/sentinel-raster-preparation.md
git diff --check
Get-FileHash Findings.md,prompt.md
.\.venv\Scripts\python.exe "$env:TEMP\hidalgo-stage-a-validate.py"
```

The branch check returned the expected branch. The no-index diff returned 1
because it found the three intended plan hunks. `git diff --check` passed.
The temporary standard-library validation script executed these exact checks:

1. Parse downloaded and saved JSON with `parse_float=Decimal` and assert complete
   document equality, preserving decimal values rather than merely comparing
   binary floating-point approximations.
2. Assert saved text equals
   `raw.replace('],[', '],\n[').rstrip() + '\n'`; this checks every source token
   and makes the normalization deterministic over the entire new-file diff.
3. Assert FeatureCollection type, exactly one Feature, expected properties,
   Polygon type, one ring, 4,132 positions, and equal first/last positions.
4. Assert each position has two finite numbers with longitude in [-180, 180]
   and latitude in [-90, 90].
5. Derive `[min(longitudes), min(latitudes), max(longitudes), max(latitudes)]`;
   assert `[round(v, 6) for v in bbox]` equals the bbox read with `tomllib` from
   `config/events.toml`. Also compare feature GEOID with config FIPS.
6. Compute SHA-256 and byte size of the saved snapshot.
7. Compare all pre-existing non-hidden project files with before-edit SHA-256
   hashes. Only the register and the explicitly authorized plan changed.
8. Scan the data/register for signed-token URL parameters, authorization/bearer
   credentials and absolute machine paths; none found. Review the three plan
   additions and this report for the same exclusions.

All assertions passed. No package installation or application test suite was
needed for this data/documentation-only stage. No production or test code was
created; the validator remains temporary.

Final `git status --short`:

```text
 M Findings.md
 M docs/data-sources.md
?? data/boundaries/
?? docs/plans/sentinel-raster-preparation.md
?? docs/plans/sentinel-stage-a-review.md
?? prompt.md
```

## Unresolved findings and limits

No Stage A blocker remains. The first attempt's bbox mismatch is resolved by
the reviewed six-decimal validation rule. The response byte size differs from
the investigation's 168,693-byte figure; the earlier response is not available
for a byte comparison, so the reason is not established. Identity, position
count, reported areas and normalized bbox agree with the investigation.

The service advertises January 1, 2026 vintage; this is not a claim of historical
2020 or 2025 boundary accuracy. Licensing and vintage sources are linked in the
data-source register. Git emitted existing global-ignore permission and
LF-to-CRLF warnings; these did not prevent repository status/diff validation.
No geometry topology, scene coverage, raster validity or label-quality decision
was evaluated. The fixed gate and Path A / Path B remain unchanged.

Stage A complete. Stopped before Stage B for review.

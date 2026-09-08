# Plan — Sentinel-1 raster preparation

**Status:** Stages A/B/F1/F2 reviewed; Stage C1 MemoryFile spike completed,
stopped before C2 for review. See `sentinel-stage-c1-rasterio-spike.md` for the
bounded-prefix result and dependency versions. Earlier investigation
measurements below retain their historical context; later stages remain proposed.
**Investigation date:** 2026-09-06
**Revised:** 2026-09-07 — see "Revision note" below.
**Branch:** `feat/sentinel-raster-preparation`
**Predecessor slice:** `docs/plans/sentinel-acquisition-manifest.md` (historical)

## Revision note — 2026-09-07

Four changes were made to the **[PROPOSED]** parts of this plan. No
**[VERIFIED]** measurement was altered, and the label-quality gate (§16.5) is
untouched.

1. **Shapely + pyproj are adopted when real geometry/coverage work begins**
   (Stage B), not deferred — the project maintains no hand-rolled projection or
   intersection code (§12.3).
2. **Rasterio is adopted when production raster metadata/pixel handling begins**
   (Stage C), not deferred — the project maintains no hand-written TIFF parser
   (§12.2).
3. **Colonia-boundary selection and a footprint-intersection viability
   *precheck* are elevated into this slice**, ahead of any flood-label
   implementation (§2.1, §9.4, §14). The precheck yields an **upper bound on a
   necessary condition** — it can falsify the gate's colonia criterion early,
   but a passing bound establishes nothing, and it never measures valid
   observations.
4. **Implementation is broken into eight learning-sized stages with a mandatory
   stop and review after each** (§17.1).

Also dropped: the proposed `--refresh-boundary` flag. Authoritative boundary
files are acquired explicitly and committed, not fetched by code (§9.1).

Changes 1 and 2 give up the "dependency-free core" property of the earlier
draft. That trade is stated explicitly in §17.3 rather than glossed.

## How to read this document

Every claim is tagged so that measurement is never confused with opinion:

- **[VERIFIED]** — established from the current repository, the committed
  manifests, a bounded live check performed during this investigation, or cited
  authoritative documentation. Live checks are listed in §3.6.
- **[PROPOSED]** — a recommendation. Not a fact, not yet agreed.
- **[UNRESOLVED]** — the investigation could not defensibly decide this. These
  are not filled in with assumptions to make the plan look finished.

§19 summarises all three categories.

**The single most important finding of this investigation is in §4.3.** It is a
measurement, it was not anticipated by any existing project document, and it
changes what the next slice can honestly promise. Read it before §5 onward.

---

## 1. Current repository state relevant to this slice

### 1.1 Where the work stands **[VERIFIED]**

The acquisition-manifest slice is complete and merged (`1366387`, merging PR #3,
which carried `8b9452d` pipeline, `d4433c7` timeout fix, `33a1e32`
`docs/data-sources.md`). `feat/sentinel-raster-preparation` is checked out and
is **zero commits ahead of `main`** — no raster work exists yet.

`docs/data-sources.md` is now committed, which closes the merge blocker recorded
at `Findings.md` §"2026-09-05 — Acquisition-manifest review follow-up". MVP
criterion A2 is satisfied for the datasets actually used so far.

### 1.2 Existing modules and their responsibilities **[VERIFIED]**

The package is flat, with exactly one network seam:

| Module | Responsibility | Purity |
|---|---|---|
| `events.py` | TOML load, Pydantic validation, half-open window resolution, config SHA-256 | pure except one `read_bytes` |
| `stac_client.py` | `SearchClient` Protocol + `PystacSearchClient`; **the only network code** | I/O |
| `acquisitions.py` | raw STAC dict → `Acquisition` \| `ExcludedItem` | pure |
| `manifest.py` | assembly, deterministic ordering, `serialize`, `sha256_hex`, `write_atomic` | pure + atomic write |
| `run_record.py` | wall-clock, library versions, git commit — deliberately separated | I/O |
| `cli.py` | argument parsing, orchestration, exit codes 0/1/2 | orchestration |

Three properties of this design are load-bearing and the raster slice should
inherit all three:

1. **One network seam.** Nothing above `stac_client.py` knows HTTP exists.
2. **Deterministic artifact / run provenance split.** `acquisitions.json` is a
   pure function of (config, catalog response); every wall-clock value lives in
   `last_run.json`. This is structural, not a convention.
3. **Enforced offline tests.** `tests/conftest.py::block_network` monkeypatches
   `socket.socket.connect` to raise for every non-`live` test.

`manifest.serialize`, `manifest.sha256_hex`, and `manifest.write_atomic` are
already generic over the document shape. **[PROPOSED]** The raster slice reuses
them rather than reimplementing determinism.

### 1.3 Committed manifests **[VERIFIED]**

Both manifests share `config_sha256`
`736f45596646555387c49c9b9566744ea976b4228f538eaad18a2af0a2ca8885`.

| Event | acquisitions | pre_event | event | excluded |
|---|---:|---:|---:|---:|
| `hanna_2020` | 14 | 13 | 1 | 0 |
| `march_2025` | 12 | 11 | 1 | 0 |

**Each event has exactly one acquisition in its observation window**, and in
both cases it is the relative-orbit-143 descending scene. There is no
alternative event-window observation in the committed manifests.

### 1.4 Dependencies at investigation time **[VERIFIED — 2026-09-06]**

Historical state; superseded by the Stage B dependency results in §12.4 and
the [Stage C1 installation results](sentinel-stage-c1-rasterio-spike.md).

`pyproject.toml`: runtime `pydantic>=2.6,<3`, `pystac-client>=0.8,<0.10`; dev
`pytest>=8.0`, `ruff>=0.6`, `mypy>=1.11`. `requires-python = ">=3.11"`; ruff and
mypy target `py311`. **No raster, array, or geometry library is installed** — no
`rasterio`, `numpy`, `shapely`, or `pyproj`. The project venv is CPython
**3.13.2** on Windows. `mypy` runs `strict = true` over `src` and `tests`.

---

## 2. Scope and explicit non-goals

### 2.1 In scope **[PROPOSED]**

Consume the committed acquisition manifests and produce a committed,
deterministic **raster profile** per event that records, for each selected
observation: real COG metadata, grid alignment against its siblings, and
measured county coverage — plus a reproducible bounded-read path to the pixels.

**Additionally in scope, elevated deliberately (§9.4):** select a colonia
boundary source and produce a **footprint-intersection viability precheck** —
an **upper bound** on how many colonia-intersecting cells *could* fall inside
the usable ~18% footprint (§4.3). It is elevated *above* its position in
`docs/mvp.md` §13 q4 because it can **falsify** a necessary condition of the
gate before any label work is paid for. It is a bound, not a measurement: it
counts cells geometrically, classifies nothing, and **does not measure valid
observations** — a cell inside a footprint may still be entirely nodata (§3.4,
§8.3). A passing bound establishes nothing.

### 2.2 Explicit non-goals

Carried from the prompt and from `docs/research/label-feasibility.md`. This
slice does **not**:

- train any model, or choose Path A or Path B;
- generate flood labels or implement a water/inundation classifier;
- interpret radar change as flooding — in particular it never assumes darker
  pixels mean water (`label-feasibility.md` measured +1.47 dB and +3.66 dB
  *median brightening* for the 2020 and 2025 events, which already refutes the
  naive rule);
- download whole scenes, or every catalog result;
- build the grid, the database, the backend, or the frontend;
- weaken, reinterpret, or renumber the label-quality gate (§16.5);
- convert missing, masked, or out-of-footprint observations into negatives;
- re-run acquisition discovery (§5.1);
- select the rainfall or DEM sources (`docs/mvp.md` §13 q2–q3) — **colonia
  source selection is no longer deferred; see §2.1 and §9.4**;
- measure valid colonia observations — §9.4 bounds them from above and does not
  count them (Stage H does, against the valid-pixel mask);
- fix the analysis grid size (§13). The precheck in §9.4 *counts* at the
  prototype's already-fixed 500 m and reports 250 m alongside it; it does not
  select the MVP cell size.

---

## 3. Verified raster-access findings

All checks in this section were executed live on 2026-09-06 against the real
hosts, using only Python's standard library. Byte totals are reported because
"bounded" is a claim that has to be measurable.

### 3.1 Unsigned hrefs do not work **[VERIFIED — live]**

The manifests store hrefs with any query string removed
(`acquisitions.py::strip_url_query`), for example:

```
https://sentinel1euwestrtc.blob.core.windows.net/sentinel1-grd-rtc/GRD/2020/7/27/
IW/DV/S1A_IW_GRDH_1SDV_20200727T122412_20200727T122441_033640_03E61B_60B6/
measurement/iw-vv.rtc.tiff
```

Requested anonymously:

| Request | Result |
|---|---|
| `HEAD` unsigned | **HTTP 409** — `Public access is not permitted on this storage account.` |
| `GET` unsigned, `Range: bytes=0-1023` | **HTTP 409** — same |

This does not contradict `docs/data-sources.md`, which correctly states that the
*catalog* returns unsigned hrefs and explicitly records raster access as
unverified. **This investigation closes that open item: anonymous raster access
is refused, and a signing step is mandatory.**

### 3.2 Anonymous SAS signing works **[VERIFIED — live]**

`GET https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-1-rtc`
returns HTTP 200 with **no credential, no subscription key, and no account**:

```json
{"msft:expiry":"2026-09-06T06:20:15Z","token":"st=…&se=…&sp=rl&sv=2025-07-05&sr=c&…&sig=…"}
```

- Token grants `sp=rl` (read + list) at `sr=c` (container scope).
- Measured lifetime: **~46 minutes** from issue, on two consecutive requests.
- The API's own OpenAPI document
  (`/api/sas/v1/openapi.json`, "Planetary Computer Data Authentication API v1")
  declares **`securitySchemes: {}`** — i.e. no authentication is required — and
  exposes three endpoints:
  `GET /api/sas/v1/token/{collection_id}`,
  `GET /api/sas/v1/token/{storage_account}/{container}`, and
  `GET /api/sas/v1/sign?href=…`.
- Both token forms were exercised and both returned 200 for this collection
  (`sentinel-1-rtc`, and `sentinel1euwestrtc/sentinel1-grd-rtc`).

**[UNRESOLVED]** Anonymous rate limits are not documented in the OpenAPI
document, and the human-readable docs pages at
`planetarycomputer.microsoft.com/docs/concepts/sas/` are client-side rendered
and returned no text to an HTTP fetch. Microsoft has historically applied a
lower anonymous quota and a longer token lifetime for authenticated callers.
**We should not design as though anonymous issuance is unlimited** (§10.4).

### 3.3 Signed range access works and is COG-suitable **[VERIFIED — live]**

With `?<token>` appended to the unsigned href:

| Check | Result |
|---|---|
| `HEAD` | **HTTP 200**, `Content-Length: 2,062,396,392`, `Accept-Ranges: bytes`, `Content-Type: application/octet-stream` |
| `GET Range: bytes=0-131071` | **HTTP 206**, `Content-Range: bytes 0-131071/2062396392` |

`Accept-Ranges: bytes` plus observed 206 responses confirm range support
suitable for Cloud-Optimized GeoTIFF access.

### 3.4 A real windowed pixel read was performed **[VERIFIED — live]**

To avoid claiming windowed reads work without doing one, a single 512×512 tile
covering Hidalgo County was fetched and fully decoded from the **Hanna event
scene** (`…20200727T122412…_60B6/measurement/iw-vv.rtc.tiff`):

- Header read: 131,072 bytes. Tile read: 7,595 bytes (offset 879,697,031).
- Decoded Deflate + TIFF predictor 3 (floating-point predictor) → 262,144
  float32 samples.
- **261,308 samples were exactly `-32768.0` (nodata); 836 were valid.**
- Valid range: min 0.00856, median 0.242, max 48.02, **no negative values**.
  In decibels (`10·log₁₀`): p5 −12.68, p50 −6.16, p95 +4.43 — plausible land
  gamma-naught.
- **Total bytes transferred: 138,667 (0.13 MiB) from a 1.97 GiB file
  — 0.0067%.**

Two things follow. First, bounded remote reads are real, not theoretical.
Second — and this matters for §8 — **a tile whose rectangular extent lies inside
Hidalgo County was 99.7% nodata**, because the RTC raster's rectangular bounds
enclose a slanted swath. Rectangular intersection is not observation.

### 3.5 Failure modes are distinguishable **[VERIFIED — live]**

Each condition returns a different, actionable status:

| Condition | Status | Detail |
|---|---|---|
| No token | **409** | `Public access is not permitted on this storage account.` |
| Malformed/expired signature | **403** | `Server failed to authenticate the request…` |
| Valid token, wrong blob path | **404** | `x-ms-error-code: BlobNotFound` |
| Range past end of file | **416** | `x-ms-error-code: InvalidRange` |

409 vs 403 is a useful distinction: 409 means *we never signed*, 403 means *we
signed and the signature is stale or wrong* — usually an expired token.

### 3.6 Exactly what was tested versus inferred

**Tested live (bounded):** unsigned 409; SAS issuance via both endpoint forms;
SAS OpenAPI document; signed HEAD and ranged GET on **all 12 candidate assets**
(6 scenes × VV/VH); IFD/overview structure and full `GDALMetadata` on one scene;
one full tile decode; the four failure modes; the `sentinel-1-rtc` collection
document; the TIGERweb Hidalgo County polygon; a catalog search across the full
rainfall-event bounds (§4.4).

**Inferred from documentation, not tested:** anonymous rate limits and quota
(§3.2); how GDAL/rasterio specifically negotiates these ranges (§12.2); token
lifetime for authenticated callers.

**Not tested at all:** any write path; any authenticated Planetary Computer
account; whole-scene download (deliberately never attempted).

---

## 4. Candidate-observation inventory

### 4.1 The six candidates are confirmed **[VERIFIED]**

Every observation named in the task brief exists in the committed manifests, and
these six are *exactly* the acquisitions with `matches_preferred_orbit = true`:

| Event | Date (UTC) | Window | Orbit | Direction | Polarizations |
|---|---|---|---|---|---|
| `hanna_2020` | 2020-07-03T12:24:25Z | pre_event | 143 | descending | VH, VV |
| `hanna_2020` | 2020-07-15T12:24:25Z | pre_event | 143 | descending | VH, VV |
| `hanna_2020` | 2020-07-27T12:24:26Z | **event** | 143 | descending | VH, VV |
| `march_2025` | 2025-03-03T12:24:35Z | pre_event | 143 | descending | VH, VV |
| `march_2025` | 2025-03-15T12:24:35Z | pre_event | 143 | descending | VH, VV |
| `march_2025` | 2025-03-27T12:24:35Z | **event** | 143 | descending | VH, VV |

All are SENTINEL-1A, all declare VV and VH, all carry both asset hrefs.

**[VERIFIED]** The asset href is **not derivable from the item ID**. Each path
ends in a 4-hex-character processing token (`_B265`, `_9C76`, `_60B6`, `_E039`,
`_2ECD`, `_6C2F`) that appears nowhere in the STAC item ID. A URL constructed by
string-building from the item ID returned **404 BlobNotFound** during this
investigation. The href must be read from the manifest, never reconstructed.

### 4.2 Measured raster characteristics **[VERIFIED — live, all 12 assets]**

Read from actual COG headers, not from collection metadata:

| Event | Date | Pol | Width | Height | Origin E | Origin N | MiB |
|---|---|---|---:|---:|---:|---:|---:|
| hanna_2020 | 2020-07-03 | VV | 28233 | 23618 | 578230 | 2993170 | 1969.0 |
| hanna_2020 | 2020-07-03 | VH | 28233 | 23618 | 578230 | 2993170 | 1947.2 |
| hanna_2020 | 2020-07-15 | VV | 28233 | 23622 | 578240 | 2993220 | 1965.0 |
| hanna_2020 | 2020-07-15 | VH | 28233 | 23622 | 578240 | 2993220 | 1945.7 |
| hanna_2020 | 2020-07-27 | VV | 28236 | 23625 | 578140 | 2993250 | 1966.9 |
| hanna_2020 | 2020-07-27 | VH | 28236 | 23625 | 578140 | 2993250 | 1944.4 |
| march_2025 | 2025-03-03 | VV | 28175 | 23601 | 578320 | 2993080 | 1960.7 |
| march_2025 | 2025-03-03 | VH | 28175 | 23601 | 578320 | 2993080 | 1945.3 |
| march_2025 | 2025-03-15 | VV | 28194 | 23602 | 578210 | 2993070 | 1964.8 |
| march_2025 | 2025-03-15 | VH | 28194 | 23602 | 578210 | 2993070 | 1946.8 |
| march_2025 | 2025-03-27 | VV | 28175 | 23606 | 578300 | 2993140 | 1969.9 |
| march_2025 | 2025-03-27 | VH | 28175 | 23606 | 578300 | 2993140 | 1950.1 |

Identical across all twelve:

- **CRS: EPSG:32614** (WGS 84 / UTM zone 14N). GeoKeys: `GTModelType=1`
  (projected), `GTRasterType=1` (`RasterPixelIsArea`), `ProjectedCRS=32614`,
  `ProjLinearUnits=9001` (metre).
- **Pixel size: exactly 10.0 m × 10.0 m**, north-up, zero rotation
  (`ModelPixelScale = [10.0, 10.0, 0.0]`; a `ModelTiepoint`, not a
  `ModelTransformation`).
- **Data type: float32** (`BitsPerSample=32`, `SampleFormat=3`), 1 band.
- **No-data: `-32768`** — as the `GDAL_NODATA` TIFF tag, as
  `NO_DATA_VALUE=-32768.000000` in `GDALMetadata`, and observed as literal
  `-32768.0` float samples in the decoded tile (§3.4). The collection document's
  `item_assets.vv.raster:bands` also declares `{"nodata": -32768,
  "data_type": "float32", "spatial_resolution": 10}`, so metadata and pixels
  agree.
- **Layout: internally tiled 512×512, Deflate (compression 8) with predictor 3**,
  plus a **6-level overview pyramid** (28236×23625 → 14118×11812 → 7059×5906 →
  3529×2953 → 1764×1476 → 882×738 → 441×369). These are genuine COGs.
- **Units: linear gamma-naught intensity, not decibels.** `GDALMetadata`
  declares `SARPixelContent=intensity`, `Scale=linear`, `Polarization=VV|VH`,
  `Matrix_Type=c2r`, `ProductType=ORTHO`. The collection describes the assets as
  "Terrain-corrected gamma naught values". The decoded tile contained **no
  negative values**, consistent with linear intensity and inconsistent with dB.
- **No scale/offset metadata exists.** No TIFF scale/offset tag and no
  scale/offset entry in `raster:bands`. Values are used as-is; the dB conversion
  in `label-feasibility.md` step 3 is a downstream analytical choice, not a
  metadata-mandated correction.
- Per-scene incidence geometry is recorded in `GDALMetadata`
  (`IncidenceNearAngle` ≈ 30.74°, `IncidenceFarAngle` ≈ 45.97°,
  `LookDirection=Right`, `OrbitDirection=Descending`) and is worth retaining as
  provenance.

**Grid alignment — measured, not assumed [VERIFIED]:**

- Every origin easting and northing is an **exact integer multiple of 10 m**
  (`origin mod 10 == 0.0` for all 24 values).
- Scene-to-scene origin offsets are therefore **whole pixel counts**: relative to
  the Hanna event scene, the other scenes are offset by +9/−8, +10/−3, +18/−17,
  +7/−18 and +16/−11 pixels.
- **VV and VH within a scene are pixel-identical** — same width, height, and
  origin in all six pairs.

**Consequence:** the candidate scenes already share one common 10 m UTM 14N
lattice. Co-registering them requires an **integer pixel-offset alignment only —
no resampling, no reprojection, no interpolation.** This is a materially better
starting position than the label-feasibility review assumed, and it removes a
whole class of resampling-artifact risk from later change detection.

### 4.3 County coverage — the decisive finding **[VERIFIED — measured]**

Using the real Hidalgo County polygon retrieved from TIGERweb (§9.1), projected
to EPSG:32614 and sampled on a 200 m lattice (102,458 in-county sample points;
polygon area by shoelace 4096.9 km² against the TIGER-reported
`AREALAND + AREAWATER` of 4099.5 km², a 0.06% agreement that validates the
projection):

| Event | Date | Orbit | Dir | Window | **County coverage** |
|---|---|---:|---|---|---:|
| hanna_2020 | 2020-06-26 | 41 | desc | pre_event | **100.00%** |
| hanna_2020 | 2020-07-01 | 107 | asc | pre_event | **100.00%** |
| hanna_2020 | 2020-07-03 | **143** | desc | pre_event | **18.12%** |
| hanna_2020 | 2020-07-08 | 41 | desc | pre_event | **100.00%** |
| hanna_2020 | 2020-07-13 | 107 | asc | pre_event | **100.00%** |
| hanna_2020 | 2020-07-15 | **143** | desc | pre_event | **18.11%** |
| hanna_2020 | 2020-07-20 | 41 | desc | pre_event | **100.00%** |
| hanna_2020 | 2020-07-27 | **143** | desc | **event** | **18.21%** |
| march_2025 | 2025-02-24 | 41 | desc | pre_event | **100.00%** |
| march_2025 | 2025-03-03 | **143** | desc | pre_event | **18.16%** |
| march_2025 | 2025-03-08 | 41 | desc | pre_event | **100.00%** |
| march_2025 | 2025-03-13 | 107 | asc | pre_event | **100.00%** |
| march_2025 | 2025-03-15 | **143** | desc | pre_event | **18.24%** |
| march_2025 | 2025-03-20 | 41 | desc | pre_event | **100.00%** |
| march_2025 | 2025-03-25 | 107 | asc | pre_event | **100.00%** |
| march_2025 | 2025-03-27 | **143** | desc | **event** | **18.19%** |

(Orbit-5 ascending scenes, omitted for brevity, cover 9.8% and 46.7–47.0% as two
partial sub-swaths.)

**The relative-orbit-143 scenes cover roughly 18% of Hidalgo County.** The
three-scene intersection — the area where a pre-event baseline *and* the event
observation both exist — is:

- **`hanna_2020`: 18.11% of the county — about 742 km² of 4,098 km²**
- **`march_2025`: 18.16% of the county — about 744 km² of 4,098 km²**

The intersection equals the smallest single footprint in each event, so the
three footprints are essentially nested; nothing is lost to misalignment between
them. The covered area is the **eastern** part of the county: at county
latitudes the orbit-143 swath's western edge runs from about −98.08° (south) to
−97.93° (north), while the county extends west to −98.586°. Independently
confirmed in raster space — the county bounding box maps to pixel columns
**−3703 … 3575** of the Hanna event scene, i.e. the county begins about 3,700
pixels (37 km) west of the raster's own western edge.

By contrast, **relative orbit 41 descending and relative orbit 107 ascending
each cover 100% of the county**, and both recur on the 12-day cycle throughout
the pre-event windows. **Neither has an acquisition inside either configured
observation window.**

This finding is not in `docs/research/label-feasibility.md`, which selected
orbit 143 for same-orbit geometric consistency and did not report a coverage
fraction. It is not a defect in the acquisition slice, which explicitly declined
to make coverage judgments (`docs/data-sources.md`, "Partial footprints").
It is new information, and it bears directly on the gate (§16.5, §13.3).

### 4.4 A window-configuration gap **[VERIFIED — live]**

A bounded metadata-only catalog query across each event's **full configured
rainfall bounds** (not the narrower observation window) returned:

| Event | Datetime (UTC) | Orbit | Dir | In a configured window? |
|---|---|---:|---|---|
| Hanna | 2020-07-25T00:34:28Z | 107 | asc | **No — in neither window** |
| Hanna | 2020-07-27T12:24:26Z | 143 | desc | Yes — `event` |
| Hanna | 2020-07-30T00:42:16/41Z | 5 | asc | No — after `event_end` |
| March | 2025-03-25T00:34:36Z | 107 | asc | Yes — `pre_event` |
| March | 2025-03-27T12:24:35Z | 143 | desc | Yes — `event` |
| March | 2025-03-30T00:42:25/50Z | 5 | asc | No — after `event_end` |

For `hanna_2020`, `pre_event_window` ends 2020-07-23 and `observation_window`
starts 2020-07-26, so the **2020-07-25 orbit-107 acquisition — which covers 100%
of the county — falls into neither window** and appears in no manifest, despite
lying inside the configured `event_start`…`event_end` rainfall bounds.

**This should not be over-read.** Hurricane Hanna made landfall on the afternoon
of 2020-07-25; a 00:34 UTC acquisition precedes landfall by roughly 17 hours. It
is a *near-event baseline*, not an event observation. It is recorded here
because it is a real, checkable discontinuity between the configured rainfall
bounds and the configured observation window — not because it solves §4.3.

**[UNRESOLVED]** Whether the window configuration should change is a labeling
decision, not a raster-preparation decision. **This plan proposes no edit to
`config/events.toml`.** See §13.3.

---

## 5. Proposed execution and data flow **[PROPOSED]**

### 5.1 Why consume the manifests rather than re-query

The brief asks for a concrete reason if the manifests are *not* consumed. There
is none. Re-querying would duplicate `manifest.query_event`, reintroduce network
dependence into a stage that does not need it, and — because Sentinel-1 archive
reprocessing changes item IDs and href processing tokens over time
(`docs/data-sources.md`, "Archive reprocessing") — could silently profile
different scenes than the ones the committed manifest names.

**The committed manifest is the authority for which scenes exist and what their
hrefs are.** The raster slice reads it and does not search.

### 5.2 Stage-by-stage flow

`▲` = network I/O possible. `◆` = raster bytes possible. `●` = pure and
deterministic. Everything unmarked is local file I/O.

```
config/events.toml ──┐
                     ├──► ① load_inputs()                          ● (+2 reads)
data/manifests/<ev>/ ┘        events.load_config(path)  -> LoadedConfig
  acquisitions.json           read_manifest(path)       -> ManifestDocument
                              └─ verifies manifest config_sha256 == config sha
                                     │  list[dict] (acquisition records)
                                     ▼
                        ② select_candidates(manifest, policy)      ●
                              filters on matches_preferred_orbit,
                              window, polarization completeness
                                     │  list[CandidateRef]  (item_id, window,
                                     ▼                       vv/vh unsigned href)
                        ③ AssetClient.head(href) + .read_range()   ▲
                              signs via SAS, HEAD + ranged GET
                              of the COG header only
                                     │  list[RawAssetHeader]  (bytes + size)
                                     ▼
                        ④ parse_profile(header_bytes)              ●
                              -> RasterProfile (crs, transform, size,
                                 dtype, nodata, tiling, overviews, units)
                                     │
                                     ▼
                        ⑤ compare_profiles(list[RasterProfile])    ●
                              -> CompatibilityReport (per-criterion,
                                 integer-pixel offsets, blockers)
                                     │
data/boundaries/     ──►⑥ coverage_metrics(footprints, county)     ●
  hidalgo_county.geojson    -> CoverageReport (per-scene %, pairwise,
                               3-scene intersection)
                                     │
                                     ▼
                        ⑦ build_raster_profile_document(...)       ●
                                     │  dict
                                     ▼
                        ⑧ manifest.serialize + write_atomic
                              ──► data/rasters/<ev>/raster_profile.json
                        ⑨ run_record.build_run_record + write
                              ──► data/rasters/<ev>/last_run.json
```

A separate, **explicitly invoked** command performs windowed pixel reads:

```
data/rasters/<ev>/raster_profile.json ──► ⑩ plan_window(profile, county_bbox)  ●
                                              -> WindowSpec (col/row offsets,
                                                 tile list, predicted bytes)
                                          ⑪ AssetClient.read_window(spec)   ▲ ◆
                                              ──► data/raw/rasters/…  (gitignored)
                                          ⑫ summarise_window(array)        ● ◆
                                              -> valid-pixel statistics only
```

A third, explicitly invoked command runs the viability **precheck** (§9.4). It
reads no pixels, writes no label, and emits upper bounds only:

```
data/boundaries/colonias.geojson ─┐
data/boundaries/hidalgo_county    ├──► ⑬ colonia_cells(colonias, county, 500)  ●
  .geojson                        ┘        -> list[CellRef] (colonia-
                                              intersecting prototype cells)
data/manifests/<ev>/                        │
  acquisitions.json ────────────────► ⑭ viability_report(cells, footprints)  ●
    (STAC footprint polygons)             -> ViabilityReport: UPPER BOUNDS on
                                             cells inside / outside the 3-scene
                                             intersection, per event, 500 m
                                             with 250 m alongside
                                              │
                                              ▼
                                   ⑮ manifest.serialize + write_atomic
                                       ──► data/analysis/colonia_viability.json
```

**Note the input, and what it costs.** ⑭ takes footprints from the **committed
manifest**, not from `raster_profile.json` — the STAC footprint polygon is
§8.3's notion (2). That is exactly why the output is a bound rather than a
measurement: notion (2) is the slanted swath, not the observed valid-pixel mask
(notion 3), and §3.4 measured a footprint-interior tile that was 99.7% nodata.
The consequence is deliberate: the precheck depends on no raster code, no
network access, and no rasterio, so it can run as soon as `coverage.py` exists
(§17 Stage F may therefore run before Stages C–E). When `raster_profile.json` is
present the command cross-checks that the two footprints agree, but it does not
require it — and agreement between them still says nothing about valid pixels.

Stages ①②④⑤⑥⑦⑩⑫⑬⑭ are pure. **Network I/O occurs only in ③ and ⑪. Raster bytes
occur only in ⑪ and ⑫** — stage ③ transfers the first ~128 KiB of each file,
which is header, not imagery. Stages ⑬–⑮ are vector-only and touch no raster
bytes at all.

### 5.3 Function call graph

```
raster_cli.main
 └─ raster_cli.run
     ├─ events.load_config                       (existing)
     ├─ raster_manifest.read_manifest
     ├─ raster_manifest.select_candidates
     ├─ asset_client.SasAssetClient.head / read_range     ← Protocol seam
     ├─ raster_profile.parse_profile
     ├─ raster_profile.compare_profiles
     ├─ coverage.load_county_boundary
     ├─ coverage.coverage_metrics
     ├─ raster_manifest.build_raster_profile_document
     ├─ manifest.serialize / sha256_hex / write_atomic    (existing, reused)
     └─ run_record.build_run_record / write_run_record    (existing, reused)

colonia_cli.main                                          ← separate command
 └─ colonia_cli.run                                          no network, no
     ├─ coverage.load_county_boundary                        raster, no GDAL
     ├─ raster_manifest.read_manifest      (footprints only)
     ├─ colonia.load_colonia_boundaries
     ├─ colonia.colonia_cells                             (grid intersection)
     ├─ colonia.viability_report
     └─ manifest.serialize / write_atomic                 (existing, reused)
```

---

## 6. Proposed file and module responsibilities **[PROPOSED]**

Flat modules, matching the existing package layout. No subpackage, no framework,
no abstraction layer beyond the one Protocol that makes offline testing possible.

| New file | Responsibility | Purity |
|---|---|---|
| `src/colonia_flood/asset_client.py` | `AssetClient` Protocol + `SasAssetClient`. Signs hrefs, `HEAD`, ranged `GET`. **The only new network code.** Mirrors `stac_client.py`. | I/O |
| `src/colonia_flood/raster_profile.py` | Pure: header bytes → `RasterProfile` **via rasterio** (§12.2); `compare_profiles` → `CompatibilityReport`. Mirrors `acquisitions.py`. | pure |
| `src/colonia_flood/coverage.py` | Pure: county polygon + footprints → `CoverageReport` **via shapely + pyproj** (§12.3); `plan_window` → `WindowSpec`. | pure |
| `src/colonia_flood/colonia.py` | Pure: colonia boundaries + county + prototype grid → `list[CellRef]`, `ViabilityReport` — **upper bounds only** (§9.4). Shares `coverage.py`'s projection helpers. | pure |
| `src/colonia_flood/raster_manifest.py` | Manifest reading, candidate selection, document assembly. Mirrors `manifest.py`; **reuses its `serialize`/`sha256_hex`/`write_atomic`**. | pure |
| `src/colonia_flood/raster_cli.py` | Argument parsing, orchestration, exit codes. Second console script; leaves the existing CLI surface untouched. | orchestration |
| `src/colonia_flood/colonia_cli.py` | Third console script for the viability precheck. Separate because it has a different input set and a different cadence from raster profiling. | orchestration |

| New data path | Committed? | Contents |
|---|---|---|
| `data/boundaries/hidalgo_county.geojson` | **yes** (~169 KiB) | TIGERweb polygon, EPSG:4326 (§9.1) |
| `data/boundaries/colonias.geojson` | **yes**, size **[UNRESOLVED]** until the source is selected (§9.4) | colonia boundaries, EPSG:4326 |
| `data/rasters/<event_id>/raster_profile.json` | **yes** | deterministic profile + compatibility + coverage |
| `data/rasters/<event_id>/last_run.json` | **yes** | run provenance |
| `data/analysis/colonia_viability.json` | **yes** | per-event colonia-cell **upper-bound** counts inside/outside the usable footprint (§9.4) |
| `data/analysis/last_run.json` | **yes** | run provenance for the precheck command |
| `data/raw/rasters/<event_id>/…` | **no** — already gitignored via `data/raw/` | cached window reads |

`.gitignore` already excludes `data/raw/` and `data/processed/`. **[PROPOSED]**
No `.gitignore` change is needed; caching goes under `data/raw/rasters/`.

### 6.1 Rejected alternatives, and why

- **A `rasters/` subpackage.** The existing package is flat with six modules;
  five more does not justify a nesting level.
- **A generic "raster source" abstraction.** There is one host and one
  collection. An interface with one implementation is speculative.
- **Extending `cli.py` with subcommands.** That would change the existing
  command's argument surface, which the README documents and tests assert.
- **A new config file.** Everything needed is already in `config/events.toml`
  and the manifests. A `rasters.toml` would create a second place for the AOI to
  drift out of sync.

---

## 7. Inputs and outputs for every stage **[PROPOSED]**

| # | Stage | Input type | Output type | Reads | Writes | Net | Bytes |
|---|---|---|---|---|---|:-:|:-:|
| ① | `load_inputs` | `Path`, `Path` | `LoadedConfig`, `ManifestDocument` | `events.toml`, `acquisitions.json` | — | | |
| ② | `select_candidates` | `ManifestDocument`, `SelectionPolicy` | `list[CandidateRef]` | — | — | | |
| ③ | `AssetClient.head/read_range` | `str` href, byte range | `RawAssetHeader` | — | — | ▲ | header |
| ④ | `parse_profile` | `RawAssetHeader` | `RasterProfile` | — | — | | |
| ⑤ | `compare_profiles` | `list[RasterProfile]` | `CompatibilityReport` | — | — | | |
| ⑥ | `coverage_metrics` | footprints, county polygon | `CoverageReport` | `hidalgo_county.geojson` | — | | |
| ⑦ | `build_raster_profile_document` | all of the above | `dict` | — | — | | |
| ⑧ | `serialize` + `write_atomic` | `dict` | `bytes` | — | `raster_profile.json` | | |
| ⑨ | `build_run_record` + write | metrics, clock | `dict` | — | `last_run.json` | | |
| ⑩ | `plan_window` | `RasterProfile`, bbox | `WindowSpec` | — | — | | |
| ⑪ | `read_window` | `WindowSpec` | array + mask | — | `data/raw/rasters/…` | ▲ | ◆ |
| ⑫ | `summarise_window` | array + mask | `WindowSummary` | — | — | | ◆ |
| ⑬ | `colonia_cells` | colonia + county polygons, cell size | `list[CellRef]` | `colonias.geojson`, `hidalgo_county.geojson` | — | | |
| ⑭ | `viability_report` | `list[CellRef]`, footprints | `ViabilityReport` (bounds) | `acquisitions.json` | — | | |
| ⑮ | `serialize` + `write_atomic` | `dict` | `bytes` | — | `colonia_viability.json` | | |

---

## 8. Raster metadata and compatibility checks **[PROPOSED]**

### 8.1 Recorded per asset

CRS (EPSG code and authority string); affine transform as six coefficients;
bounds in native CRS; width and height; pixel size x/y; data type; nodata value
and its declared-versus-observed agreement; tile dimensions; compression and
predictor; overview level count and shapes; band count; polarization;
`SARPixelContent` and `Scale` (the units evidence); incidence near/far angles;
look direction; orbit direction; acquisition datetime from `GDALMetadata`
cross-checked against the STAC `datetime`.

### 8.2 Three separate verdicts, never merged

The brief requires this separation, and it matters because §4.3 makes them
diverge sharply.

**(a) Metadata compatibility** — mechanical, decidable now, per criterion:

| Criterion | Rule | Status for the six candidates |
|---|---|---|
| Relative orbit | all equal | **PASS** (143) |
| Orbit direction | all equal | **PASS** (descending) |
| Polarizations | VV and VH present in all | **PASS** |
| CRS | all equal | **PASS** (EPSG:32614) |
| Pixel size | all equal | **PASS** (10.0 m) |
| Rotation | zero in all | **PASS** |
| Grid lattice | origins share a common 10 m lattice | **PASS** (all `mod 10 == 0`) |
| Co-registration | offsets are whole pixels | **PASS** (7–18 px) |
| Data type | all equal | **PASS** (float32) |
| Nodata | equal, and declared == observed | **PASS** (−32768) |
| VV/VH pairing | pixel-identical within a scene | **PASS** (all 6) |

**All metadata-compatibility criteria pass.** This is a genuine, verified green
light — and it is *not* a statement about county coverage.

**(b) Spatial coverage** — measured, §4.3. Roughly **18%** of the county for the
three-scene intersection, in both events.

**(c) Later scientific suitability** — **[UNRESOLVED] and explicitly out of
scope.** Whether a two-date pre-event median over an 18% footprint supports
defensible inundation labels is a labeling question. Nothing in this slice
interprets radar change as flooding.

### 8.3 Valid-data footprint versus rectangular extent

**[VERIFIED]** §3.4 measured a county-interior tile that was 99.7% nodata. The
raster's rectangular bounds substantially exceed its valid-data swath.

**[PROPOSED]** Therefore three distinct footprint notions are recorded and never
conflated:

1. **Raster extent** — the rectangle from the transform. Cheap, metadata-only,
   and an *upper bound only*.
2. **STAC footprint polygon** — the slanted swath from `acquisitions.json`.
   The right proxy for planning, used for the §4.3 numbers.
3. **Observed valid-pixel mask** — `value != -32768`, per pixel. The only
   defensible basis for "this cell was observed", and the only one that can
   support the gate's ≥90% valid-observed-area negative rule.

Only (3) may ever feed a negative-class decision. This slice measures (1) and
(2) for every candidate and demonstrates (3) on the bounded window.

---

## 9. County and valid-observation coverage methodology **[PROPOSED]**

### 9.1 Obtaining the county boundary **[VERIFIED — live]**

`docs/data-sources.md` §2 already registers TIGERweb as the source of the
bounding box and records that the polygon itself is not committed. The same
service returns the polygon in one request:

```
https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/
  MapServer/1/query?where=GEOID%3D%2748215%27&outFields=GEOID,NAME,AREALAND,
  AREAWATER&returnGeometry=true&outSR=4326&f=geojson
```

Verified during this investigation: HTTP 200; a **single-ring polygon with 4,132
vertices**; **168,693 bytes** of GeoJSON; `AREALAND = 4,069,433,006 m²`,
`AREAWATER = 30,081,128 m²`. Its derived bounding box is
`[-98.586444, 26.036268, -97.861684, 26.783081]` — **byte-identical to the bbox
already in `config/events.toml`**, which independently confirms the committed
extent's provenance.

**[PROPOSED]** Commit this GeoJSON to `data/boundaries/hidalgo_county.geojson`
(169 KiB is small, and it makes coverage reproducible offline and diffable) and
add a register entry to `docs/data-sources.md` recording the exact query URL,
the retrieval date, and the feature's `AREALAND`/`AREAWATER`. This is the
smallest reproducible option: one documented URL, one committed file, no new
dependency, no download step in any path. US Census TIGER/Line products are
public domain.

**[PROPOSED — Stage A validation clarification, reviewed 2026-09-07]**
Preserve every source polygon coordinate exactly as retrieved. Derive its bbox,
normalize only those four derived values to six decimal places, and compare
against `config/events.toml` at that configuration precision. Raw floating-point
equality is not required. If the normalized values disagree, stop and report;
do not widen the tolerance or change the config. The earlier investigation's
"byte-identical" bbox wording above describes its printed six-decimal extent,
not equality of the full-precision source coordinates.

**No `--refresh-boundary` flag, and no boundary-fetching code.** An earlier
draft proposed one that re-fetched and diffed. It is dropped: authoritative
boundary files are acquired **explicitly, out of band, by a person**, and
committed as a reviewed diff. A refresh flag would add a second network path to
a slice whose one-network-seam property (§1.2) is the reason its tests are
trustworthy — and it would do so for a file that changes on the Census
Bureau's annual cadence, not on ours. Re-fetching is a documented manual step
(the URL above), not a code path. The same rule applies to the colonia
boundaries of §9.4.

### 9.2 Coverage metrics computed

Per event, all in EPSG:32614 so areas are in metres:

- **per-observation county coverage** — footprint ∩ county ÷ county;
- **pairwise overlap** — each pre-event scene ∩ event scene ÷ county;
- **three-scene intersection** — the headline number (§4.3);
- **valid-observation coverage** — the same three, recomputed against the
  observed valid-pixel mask rather than the STAC polygon, on the bounded window.

The polygon-based figures are metadata-only and cheap; the valid-pixel figures
require pixels and are produced by the explicitly invoked windowed-read command.
**Both are recorded, separately labelled, and never averaged together.**

### 9.3 No coverage threshold is invented **[UNRESOLVED]**

The brief forbids inventing an acceptance threshold without support. Searching
the existing documents:

- `docs/research/label-feasibility.md` fixes a **≥90% valid observed area within
  a cell** rule — that is a *per-cell negative-eligibility* rule, not a
  county-level scene-acceptance threshold;
- the gate's "at least 20 colonia-intersecting cells with valid event
  observations" is a *count*, not a fraction;
- `docs/mvp.md` §4 requires cells with missing inputs to be marked missing (F6,
  A5), which again is per-cell.

**No project requirement establishes a minimum usable county fraction for a
scene, and no defensible external source supplies one.** This plan therefore
**reports coverage and does not judge it.** Whether ~18% is sufficient is
recorded as the primary open question (§19.3, §13.3) for an explicit,
documented project decision — made *before* labels are generated, and made on
the gate's own criteria rather than a number invented here.

### 9.4 Colonia footprint-intersection viability **precheck** — elevated **[PROPOSED]**

**This is an upper-bound precheck on a necessary condition. It is not a
measurement of valid observations, and it cannot show that the gate will pass.**
That framing governs everything below and is repeated in the artifact itself.

§9.3 declines to invent a county-fraction threshold, and that remains right. But
the gate *does* supply one hard, countable criterion that bears directly on the
~18% finding: **at least 20 colonia-intersecting cells with valid event
observations** (§16.5). The precheck addresses only the *geometric* half of that
criterion — which colonia cells lie inside a footprint at all — from vector data
alone, without a single pixel or flood label.

**The logic is one-directional.** A cell outside the footprint can never carry a
valid event observation, so the count of colonia cells inside the footprint is a
**strict upper bound** on the gate's ≥20. If that bound is already below 20,
Path A is arithmetically out of reach and the precheck has **falsified** a
necessary condition. If the bound is comfortably above 20, **nothing is
established** — the true count can only be lower, because §3.4 measured a
county-interior tile that was 99.7% nodata, and §8.3 is explicit that the STAC
footprint polygon (notion 2) is not the observed valid-pixel mask (notion 3).
Only notion 3 can support "this cell was observed", and this precheck does not
compute it.

**This is elevated ahead of flood-label implementation** for the falsification
case only. The reasoning is sequencing, not enthusiasm: if the bound comes in
under 20, every subsequent hour spent on label construction, thresholds, and
audits answers a question whose blocking constraint was knowable up front.
Running it late means learning the same fact after paying for it. A passing
precheck buys no confidence at all — it merely fails to stop the work.

**What it computes** (all in EPSG:32614, all vector, no pixels):

1. the colonia geometries, clipped to Hidalgo County;
2. the prototype 500 m grid over the county (§13.3 item 1 — already fixed, not
   renegotiated here), and the set of cells any colonia intersects;
3. for each event, how many of those cells fall **inside the three-scene
   intersection** of §4.3, how many fall partly inside, and how many fall
   outside entirely;
4. the same counts at 250 m, reported **beside** the 500 m figures and never
   substituted for them, so the §13.3 non-transfer rule stays visible;
5. the same counts against the orbit-41 and orbit-107 100%-coverage footprints,
   so the cost of the §19.3 q1 options is quantified rather than argued.

**What it does not do.** It does not classify water, assert inundation, count
valid observations, or declare the gate passed. A colonia cell inside the
footprint is a cell that *could* carry an observation — nothing more. Every
count it emits is named `*_upper_bound` in the artifact and carries an explicit
`is_upper_bound: true` and a note that the observed valid-pixel figure will be
lower by an unmeasured margin. **The true count is produced only by Stage H
against the valid-pixel mask (§8.3 notion 3), and until then the gap between the
two is unknown, not small.**

**[UNRESOLVED] The colonia boundary source is not selected here.** Candidates
that exist for Texas colonias include the Texas Water Development Board / Texas
Secretary of State colonia datasets and the Texas A&M Colonias Program mapping;
this investigation did **not** fetch, verify, or compare them, and none of their
coverage, vintage, licensing, or geometry quality is claimed. Selecting the
source — with a `docs/data-sources.md` register entry, a documented URL, a
committed file, and the same live-verification discipline §9.1 applied to the
county polygon — is the first task of this stage, and it is the point at which
the analysis could stall. Colonia definitions are administrative and contested;
different registries disagree about what counts as a colonia, so the artifact
records **which source, which vintage, and how many features**, and the counts
are only ever interpreted against that named source.

---

## 10. Bounded access and storage strategy **[PROPOSED]**

### 10.1 The measured case for bounded reads **[VERIFIED — live]**

Computed from each asset's real `TileByteCounts`, for the tiles a Hidalgo County
window actually touches:

| | Full download | County window |
|---|---:|---:|
| Per asset | ~1,950 MiB | **~42 MiB** (126 of 2,632 tiles, 4.8%) |
| All 12 candidate assets | **22.93 GiB** | **509 MiB — 2.17%** |

A 45× reduction, measured rather than estimated. Header-only profiling (stage ③)
is smaller still: ~128 KiB per asset, **~1.5 MiB for all twelve**.

### 10.2 Access tiers

| Tier | Transfers | When | Cached? |
|---|---|---|---|
| **T0 — metadata** | ~128 KiB/asset | default; every profile run | no |
| **T1 — county window** | ~42 MiB/asset | explicit flag only | yes, `data/raw/rasters/` |
| **T2 — overview** | ≪1 MiB | quick-look checks | no |
| **T3 — full scene** | ~1.9 GiB | **never in this slice** | n/a |

**[PROPOSED]** T3 is not merely discouraged — the client refuses ranges beyond a
configurable `max_bytes_per_request` and tracks a per-run byte budget, raising
when exceeded. A guard that is only a comment is not a guard (§15.4).

### 10.3 Caching

Cache T1 reads under `data/raw/rasters/<event_id>/<item_id>/<pol>_<window>.tif`,
keyed by item ID, polarization, and window bounds. Already gitignored.
Warranted because a T1 read costs ~42 MiB and a token round-trip, and the label
prototype will re-read the same windows repeatedly while thresholds are tuned.
**Never cached: SAS tokens.** They live in memory for the life of one run.

### 10.4 Token handling

Sign lazily, once per run, and re-sign on **403** (§3.5) with bounded retry —
the measured ~46-minute lifetime (§3.2) is shorter than a long batch could run.
Because anonymous quota is undocumented **[UNRESOLVED]**, request **one token
per run and reuse it across all assets** (it is container-scoped, `sr=c`, so one
token covers every candidate), rather than signing per asset.

**No token, signed URL, credential, or absolute machine path ever reaches a
committed artifact.** Committed artifacts store the unsigned href only —
`strip_url_query` already guarantees this upstream, and the raster document
copies the manifest's href verbatim rather than re-deriving it.

---

## 11. Provenance and artifact design **[PROPOSED]**

### 11.1 Preserving the deterministic/run-specific split

The existing split is load-bearing and is preserved exactly.

**`data/rasters/<event_id>/raster_profile.json` — deterministic.** A pure
function of (config, committed manifest, committed county polygon, and the
immutable content of the remote COG headers). Contains no timestamp, no path, no
token, no library version.

**`data/rasters/<event_id>/last_run.json` — run-specific.** Everything that
varies: retrieval time, library versions, git commit, tool version, byte counts
transferred, token issuance count.

One honest wrinkle: stage ③ reads bytes over the network, so `raster_profile.json`
is deterministic *given a fixed remote archive*, exactly as `acquisitions.json`
is deterministic given a fixed catalog response. Archive reprocessing changes
both. The mitigation is the same one already in use — commit the artifact and
record a hash, so a change appears as a reviewable diff. **[PROPOSED]** Record a
`header_sha256` per asset over the fetched header bytes, making reprocessing
detectable at asset granularity.

### 11.2 Fields recorded

**Document level:** `schema_version`; `event_id`; `config_sha256`;
`source_manifest_sha256` (the SHA-256 of the exact `acquisitions.json` consumed
— the link the brief asks for); `county_boundary_sha256`; `selection_policy`;
`profile_method_version`.

**Per selected observation:** `item_id`; `window`; `datetime_utc`;
`relative_orbit`; `orbit_direction`; `platform`; `polarizations`; per
polarization the unsigned `asset_href`, `header_sha256`, `content_length`, CRS,
transform, bounds, width/height, pixel size, dtype, nodata, tiling, compression,
predictor, overview shapes, `sar_pixel_content`, `scale`, incidence angles;
`footprint`; `county_coverage_fraction`.

**Per event:** the `CompatibilityReport` (per criterion, with integer pixel
offsets); the `CoverageReport` (per-scene, pairwise, three-scene intersection);
counts of selected and rejected candidates with reason codes.

**In `last_run.json` only:** `retrieved_at_utc`; `tool_version`; `git_commit`;
`client_library_versions` (extended to include whatever raster library is
adopted, plus its GDAL and PROJ versions, since those change parsing behaviour);
`bytes_transferred`; `requests_made`; `sas_tokens_issued`.

### 11.3 Reason codes

Reusing the `ReasonCode` `StrEnum` pattern from `acquisitions.py`, with a
separate enum: `NOT_PREFERRED_ORBIT`, `MISSING_POLARIZATION_ASSET`,
`ASSET_UNREACHABLE`, `ASSET_NOT_COG`, `CRS_MISMATCH`, `PIXEL_SIZE_MISMATCH`,
`GRID_MISALIGNED`, `NODATA_MISMATCH`, `ZERO_COUNTY_OVERLAP`. Every rejection is
recorded with its code and a deterministic detail string — never silently
dropped.

---

## 12. Dependency recommendations **[PROPOSED]**

The starting point, version-resolution notes and sequencing proposals below
describe the historical investigation as of 2026-09-06. Current dependencies
are recorded in the Stage B implementation note in §12.4 and the
[Stage C1 results](sentinel-stage-c1-rasterio-spike.md); statements that nothing
was installed are historical, not the current environment.

### 12.1 Verified starting point

`pyproject.toml` declares only `pydantic` and `pystac-client` at runtime
(§1.4). Nothing raster-capable is present.

### 12.2 Rasterio — recommended, from the first production raster code

The brief asks specifically whether Rasterio is appropriate.

**Yes — and it is introduced as soon as production raster metadata or pixel
handling begins, not deferred to the last stage.** The alternative is a
hand-written TIFF parser in the production path, and that is the wrong code to
own (see below). The investigation's standard-library parser was the right tool
for *establishing the facts in §4.2 without installing anything*; it is not the
right tool for shipping.

- **What it owns:** COG metadata parsing, windowed reads (`rasterio.windows`),
  nodata mask handling, overview selection, CRS handling.
- **Why the standard library is insufficient:** it isn't, strictly, for
  *metadata*. This investigation parsed every field in §4.2 from a 128 KiB range
  read using only `struct` and `zlib`, and decoded a full tile including the
  floating-point predictor. But doing that in production means maintaining a
  partial reimplementation of GDAL's TIFF reader — BigTIFF, alternative
  compressors, mask bands, sparse tiles, and predictor variants are all real
  cases this archive could present after reprocessing. **That is the decisive
  argument, and it applies to `parse_profile` exactly as much as to
  `read_window`:** a hand-written parser that is correct today becomes a silent
  liability the first time the archive is reprocessed into a variant it does not
  handle. `parse_profile` therefore opens the fetched header bytes through
  rasterio rather than through `struct`.
- **Runtime or dev:** runtime, from the first module that reads raster metadata.
- **Windows / CPython 3.13:** `pip index versions` resolves **rasterio 1.5.1**
  for this interpreter (CPython 3.13.2, win_amd64), so a compatible wheel
  exists. **[VERIFIED]** — resolution only; **nothing was installed**, as the
  brief requires.
- **GDAL/native concerns:** the rasterio wheel vendors GDAL and PROJ. That is
  precisely the risk the README already warns about ("the wheel situation gets
  worse once `rasterio` and `geopandas` arrive"). Consequences to plan for:
  installed size, a GDAL/PROJ version that must be captured in `last_run.json`
  because it changes parsing behaviour, `GDAL_DISABLE_READDIR_ON_OPEN` and
  `CPL_VSIL_CURL_*` tuning for `/vsicurl` efficiency, and the fact that GDAL's
  own HTTP layer bypasses our `AssetClient` seam — so `block_network` would no
  longer catch an accidental live read (§15.3).
- **Typing:** rasterio ships no `py.typed`, so `mypy --strict` will need an
  `ignore_missing_imports` override for `rasterio.*` in `pyproject.toml`. That
  override is scoped to the third-party import only and does not loosen strict
  checking of our own code. pyproj ships type information; installed Shapely
  2.1.2 requires separate `types-shapely` dev stubs (Stage B verification).

**[PROPOSED] Sequencing:** add rasterio at **Stage C** (§17) — the stage that
implements `raster_profile.py` — because that is where production raster
metadata handling begins. It is no longer deferred to the windowed-read stage.

**Consequence, stated plainly:** the native toolchain arrives earlier, so the
"dependency-free deterministic core" property from an earlier draft of this plan
is given up on purpose. What is bought for it is that no hand-written TIFF
parsing code ever enters the repository. The cost is real — a GDAL/PROJ pair in
the install from Stage C onward, and the §15.3 network-isolation problem binding
at Stage C instead of Stage G.

**[UNRESOLVED at the original investigation; C1 result below]** Whether rasterio can open the **truncated** 128 KiB header
range through `MemoryFile` cleanly, or whether it needs the full file via
`/vsicurl`. COGs place their IFDs and `GDALMetadata` at the front, so a
header-only open is expected to work for metadata, but GDAL may emit warnings or
refuse some operations on a truncated file, and this investigation did not test
it (nothing was installed). **Stage C must resolve this empirically before
committing to the `MemoryFile` route in §15.3**; if it fails, the fallback is
`/vsicurl` with the isolation mitigation (b) of §15.3, and that choice must be
recorded rather than defaulted into.

**[VERIFIED — C1, 2026-09-07]** Rasterio 1.5.1 / GDAL 3.12.4 opened the
131,072-byte prefix of the Hanna event VV asset through `MemoryFile` and read
the structural/profile metadata, overview factors and SAR tags with Python
network access blocked. No configured GDAL HTTP proxy connection was observed;
GDAL received only bytes and a `/vsimem` filename. No larger range or `/vsicurl`
was needed. This supports the AssetClient-bytes → MemoryFile design for C2
metadata, not arbitrary COGs or future pixel reads. See the
[C1 spike](sentinel-stage-c1-rasterio-spike.md) for exact ranges, metadata,
isolation limits and remaining questions. Production parsing is not implemented.

### 12.3 Shapely and pyproj — recommended, from the first coverage code

Same reasoning, applied one stage earlier still: geometry and projection work
begins at `coverage.py`, so the libraries arrive with it.

- **Shapely** (`2.1.2` resolves for this interpreter) owns polygon intersection
  and area. This investigation used 200 m point sampling instead, which is
  accurate enough for §4.3 but is O(vertices × samples) and approximate at
  boundaries. Shapely makes it exact and fast.
- **pyproj** (`3.8.0` resolves) owns EPSG:4326 → EPSG:32614. This investigation
  hand-rolled the Krüger series; it agreed with TIGER's reported county area to
  0.06%, which validates the §4.3 numbers but is **not projection code the
  project should maintain**. A hand-rolled transverse-Mercator series is a
  correctness risk with no upside: it is exactly the kind of code that is subtly
  wrong at the edges and never obviously wrong anywhere.
- **[PROPOSED] Sequencing:** add both at **Stage B** (§17), the stage that
  implements `coverage.py`. They are also the only dependencies the §9.4
  viability precheck needs, so Stage B unblocks the elevated precheck without
  waiting for any raster code.
- Neither pulls GDAL: shapely vendors GEOS, pyproj vendors PROJ, and both have
  pure-wheel installs on win_amd64 for CPython 3.13. Stage B is therefore a
  materially lighter dependency step than Stage C.

**Migration note.** The §4.3 numbers were produced by the sampling/Krüger code.
When shapely and pyproj replace it, the regression test of §15.2 pins the
percentages, so the exact-geometry result must agree with the sampled result to
within the sampling tolerance. **If it does not, the discrepancy is a finding,
not a test to relax** — and the exact result supersedes the number printed in
§4.3, with §4.3 corrected rather than quietly left stale.

### 12.4 NumPy — transitive

Required by rasterio and by shapely's vectorised paths; `2.5.2` resolves for
this interpreter. Arrives with Stage B. Not a separate decision.

**Stage B implementation verification — 2026-09-07.** Installed Shapely 2.1.2,
pyproj 3.8.0 and NumPy 2.3.5 in the CPython 3.13 project environment. Runtime
ranges are `shapely>=2.1.2,<3`, `pyproj>=3.7,<4`, `numpy>=2.1,<2.4`.
pyproj 3.8 requires Python >=3.12, so the range permits the 3.7 line for the
project's supported Python 3.11. Shapely pulls NumPy transitively; its explicit
bound is necessary here because initially resolved NumPy 2.5.3 stubs use Python
3.12 syntax and failed the unchanged Python 3.11 mypy target. The 2.1–2.3 line
supports that target and CPython 3.13 wheels. Installed Shapely has no `py.typed`;
`types-shapely>=2.1,<3` is a dev dependency, resolved to 2.1.0.20260728. No mypy
ignore or strictness relaxation was added. The earlier version-resolution notes
are investigation history, not the final compatibility constraints.

The exact Stage B three-scene fractions are 0.18108366695891062 (Hanna) and
0.18168297400827138 (March), within the 0.0002 absolute-fraction migration
regression budget of the 200 m sampled estimates. These are STAC-footprint
metrics, not valid-pixel coverage. See the Stage B review for full metrics,
tolerance rationale, and limits of the projected polygon calculation.

### 12.5 Not recommended

**GeoPandas** — a DataFrame layer for one 4,132-vertex polygon and six
footprints. **`planetary-computer`** (the official signing helper) — signing is
one `GET` and a string concatenation, already verified working in §3.2; a
dependency for that is not warranted, and the OpenAPI contract is stable enough
to call directly. **`stackstac` / `odc-stac`** — lazy-array machinery for a
slice that reads one window.

---

## 13. Grid-size reconciliation **[PROPOSED]**

### 13.1 The inconsistency, stated precisely **[VERIFIED]**

- `docs/research/label-feasibility.md` specifies **500 m** — in the amended
  target wording, in "Create a 500 m Hidalgo County grid", and in the
  georeferencing criterion. The pass/fail gate's thresholds are calibrated to
  that cell size.
- `docs/mvp.md` §4 keeps cell size **[PROVISIONAL] within 250–500 m**, requires
  a single value chosen before implementation, and requires it to be **justified
  in writing against the effective resolution of each input**. §13 question 5
  makes it dependent on questions 2 (rainfall) and 3 (DEM), both **[OPEN]**.

### 13.2 When the decision actually becomes necessary

**Not in this slice.** Raster preparation records native 10 m geometry and never
aggregates. The decision binds at the first aggregation to cells — step 6 of the
label-construction sequence.

**[VERIFIED]** The Sentinel-1 input does not discriminate between the two
candidates: at 10 m native pixels, a 500 m cell contains 50×50 = 2,500 pixels
and a 250 m cell 25×25 = 625. Both are amply supported, and both divide the 10 m
lattice exactly, so either grid aligns to the raster without resampling. **The
radar input is not the binding constraint** — the DEM and rainfall resolutions
are, and those sources are unselected.

### 13.3 Proposed reconciliation

**[PROPOSED]** Treat them as two decisions, not one:

1. **The prototype grid is 500 m and is not renegotiated.** The gate is fixed,
   its thresholds were set against 500 m, and changing the cell size after
   seeing results is exactly the post-hoc adjustment the gate forbids.
2. **The MVP's 250–500 m choice stays open** until the DEM and rainfall sources
   are selected (`docs/mvp.md` §13 q2–q3), then is justified in writing per §4.
3. **They are reconciled by an explicit written rule, added when the prototype
   concludes:** if the MVP later adopts a cell size other than 500 m, the gate
   results **do not automatically transfer** — positive-row counts and
   colonia-cell counts are cell-size dependent, and the gate must be
   re-evaluated at the adopted size or the discrepancy documented.
4. **Neither document is edited by this slice**, and no flood label is generated
   until this is written down.

**[UNRESOLVED]** §4.3 sharpens this considerably. At ~742 km² of usable
three-scene intersection, a 500 m grid yields roughly **2,970 candidate cells**
per event and a 250 m grid roughly **11,900** — against roughly 16,390 and
65,570 for the whole county. Whether ~2,970 cells in the county's eastern
portion can produce the gate's **≥100 positive rows spread across multiple
areas** and **≥20 colonia-intersecting cells with valid event observations**
depends on where colonias sit relative to that footprint.

**It is the question most likely to decide Path A versus Path B, and that is
precisely why §9.4 elevates a precheck into this slice.** Stage F of §17 bounds
the ≥20-colonia-cell criterion from above using vectors alone — enough to
**falsify** it early, never enough to confirm it, since the observed valid-pixel
count can only be lower. The ≥100-positive-rows half remains genuinely
unanswerable here, because it depends on labels this slice does not produce.

---

## 14. Supporting-data sequencing **[PROPOSED]**

Keeping this slice narrow means most of these are explicitly deferred.

| Dataset | Needed when | In this slice? |
|---|---|---|
| **Full Hidalgo County polygon** | now — exact coverage is impossible without it (§9.1) | **YES** |
| **Colonia boundaries** | **now** — the ≥20-colonia-cell criterion can be *bounded* from vectors alone, before labels exist (§9.4) | **YES** — elevated above its `docs/mvp.md` §13 q4 position |
| **Permanent/seasonal-water mask** | label construction step 4 | no |
| **Land-cover mask** | label construction step 4 | no |
| **DEM/terrain** | MVP features; also binds the grid decision (§13.2) | no |
| **Rainfall** | MVP features; binds the grid decision | no |
| **Sentinel-2 / MODIS / VIIRS** | stratified validation, step 8 | no |

This slice pulls exactly two supporting datasets: the county polygon, because
coverage — the question the slice exists to answer — is undefined without it;
and the colonia boundaries, because the §4.3 finding turned the gate's
≥20-colonia-cell criterion from a downstream check into a live risk that can be
**bounded** now (§9.4). Both are acquired explicitly and committed; neither has
a fetching code path (§9.1). Everything else stays deferred.

---

## 15. Offline and live test strategy **[PROPOSED]**

Preserving the existing philosophy: offline, deterministic, network severed by
default.

### 15.1 Fixtures

Commit **COG header bytes**, not scenes: the first 128 KiB of a small number of
candidate assets, stored under `tests/fixtures/rasters/`. These are real bytes
from real products, they exercise the real parser, and each is 128 KiB. Plus a
few synthetic headers for defect cases that the real archive does not offer
(mismatched CRS, half-pixel-offset origin, absent nodata, BigTIFF).

Commit a **decimated county polygon** for fast geometry tests alongside the real
one used by the pipeline, and a **small synthetic colonia set** (a handful of
polygons with hand-computed cell intersections, including one straddling a cell
boundary and one straddling the footprint edge) for §9.4's tests.

### 15.2 Offline unit tests

- `parse_profile` against committed headers → asserts the exact §4.2 values.
- `compare_profiles` → PASS on the six real candidates; a specific,
  correctly-coded failure for each synthetic defect.
- **Grid-alignment arithmetic**, including the half-pixel-offset case that must
  fail — the check most likely to be wrong and least likely to be noticed.
- `coverage_metrics` against hand-computed values on simple geometry, plus a
  regression test pinning the §4.3 percentages (18.11% / 18.16%) so a silent
  change in the polygon or projection is caught.
- `plan_window` → asserts tile lists and predicted byte counts, including the
  **negative-column case** from §4.3 (the county starting 3,700 px west of the
  raster) which must clip rather than wrap or raise.
- Nodata semantics: `-32768` never becomes 0, never becomes a negative label,
  and always propagates as unknown.
- `colonia_cells` and `viability_report` against the synthetic colonia set with
  hand-computed counts, including the cell-boundary and footprint-edge straddle
  cases; an assertion that a cell counted as "inside the footprint" is never
  reported as an observation or a positive; and an assertion that **every count
  the artifact emits is named and flagged as an upper bound** (§9.4) — the
  framing is enforced by a test, not by prose alone.

### 15.3 Network isolation

The existing autouse `block_network` fixture covers the `AssetClient` seam for
stages ①–⑩ unchanged, because all network use goes through it.

**[PROPOSED]** rasterio now arrives at Stage C rather than Stage G (§12.2), so
this problem binds earlier: `block_network` alone becomes insufficient the
moment GDAL is importable, because `/vsicurl` uses its own HTTP stack.
Mitigations, in preference order: (a) have both `parse_profile` and
`read_window` accept **bytes already fetched through `AssetClient`** and hand
rasterio a `MemoryFile`, keeping one seam and keeping `block_network` effective;
(b) if `/vsicurl` is used directly, set `GDAL_HTTP_*` to a nonexistent proxy in
the offline fixture and assert the failure. **(a) is recommended** — it
preserves the single-seam property that makes the existing suite trustworthy —
but it depends on the truncated-header question in §12.2, which **Stage C must
settle empirically before the route is fixed**. Whichever route is taken, the
offline suite must contain a test that *proves* GDAL cannot reach the network,
not merely a convention that it shouldn't.

shapely and pyproj (Stage B) raise no isolation concern: neither performs
network I/O, and pyproj resolves EPSG:32614 from its bundled PROJ database
without a grid download for this transformation.

### 15.4 Bounded-access tests

Tests that the guard is a guard:

- a request exceeding `max_bytes_per_request` raises rather than transferring;
- a run's cumulative byte budget is enforced and reported;
- `plan_window` never emits a full-raster window for the county bbox — asserted
  against the measured 126-of-2,632-tile figure with a tolerance;
- a fake `AssetClient` records every range requested, and tests assert both the
  count and the total size — the same technique as
  `FakeSearchClient.requested_urls`.

### 15.5 Live tests, explicitly invoked

Extending the existing `live` marker, in `tests/live/test_asset_access_live.py`,
asserting **structural** facts only (never item IDs or byte counts, which
reprocessing changes):

- unsigned access still returns 409 — if it ever returns 200, the access model
  changed and §3 needs revisiting;
- anonymous SAS issuance still returns a token with `sp=rl`;
- signed HEAD returns 200 with `Accept-Ranges: bytes`;
- a signed 1 KiB ranged GET returns 206 with a valid TIFF magic number;
- the four §3.5 failure modes still map to 409/403/404/416.

**[PROPOSED]** Add a second marker, `live_raster`, deselected even under
`-m live`, for the one test that reads an actual tile — so that "run the live
tests" never silently transfers tens of megabytes.

---

## 16. Failure handling and unknown/no-data semantics **[PROPOSED]**

### 16.1 Access failures

Per §3.5: **409** → we failed to sign, a bug, fail loudly. **403** → re-sign
once, then fail. **404** → the archive was reprocessed and the manifest href is
stale; record `ASSET_UNREACHABLE` and **do not** attempt to reconstruct the URL
(§4.1). **416** → a window-planning bug, fail. **429/5xx** → bounded retry with
backoff, then fail.

### 16.2 The cardinal rule

**No failure mode may produce a negative label, and none may be silently
absorbed.** Every unreachable asset, every unparseable header, every masked
pixel, and every out-of-footprint area propagates as **unknown**. This
implements `docs/research/label-feasibility.md` ("Mark ambiguous cells as
`unknown`"; "never convert cloud/no-data or no-report cells to negatives") and
`docs/mvp.md` F6.

### 16.3 Exit codes

Following `cli.py`'s existing convention: `0` success; `1` a candidate was
selected but could not be profiled, or an event's compatibility check failed —
the silent-partial-success failure mode; `2` configuration, manifest, or access
error.

### 16.4 Empty and partial results

An event with no selected candidates is an error, not an empty artifact — the
same reasoning as the existing `EXIT_EMPTY_WINDOW`. Partial coverage is
**recorded, never rejected and never rounded up**.

### 16.5 The label-quality gate is unchanged

Read from `docs/research/label-feasibility.md`, "Pass/fail gate", and reproduced
here **verbatim in substance and unmodified**. Path A requires **all** of:

- at least **three independent storm events** yielding usable labels;
- at least **100 positive grid-event rows** after quality filters, spread across
  multiple areas rather than one contiguous water body;
- at least **20 colonia-intersecting cells** with valid event observations, with
  colonia coverage reported even if no positive is detected;
- a negative rule requiring at least **90% valid observed area** within a cell,
  explicitly excluding permanent water, clouds/no-data, and ambiguous change;
- a stratified manual audit of at least **100 labeled cell-events** achieving at
  least **80% precision** for the positive class, with protocol and
  disagreements retained;
- results **materially stable** under reasonable changes to water-fraction and
  radar-change thresholds;
- **one entire storm** reserved as the final test event, with neighbouring cells
  never randomly split across train and test;
- target and UI wording explicitly saying **"satellite-observed persistent
  inundation"**, not general flood occurrence or safety risk.

If any criterion fails, Path B is taken. **The gate is not weakened after seeing
results, and nothing in this plan adjusts it.** The two configured events cannot
satisfy the three-event criterion; a third and fourth (2018, 2019) remain
required, and `label-feasibility.md` already identifies 2019 as **ascending
orbit 107** — an orbit whose Hidalgo coverage is 100% (§4.3), which is a further
reason the orbit-143 coverage question (§13.3) must be settled deliberately
rather than by default.

---

## 17. Staged implementation order **[PROPOSED]**

### 17.1 How these stages are run

**Implementation stops at the end of every stage.** Each stage below is sized to
be read and understood in one sitting — one or two modules, one coherent idea,
a diff small enough to review line by line — rather than sized to make progress
look fast. The point is that the person reviewing it learns the code, not merely
approves it.

At the end of each stage, before any work on the next one begins:

1. **The diff is inspected in full.** Every file, not a summary of them.
2. **The tests are run and read.** What each test actually asserts, and — more
   usefully — what it would fail to catch.
3. **The call flow is walked end to end.** From the CLI entry point to the
   bytes written, naming each function and what it hands the next one.
4. **The engineering concepts in play are explained and questioned.** The
   stage's "Concepts" line below names them; anything unclear is resolved before
   continuing, and disagreement at this point is cheaper than disagreement three
   stages later.

Only after that does the next stage start. A stage that turns out to be too
large to review comfortably is **split, not rushed** — that is a signal about
the plan, not about the reviewer.

Stages are ordered so that the pure, verifiable core comes first, dependencies
arrive with the code that needs them (§12), and the network arrives late.

### 17.2 The stages

**Stage A — Commit the county boundary. No code.**
Fetch per §9.1, write `data/boundaries/hidalgo_county.geojson`, add the
`docs/data-sources.md` register entry, verify the derived bbox still equals the
config bbox at the configuration's six-decimal precision. Normalize only the
four derived bbox values for validation; never round or simplify the polygon.
*Concepts:* data provenance, committing inputs for reproducibility, why a
derived bbox matching the committed one is evidence rather than coincidence.
*Review:* one file and one register entry.

**Stage B — `coverage.py`, and the first dependencies.**
Add shapely + pyproj + numpy (§12.3). Polygon load, projection to EPSG:32614,
intersection, coverage metrics. Tests against hand-computed geometry and the
§4.3 regression values.
*Reproduces the §4.3 numbers from committed inputs using exact geometry rather
than the investigation's sampling — the first real check that the headline
finding is durable, and the migration check of §12.3 applies here.*
*Concepts:* projected vs geographic CRS and why area demands the former; exact
polygon intersection vs point sampling; pinning a measured result in a
regression test; why a dependency is added at the stage that needs it.
*Review:* one module, one dependency bump, one test file.

**Stage C — `raster_profile.py`, and rasterio.**
Add rasterio (§12.2) and the mypy override. Header bytes → `RasterProfile` via
rasterio; `compare_profiles` → `CompatibilityReport`. Tests against committed
header fixtures and synthetic defects. No network.
**This stage must first settle the §12.2 truncated-header question empirically**
— whether `MemoryFile` over a 128 KiB range opens cleanly — and record the
answer, because §15.3's isolation route depends on it. Settle that before
writing the parser around it.
*Concepts:* what a COG actually is (IFDs, internal tiling, overviews); why
metadata parsing is delegated rather than hand-written; grid-alignment
arithmetic and the half-pixel case; GDAL as a native dependency and what it
drags in.
*Review:* one module, one dependency bump, fixture bytes, one test file. **This
is the largest single conceptual jump in the plan** — if it reads as two stages,
split it into parser and comparator.

**Stage D — `asset_client.py`.**
`AssetClient` Protocol, `SasAssetClient`, SAS signing, byte budget, failure-mode
mapping (§3.5, §16.1). Offline tests use a fake; the `live` test asserts §3.5
structurally.
*Concepts:* the Protocol seam and why the existing suite's trustworthiness rests
on it; HTTP range requests; SAS tokens as short-lived capabilities that are
never persisted; enforcing a budget in code rather than in a comment.
*Review:* one module, one fake, one live test.

**Stage E — `raster_manifest.py` + `raster_cli.py` + console script.**
Manifest reading with `config_sha256` verification, candidate selection,
document assembly, reason codes; then orchestration, exit codes, `--dry-run`.
Generate and commit `raster_profile.json` and `last_run.json` for both events,
and **verify byte-identical regeneration**, as the README does for manifests.
*Concepts:* the deterministic-artifact / run-provenance split and why it is
structural; deterministic serialisation and byte-identical regeneration; reason
codes as a refusal to drop data silently; exit codes as an API.
*Review:* two modules plus two committed artifacts. Split at the module boundary
if the diff is large.

**Stage F — `colonia.py` + `colonia_cli.py`: the viability precheck (§9.4).**
Acquire and register the colonia source explicitly (out of band, per §9.1 — no
fetching code), commit the boundaries, build the 500 m prototype grid, count
colonia-intersecting cells inside and outside the three-scene intersection, and
write `data/analysis/colonia_viability.json`.
**Depends only on Stage B** — no rasterio, no network, no pixels — so it may be
run immediately after Stage B if the answer is wanted before the raster work
lands. That reordering is expected to be the common case, and is why the
dependency was kept this narrow.
**It produces an upper bound on a necessary condition, nothing more.** A result
under 20 falsifies the gate's colonia criterion; a result over 20 establishes
nothing and must not be reported as though the criterion is met. The true count
comes from Stage H against the valid-pixel mask.
*Concepts:* gridding and cell-intersection semantics; **necessary vs sufficient
conditions, and why a bound that only falsifies is still worth computing
first**; upper bounds vs measured results; why counting cells is not labelling
them; the contested definition of a colonia and what that does to a count.
*Review:* one module, one CLI, one committed dataset, one artifact.
**Stop here regardless of appetite** — a falsifying number changes what the
remaining stages are for (§19.3 q1–q2).

**Stage G — README section.**
Commands, outputs, exit codes, and — stated plainly — the §4.3 coverage finding
and the Stage F precheck result **with its upper-bound framing intact**. Also
document that boundary files are refreshed manually, with the URLs.
*Concepts:* documenting a limitation as prominently as a capability; why a bound
reported as a measurement is worse than no bound at all.
*Review:* one document.

**Stage H — `plan_window` and stage ⑪, windowed pixel reads.**
Implement windowed reads through the route settled in Stage C (§15.3), add the
`live_raster` marker and the bounded-access guards (§15.4). Produce valid-pixel
coverage figures to sit beside the polygon figures (§8.3 notion 3) — **this is
the stage that turns Stage F's upper bound into an actual count of colonia cells
with valid event observations**, and the gap between the two is the thing to
look at first.
*Concepts:* window planning and tile arithmetic including the negative-column
clip; nodata as unknown and never as zero; valid-pixel mask vs footprint
polygon; measuring bytes transferred as a test assertion.
*Review:* one module, guards, live tests. Deferrable on its own without
invalidating Stages A–G.

### 17.3 What changed from the earlier sequencing, and the cost

An earlier draft kept Stages A–G dependency-free and deferred rasterio, shapely
and pyproj to the last stage. That is given up deliberately (§12.2, §12.3): the
dependencies now arrive at Stage B and Stage C, with the code that needs them.

**Bought:** no hand-written TIFF parser and no hand-rolled projection code ever
enters the repository, so neither has to be maintained, reviewed, or debugged
when the archive is reprocessed.
**Paid:** the native toolchain is required from Stage B, and the GDAL network-
isolation problem (§15.3) binds at Stage C instead of last. Both are stated in
the acceptance criteria rather than discovered later.

---

## 18. Acceptance criteria for this slice **[PROPOSED]**

Each is a binary check.

**Artifacts**

- [ ] **R1.** `data/boundaries/hidalgo_county.geojson` is committed, registered
      in `docs/data-sources.md`, and its derived bbox equals the
      `config/events.toml` bbox at the configuration's six-decimal precision,
      without changing any source polygon coordinates.
- [ ] **R2.** `data/rasters/<event_id>/raster_profile.json` exists for both
      events and regenerates **byte-identically**.
- [ ] **R3.** `data/rasters/<event_id>/last_run.json` exists and carries every
      run-specific value; `raster_profile.json` carries **none**.
- [ ] **R4.** No committed artifact contains a SAS token, signed URL, credential,
      or absolute machine path. Asserted by a test, not by inspection.

**Content**

- [ ] **R5.** Every selected observation records CRS, transform, bounds, size,
      pixel size, dtype, nodata, tiling, overviews, units evidence, and
      `header_sha256`.
- [ ] **R6.** The compatibility report gives a per-criterion verdict and states
      the integer pixel offset between every pair.
- [ ] **R7.** The coverage report gives per-observation, pairwise, and
      three-scene-intersection county coverage, and **reports no
      accept/reject judgment** (§9.3).
- [ ] **R8.** `source_manifest_sha256` matches the consumed `acquisitions.json`,
      and a mismatched config SHA is a hard error.
- [ ] **R9.** Every rejected candidate carries a reason code. None is dropped.
- [ ] **R9a.** `data/analysis/colonia_viability.json` exists, names its colonia
      source and vintage, and gives colonia-intersecting cell counts inside,
      partly inside, and outside the three-scene intersection at 500 m with
      250 m reported alongside.
- [ ] **R9b.** Every count in that artifact is named `*_upper_bound`, carries
      `is_upper_bound: true`, and is accompanied by a statement that it bounds
      the gate's ≥20 criterion from above and **does not measure valid
      observations** (§9.4). Asserted by a test, not by inspection.
- [ ] **R9c.** The colonia source is registered in `docs/data-sources.md` with
      its URL, retrieval date, vintage, licence, and feature count, and the
      committed boundary file reproduces those figures.
- [ ] **R9d.** No code path in this slice fetches a boundary file. Both
      `hidalgo_county.geojson` and `colonias.geojson` are acquired out of band
      and committed (§9.1); the only network code remains `asset_client.py`.

**Behaviour**

- [ ] **R10.** The default command transfers **less than 5 MiB total** across
      both events, verified by the run record.
- [ ] **R11.** No full-scene download occurs in any code path; the byte guard
      raises when a limit is exceeded.
- [ ] **R12.** All four §3.5 failure modes map to distinct, tested outcomes, and
      none produces a negative or a default value.

**Quality**

- [ ] **R13.** The offline suite passes with sockets severed; `pytest` (default
      addopts) makes no network call — **including a test that proves GDAL's own
      HTTP stack cannot reach the network** (§15.3), not merely a convention.
- [ ] **R14.** `ruff check .` and `mypy` (strict) pass, with third-party stub
      overrides scoped to `rasterio.*` only and no loosening of strict checking
      on first-party code (§12.2).
- [ ] **R14a.** No hand-written TIFF parsing and no hand-rolled projection math
      exists in `src/`. Geometry goes through shapely/pyproj and raster metadata
      through rasterio (§12.2, §12.3).
- [ ] **R14b.** Each stage of §17.2 was stopped at, and its diff, tests, and
      call flow reviewed, before the next began. **Not automatable — it is a
      process criterion, and it is listed here so that skipping it is a visible
      omission rather than a silent one.**
- [ ] **R15.** Live tests pass under `-m live` and are deselected by default;
      the tile-reading test is deselected even then.
- [ ] **R16.** README documents the commands, the outputs, and the §4.3 coverage
      finding.

**Integrity**

- [ ] **R17.** No artifact, code path, or document produced by this slice
      classifies water, asserts inundation, or converts a missing observation
      into a negative — **including the §9.4 precheck**, which bounds the count
      of cells that could carry an observation and never asserts one did.
- [ ] **R18.** The label-quality gate in `docs/research/label-feasibility.md` is
      textually unchanged.

---

## 19. Summary — verified, proposed, unresolved

### 19.1 Verified facts

Historical investigation summary as of 2026-09-06. Its repository/dependency
state is superseded by the Stage B/C1 implementation results in §12 and the
current status at the top of this plan.

**Repository:** the acquisition slice is merged and `docs/data-sources.md` is
committed; `feat/sentinel-raster-preparation` is empty; the package is flat with
one network seam, a deterministic/run-provenance split, and socket-severing
offline tests; runtime dependencies are `pydantic` and `pystac-client` only;
manifests hold 14 and 12 acquisitions with 0 exclusions and **exactly one
event-window acquisition each**.

**Access (live-tested):** unsigned hrefs return **409**; anonymous SAS issuance
returns **200** with `sp=rl`, `sr=c`, ~46-minute lifetime, and the SAS API
declares **no security scheme**; signed HEAD returns 200 with
`Accept-Ranges: bytes`; ranged GETs return 206; **a real 512×512 tile was
fetched and decoded using 138,667 bytes — 0.0067% of a 1.97 GiB file**; failure
modes map cleanly to 409/403/404/416.

**Raster characteristics (all 12 assets):** EPSG:32614; exactly 10.0 m pixels,
north-up, no rotation; float32; nodata **−32768** with metadata and pixels in
agreement; 512×512 Deflate + predictor 3 with a 6-level overview pyramid;
**linear gamma-naught intensity, not dB**; **no scale/offset metadata**; ~1.95
GiB each.

**Grid alignment:** every origin is an exact multiple of 10 m; scene offsets are
whole pixel counts (7–18 px); VV and VH are pixel-identical within every scene.
**Co-registration needs an integer pixel offset only — no resampling.**

**Coverage (measured against the real TIGERweb polygon):** the orbit-143
candidates cover **~18%** of Hidalgo County; the three-scene intersection is
**18.11%** (Hanna) and **18.16%** (March) — about **742–744 km² of 4,098 km²**,
in the county's eastern portion. **Relative orbit 41 descending and relative
orbit 107 ascending each cover 100%, and neither has an event-window
acquisition.** A county-interior tile was **99.7% nodata**, so rectangular
extent is not observation.

**Bounded reads:** 22.93 GiB full versus **509 MiB** windowed (**2.17%**);
header-only profiling is ~1.5 MiB for all twelve assets.

**Other:** asset hrefs contain a processing token not derivable from the item ID
(a reconstructed URL returned 404); the TIGERweb polygon is 4,132 vertices /
169 KiB and its bbox matches `config/events.toml` exactly; the collection is
CC-BY-4.0; rasterio 1.5.1, shapely 2.1.2, pyproj 3.8.0 and numpy 2.5.2 all
resolve for CPython 3.13 on Windows (**nothing was installed**); for
`hanna_2020`, a 100%-coverage orbit-107 acquisition on 2020-07-25 falls in
neither configured window.

### 19.2 Proposed decisions

Consume the committed manifests rather than re-querying; seven flat modules
mirroring the existing layout plus two console scripts; one `AssetClient`
Protocol as the sole new network seam; commit the county polygon; keep the
deterministic/run-provenance split and reuse `manifest.serialize` /
`sha256_hex` / `write_atomic`; record three distinct footprint notions and never
conflate them; four access tiers with an enforced byte budget and no full-scene
path; commit COG header bytes as fixtures; hand rasterio bytes via `MemoryFile`
to preserve the single seam, subject to the truncated-header check; add a
`live_raster` marker; treat 500 m as fixed for the prototype and 250–500 m as a
separate later MVP decision with an explicit non-transfer rule.

Three decisions changed in this revision:

- **Adopt shapely + pyproj at Stage B and rasterio at Stage C** — with the code
  that needs them — rather than deferring all three to the final stage. The
  project maintains no hand-written TIFF parser and no hand-rolled projection
  math; the price is a native toolchain from Stage B and the GDAL isolation
  problem binding earlier (§12.2, §12.3, §17.3).
- **Elevate colonia-source selection and a footprint-intersection viability
  *precheck* into this slice**, ahead of any flood-label implementation, because
  the gate's ≥20-colonia-cell criterion can be **bounded from above** using
  vectors alone. The bound can falsify the criterion early; it can never confirm
  it, and it is not a count of valid observations (§9.4, §17.2 Stage F).
- **Implement in eight learning-sized stages, stopping after each** for a full
  review of diff, tests, call flow, and the engineering concepts involved
  (§17.1). A stage too large to review comfortably gets split.

### 19.3 Unresolved questions

1. **Is ~18% county coverage sufficient for the label prototype?** The primary
   question. No project requirement and no defensible external source supplies a
   minimum usable county fraction (§9.3), so this plan reports and does not
   judge. Options exist — accept the reduced footprint and say so plainly; add
   full-coverage orbit 41/107 pre-event scenes and give up strict same-orbit
   comparison; widen the observation window; or reconsider event selection — and
   **none should be chosen silently.**
2. **Where are the colonias relative to that ~18%?** Still open, but **no longer
   deferred**: §9.4 brings a precheck into this slice and §17.2 Stage F bounds
   the answer from vector data alone, before any label work. Two things remain
   unresolved even after Stage F runs. First, *which colonia boundary source* to
   adopt — candidate registries disagree about what counts as a colonia, and
   none was fetched or verified during this investigation; selecting and
   registering it is Stage F's first task and its likeliest stall point. Second,
   **the size of the gap between the bound and the true count**, which depends
   on valid-pixel coverage inside the footprint and is not known until Stage H.
   §3.4's 99.7%-nodata tile is a warning that the gap may be large.
3. **Anonymous SAS rate limits and quota.** Undocumented in the OpenAPI
   document; the human-readable docs are client-side rendered and unfetchable.
4. **Whether `config/events.toml` windows should change** in light of §4.4. A
   labeling decision; no edit is proposed here.
5. **The 250 m vs 500 m MVP grid size**, which depends on the unselected DEM and
   rainfall sources. The radar input does not discriminate (§13.2).
6. **Whether GDAL's `/vsicurl` or the `MemoryFile` route is adopted**, and the
   network-isolation consequences either way (§15.3). This now binds at **Stage
   C**, not last, and turns on an untested question: whether rasterio opens a
   truncated 128 KiB COG header cleanly (§12.2). Stage C settles it empirically
   before building on it.
7. **Scientific suitability** of a two-date pre-event median over this footprint
   — deliberately out of scope, and untouched by this slice.

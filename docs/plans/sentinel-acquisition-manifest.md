# Implementation plan — Sentinel-1 RTC acquisition manifests

**Status:** Proposed; awaiting review before any code is written
**Plan date:** 2026-09-01
**Slice:** First data-engineering slice, upstream of `docs/mvp.md` §11 / F22 / A1
**Authority for scope:** `docs/research/label-feasibility.md`

## The slice being planned

> Query Sentinel-1 RTC catalog metadata for the Hurricane Hanna 2020 and March
> 2025 Hidalgo County flood events, validate the returned acquisition metadata,
> and write deterministic local acquisition manifests without downloading raster
> assets.

This document is a plan only. No file described here has been created, no
dependency has been installed, and no command in section 8 has been run. The
only actions taken to produce it were read-only inspection of the repository.

### Required behavior this plan must satisfy

The eventual implementation must:

1. Define both historical events through configuration rather than hardcoded
   dates scattered through Python modules.
2. Represent, at minimum: stable event ID; event name; rainfall/event start and
   end; pre-event search window; event-observation search window; Hidalgo County
   area-of-interest reference.
3. Query a STAC-compatible catalog for Sentinel-1 RTC items intersecting Hidalgo
   County and the configured date windows.
4. Retain the metadata needed to compare acquisitions: STAC item or product ID;
   acquisition timestamp; platform; relative orbit; orbit direction;
   polarization availability; geographic footprint or bounding box; VV asset
   reference; VH asset reference; source collection; query/retrieval timestamp.
5. Validate required fields and reject incomplete acquisitions with a clear
   error or documented exclusion reason.
6. Distinguish pre-event observations from event-window observations.
7. Produce deterministic output: stable field names; explicit timestamps and
   timezone; deterministic record ordering; identical output for identical
   catalog responses. Deterministic acquisition content must be separated from
   run-specific metadata — a wall-clock retrieval timestamp must not cause the
   manifest to change when the catalog response and configuration are unchanged.
8. Be rerunnable without creating duplicated manifest records.
9. Avoid storing credentials, signed temporary URLs, or machine-specific
   absolute paths.
10. Support unit tests without requiring live network access.
11. Keep any live-catalog test separate from the normal unit-test suite.
12. Write no raster data during this slice.

---

## 1. Current repository assessment

The repository is effectively **greenfield**. Tracked files are only three:

| Path | Status |
|---|---|
| `.gitignore` | tracked |
| `README.md` | tracked |
| `docs/mvp.md` | tracked |
| `docs/research/label-feasibility.md` | **untracked** |
| `prompt.md` | untracked |

### Language and dependency management

None exists. There is no `pyproject.toml`, `requirements.txt`, `setup.cfg`,
`environment.yml`, or any lock file. There is no virtual environment in the
tree. The interpreter currently on `PATH` is
`C:\msys64\ucrt64\bin\python.exe` (Python 3.12.7) — an MSYS2 interpreter, not a
project-local one. **Nothing about the Python toolchain has been decided in this
repository yet.**

### Source and test structure

None. There is no `src/`, no package directory, no `tests/`, no `scripts/`, no
`config/`, no `data/`, no `.github/`, no `docker-compose.yml`, and no
`Makefile`. There is no `AGENTS.md` and no `CLAUDE.md`.

### Existing conventions we should reuse

Only two, both from `.gitignore`:

- Data artifact paths are already anticipated: `data/raw/` and `data/processed/`
  are ignored (lines 29–30), as are `artifacts/`, `models/`, `mlruns/`. Note
  that **`data/` itself is not ignored** — only those two subdirectories.
- Secrets convention: `.env` and `.env.*` ignored, `.env.example` explicitly
  un-ignored (lines 2–4). This matches `docs/mvp.md` N18.
- Caches for `pytest`, `mypy`, and `ruff` are ignored (lines 11–13). This
  *hints* at an intended toolchain but is not a commitment — no config for any
  of those tools exists.

Documentation conventions are observable and worth matching: both existing docs
are Markdown, hard-wrapped near 80 columns, use
`**[CONFIRMED]` / `[PROVISIONAL]` / `[OPEN]**` tagging, and use tables for
comparative evidence.

### Missing foundations

Each of the following is a decision this slice would be the first to force. None
should be assumed silently:

1. Packaging and dependency manager (pip + `pyproject.toml`, Poetry, uv, PDM —
   undecided).
2. Package name and layout (`src/` layout vs. flat — undecided).
3. Test runner configuration and marker conventions (`docs/mvp.md` N10–N14
   require tests but name no tool).
4. Lint and type-check tooling (`docs/mvp.md` N13 requires both; neither is
   selected).
5. CI (`docs/mvp.md` N12 requires it; no `.github/` exists).
6. Configuration file format and location.
7. Where generated non-raster artifacts live, and whether they are committed.

### Conflicts found

These are real and should be resolved, not papered over.

- **The feasibility report is not where the task and the MVP say it is, and is
  not committed.** The task referenced `docs/label-feasibility.md`; the file is
  at `docs/research/label-feasibility.md` and is untracked. `docs/mvp.md` A1
  requires the decision be *recorded in `docs/`* — an untracked file does not
  satisfy that.
- **`docs/mvp.md` is stale relative to the feasibility report.** `docs/mvp.md`
  §11 "Current state" says the feasibility assessment *"has not been performed"*
  and §13 lists it as blocking question 1. The feasibility report says the
  review is complete and prescribes a satellite-label prototype. Two
  committed/near-committed documents currently disagree about the project's
  state.
- **`docs/mvp.md` §5 does not mention Sentinel-1 or any satellite input.** Its
  input list is rainfall, terrain, colonia boundaries, plus a conditional §5.4
  "Historical flood observations." This slice feeds §5.4, but the MVP document
  does not yet describe a satellite acquisition path at all.
- **Grid cell size:** `docs/mvp.md` §4 leaves it `[PROVISIONAL]` at 250–500 m;
  the feasibility report assumes 500 m throughout. Not blocking for *this* slice
  (no gridding happens here), but it is an unreconciled difference.
- **Branch state:** the current branch is `feat/sentinel-acquisition-manifest`,
  which already anticipates this work; the session's initial git status reported
  `research/assess-flood-labels`, which is stale.

### Do the two documents agree with this slice?

Yes, with one caveat. The feasibility report's "Satellite-label prototype →
Scope" section names exactly Hurricane Hanna 2020 and March 2025 as the first
two events, and its "Label construction" steps 2 and 6 require same-orbit
pre-event and event acquisitions plus `source_product_ids` provenance — this
slice produces precisely the input to those steps. It sits upstream of
`docs/mvp.md` F22/A1 and violates none of §10's exclusions.

The caveat: `docs/mvp.md` will need an amendment to describe this input, and
that amendment is out of scope here.

---

## 2. Proposed architecture

The smallest design that satisfies all twelve behavioral requirements is **six
modules, one config file, and one CLI command**. No classes beyond data models;
no framework; no plugin system.

**Event configuration** — a single TOML file read with stdlib `tomllib`
(Python ≥3.11, no dependency) into Pydantic models. All dates, windows, orbit
preferences, and the AOI reference live here. Python modules contain no event
dates. Validation happens at load time: window start < end, pre-event window
strictly precedes the event window, windows do not overlap, event IDs unique.

**Catalog client** — a narrow `typing.Protocol` with one method, roughly
`search(collection, bbox, datetime_range) -> list[dict]`, returning raw STAC
item dictionaries. One production implementation wraps the STAC client library;
tests substitute a fake that replays committed JSON fixtures. **This boundary is
what makes requirement 10 (unit tests without network) achievable** — nothing
above this line knows HTTP exists. The implementation is responsible only for
pagination, timeouts, and turning transport failures into one domain exception
type.

**Metadata validation and mapping** — pure functions from a raw STAC item dict
to either a validated `Acquisition` model or an `ExcludedItem` with a reason
code. This is where every requirement-4 field is extracted and every
requirement-5 rejection is decided. It is the most test-dense module and it is
entirely pure: dict in, model or exclusion out.

**Acquisition-selection logic** — pure functions that assign each acquisition to
`pre_event` or `event` based on which configured window contains its timestamp,
deduplicate by item ID, flag whether an acquisition matches the event's
preferred relative orbit and direction, and apply the deterministic sort.
Rejecting duplicates and sorting here (not at write time) keeps the writer
trivial.

**Manifest serialization** — assembles the document, serializes with fixed
formatting rules (see section 5), and writes atomically via
temp-file-plus-replace. **It writes only content derived from configuration and
the catalog response.** The wall-clock retrieval timestamp never enters this
document.

**Run record** — a separate writer emitting the provenance envelope (retrieval
timestamp, catalog URL, library versions, config hash, manifest SHA-256). See
section 5 for why this split is the right answer to requirement 7.

**Command-line entry point** — `argparse`, no dependency. Arguments: `--event`
(repeatable, defaults to all configured), `--config`, `--out-dir`, `--dry-run`.
Exit non-zero if any configured event yields zero acquisitions in either window,
because a silently empty manifest is the failure mode most likely to go
unnoticed.

### Data flow

```text
config/events.toml
   └─(tomllib + Pydantic)→ EventConfig[]
        └─ for each event, for each of 2 windows:
             SearchClient.search(collection, bbox, window)
                └─ raw STAC item dicts
                     └─ validate/map ──┬→ Acquisition
                                       └→ ExcludedItem(reason)
                          └─ assign window · dedupe by item_id · sort
                               ├→ manifest writer
                               │     → data/manifests/<event_id>/acquisitions.json
                               │       (deterministic)
                               └→ run writer
                                     → data/manifests/<event_id>/last_run.json
                                       (non-deterministic)
```

The two output paths are the architectural expression of requirement 7:
**everything above the fork is a pure function of (config, catalog response);
everything on the right branch is not.**

---

## 3. Proposed file plan

Nothing below has been created. This is a proposal only.

| Proposed path | New/Modified | Responsibility | Why it belongs there |
|---|---|---|---|
| `pyproject.toml` | New | Package metadata, dependencies, pytest/lint/type-check config | No dependency manifest exists; this slice is the first code and must establish one. Single file keeps tool config co-located. |
| `config/events.toml` | New | The two event definitions — the only place dates and windows appear | Requirement 1 forbids scattered hardcoded dates. Top-level `config/` is discoverable and is not covered by any `.gitignore` rule. |
| `src/colonia_flood/__init__.py` | New | Package marker, `__version__` | `src/` layout prevents tests from importing an uninstalled working copy by accident. Package name is an open decision (section 9). |
| `src/colonia_flood/events.py` | New | Event config Pydantic models + TOML loader + window validation | Config parsing is the one thing every other module depends on; isolating it keeps the dependency graph acyclic. |
| `src/colonia_flood/stac_client.py` | New | `SearchClient` Protocol; live implementation; timeout and pagination handling; `CatalogError` | The single seam between the program and the network. Requirements 10 and 11 depend on this file being the only network-aware module. |
| `src/colonia_flood/acquisitions.py` | New | STAC item → `Acquisition` mapping, field validation, `ExcludedItem` reason codes | Requirements 4 and 5 are one concern: what a valid acquisition is. Pure functions, no I/O. |
| `src/colonia_flood/manifest.py` | New | Window assignment, dedupe, deterministic ordering, document assembly, atomic write | Requirements 6, 7, and 8 are all "what goes in the file and in what order." Keeping ordering next to serialization prevents the two from drifting. |
| `src/colonia_flood/run_record.py` | New | Provenance envelope: retrieval timestamp, versions, hashes | Physically separate from `manifest.py` so it is structurally impossible for a wall-clock value to reach the manifest. |
| `src/colonia_flood/cli.py` | New | Argument parsing, orchestration, exit codes, structured logging | Keeps every other module importable and testable without argv or stdout. |
| `tests/conftest.py` | New | Fixture loading helpers, `FakeSearchClient` | Shared test doubles belong at the test-root level. |
| `tests/fixtures/stac/*.json` | New | Captured STAC search responses, plus hand-built malformed variants | Requirement 10. Committing real captured responses makes the offline tests meaningful rather than self-referential. |
| `tests/test_events.py` | New | Config parsing and window-validation cases | Mirrors `src/` module-for-module. |
| `tests/test_acquisitions.py` | New | Field extraction, missing-polarization, missing-orbit, out-of-extent | — |
| `tests/test_manifest.py` | New | Ordering, dedupe, byte-identical rerun, no-raster assertions | — |
| `tests/test_cli.py` | New | End-to-end through the CLI with the fake client, tmp output dir | — |
| `tests/live/test_catalog_live.py` | New | Optional real-catalog query, marked `live`, deselected by default | Requirement 11 — a separate directory *and* a marker makes accidental inclusion unlikely. |
| `data/manifests/<event_id>/acquisitions.json` | New (generated) | Deterministic acquisition manifest | Not covered by existing ignore rules (only `data/raw/` and `data/processed/` are ignored), so it is committable — which is what makes reruns reviewable in diffs. |
| `data/manifests/<event_id>/last_run.json` | New (generated) | Run provenance | Same directory, adjacent to what it describes. |
| `docs/data-sources.md` | New | Data-source register entry for Sentinel-1 RTC | `docs/mvp.md` §5.5 requires this register for *every* ingested dataset. This slice is the first one that triggers it. |
| `.gitignore` | **Modified — only if** the decision in section 9 is to not commit manifests | Would add `data/manifests/` | Listed for completeness; the recommendation is *not* to modify it. |
| `README.md` | Modified | Add the developer commands from section 8 | `docs/mvp.md` N19 requires a clean checkout to be reproducible from the README. |
| `docs/mvp.md` | Modified (separate change) | Reconcile §11 "Current state" and §5 with the feasibility report | Flagged, **not** part of this slice. |

---

## 4. Event-configuration schema

Proposed `config/events.toml`:

```toml
schema_version = "1"

[aoi.hidalgo_county]
name        = "Hidalgo County, Texas"
fips        = "48215"
source      = "US Census TIGERweb county service"
source_url  = "<TIGERweb county service URL>"
retrieved   = "<YYYY-MM-DD>"
bbox        = [<west>, <south>, <east>, <north>]   # EPSG:4326, decimal degrees

[catalog]
name          = "Microsoft Planetary Computer STAC"
url           = "https://planetarycomputer.microsoft.com/api/stac/v1"
collection    = "sentinel-1-rtc"
vv_asset_key  = "vv"
vh_asset_key  = "vh"

[[events]]
event_id            = "hanna_2020"
event_name          = "Hurricane Hanna, 2020"
aoi                 = "hidalgo_county"
event_start         = "<YYYY-MM-DD>"          # rainfall event start — OPEN
event_end           = "<YYYY-MM-DD>"          # rainfall event end   — OPEN
pre_event_window    = { start = "2020-06-15", end = "2020-07-16" }
observation_window  = { start = "2020-07-26", end = "2020-07-29" }
preferred_relative_orbit  = 143
preferred_orbit_direction = "descending"

[[events]]
event_id            = "march_2025"
event_name          = "March 2025 Hidalgo County flood"
aoi                 = "hidalgo_county"
event_start         = "<YYYY-MM-DD>"          # OPEN
event_end           = "<YYYY-MM-DD>"          # OPEN
pre_event_window    = { start = "2025-02-15", end = "2025-03-16" }
observation_window  = { start = "2025-03-26", end = "2025-03-29" }
preferred_relative_orbit  = 143
preferred_orbit_direction = "descending"
```

### Field types and constraints

| Field | Type | Required | Constraint |
|---|---|---|---|
| `schema_version` | `str` | yes | Must match a supported value; unknown version is a hard error |
| `aoi.<key>.name` | `str` | yes | non-empty |
| `aoi.<key>.fips` | `str` | yes | 5 digits, string not int (leading-zero safety) |
| `aoi.<key>.bbox` | `list[float]` len 4 | yes | `west < east`, `south < north`, all within EPSG:4326 valid range |
| `aoi.<key>.source`, `source_url`, `retrieved` | `str` | yes | Provenance is mandatory per `docs/mvp.md` §5.5 |
| `catalog.url` | `str` | yes | `https` scheme; no query string; no credentials |
| `catalog.collection` | `str` | yes | non-empty |
| `catalog.vv_asset_key`, `vh_asset_key` | `str` | yes | non-empty; configurable so an asset-name mismatch is a config change, not a code change |
| `event_id` | `str` | yes | `^[a-z][a-z0-9_]*$`, unique across events, used as a directory name |
| `event_name` | `str` | yes | non-empty |
| `aoi` (per event) | `str` | yes | must reference a defined `[aoi.<key>]` |
| `event_start` / `event_end` | `date` | yes | `event_start <= event_end` |
| `pre_event_window` | `{start: date, end: date}` | yes | `start < end`; `end <= event_start` |
| `observation_window` | `{start: date, end: date}` | yes | `start < end`; must not overlap `pre_event_window` |
| `preferred_relative_orbit` | `int` | no | 1–175 for Sentinel-1 |
| `preferred_orbit_direction` | `"ascending" \| "descending"` | no | enum |

Dates are calendar dates, converted to half-open UTC instant ranges at query
time (`[start T00:00:00Z, end+1d T00:00:00Z)`). Using dates in config and doing
the instant conversion in one place avoids per-field timezone ambiguity; the
manifest records the resolved instants explicitly.

### Confirmed by the feasibility report

- Both event names and that these two are the first-prototype scope
  ("Satellite-label prototype → Scope").
- Hanna event acquisition `2020-07-27 12:24 UTC`, descending, relative orbit
  143; comparable pre-event `2020-07-15`, same orbit.
- March 2025 event acquisition `2025-03-27 12:24 UTC`, descending, relative
  orbit 143; comparable pre-event `2025-03-15`, same orbit.
- AOI is Hidalgo County, FIPS `48215`, geometry from Census TIGERweb
  ("Reproducibility notes").
- Collection family is Sentinel-1 RTC with VV and VH polarization; the assets
  are 10 m float-valued Cloud-Optimized GeoTIFFs. Microsoft Planetary Computer
  is the referenced host.

### Requires a project decision

Values above are left as placeholders deliberately. These have **not** been
invented:

- **`event_start` / `event_end` for both events.** The feasibility report gives
  *satellite acquisition* dates, never rainfall event bounds. It references the
  NWS Brownsville event pages, which is the right source, but no value in the
  repository supplies these. **Do not derive them from the acquisition dates** —
  that would silently redefine the field.
- **The `bbox` numbers.** The report records that TIGERweb FIPS `48215` was used
  but does not state the extent. These must be derived from that service and
  recorded with `source_url` and `retrieved`, not guessed.
- **Pre-event window length.** The ~30-day values above are a *proposed
  default*, chosen because the report's label-construction step 3 requires a
  "multi-date pre-event median, not a single image," and ~30 days yields roughly
  2–3 same-orbit passes at Sentinel-1's repeat interval. The report confirms
  only one representative pre-event date per event.
- **Observation window width.** Proposed ±1 day around the confirmed
  acquisition; the report does not specify a window.
- **Whether preferred orbit is a filter or an annotation.** Recommendation:
  **annotation only.** Query without an orbit filter, record what exists, and
  flag matches. Filtering at query time hides whether the assumed orbit is
  actually the only coverage.
- **`vv` / `vh` asset key names.** Expected for the Planetary Computer
  `sentinel-1-rtc` collection but not stated in the report — confirm against one
  live item before fixing the mapping, and keep them configurable as above.

---

## 5. Acquisition-manifest schema

**Recommended format: a single pretty-printed JSON document per event**, at
`data/manifests/<event_id>/acquisitions.json`.

### Why JSON rather than JSON Lines

The record count is small (a handful to a few dozen per event); the document
needs a header block (event, resolved query windows, schema version) that JSONL
cannot express without a sentinel record; and requirement 8 — rerunnable without
duplicate records — is satisfied trivially by whole-file replacement, whereas
JSONL's natural append idiom is exactly the operation that creates duplicates.

JSONL would be the better choice if this later grows to thousands of rows per
event or needs streaming ingestion; it does not in this slice.

Neither Parquet nor CSV is appropriate: Parquet is a binary format whose byte
output is not stable across library versions, defeating requirement 7, and CSV
cannot represent the polarization list or the footprint.

### Serialization rules

These are what actually deliver determinism:

- UTF-8, `indent=2`, `sort_keys=True`, `ensure_ascii=False`
- `\n` line endings, single trailing newline
- All floats rounded to 6 decimal places before serialization
- All timestamps RFC 3339 with an explicit `Z`
- Written atomically to a temp file, then `os.replace`d

### Document structure

```jsonc
{
  "schema_version": "1",
  "event": {
    "event_id": "...", "event_name": "...",
    "event_start": "...", "event_end": "..."
  },
  "query": {
    "catalog_url": "...", "collection": "...",
    "aoi": { "name": "...", "fips": "...", "bbox": [ ... ] },
    "windows": {
      "pre_event": { "start": "...Z", "end": "...Z" },
      "event":     { "start": "...Z", "end": "...Z" }
    }
  },
  "config_sha256": "...",
  "acquisitions": [ ... ],
  "excluded": [ ... ]
}
```

### Stable source metadata

Copied from the STAC item, never computed:

| Field | Type | Notes |
|---|---|---|
| `item_id` | `str` | STAC item ID; the dedupe key |
| `collection` | `str` | source collection |
| `datetime_utc` | `str` | RFC 3339, `Z` suffix |
| `platform` | `str` | e.g. `sentinel-1a` |
| `relative_orbit` | `int` | from `sat:relative_orbit` |
| `orbit_direction` | `str` | `ascending` \| `descending`, from `sat:orbit_state` |
| `polarizations` | `list[str]` | from `sar:polarizations`, sorted |
| `bbox` | `list[float]` len 4 | rounded to 6 dp |
| `footprint` | GeoJSON geometry | coordinates rounded to 6 dp; retained because the report flags "partial footprints" as a real risk |
| `vv_asset_href` | `str` | unsigned base URL |
| `vh_asset_href` | `str` | unsigned base URL |

### Project-derived fields

Computed by our code from config + item:

| Field | Type | Notes |
|---|---|---|
| `event_id` | `str` | |
| `window` | `str` | `pre_event` \| `event` — requirement 6 |
| `matches_preferred_orbit` | `bool` | relative orbit **and** direction both match |
| `intersects_aoi_bbox` | `bool` | independent re-check of the catalog's own filtering |

### Provenance fields

**Not in the manifest.** In `data/manifests/<event_id>/last_run.json`:

| Field | Type |
|---|---|
| `retrieved_at_utc` | `str` (RFC 3339 `Z`) |
| `catalog_url` | `str` |
| `tool_version` | `str` |
| `git_commit` | `str` \| `null` |
| `client_library_versions` | `object` |
| `config_sha256` | `str` |
| `manifest_sha256` | `str` |
| `acquisition_count` | `int` |
| `excluded_count` | `int` |

### Exclusion and validation information

In the manifest's `excluded` array, sorted by `item_id`:

| Field | Type | Notes |
|---|---|---|
| `item_id` | `str` | |
| `reason_code` | enum | `missing_datetime`, `missing_platform`, `missing_relative_orbit`, `missing_orbit_direction`, `missing_vv_asset`, `missing_vh_asset`, `missing_footprint`, `outside_aoi`, `outside_all_windows`, `duplicate_item_id` |
| `detail` | `str` | human-readable, deterministic — no timestamps, no paths |

Exclusions are recorded rather than raised, per requirement 5's "clear error
**or** documented exclusion reason": a per-item defect excludes that item with a
reason; a malformed *response* or a config defect raises. Exclusions living
inside the deterministic manifest is deliberate — a reviewer diffing two runs
should see coverage changes and rejection changes side by side.

### Ordering

`acquisitions` sorted by `(window, datetime_utc, item_id)`, with `window` sorted
`pre_event` before `event`. The triple is unique, so the sort is total and
stable regardless of the catalog's response order.

### On requirement 7 specifically

The retrieval timestamp belongs in the **run record**, not in structured logs
alone. Logs are the right place for the human narrative of a run, but they are
ephemeral and unstructured; the manifest–run-record pair gives a durable
provenance artifact linked to exactly the bytes it describes via
`manifest_sha256`.

Commit the manifest. The run record can be committed or ignored — committing it
is more useful and costs nothing, and its churn is confined to a file nobody
diffs for content.

---

## 6. Dependency decision

The repository has **zero existing dependencies**, so there is no incumbent to
reuse. `README.md` names an intended stack (GeoPandas, rasterio, scikit-learn,
XGBoost, Pydantic, FastAPI) but none of it is installed or declared, and this
slice needs none of the geospatial or ML pieces.

| Option | Cost | Testability | Risk |
|---|---|---|---|
| stdlib `urllib.request` | Zero deps. ~60 lines: POST `/search`, JSON encode/decode, `next` link pagination, timeout, retry | Easy to fake at our own seam | We own STAC pagination and error semantics forever; `next`-link handling is the classic silent-truncation bug |
| `requests` or `httpx` | One small dep; ~40 lines of the same logic | Same | Same pagination risk, slightly less boilerplate |
| `pystac-client` | Pulls `pystac` + `requests`; a real geospatial dependency | Fine — we mock at *our* Protocol, not at theirs | Larger surface; version churn in the STAC ecosystem |

**Recommendation: `pystac-client`**, behind the `SearchClient` Protocol
described in section 2.

The deciding factor is that the one piece of nontrivial logic in this slice is
STAC search pagination, and it fails *quietly* when hand-rolled — a truncated
result set produces a manifest that looks fine and is wrong. That is precisely
the failure this slice exists to prevent. `pystac-client` also handles
`datetime` interval formatting and `bbox` encoding correctly, which are the
second and third most common sources of a subtly wrong query.

The Protocol boundary neutralizes the usual objection: because unit tests
substitute a fake and never construct a `pystac_client.Client`, the dependency
is exercised only by the optional live test. If it later becomes a maintenance
burden, replacing it means rewriting one file with no test churn.

### Proposed dependency set

Declared, **not installed**:

- Runtime: `pystac-client`, `pydantic` (v2)
- Dev: `pytest`
- Deliberately not added: `PyYAML` (stdlib `tomllib` covers config), `requests`
  (transitive), `geopandas`/`shapely` (bbox intersection is four comparisons; a
  full geometry library is unjustified until the raster slice), `httpx`

`pydantic` is chosen over `dataclasses` because `README.md` and `docs/mvp.md`
F10 already commit the project to Pydantic for schema declaration, and this
slice's core job is validation with actionable error messages. If the project
would rather keep the data layer dependency-free, stdlib `dataclasses` plus
hand-written validators is a defensible substitute at the cost of roughly 100
extra lines.

---

## 7. Testing strategy

### What is mocked

Exactly one thing — the `SearchClient` Protocol. `FakeSearchClient` is
constructed from committed JSON fixtures and returns them verbatim. Nothing else
is patched; no `unittest.mock.patch` of HTTP libraries, no `responses`/`respx`
layer. Everything above the client seam is pure and needs no mocking at all.

### Fixtures

Capture one real STAC search response per event per window, once, and commit
them under `tests/fixtures/stac/`. Then hand-derive the defect variants (missing
fields, out-of-extent, duplicates) by editing copies. Real captures keep the
happy-path tests honest; hand-built variants keep the failure tests precise.

### Unit-test cases

| # | Test | Asserts |
|---|---|---|
| 1 | Valid config parses | Both events load; types correct; resolved UTC instants match expected half-open ranges |
| 2 | Reversed window | `start > end` in either window raises a validation error naming the field |
| 3 | Overlapping windows | Pre-event window overlapping observation window raises |
| 4 | Pre-event after event | `pre_event.end > event_start` raises |
| 5 | Duplicate `event_id` | Raises at load, before any query |
| 6 | Invalid bbox | `west >= east` or out-of-range latitude raises |
| 7 | Missing VV asset | Item excluded with `missing_vv_asset`; absent from `acquisitions` |
| 8 | Missing VH asset | Item excluded with `missing_vh_asset` |
| 9 | `sar:polarizations` lacks VV or VH | Excluded even when an asset key happens to exist — asset presence and declared polarization must agree |
| 10 | Missing `sat:relative_orbit` | Excluded with `missing_relative_orbit` |
| 11 | Missing `sat:orbit_state` | Excluded with `missing_orbit_direction` |
| 12 | Item outside Hidalgo bbox | Excluded with `outside_aoi`, even though the catalog returned it |
| 13 | Item touching bbox edge | Included — edge contact is intersection; pins the boundary convention |
| 14 | Duplicate item IDs in one response | One `acquisitions` entry; one `duplicate_item_id` exclusion |
| 15 | Same item in both windows | Config-overlap guard (test 3) makes this unreachable; assert it raises if reached |
| 16 | Deterministic ordering | Shuffled fixture order produces byte-identical output to sorted order |
| 17 | Byte-identical rerun | Run twice against the same fixture into the same directory; `acquisitions.json` bytes are identical and record count is unchanged |
| 18 | Manifest excludes wall-clock data | Freeze/inject two different clock values; manifest bytes identical, `last_run.json` bytes differ |
| 19 | Catalog timeout | `SearchClient` raising a timeout surfaces as `CatalogError`; **no manifest file is written or truncated** |
| 20 | Malformed response | Non-JSON / missing `features` raises `CatalogError`, not `KeyError` |
| 21 | Empty result set | Manifest is written with `acquisitions: []`; CLI exits non-zero |
| 22 | **No raster downloads** | `FakeSearchClient` records every URL requested and asserts none is an asset href; after a full CLI run, the output tree contains only `.json` files and total bytes are under a small bound (e.g. 1 MB) |
| 23 | No signed URLs or secrets | Serialized manifest contains no `sig=`, `st=`, `se=`, or other SAS query parameters, and no `Authorization`-like strings |
| 24 | No machine-specific paths | Manifest contains no absolute path, no drive letter, no username — important on Windows |
| 25 | Atomic write | Simulated failure mid-write leaves the prior manifest intact and no temp file behind |
| 26 | CLI end-to-end | With the fake client and a `tmp_path` output dir, both event directories are produced with expected structure |

### Optional live integration test

At `tests/live/`, marked `live`, deselected by default via
`addopts = "-m 'not live'"`.

It queries the real catalog for the Hanna 2020 observation window and asserts
only structural facts — the response is a valid ItemCollection, at least one
item is returned, and every field this slice depends on
(`sat:relative_orbit`, `sat:orbit_state`, `sar:polarizations`, the `vv`/`vh`
asset keys) is present with the expected type.

It should **not** assert specific item IDs or counts, which change as the
archive is reprocessed. Its purpose is narrow and important: catching the day
the catalog's property names or asset keys change, which no fixture-based test
can ever detect. It must not write to `data/`.

### One honesty note on determinism

Requirement 7 asks for identical output for identical catalog responses, and the
design delivers that. It does **not** guarantee identical output across time,
because Sentinel-1 archives are reprocessed and item IDs and metadata can
change. That is why `manifest_sha256` and the committed manifest matter — a diff
makes such a change visible instead of invisible.

---

## 8. Expected developer commands

These presuppose the files in section 3 exist. None of them has been run.
PowerShell form, matching the platform.

```powershell
# 1. Dependency installation (first-time setup)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

# 2. Unit tests — offline, live tests deselected by pyproject addopts
pytest

# 3a. Generate manifests (uses the real catalog; metadata only)
python -m colonia_flood.cli --config config/events.toml --out-dir data/manifests

# 3b. Single event, no writes
python -m colonia_flood.cli --event hanna_2020 --dry-run

# 3c. Optional live catalog test, explicitly opted into
pytest -m live

# 4. Inspect the generated manifest
Get-Content data\manifests\hanna_2020\acquisitions.json | ConvertFrom-Json |
    Select-Object -ExpandProperty acquisitions |
    Select-Object window, datetime_utc, platform, relative_orbit, orbit_direction |
    Format-Table

# 4b. Confirm the rerun is byte-identical
(Get-FileHash data\manifests\hanna_2020\acquisitions.json).Hash
python -m colonia_flood.cli --event hanna_2020
(Get-FileHash data\manifests\hanna_2020\acquisitions.json).Hash

# 4c. Confirm no raster was written
Get-ChildItem -Recurse data\manifests | Where-Object { $_.Extension -notin '.json' }
```

Note on step 1: the interpreter currently on `PATH` is the MSYS2 build at
`C:\msys64\ucrt64\bin\python.exe`. A project-local `.venv` is worth insisting on
here, before the later slices bring in `rasterio` and `geopandas`, where the
MSYS2/wheel mix becomes an actual problem.

Lint and type-check commands are intentionally omitted: `docs/mvp.md` N13
requires both, but no tool has been chosen (section 9).

---

## 9. Risks and open decisions

### Blocking — implementation should not start until these are answered

1. **Rainfall `event_start` / `event_end` for both events.** Required by
   requirement 2, and no value exists in the repository. Must be sourced from
   the NWS Brownsville event pages the feasibility report cites, recorded with
   source and retrieval date. *Not defaultable* — inferring it from the
   satellite acquisition date would quietly redefine the field.
2. **The Hidalgo County bounding box.** Required to issue any query. The report
   records TIGERweb FIPS `48215` as the source but not the extent. Must be
   derived from that service, not guessed. Mechanical to resolve, but it gates
   every query.
3. **Catalog endpoint and access model.** The Planetary Computer
   `sentinel-1-rtc` collection is documented as requiring an account or
   subscription key for *data* access; item **search** is generally anonymous.
   This slice only searches, so it should work unauthenticated — **but that must
   be verified against the live API before committing to this endpoint**,
   because if search also requires a key, requirement 9 (no stored credentials)
   and requirement 10 (offline tests) both need a different answer, and ASF or
   AWS Open Data become alternatives.
4. **`docs/research/label-feasibility.md` is untracked, and `docs/mvp.md` §11
   contradicts it.** `docs/mvp.md` A1 requires a committed decision record in
   `docs/`. Building on an uncommitted authority is the kind of thing that is
   invisible until someone else clones the repo. Commit it, decide its final
   path, and reconcile §11 "Current state" and §13 question 1.

### Resolvable with a documented default — these should not block

| Decision | Proposed default | Rationale |
|---|---|---|
| Pre-event window length | ~30 days ending before `event_start` | Yields 2–3 same-orbit passes, satisfying the report's multi-date-median requirement |
| Observation window width | ±1 day around the confirmed acquisition | Confirmed acquisitions fall inside; widens only if coverage proves thin |
| Preferred orbit: filter or annotation | **Annotation** | Recording what exists is more informative than filtering to what we assumed |
| Manifest format | JSON, one file per event | Section 5 |
| Commit generated manifests? | **Yes** — `data/manifests/` is not currently ignored | Makes rerun determinism reviewable in diffs; artifacts are small text |
| Config format | TOML via stdlib `tomllib` | Zero dependency |
| Package name | `colonia_flood` | No convention exists; any consistent choice works, but it should be made once |
| Layout | `src/` | Prevents accidental imports of an uninstalled tree |
| Timestamps | RFC 3339, always `Z` | Requirement 7 |
| Float precision | 6 decimal places | ~0.1 m at this latitude; far below any resolution in play |
| Lint / type-check tooling | `ruff` + `mypy` | The cache entries in `.gitignore` lines 12–13 suggest this was already the intent — **but it is an inference, not a recorded decision.** Worth confirming and writing down. |

### Technical risks worth naming — none blocking

- **Archive reprocessing** can change item IDs and metadata over time.
  Determinism holds per-response; cross-time stability does not, and no design
  can make it. Committed manifests plus `manifest_sha256` make such a change
  visible rather than silent.
- **Asset key names** (`vv`/`vh`) are expected but unconfirmed. Keeping them in
  config means a mismatch is a one-line config fix; the live test is what
  catches it.
- **Partial footprints.** The feasibility report explicitly flags partial county
  coverage as a complication. This slice records the footprint but makes no
  coverage judgment; deciding what fraction of the county an acquisition must
  cover to be usable is a labeling decision that belongs to the next slice, not
  this one.
- **Windows path handling.** Requirement 9 forbids machine-specific absolute
  paths; drive letters and user directories are the likely leak. Test 24 exists
  specifically for this.

---

## 10. Scope confirmation

### What the proposed implementation will change

- Add a dependency manifest (`pyproject.toml`) declaring `pystac-client`,
  `pydantic`, and `pytest` — establishing Python packaging for this repository
  for the first time.
- Add one configuration file, `config/events.toml`, defining `hanna_2020` and
  `march_2025`.
- Add a Python package at `src/colonia_flood/` with six modules: event config,
  STAC client seam, acquisition validation, manifest assembly and serialization,
  run record, CLI.
- Add a test suite at `tests/` with committed STAC fixtures and a
  `FakeSearchClient`, plus a separately marked, default-deselected live test at
  `tests/live/`.
- Generate two JSON acquisition manifests and two JSON run records under
  `data/manifests/`.
- Add `docs/data-sources.md` recording the Sentinel-1 RTC source per
  `docs/mvp.md` §5.5.
- Update `README.md` with the section 8 commands.

### What it will not change

- No raster asset is downloaded, and no raster data is written anywhere.
- No frontend, no FastAPI service, no database, no PostGIS, no schema, no
  migration.
- No Docker or Docker Compose file; no GitHub Actions workflow.
- No Airflow, dbt, MLflow, model training, evaluation, gridding, or raster
  processing.
- No change to `docs/mvp.md`. The §11/§5 reconciliation and the §4 cell-size
  question are flagged in sections 1 and 9 as separate work.
- No modification to `.gitignore`, under the recommended decision to commit
  manifests. If that decision goes the other way, `.gitignore` gains a single
  `data/manifests/` line and nothing else.
- No credentials, no signed URLs, no `.env` requirement, no machine-specific
  paths in any committed artifact.
- No change to the Path A / Path B decision. This slice produces the input to
  the feasibility report's prototype; it does not perform, prejudge, or record
  that decision.

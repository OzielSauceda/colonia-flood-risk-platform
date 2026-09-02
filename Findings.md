# Findings log

A running record of what each work session found, verified, and left open.

**How to read this file.** Each entry is written for someone with no prior
context on the session that produced it. It separates what was **verified**
against a real source from what was **assumed or defaulted**, and it records
deviations and open questions explicitly. Newest entries go at the bottom.

---

## 2026-09-02 — Sentinel-1 RTC acquisition-manifest slice

**Task.** Implement the first data-engineering slice: query Sentinel-1 RTC
catalog *metadata* for two Hidalgo County flood events, validate it, and write
deterministic local manifests. No raster downloads, no CI, no commit.

**Project context for an outside reader.** This repository is building a
flood-risk prototype for Hidalgo County, Texas. A prior feasibility review
(`docs/research/label-feasibility.md`) rejected NWS Local Storm Reports as a
machine-learning training target and authorized one time-boxed Sentinel-1
satellite-label prototype behind a fixed pass/fail gate. **That gate has not
been evaluated.** Both the supervised path (Path A) and the unsupervised
susceptibility-index fallback (Path B) remain open. This slice sits *upstream*
of that prototype — it only enumerates which radar observations exist. It does
not classify water and does not prejudge the path decision.

### Blocking unknowns that were resolved

The implementation plan listed four blockers. All four were resolved from real
sources rather than guessed.

| Unknown | Resolved value | How it was established |
|---|---|---|
| Hidalgo County bounding box | `[-98.586444, 26.036268, -97.861684, 26.783081]` (W, S, E, N; EPSG:4326) | Live query to US Census TIGERweb `State_County` MapServer layer 1 for `GEOID = 48215`; min/max taken over the returned polygon's 4,132 vertices |
| Hurricane Hanna rainfall event bounds | 2020-07-24 → 2020-07-29 | NWS Brownsville event page states its rainfall accumulation period as "7 AM July 24 – 7 AM July 29" |
| March 2025 flood event bounds | 2025-03-26 → 2025-03-28 | NWS Brownsville event summary titled "March 26-28, 2025 Historic Flooding/QLCS Event" |
| Catalog access model | Anonymous search is sufficient | Live `POST /search` against Microsoft Planetary Computer returned items with no credentials |

**Important nuance on the event bounds.** These are *rainfall* event windows,
deliberately **not** derived from the satellite acquisition dates. Inferring one
from the other would silently redefine what the field means. They come from the
NWS event summaries, which is also the source the feasibility review cites.

### Facts verified against the live catalog

- **Anonymous item search works.** Planetary Computer documents that *data*
  access may need an account or subscription key, but **search does not**. This
  matters: had search required a key, the "no stored credentials" and "offline
  unit tests" requirements would both have needed different answers.
- **Asset keys are `vv` and `vh`** — previously expected but unconfirmed.
- **Asset hrefs come back unsigned**, plain blob URLs with no SAS token.
- **`platform` is `SENTINEL-1A`** (uppercase). The plan had guessed
  `sentinel-1a`; the real value differs.
- The four properties this slice depends on are all present:
  `datetime`, `platform`, `sat:relative_orbit`, `sat:orbit_state`,
  `sar:polarizations`.

### Acquisition results

| Event | Total | Pre-event | Event window | Excluded |
|---|---|---|---|---|
| `hanna_2020` | 14 | 13 | 1 | 0 |
| `march_2025` | 12 | 11 | 1 | 0 |

**These independently reproduce the feasibility review's findings.** That review
named one event acquisition and one comparable pre-event scene per event; the
pipeline found exactly those:

- Hanna: event `2020-07-27T12:24Z`, pre-event `2020-07-15` — both relative
  orbit 143, descending.
- March 2025: event `2025-03-27T12:24Z`, pre-event `2025-03-15` — both orbit
  143, descending.

**A useful finding beyond the review:** each event has a **second** same-orbit
pre-event scene (Hanna `2020-07-03`, March 2025 `2025-03-03`). The label method
requires a *multi-date* pre-event median rather than a single baseline image, so
two same-orbit baselines per event is the minimum that makes that method
possible. The chosen ~30-day pre-event window supplies it.

Zero items were excluded — the live catalog data is clean for both events.

### What was built

Six Python modules under `src/colonia_flood/`, one TOML config, and a test
suite. The architecture's central idea is a **single network seam**: one
`SearchClient` Protocol is the only thing that knows HTTP exists, so unit tests
substitute a fake and never touch the network.

The second structural idea addresses determinism. Output is split into two
files per event:

- `acquisitions.json` — a **pure function of (configuration, catalog
  response)**. Contains no timestamp of when it ran.
- `last_run.json` — run provenance (retrieval time, library versions, git
  commit, hashes).

Because the wall-clock value is assembled in a different module and written to a
different file, it is *structurally impossible* for it to change the manifest's
bytes. This was verified by running twice under two different injected clocks:
the manifest was byte-identical, the run record differed.

### Verification performed

| Check | Result |
|---|---|
| Offline test suite | **94 passed**, 6 live tests correctly deselected |
| `ruff check` | Clean |
| `mypy --strict` | Clean, 15 files |
| Live catalog test (`pytest -m live`) | **6 passed** |
| Byte-identical rerun against the live catalog | **Confirmed** — SHA-256 unchanged |
| Output hygiene audit | 4 JSON files, ~50 KB, zero raster bytes, no SAS tokens, no credentials, no machine-specific paths |

The offline suite **enforces** its offline-ness rather than assuming it: an
autouse fixture severs `socket.connect` for every non-live test, so an
accidental network call fails loudly instead of passing quietly.

### Deviations from the plan, and why

1. **Interpreter changed.** The Python on `PATH` was an MSYS2 build, which
   creates a POSIX-layout virtualenv (`bin/`, no `Scripts/`) that breaks the
   documented Windows commands. Switched to native CPython 3.13. The plan's own
   notes had anticipated this becoming a problem once `rasterio`/`geopandas`
   arrive.
2. **Malformed-item fixtures derived in code**, not committed as ~15 near-
   identical JSON files. The four *real* captured catalog responses are
   committed; defect variants are mutations of them. Keeps the fixture
   directory reviewable.
3. **An item with no `id` raises instead of being excluded.** The plan's list of
   exclusion reason codes has no entry for it, and an item that cannot be keyed
   cannot be reported item-by-item either — so it is treated as a malformed
   *response*, not an excludable item.
4. **Polarization/asset disagreement reuses the existing `missing_vv_asset` /
   `missing_vh_asset` codes** rather than adding a new one, keeping the reason
   code list exactly as specified.
5. **`ruff format` was applied.** Linting and type checking were required;
   formatting was not specified. Applied for consistency.

### Environmental issue worth knowing

`pytest`'s default temp directory (`%LOCALAPPDATA%\Temp\pytest-of-oziel`) is
permission-denied on this machine, which makes any test using `tmp_path` error
out. Worked around at the command line with `--basetemp`. **Deliberately not
baked into `pyproject.toml`**, since that would hardcode a machine-specific
path. Anyone hitting this should pass `--basetemp` to a writable directory.

### Open questions and deliberate non-decisions

- **Search-window widths are still defaults**, not evidence-based: ~30 days for
  the pre-event window, ±1 day around the known acquisition for the event
  window. Both confirmed acquisitions fall inside, but **no judgment was made
  about whether coverage is adequate** for labeling.
- **Partial footprints are recorded but not judged.** Sentinel-1 scenes may
  cover only part of the county. Deciding the minimum usable county fraction is
  a labeling decision for the next slice.
- **Determinism holds per catalog response, not across time.** Sentinel-1
  archives get reprocessed, and item IDs and metadata can change. No design can
  prevent this; committing the manifests plus their SHA-256 makes such a change
  visible in a diff rather than invisible.
- **2018 and 2019 events are out of scope** until the two-event pipeline is
  settled.
- **Rainfall, DEM, and colonia-boundary sources remain unselected.** This slice
  supplies no rainfall quantity — the NWS event bounds are an event-scoping
  device, not a measurement.
- **Nothing here advances the Path A / Path B decision.** No label was created,
  no water was classified, no model was trained.

### State left behind

No git commit was created. `docs/mvp.md` was not modified. Generated manifests
live in `data/manifests/`, which is *not* gitignored (only `data/raw/` and
`data/processed/` are), so they are committable — the plan recommended
committing them so rerun determinism is reviewable in diffs.

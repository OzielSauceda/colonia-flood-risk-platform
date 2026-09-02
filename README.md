# Colonia Flood Risk Platform

An end-to-end geospatial data and machine-learning platform for exploring
rainfall-driven flood risk in Hidalgo County colonias.

## Project goal

This project will integrate rainfall, terrain, geographic, and historical
flood data to estimate and visualize localized flood risk. The first version
will be a research and decision-support prototype, not an official emergency
warning system.

## Initial MVP

The first working vertical slice will include:

- Hidalgo County geographic coverage
- Colonia boundary overlays
- Rainfall and elevation-derived features
- One defensible flood-label source or a clearly identified susceptibility score
- One baseline model and one gradient-boosted model
- PostgreSQL/PostGIS storage
- A FastAPI backend
- A React and TypeScript interactive map
- Automated testing and a deployed demonstration

## Technology stack

- **Data and machine learning:** Python, GeoPandas, rasterio, scikit-learn, XGBoost
- **Database:** PostgreSQL and PostGIS
- **Backend:** FastAPI, Pydantic, SQLAlchemy
- **Frontend:** React, TypeScript, MapLibre GL
- **Infrastructure:** Docker Compose, GitHub Actions
- **Later enhancements:** Airflow, dbt, MLflow, AWS, Terraform

## Project status

Currently in the feasibility and initial setup phase.

The model-label feasibility review is complete and recorded in
[docs/research/label-feasibility.md](docs/research/label-feasibility.md). It
rejected NWS Local Storm Reports as a standalone training target and authorized
one time-boxed Sentinel-1 satellite-label prototype behind a fixed pass/fail
gate. **That gate has not been evaluated, so both Path A and Path B remain
open**, and no defensible training label exists yet.

The first data-engineering slice — Sentinel-1 RTC acquisition manifests — is
implemented and described below. It sits upstream of that prototype: it
enumerates which radar observations exist for each event. It downloads no raster
data, classifies no water, and does not prejudge the Path A / Path B decision.

## Sentinel-1 acquisition manifests

Queries Sentinel-1 RTC **catalog metadata** for the configured Hidalgo County
flood events and writes a deterministic manifest per event. No raster asset is
ever downloaded.

- Events, search windows, and the county extent live in
  [config/events.toml](config/events.toml) — the only place these dates appear.
- Generated output lands in `data/manifests/<event_id>/`:
  `acquisitions.json` (deterministic; a pure function of configuration and the
  catalog response) and `last_run.json` (run provenance: retrieval timestamp,
  library versions, hashes). The split is what keeps a wall-clock value out of
  the manifest.
- Data sources are registered in [docs/data-sources.md](docs/data-sources.md).

### First-time setup

Use a project-local virtual environment. On Windows, base it on a native
CPython install rather than an MSYS2 interpreter — MSYS2 produces a POSIX-layout
venv, and the wheel situation gets worse once `rasterio` and `geopandas` arrive
in a later slice.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### Tests, linting, and type checks

```powershell
pytest                  # offline suite; live tests deselected by pyproject addopts
ruff check .
mypy
pytest -m live          # optional: queries the real catalog, explicitly opted into
```

The offline suite requires no network access and enforces it: a fixture blocks
socket connections for every non-`live` test, so an accidental live call fails
rather than passing quietly.

### Generating manifests

```powershell
# All configured events (queries the real catalog; metadata only)
python -m colonia_flood.cli --config config/events.toml --out-dir data/manifests

# One event, no writes
python -m colonia_flood.cli --event hanna_2020 --dry-run
```

Exit codes: `0` success, `1` an event returned no acquisitions in one of its
windows (a silently empty manifest is the failure most likely to go unnoticed),
`2` configuration or catalog error.

### Verifying the output

```powershell
# Inspect a manifest
Get-Content data\manifests\hanna_2020\acquisitions.json -Raw | ConvertFrom-Json |
    Select-Object -ExpandProperty acquisitions |
    Select-Object window, datetime_utc, platform, relative_orbit, orbit_direction |
    Format-Table

# Confirm a rerun is byte-identical
(Get-FileHash data\manifests\hanna_2020\acquisitions.json).Hash
python -m colonia_flood.cli --event hanna_2020
(Get-FileHash data\manifests\hanna_2020\acquisitions.json).Hash

# Confirm no raster was written
Get-ChildItem -Recurse data\manifests | Where-Object { $_.Extension -ne '.json' }
```

## Disclaimer

This project is an experimental research prototype. It does not replace
official flood forecasts, alerts, evacuation guidance, or emergency services.
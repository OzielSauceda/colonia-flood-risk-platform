# Data-source register

**Status:** Living document
**Requirement:** `docs/mvp.md` §5.5 — every ingested dataset is recorded here
with source name, publisher, access method, retrieval date, native CRS, native
resolution, license or terms of use, and known limitations.

This register currently covers the **metadata-acquisition slice only**. No
raster asset has been downloaded, and no dataset below has yet been ingested
into a database or used to produce any modeled value.

**[OPEN]** Rainfall, DEM, and colonia-boundary sources remain unselected
(`docs/mvp.md` §13, questions 2–4). They are added here when they are chosen.

---

## 1. Sentinel-1 RTC — radar acquisition metadata

| Field | Value |
|---|---|
| Source name | Sentinel-1 Radiometrically Terrain Corrected (RTC) |
| Producing mission | Copernicus Sentinel-1, European Space Agency |
| Host / access method | Microsoft Planetary Computer STAC API, anonymous item search at `https://planetarycomputer.microsoft.com/api/stac/v1`, collection `sentinel-1-rtc` |
| Retrieval date | 2026-09-02 |
| What was retrieved | **Catalog metadata only.** No raster asset was requested or downloaded. |
| Native CRS | Item footprints and bounding boxes are served in EPSG:4326. The RTC raster assets themselves are UTM-projected Cloud-Optimized GeoTIFFs. |
| Pixel spacing and spatial resolution | Collection metadata lists 10 m radar pixel spacing, with radar resolution of approximately 20 m in range and 22 m in azimuth. These describe different properties. The selected RTC assets' actual pixel size, grid, and CRS will be verified during raster preparation. This slice queries VV/VH metadata only. |
| License / terms | The hosted Sentinel-1 RTC collection declares CC BY 4.0. Collection metadata identifies Catalyst as processor and Microsoft as host/licensor. Anonymous catalog search was verified; raster asset access requirements remain unverified for this slice. |

Source: [Planetary Computer Sentinel-1 RTC collection metadata](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc).

### Access model — verified, not assumed

The plan flagged as blocking whether anonymous access is sufficient
(`docs/plans/sentinel-acquisition-manifest.md` §9, item 3). It was verified
against the live API on 2026-09-02: anonymous `POST /search` returns items, and
the returned `vv`/`vh` asset hrefs are **unsigned** blob URLs with no SAS query
string. When explicitly executed, the optional live test
`tests/live/test_catalog_live.py` checks anonymous search and unsigned asset
URLs. These checks are not performed during ordinary offline test runs.
A failure indicates that the catalog behavior needs investigation.

### Known limitations

- **Archive reprocessing.** Item IDs and metadata can change as ESA and the host
  reprocess the archive. Determinism holds per catalog *response*; it does not
  hold across time, and no design can make it. The committed manifests plus
  `manifest_sha256` make such a change visible in a diff instead of invisible.
- **Partial footprints.** A returned scene may cover only part of Hidalgo
  County. This slice records each footprint but makes no coverage judgment;
  deciding the minimum usable county fraction is a labeling decision for the
  next slice.
- **Radar interpretation is not settled.** `docs/research/label-feasibility.md`
  found that a naive "darker after the storm equals flooded" rule is not
  defensible: open water lowers backscatter, while flooded vegetation, urban
  double-bounce, and wet soil can raise it. Nothing in this slice classifies
  water; it only enumerates which observations exist.
- **Asset key names** (`vv`, `vh`) are configuration, not code, so a rename by
  the host is a one-line config change. The live test is what detects it.

---

## 2. Hidalgo County boundary extent — query area of interest

| Field | Value |
|---|---|
| Source name | TIGERweb State_County MapServer, layer 1 (Counties) |
| Publisher | US Census Bureau |
| Access method | `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1`, queried for `GEOID = 48215` with `outSR=4326` |
| Retrieval date | 2026-09-02 |
| Native/service CRS and retrieved CRS | The service advertises EPSG:3857 (Esri WKID 102100). Our query requests EPSG:4326 using `outSR=4326`, so the retrieved coordinates and derived bounding box use longitude and latitude. |
| Native resolution | Vector polygon; not a raster product |
| License / terms | US Census Bureau TIGER/Line products are in the public domain |

**Derived value in use.** Only the bounding box of the returned polygon is used,
recorded in `config/events.toml` as
`[-98.586444, 26.036268, -97.861684, 26.783081]` (west, south, east, north).

**Known limitations.** A bounding box is a rectangle, not the county. It
deliberately over-covers: any acquisition intersecting the rectangle is
enumerated, and clipping to the actual county polygon is a later concern. The
full polygon geometry is **not** yet committed anywhere in this repository —
this slice needs only the extent. The polygon itself becomes a tracked dataset
when gridding begins (`docs/mvp.md` A4).

---

## 3. NWS Brownsville event summaries — rainfall event bounds

| Field | Value |
|---|---|
| Source name | NWS Brownsville/Rio Grande Valley significant-weather event summaries |
| Publisher | NOAA National Weather Service |
| Retrieval date | 2026-09-02 |
| Native CRS | Not applicable — event-summary documents |
| Native resolution | Not applicable — event-summary documents, not raster measurements |
| License / terms | US Government work; public domain |

Used **only** to fix the `event_start` / `event_end` calendar bounds of each
configured event. These are recorded per event in `config/events.toml` and
copied into every generated manifest.

| Event | Bounds used | Source |
|---|---|---|
| `hanna_2020` | 2020-07-24 → 2020-07-29 | [Hurricane Hanna event page](https://www.weather.gov/bro/2020event_hanna), whose rainfall accumulation period is stated as "7 AM July 24 – 7 AM July 29" |
| `march_2025` | 2025-03-26 → 2025-03-28 | [March 26-28, 2025 Historic Flooding/QLCS Event](https://www.weather.gov/media/bro/wxevents/2025/pdf/March_26to28_HistoricFlooding_QLCS.pdf) |

**These bounds were not derived from the satellite acquisition dates.** The plan
explicitly forbids that, because inferring the rainfall window from the
observation would quietly redefine the field. They come from the event summaries
above, which is also the source `docs/research/label-feasibility.md` cites for
event discovery.

**Known limitations.** An event summary reports a regional rainfall period, not
a per-cell start and end. The bounds are an event-scoping device for selecting
satellite observations; they are not a rainfall measurement and supply no
rainfall quantity. The rainfall *input* of `docs/mvp.md` §5.1 is still
unselected.

---

## 4. Supplemental — NWS/IEM Local Storm Reports

**Not ingested by this slice.** Recorded here because
`docs/research/label-feasibility.md` retains LSRs as **supplemental
corroboration and qualitative validation only** — never as a training target.
They are presence-only, spatially coarse, and reporting-biased, and the IEM
archive states it is neither complete nor official. If and when they are
actually retrieved, a full register entry is added here first.

Access method of record:
[Iowa Environmental Mesonet archived LSRs](https://mesonet.agron.iastate.edu/request/gis/lsrs.phtml).

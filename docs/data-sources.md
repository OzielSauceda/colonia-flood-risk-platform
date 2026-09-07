# Data-source register

**Status:** Living document
**Requirement:** `docs/mvp.md` §5.5 — every ingested dataset is recorded here
with source name, publisher, access method, retrieval date, native CRS, native
resolution, license or terms of use, and known limitations.

This register covers acquisition metadata, the **Stage A county polygon
snapshot**, and the **Stage F1 colonia polygon snapshot**. These ingestion
steps do not download raster assets, and no
dataset below has yet been ingested
into a database or used to produce any modeled value.

**[OPEN]** Rainfall and DEM sources remain unselected
(`docs/mvp.md` §13). They are added here when they are chosen.
The colonia-boundary source is selected and recorded in §5 below.

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

## 2. Hidalgo County boundary — query extent and tracked polygon

| Field | Value |
|---|---|
| Source name | TIGERweb State_County MapServer, layer 1 (Counties) |
| Publisher | US Census Bureau |
| Access method | `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1`, queried for `GEOID = 48215` with `outSR=4326` |
| Retrieval date | Extent: 2026-09-02; full polygon snapshot: 2026-09-07 |
| Native/service CRS and retrieved CRS | The service advertises EPSG:3857 (Esri WKID 102100). Our query requests EPSG:4326 using `outSR=4326`, so the retrieved coordinates and derived bounding box use longitude and latitude. |
| Native resolution | Vector polygon; not a raster product |
| License / terms | Public-domain Census Bureau material; the Bureau permits reproduction and requests source attribution (technical documentation §1.6, linked below). TIGER/Line is a registered Census Bureau trademark. |
| County identifier | GEOID `48215` (Texas `48`, Hidalgo `215`); source `NAME`: `Hidalgo County` |
| Service vintage | January 1, 2026, as advertised by layer 1 when checked on 2026-09-07; not a historical event-year boundary |
| Repository input | `data/boundaries/hidalgo_county.geojson`, prepared for version control in Stage A |
| Committed-file CRS | EPSG:4326, longitude then latitude in decimal degrees, requested with `outSR=4326` |
| Source integrity | One `FeatureCollection` feature, `Polygon`, one closed ring, 4,132 coordinate positions including closure; `AREALAND = 4069433006` m², `AREAWATER = 30081128` m² |

**Derived value in use.** Acquisition discovery uses the bounding box,
recorded in `config/events.toml` as
`[-98.586444, 26.036268, -97.861684, 26.783081]` (west, south, east, north).

**Known limitations.** A bounding box is a rectangle, not the county. It
deliberately over-covers: any acquisition intersecting the rectangle is
enumerated, and clipping to the actual county polygon is a later concern. The
full polygon snapshot is now a tracked project input for the future
`coverage.py` consumer, which will need the county outline for spatial
intersection and county-area calculations. No coverage calculation is performed
in Stage A. The polygon alone establishes no valid raster observations.

### Snapshot provenance and reproduction

Source: U.S. Census Bureau,
[TIGERweb State_County, layer 1 (Counties)](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1?f=pjson).
Reproduce the one-time, anonymous GET using this query:

```text
https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query?where=GEOID%3D%2748215%27&outFields=GEOID,NAME,AREALAND,AREAWATER&returnGeometry=true&outSR=4326&f=geojson
```

No geometry precision, generalization, or simplification parameter was supplied.
The reviewed response was 168,672 bytes, SHA-256
`25cdbcbec6b08881533038c72aa7033341e8135744199aa7e06a756d92da63dd`.
The snapshot preserves all returned fields, coordinate values, their numeric
text, and array ordering. Only whitespace was normalized: a newline between
coordinate positions and one final newline. No retrieval timestamp or local
metadata was inserted into the GeoJSON. Decimal-preserving JSON comparison
against the downloaded response verifies that formatting changed no values.

The raw derived bbox is
`[-98.58644400000378, 26.03626800000421, -97.86168400042897, 26.783080999883026]`.
Normalizing only these four values to the config's six-decimal precision yields
`[-98.586444, 26.036268, -97.861684, 26.783081]`, matching `config/events.toml`.
This validation does not round any polygon vertex or introduce a wider tolerance.

Network I/O occurred only during explicit ingestion and source-document review.
Normal future processing reads the version-controlled local snapshot. A future
boundary update requires another explicit retrieval and reviewed diff; there is
no automatic refresh command or runtime download path. The endpoint can change
over time, so retaining the snapshot makes calculations reproducible against
fixed input rather than assuming a later query returns identical data.

Licensing and limitations: [Census TIGER/Line technical documentation,
§§1.5–1.6](https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2018/TGRSHP2018_TechDoc.pdf)
states that Census materials may be reproduced with requested source attribution.
It also explains that statistical boundaries are not legal land descriptions.
This citation supports reuse terms, not the snapshot's 2026 vintage.

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

---

## 5. Hidalgo colonias — OAG geographic database, Stage F1 snapshot

| Field | Value |
|---|---|
| Source name / publisher | Texas Office of the Attorney General (OAG), Colonia Geographic Database / Texas Colonias Viewer |
| Authoritative entry point | [OAG Open Reports and Publications, Colonias](https://www.texasattorneygeneral.gov/open-government/open-reports-and-publications) directly links the application below and identifies the database as OAG-maintained. |
| Provenance chain | Application `1bc9c4f7b1da47dd8fc535fbd17dc060` → web map `d820fc1df66f44ceac8bf88dabc44468` → Feature Service item `f1405427feea43d28bc6c994c32aa3ae`. The map labels this layer `Colonias`. |
| Exact service / layer | [communities FeatureServer, layer 0](https://services9.arcgis.com/8EiW1jmucmoP1yM9/arcgis/rest/services/communities/FeatureServer/0?f=pjson), layer name `communities`, `esriGeometryPolygon` |
| Inspected ArcGIS owners | Application and map: `oaglts`; service item: `todd.giberson`. The latter account's institutional role is not established by item metadata; authority follows the official OAG link and application configuration. |
| Access / selection | Public, anonymously queried; `COUNTYNAME='HIDALGO'` under the service's case-insensitive collation, `outFields=*`, `outSR=4326`, `returnGeometry=true`, `orderByFields=FID ASC`, `f=geojson`. No spatial selection, clipping, generalization or precision parameter. |
| Retrieval date | 2026-09-07 |
| Source vintage | Service item modified 2021-03-22 18:48:20 UTC; layer data/schema last edit 2021-03-22 19:30:53.157 UTC. Map modified 2025-04-15 16:53:14 UTC. These are metadata/edit dates, not certified survey dates or event-year coverage. |
| Native/service CRS | Esri WKID `102100`, latest WKID `3857` (WGS 84 / Pseudo-Mercator), metres; original pre-publication CRS not stated. |
| Retrieved / committed CRS | EPSG:4326 longitude/latitude, requested from the service; source response's `crs` member retained. |
| Native resolution | Vector polygons; no raster resolution. Positional accuracy not specified. |
| License / terms | OAG's linked open-data page encourages reuse and states its publications are not copyright-protected. Application/map/service item license fields are null/empty; layer/service copyright and description fields are empty. No named dataset-specific license, attribution clause or additional use restriction was supplied in inspected metadata. Retain OAG attribution and these qualifications. |
| Feature count / identity | 846 features; system-maintained `FID` is unique/nonblank and equals GeoJSON feature `id`. `MNUMBER` and `MNUMBER_1` are also unique/nonblank in this snapshot. Preserve all 145 returned attributes per feature. Name fields: `COLONIA_NM`, `COMM_NM`; county fields: `COUNTYNAME`, `COUNTY`. |
| Repository input | `data/boundaries/colonias.geojson` — explicitly acquired source snapshot for review, not an automatic runtime download |
| File size / SHA-256 | 2,431,551 bytes; `17302574bd121d859981ef51cbbd8a0caa65fc051c97ec54cf8f523db8b9f238` |
| Geometry inventory | 846 valid, nonempty Polygons; 0 MultiPolygons; 1 interior ring; 6,058 finite 2D coordinate positions including ring closures. No source polygon extends outside the committed county polygon. |
| Snapshot extent | `[-98.5826393750855, 26.0646999136896, -97.8688114087686, 26.5042730701565]` in EPSG:4326 |

**Known limitations.** This named OAG registry is not a guarantee of exhaustive,
current or historical colonia coverage. Definitions of **colonia differ between
administrative registries**; all future Stage F counts are conditional on this
**named source and vintage**, including its polygon boundaries. Item modification
dates do not establish when individual communities were surveyed. One `SUBD_ID`
is blank, and `TWDB_ID` has 20 blanks and 30 duplicated nonblank values; neither
is a safe unique key. Names are unique but `COMM_NM` and `COLONIA_NM` differ in
six records. No values were repaired, normalized, discarded or dissolved.
Source infrastructure/population attributes remain provenance data, not verified
current conditions or flood labels. Service `FID` stability across republishing
is not guaranteed; retain item/layer identity and the snapshot hash together.

The [Stage F1 source review](plans/sentinel-stage-f1-source-review.md) records
the complete reproduction request, metadata findings, identity exceptions,
geometry checks and whitespace-only normalization. Coordinate numeric values,
numeric spellings, attributes and array ordering were verified unchanged from
the service response. This source acquisition does not implement a 500 m grid,
calculate colonia/Sentinel overlap counts, or establish valid raster observations.

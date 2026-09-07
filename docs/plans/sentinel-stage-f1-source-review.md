# Stage F1 review — authoritative Hidalgo colonia source snapshot

Retrieved and inspected 2026-09-07 on `feat/sentinel-raster-preparation`.
Scope: identify, verify, acquire and register the source only. No commit or
push was made. The 500 m grid and viability precheck remain unimplemented.

## Selection and authority

The [Texas OAG Open Reports and Publications page](https://www.texasattorneygeneral.gov/open-government/open-reports-and-publications)
identifies its Colonia Geographic Database as OAG-maintained and directly links
the [public application](https://texasoag.maps.arcgis.com/apps/webappviewer/index.html?id=1bc9c4f7b1da47dd8fc535fbd17dc060).
Following its live configuration, rather than searching for a similarly named
third-party layer, establishes this chain:

| Resource | Inspected identity and metadata |
|---|---|
| Application | `1bc9c4f7b1da47dd8fc535fbd17dc060`; item title `Texas Colonia Communities Test`, configured title `Texas Colonia Communities`; owner `oaglts`; public; created 2021-02-25 21:33:29 UTC, modified 2021-05-26 16:42:21 UTC |
| Web map | `d820fc1df66f44ceac8bf88dabc44468`; `Colonias Geography Database`; owner `oaglts`; public; created 2021-02-05 21:47:02 UTC, modified 2025-04-15 16:53:14 UTC |
| Feature Service item | `f1405427feea43d28bc6c994c32aa3ae`; title `communities`; owner `todd.giberson`; public; created 2021-02-24 20:27:23 UTC, modified 2021-03-22 18:48:20 UTC |
| FeatureServer | `https://services9.arcgis.com/8EiW1jmucmoP1yM9/arcgis/rest/services/communities/FeatureServer` |
| Geometry layer | `/0`, name `communities`, web-map title `Colonias`, operational-layer ID `1963a4e8681-layer-5`, geometry type `esriGeometryPolygon` |
| Layer edit metadata | `lastEditDate`, `schemaLastEditDate`, `dataLastEditDate`: `1616441453157`, or 2021-03-22 19:30:53.157 UTC |
| Service spatial reference | `wkid: 102100`, `latestWkid: 3857`, metres; layer has neither Z nor M |
| Layer full extent | EPSG:3857: `[-11870295.275644016, 2981598.873264204, -10816261.397590078, 3762983.5291405064]` |
| Item geographic extent | `[[-106.63267673122766, 25.85876499975064], [-97.16412930487144, 31.997508085898016]]`; whole service, not Hidalgo-only |

Metadata can be reproduced at
`https://texasoag.maps.arcgis.com/sharing/rest/content/items/{item_id}?f=pjson`.
Append `/data?f=pjson` to the item path for application or map configuration.
The application data's `map.itemId` points to the map above; the map's
`operationalLayers` supplies both the geometry URL and service item ID.
Service and layer metadata use their URLs with `?f=pjson`.

The service-item owner differs from the map owner. No institutional role is
inferred for `todd.giberson`; provenance rests on the OAG-linked configuration.
The application item's word `Test` is preserved here as an unresolved naming
detail, not suppressed. It is nevertheless the application linked by OAG.
No Communities Unlimited/NADBank or other secondary dataset was acquired or
compared: the preferred source was technically usable.

## Public query and export capabilities

Service and layer advertise `capabilities: Query`, `hasStaticData: true`,
`maxRecordCount: 2000`, `maxIdsCount: 1000000`. Layer query formats are
`JSON, geoJSON, PBF` (service-root query formats list only `JSON`). Layer
metadata supports pagination, ordering, distinct values, statistics, spatial
queries and output projection. Advertised layer export formats are CSV,
shapefile, SQLite, GeoPackage, file geodatabase, feature collection, GeoJSON,
KML, Excel and Parquet; only query-to-GeoJSON was exercised, not item export.
Editor-tracking metadata says anonymous queries are allowed. All metadata,
count, ID and geometry requests here succeeded without tokens or credentials.
No editing capabilities were exercised.

## Hidalgo selection and identifying fields

A distinct query of `COUNTYNAME,COUNTY` revealed an explicit county attribute.
The selection is `COUNTYNAME='HIDALGO'`; the service's collation is
case-insensitive. This selects 845 records spelled `HIDALGO` and one spelled
`Hidalgo` (FID 2087). All 846 have `COUNTY='Hidalgo'`. An independent
`COUNTY='Hidalgo'` ID query returned exactly the same ID set. Thus this is
an administrative attribute selection, not a county spatial filter.

| Field | Inspected type / role and Hidalgo findings |
|---|---|
| `FID` | OID, nonnullable, system-maintained unique field and primary index; 846 unique values, zero null/blank/duplicate IDs; GeoJSON `id` equals `FID` |
| `MNUMBER`, `MNUMBER_1` | String identifiers; each has 846 unique nonblank values; zero duplicate/null identifiers |
| `COL_ALL2_`, `COL_ALL2_I` | Integer identifiers; each has 846 unique values, none null; undocumented legacy semantics, not assumed to be stable external identifiers |
| `SUBD_ID` | String; no repeated values, but one whitespace-only value, FID 2087 / MNUMBER `M1080941` / `Garzas de Capisallo` |
| `TWDB_ID` | String; 20 whitespace-only values, 30 duplicated nonblank values; unsuitable as a feature primary key |
| `COLONIA_NM` | String, length 254; preferred descriptive colonia-name field; 846 unique nonblank values |
| `COMM_NM` | String, alias `Community Name`; 846 unique nonblank values; differs from `COLONIA_NM` on six records |
| `COUNTYNAME`, `COUNTY` | Strings; `COUNTYNAME` alias `County Name`, length 20; `COUNTY` length 254 |
| `DATASOURCE` | String source-code attribute, retained without interpreting undocumented codes |
| `TYPECOMMUN` | String, whitespace-only in all selected records; no classification filter was inferred from it |

Name and MNUMBER duplicates were also checked after trimming and case-folding:
none. This check did not modify the snapshot. Name differences (FID,
`COMM_NM` → `COLONIA_NM`): 327, `El Sol` → `El Sol Subdivision #1`;
604, `Spring Gardens` → `SPRING GARDENS`; 625, `Meadow Lands` → `MEADOW LANDS`;
785, `Brenda Gay` → `BRENDA GAY`; 899, `Schuerbach Acres` → `SCHUERBACH ACRES`;
1155, `Tiny Acres` → `TINY ACRES`.

Duplicated nonblank `TWDB_ID` values with multiplicities:
`1080307:4`, `1080468:2`, `1080290:4`, `1080706:2`, `1080640:3`,
`1080751:2`, `1080966:3`, `1080871:2`, `1080747:2`, `1080774:4`,
`1080785:4`, `1080792:4`, `108A040:2`, `1080850:2`, `108A087:2`,
`1080797:3`, `1080003:2`, `108A123:2`, `1080090:2`, `1081022:2`,
`1080137:2`, `1080136:4`, `1080076:2`, `108A069:2`, `1080146:3`,
`1080242:2`, `1080416:2`, `1081061:2`, `1080246:5`, `1080414:2`.
These source values were reported and retained, never deduplicated or repaired.

## Snapshot acquisition and exact reproduction

Anonymous GET, with no geometry precision, quantization, simplification,
generalization, clipping or dissolve parameters:

```text
https://services9.arcgis.com/8EiW1jmucmoP1yM9/arcgis/rest/services/communities/FeatureServer/0/query?where=COUNTYNAME%3D%27HIDALGO%27&outFields=*&returnGeometry=true&outSR=4326&orderByFields=FID%20ASC&f=geojson
```

The response has 846 features, below the 2,000-feature limit. Count-only and
ID-only checks at the same `/query` endpoint used:

```text
where=COUNTYNAME%3D%27Hidalgo%27&returnCountOnly=true&f=pjson
where=COUNTYNAME%3D%27Hidalgo%27&returnIdsOnly=true&f=pjson
where=COUNTY%3D%27Hidalgo%27&returnIdsOnly=true&f=json
```

The returned count, both ID sets and downloaded feature IDs agree exactly.
Records are ordered by ascending `FID`. The service performed the conversion
from EPSG:3857 to EPSG:4326; no custom acquisition projection code was used.
To check for curves, another query used the same uppercase county predicate,
`outFields=FID&returnGeometry=true&returnTrueCurves=true&outSR=4326&orderByFields=FID%20ASC&f=json`.
It returned 846 ring geometries, zero `curveRings`, and no transfer-limit flag.
Thus no curve approximation was required for these polygons.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Raw GeoJSON response | 2,425,493 | `f185ae78a0ef73e1a9210f8169704c3f4024b0d34e005025e600cc6b5116c624` |
| `data/boundaries/colonias.geojson` | 2,431,551 | `17302574bd121d859981ef51cbbd8a0caa65fc051c97ec54cf8f523db8b9f238` |

Normalization changed whitespace only: outside JSON strings, replace `],[`
with `],` + LF + `[` and `},{` with `},` + LF + `{`, then ensure one final LF.
UTF-8 is retained without a BOM. The exact one-off normalization is:

```python
formatted = re.sub(
    r'("(?:\\.|[^"\\])*")|(\],\[)|(\},\{)',
    lambda m: m[1] if m[1] is not None else m[0].replace(',', ',\n'),
    text,
).rstrip('\r\n') + '\n'
```

`json.loads(..., parse_float=Decimal, parse_int=Decimal)` comparison proved
the raw and normalized documents equal. A separate string-aware token
comparison proved every non-whitespace token unchanged, including exact
numeric spellings. All 145 properties per feature, source strings, source
date attributes, `id`, CRS member, coordinate values, ring/feature ordering
and hole geometry survive intact. No retrieval timestamp or machine path was
inserted. Source date fields are retained as attributes, not retrieval metadata.
No coordinate rounding, geometry repair, clipping or dissolve occurred.

Raw responses and metadata are retained locally under the already-ignored
`data/raw/stage-f1/` investigation directory; they are not additional
version-controlled inputs. The snapshot and this provenance record are the
reviewable repository artifacts. A later query may differ; the recorded hash
identifies this input vintage without requiring future service availability.

## Geometry and local validation

The existing Shapely environment checked the downloaded and normalized data:

- Valid JSON `FeatureCollection`; 846 GeoJSON `Feature` objects, 145 properties
  each; no null geometries or unexpected feature types.
- 846 Polygons, zero MultiPolygons/multipart geometries, one interior ring.
- Zero empty or invalid geometries; no repair/discard was necessary.
- 6,058 coordinate positions including ring closures: all finite, exactly 2D,
  and within longitude/latitude bounds; rings closed and at least four positions.
- EPSG:4326 bounds:
  `[-98.5826393750855, 26.0646999136896, -97.8688114087686, 26.5042730701565]`.
- The committed Hidalgo County polygon `covers` each source polygon: zero
  outside or partially outside features. This direct same-CRS topology check
  did not clip geometry, measure areas, or calculate any Stage F cell counts.
- Unique `FID` inventory, sorted order and IDs match the independent server
  queries. Exact numeric/attribute preservation and snapshot SHA-256 verified.
- `git diff --check` passed. Production/test Python files were untouched, so
  conditional Ruff, mypy and test-suite runs were not required for this data/doc
  acquisition. One-off investigation commands introduced no production module.

## Terms, limitations and unresolved questions

The [OAG open-data page](https://www.texasattorneygeneral.gov/open-government/open-reports-and-publications)
encourages use of its public data and says its publications are not protected
by copyright. No named dataset-specific license was present: `licenseInfo`
and `accessInformation` are null on the service item/application and empty on
the map; service/layer copyright and description strings are empty. This is
the observed reuse statement, not an inferred Creative Commons license.
OAG attribution and the exact source identifiers are retained here.

Unresolved limits for human review:

1. The last reported data edit is March 2021. Individual survey dates,
   positional accuracy and completeness for 2020, 2025 or 2026 are not certified
   by the inspected metadata. A 2025 map edit is not evidence of 2025 geometry.
2. The service account's institutional role and the application's `Test`
   title are not explained in metadata; the direct OAG link is the provenance
   evidence. Dataset-specific licensing detail is absent beyond the OAG portal
   statement. No contact with the publisher was made.
3. Original pre-publication CRS and legacy field-code semantics are unstated.
   Blank `SUBD_ID`, nonunique `TWDB_ID` and six name-field differences remain
   as recorded above. Source `FID` need not survive a future republication.
4. Definitions of **colonia can differ between administrative registries**.
   All future Stage F counts are conditional on this **named OAG source and
   vintage**. This snapshot does not establish exhaustive communities, current
   infrastructure conditions, raster validity or flood labels.

## Scope and files

Only `data/boundaries/colonias.geojson`, `docs/data-sources.md`, and this review
were added/edited for F1. Existing `Findings.md` and `prompt.md` were preserved.
The rainfall and DEM source-selection questions remain open.

No `colonia.py`, `colonia_cli.py`, refresh command, 500 m grid, viability JSON,
colonia/Sentinel overlap count, raster reading, Rasterio, SAS token request,
Stage C/D/E/H implementation, Path-A gate change or Stage B calculation change
was introduced. Stop here for source/snapshot review before the viability work.

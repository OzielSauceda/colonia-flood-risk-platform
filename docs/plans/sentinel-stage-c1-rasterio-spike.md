# Stage C1 — Rasterio truncated-prefix MemoryFile spike

Investigation date: 2026-09-07. Branch: `feat/sentinel-raster-preparation`.
**Result: a 128 KiB prefix opened successfully and supplied the requested
metadata for the tested Hanna VV COG.** No larger prefix, full raster, pixel
read, `/vsicurl` fallback or production raster module was needed.

## Dependency and environment

Added runtime constraint `rasterio>=1.4.4,<1.6`. The lower bound preserves a
Python 3.11-compatible release; the upper bound limits adoption to the examined
1.4/1.5 release families. The package still declares Python `>=3.11`.
[Rasterio 1.4.4 PyPI metadata](https://pypi.org/pypi/rasterio/1.4.4/json)
reports Python `>=3.10` and includes
`rasterio-1.4.4-cp311-cp311-win_amd64.whl`.
[Rasterio 1.5.1](https://pypi.org/project/rasterio/1.5.1/) requires Python
`>=3.12`. Pip can select 1.4 on Python 3.11; this spike did not runtime-test
Python 3.11 or Rasterio 1.4.

Resolved in the existing native Windows CPython **3.13.2** environment:

| Package/component | Exact version |
|---|---|
| Rasterio | **1.5.1**, wheel `rasterio-1.5.1-cp313-cp313-win_amd64.whl` |
| GDAL reported by Rasterio | **3.12.4** |
| PROJ reported by Rasterio | **9.8.1** |
| Newly installed transitive dependencies | affine **3.0.1**, click **8.5.0**, pyparsing **3.3.2** |
| Existing NumPy retained | **2.3.5** (`>=2.1,<2.4` unchanged) |
| Existing vector libraries retained | Shapely **2.1.2**, pyproj **3.8.0** |

The Rasterio package has no `py.typed` marker. Added only a mypy override for
`rasterio.*` with `ignore_missing_imports = true`; global strict checking and
all other settings remain unchanged. This addresses the untyped dependency
boundary without claiming Rasterio calls are statically verified.

Installation command: `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`.
The initial sandbox attempt failed fetching build dependencies because socket
access was denied. An approved retry succeeded, installed the four packages
above and reinstalled the editable project so its dependency metadata matches
`pyproject.toml`. Existing dependencies were otherwise retained. Pip reported
a 30.6 MB Rasterio wheel and 10/125/122 kB affine/click/pyparsing wheels;
package/index/build traffic is separate from the precisely measured asset
investigation byte budget below.

## Exact asset and bounded transfer

Loaded `data/manifests/hanna_2020/acquisitions.json` and reused Stage B's
`select_preferred_group`; tested the selected event record's VV href:

```text
S1A_IW_GRDH_1SDV_20200727T122412_20200727T122441_033640_03E61B_rtc
https://sentinel1euwestrtc.blob.core.windows.net/sentinel1-grd-rtc/GRD/2020/7/27/IW/DV/S1A_IW_GRDH_1SDV_20200727T122412_20200727T122441_033640_03E61B_60B6/measurement/iw-vv.rtc.tiff
```

Anonymous GET to
`https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-1-rtc`
returned a **345-byte** JSON body. Its token was appended to the manifest href
only in process memory. Neither response content, token nor signed URL was
printed, saved or passed to Rasterio. HTTP failures would report status/type
only to avoid exception messages containing a signed URL.

Exactly one asset GET was sent, with `Range: bytes=0-131071` and
`Accept-Encoding: identity`. Response: **206**, `Content-Length: 131072`,
`Content-Range: bytes 0-131071/2062396392`. The response status and range were
checked before reading; the body read was bounded to 131,072 bytes. No HEAD,
retry, additional asset range, tile or whole-scene request was made.

| Measurement | Bytes |
|---|---:|
| Full object size, from Content-Range | **2,062,396,392** |
| Raster prefix actually transferred | **131,072** |
| SAS response body | **345** |
| Total measured investigation response bodies | **131,417** |

Totals exclude HTTP/TLS overhead, package installation, PyPI metadata checks
and documentation browsing. Prefix SHA-256:
`1a2ab8b669b5a5b0598609077db36081a86e18db2ffbf34ae07e99023f5bd781`.
The prefix was kept in memory only and was not retained as a fixture.

## MemoryFile experiment and accessible metadata

After acquisition, deleted token/signed-request references and patched
`socket.socket.connect`, `connect_ex` and `socket.create_connection` to raise.
Passed only the prefix bytes to `rasterio.io.MemoryFile`, then called
`memory.open()` and inspected the dataset inside both context managers.
No `read`, mask, window, statistics or overview-pixel operation was called.

| Field | Observed value |
|---|---|
| Driver | `GTiff` |
| CRS | `EPSG:32614` |
| Affine `(a,b,c,d,e,f)` | `(10.0, 0.0, 578140.0, 0.0, -10.0, 2993250.0)` |
| Width / height | **28236 / 23625** |
| Band count / dtype | **1 / float32** |
| Nodata / nodatavals | `-32768.0` / `(-32768.0,)` |
| Block shapes | `[(512, 512)]`; tiled |
| Bounds, EPSG:32614 metres | `(578140.0, 2757000.0, 860500.0, 2993250.0)` |
| Overview factors, band 1 | `[2, 4, 8, 16, 32, 64]` |
| Band description | `Sentinel-1 Calibrated and Terrain Corrected VV` |
| Units | `(None,)` — no formal band unit supplied |
| Scales / offsets | `(1.0,)` / `(0.0,)` |
| Color interpretation | `gray` |
| IMAGE_STRUCTURE tags | `LAYOUT=COG`, `COMPRESSION=DEFLATE`, `INTERLEAVE=BAND`, `PREDICTOR=3` |
| Band tags | `Matrix_Element=_1_1`, `Polarization=VV`, `SARPixelContent=intensity`, `Scale=linear` |
| Dataset namespaces | `IMAGE_STRUCTURE`, `DERIVED_SUBDATASETS` |
| Dataset file references | All in `/vsimem/`; no remote filename |

The default dataset tags were also readable: `Acquisition_DateTime`,
`ColumnCount`, `DefaultBlue`, `DefaultGreen`, `DefaultRed`, `IncidenceFarAngle`,
`IncidenceNearAngle`, `LookDirection`, `Matrix_Type`, `NominalLocation_Height`,
`NO_DATA_VALUE`, `OrbitDirection`, `ProductType`, `PulseRepetitionFrequency`,
`RadarCenterWavelength`, `RangeDistFirstpixel`, `RangeDistLastpixel`, `RowCount`,
`SatPositions`, `SlantRangeFarEdge`, `SlantRangeNearEdge`, `TimeOfFirstLine`,
`TimeOfLastLine`, `totalProcessedRangeBandwidth`, and `AREA_OR_POINT`.
Relevant values include `AREA_OR_POINT=Area`, `NO_DATA_VALUE=-32768.000000`,
`OrbitDirection=Descending`, `ProductType=ORTHO`, `LookDirection=Right`.
The derived-subdataset namespace was enumerated but its contents were not read.

Legacy `ColumnCount=25280` and `RowCount=19463` disagree with TIFF dimensions.
C2 must use structural `dataset.width/height` for the raster grid, not these
descriptive tags. Linear intensity is explicitly a band tag; absent formal
units must remain absent, not be invented as dB or another unit.

**No open/metadata failure occurred.** The sole captured warning came from
accessing `is_tiled`: it is deprecated for future removal. This was not a
truncation/IFD warning. C2 should avoid depending on that deprecated property.
No larger-prefix experiment was warranted: 128 KiB sufficed for all fields
actually exercised. This does not locate every TIFF structure or prove tile
payloads reside in the prefix; overview factors are metadata, not pixel reads.

## Network isolation evidence and limits

Python socket calls were blocked before constructing/opening MemoryFile:
**zero attempts**. Additionally, a local listening proxy counted connections
while `GDAL_HTTP_PROXY` targeted it; HTTP timeout was 2 seconds, retries zero,
and `NO_PROXY`/`no_proxy` were cleared. **Zero proxy connections** were observed.
The listener would close any connection without forwarding it. PROJ networking
was disabled; GDAL PAM was disabled and directory scans disabled with
`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`. No global test fixture was changed.

Thus bytes-to-metadata parsing succeeded under the requested Python network
block with no observed GDAL HTTP request. GDAL was never given the source URL,
only an in-memory TIFF. The proxy observation is additional evidence, **not an
OS firewall or packet trace**: Python monkeypatches alone cannot block GDAL's
native HTTP stack, and the proxy does not prove absence of every possible
native transport. No `/vsicurl` diagnostic was performed.

## C2 recommendation, validation and unresolved scope

Proceed, after review, with **AssetClient-controlled bounded HTTP bytes →
Rasterio MemoryFile → metadata profile**. C1 establishes feasibility for the
tested object/version without giving GDAL a remote href. Keep byte limits and
HTTP range validation at the explicit network boundary. A future incomplete
prefix must fail explicitly or request further bounded data through that seam;
do not silently fall back to `/vsicurl` or a full download.

Remaining questions: other assets/COG layouts and versions may need more bytes;
Python 3.11/Rasterio 1.4 parsing is untested; some unexercised metadata accesses
may seek beyond the prefix. Native network isolation still needs an appropriate
production/test policy. The observed dimensions-versus-tags distinction and
missing formal units need explicit profile semantics in C2. Window/pixel reads
have different byte requirements and were not investigated here. The complete
object is demonstrably unnecessary for these metadata calls, not for all reads.

Validation after installation: **166 offline tests passed, 6 live tests
deselected**; Ruff passed; strict mypy passed across **20 source files**;
`pip check` found no broken requirements; `git diff --check` passed.
No new production test or helper file was created; the spike ran as an inline
investigation command. No bytes or credentials were persisted. Changed only
`pyproject.toml`, this review and the small main-plan status/result update.
No Stage B/F result, gate, source snapshot or production behavior was edited.
No C2/D/E/H implementation or commit was made. Stop here for C1 review.

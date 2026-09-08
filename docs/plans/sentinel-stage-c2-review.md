# Stage C2 review — bytes-only raster profiles and grid compatibility

C2 implements metadata parsing and mechanical comparison only. No HTTP client,
SAS implementation, raster manifest, CLI, window read, mask, dB conversion or
scientific classification was added. Stage B/F results and gates are unchanged.

## Production API and profile semantics

`src/colonia_flood/raster_profile.py` contains:

- Frozen `RasterProfile`, `Criterion` and `CompatibilityReport` dataclasses.
- `parse_profile(header_bytes: bytes) -> RasterProfile` and `ProfileError`.
- `compare_profiles(a, b, *, require_identical_grid=False)`.
- Private parsing, optional-numeric-tag and comparison helpers.

The parser accepts nonempty bytes only. It opens them with Rasterio
`MemoryFile`, restricted to the `GTiff` driver; it never receives or constructs
a remote URL. PAM and directory scanning are disabled. No handwritten TIFF
parser, deprecated `is_tiled`, pixel operation or retrieval fallback is used.
Only whitelisted metadata fields are retained, not filenames or arbitrary tags.

| Profile field(s) | Meaning |
|---|---|
| `driver`, `crs` | GDAL driver and Rasterio CRS string (authority identifier where available, otherwise WKT) |
| `transform` | Six affine coefficients `(a,b,c,d,e,f)`; no homogeneous matrix tail |
| `bounds` | Structural `(left,bottom,right,top)` in CRS coordinate units |
| `width`, `height`, `band_count`, `dtype`, `nodata` | Structural fields; currently exactly one band is supported; absent nodata stays None, NaN nodata is permitted |
| `pixel_size` | Derived immutable property `(hypot(a,d), hypot(b,e))`: positive column/row vector lengths in CRS units, not necessarily metres |
| `rotation_shear` | Derived immutable property `(b,d)`; the signed Y step remains available as affine `e` |
| `block_shape`, `overview_factors` | `(rows,columns)` and band-1 overview decimation factors; no tile/overview pixel reads |
| `compression`, `predictor` | IMAGE_STRUCTURE tags, preserving absence as None |
| `band_description`, `units` | Rasterio band metadata; absent formal units stay None |
| `scale`, `offset` | Rasterio band scale/offset values, including its API defaults of 1/0; no conversion applied and no claim these defaults were explicitly tagged |
| `polarization`, `sar_pixel_content`, `source_scale` | Band tags `Polarization`, `SARPixelContent`, `Scale`, or None |
| `orbit_direction`, `look_direction`, `product_type` | Corresponding dataset tags, or None |
| `incidence_near_angle`, `incidence_far_angle` | Optional finite numeric incidence tags; malformed present values fail |

`dataset.width/height` are authoritative; legacy `ColumnCount/RowCount` are
not used. No formal unit or gamma-naught/dB conversion is invented from the
linear-intensity tags. Pixel size and shear are derived from the stored affine
to avoid contradictory duplicate fields; they are properties, not additional
fields in `dataclasses.asdict`.

Empty, non-TIFF, insufficient-prefix, missing-CRS, multiband and malformed
metadata inputs fail with `ProfileError`. A missing geotransform warning is
also an error, rather than accepting Rasterio's identity-transform fallback.
Dimensions, finite transform/bounds, nonzero determinant, positive block shape,
overview factors and finite scale/offset are checked. Low-level exceptions
become a deterministic error without a generated `/vsimem` path or displayed
exception chain. Invalid bytes never trigger a larger fetch.

## Mechanical compatibility and tolerance

Every criterion has `passed` and a reason. Separate verdicts cover CRS equality
(Rasterio CRS equivalence), pixel-vector sizes, north-up/zero rotation, dtype,
nodata, one-band expectations, grid lattice, and exact grid identity.
Absent nodata equals absent nodata; paired NaNs are treated as equal nodata.
Missing nodata does not equal a numeric sentinel.

This version supports north-up alignment only: `a > 0`, `e < 0`, `b = d = 0`,
all affine values finite. Even identical rotated/south-up grids fail the
rotation criterion explicitly. Pixel sizes may differ by at most eight ULPs
at the larger size, permitting only representational roundoff.

Offsets are B relative to A, using **signed** affine coefficients:

```text
dx_pixels = (c_b - c_a) / a_a
dy_pixels = (f_b - f_a) / e_a
```

For each axis, the absolute tolerance in pixels is:

```text
8 * ulp(max(abs(origin_a), abs(origin_b))) / abs(pixel_step)
    + 8 * ulp(offset_pixels)
```

This allows a handful of coordinate-subtraction/division rounding steps, not
resampling or a scientific position tolerance. Around Hidalgo's coordinates
with 10 m pixels it is approximately 1e-10 pixels in X and 4e-10 in Y for small
offsets. Offsets must lie within that allowance of an integer; nonfinite
offsets and allowances exceeding **1e-8 pixel** are rejected as numerically
unresolvable. This ceiling is a precision rejection rule, not an allowance
substituted for the smaller ULP-derived tolerance. A 5 m shift at 10 m spacing
is rejected, never rounded to fit.
Actual floating offsets, accepted integer offsets (or None), and tolerances
are included in the report. CRS/size/rotation failure leaves offsets undefined.

`compatible` derives from the seven basic criteria. Cross-acquisition grids
can differ in extent/dimensions while occupying the same lattice. For VV/VH,
the caller sets `require_identical_grid=True`, adding exact dimensions,
transform and CRS equality. Thus a 10 m shift passes lattice alignment but
fails VV/VH grid identity. Callers must establish that assets are the intended
same-acquisition VV/VH pair; this module does not infer acquisition identity.
No compatibility verdict establishes valid observations or scientific suitability.

## Real fixture and parsed values

Fixture: `tests/fixtures/rasters/hanna_20200727_vv_prefix.tiff`.
Size: **131,072 bytes**. SHA-256:

```text
1a2ab8b669b5a5b0598609077db36081a86e18db2ffbf34ae07e99023f5bd781
```

Source item: `S1A_IW_GRDH_1SDV_20200727T122412_20200727T122441_033640_03E61B_rtc`,
VV, from the committed Hanna manifest's preferred event record. Unsigned href:

```text
https://sentinel1euwestrtc.blob.core.windows.net/sentinel1-grd-rtc/GRD/2020/7/27/IW/DV/S1A_IW_GRDH_1SDV_20200727T122412_20200727T122441_033640_03E61B_60B6/measurement/iw-vv.rtc.tiff
```

Explicit one-time fixture acquisition on 2026-09-07 used the already-verified
anonymous collection SAS endpoint, keeping its token and signed request only
in memory. One GET requested `bytes=0-131071`, received 206 and
`Content-Range: bytes 0-131071/2062396392`; the body read was capped at 131,072
bytes. The 349-byte SAS response was not persisted. Total measured response
bodies: 131,421 bytes, excluding protocol overhead. The raw prefix hash was
required to match C1 **before writing**; no extra asset or full object was fetched.
Only the exact TIFF bytes are retained, with no added metadata or credential.
Source attribution/reuse follows the Sentinel RTC entry in
[the data-source register](../data-sources.md) (CC BY 4.0).

| Parsed field | Pinned real-fixture result |
|---|---|
| Driver / CRS | GTiff / EPSG:32614 |
| Transform | `(10.0, 0.0, 578140.0, 0.0, -10.0, 2993250.0)` |
| Bounds | `(578140.0, 2757000.0, 860500.0, 2993250.0)` |
| Width / height / count | 28236 / 23625 / 1 |
| Dtype / nodata | float32 / -32768.0 |
| Pixel size / rotation-shear | `(10.0,10.0)` / `(0.0,0.0)` |
| Blocks / overviews | `(512,512)` / `(2,4,8,16,32,64)` |
| Compression / predictor | DEFLATE / 3 |
| Description | Sentinel-1 Calibrated and Terrain Corrected VV |
| Formal units / scale / offset | None / 1.0 / 0.0 |
| Polarization / SARPixelContent / source Scale | VV / intensity / linear |
| Orbit / look / product | Descending / Right / ORTHO |
| Near / far incidence | 30.743120 / 45.974335 |

## Tests, validation and limits

`tests/test_raster_profile.py`: **33 passed**. Tests pin fixture integrity and
all values above, absent tags, parser errors, identical/shifted/fractional
grids, correct negative-Y sign, reversal/determinism, ULP-scale allowance,
individual incompatibilities, unsupported rotation, exact VV/VH geometry,
None/NaN nodata and output free of remote URLs or `/vsimem` paths.

All C2 tests run under the existing autouse socket blocker, unchanged. One
test explicitly verifies a Python socket connection raises before parsing the
fixture successfully. This proves ordinary Python network blocking, not a
native GDAL firewall; C1's isolation limitations still apply. Restricting to
GTiff and handing GDAL only in-memory bytes avoids VRT external-source dispatch.

Validation: **199 passed, 6 live tests deselected** in the full offline suite;
Ruff lint/format passed; strict mypy passed across **22 files**; `pip check`
passed; `git diff --check` passed. Existing Rasterio 1.5.1 / GDAL 3.12.4 /
PROJ 9.8.1 dependencies and scoped typing override were unchanged.

Remaining limits: one real asset prefix/runtime combination is tested, not all
12 assets or Python 3.11/Rasterio 1.4. Other TIFF layouts may need larger prefixes,
which fail here rather than fetch. The parser is deliberately single-band and
the comparator north-up only. Synthetic pairing tests prove mechanics, not an
independently acquired VH pair. Low-level Rasterio imports remain untyped;
project strict typing stays enabled. No production network-isolation guarantee
for arbitrary GDAL native transports or pixel/mask behavior is claimed.

No implementation blocker remains. C2 stops here without a commit or Stage D.

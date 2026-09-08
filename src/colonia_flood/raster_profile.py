"""Pure single-band GeoTIFF metadata parsing and mechanical grid comparison."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import rasterio
from rasterio.crs import CRS
from rasterio.errors import NotGeoreferencedWarning, RasterioError
from rasterio.io import MemoryFile


class ProfileError(ValueError):
    """Input bytes cannot supply the required structural or tagged metadata."""


@dataclass(frozen=True)
class RasterProfile:
    driver: str
    crs: str
    transform: tuple[float, float, float, float, float, float]
    bounds: tuple[float, float, float, float]
    width: int
    height: int
    band_count: int
    dtype: str
    nodata: float | None
    block_shape: tuple[int, int]
    overview_factors: tuple[int, ...]
    compression: str | None = None
    predictor: int | None = None
    band_description: str | None = None
    units: str | None = None
    scale: float = 1.0
    offset: float = 0.0
    polarization: str | None = None
    sar_pixel_content: str | None = None
    source_scale: str | None = None
    orbit_direction: str | None = None
    look_direction: str | None = None
    incidence_near_angle: float | None = None
    incidence_far_angle: float | None = None
    product_type: str | None = None

    @property
    def pixel_size(self) -> tuple[float, float]:
        """Positive lengths of the affine column and row vectors, in CRS units."""
        a, b, _, d, e, _ = self.transform
        return math.hypot(a, d), math.hypot(b, e)

    @property
    def rotation_shear(self) -> tuple[float, float]:
        return self.transform[1], self.transform[3]


def _optional_float(value: str | None, field: str) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ProfileError(f"{field} must be finite when present")
    return result


def parse_profile(header_bytes: bytes) -> RasterProfile:
    """Parse already-acquired bytes; never retrieve data or read raster pixels.

    Only GTiff is enabled, preventing VRT/other drivers from resolving external
    datasets. CRS and one band are required. Missing scientific tags stay None.
    Rasterio's scale/offset defaults are metadata API values, not conversions.
    """
    if not isinstance(header_bytes, bytes) or not header_bytes:
        raise ProfileError("expected nonempty raster bytes")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", NotGeoreferencedWarning)
            return _parse_geotiff(header_bytes)
    except ProfileError:
        raise
    except (
        RasterioError,
        NotGeoreferencedWarning,
        ValueError,
        TypeError,
        IndexError,
        OverflowError,
    ):
        # GDAL errors may contain generated /vsimem names. Keep the public error
        # deterministic, without a path-bearing chained exception or fallback.
        raise ProfileError(
            "cannot parse GeoTIFF profile: invalid metadata or insufficient bytes"
        ) from None


def _parse_geotiff(header_bytes: bytes) -> RasterProfile:
    with (
        rasterio.Env(GDAL_PAM_ENABLED="NO", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"),
        MemoryFile(header_bytes) as memory,
        memory.open(driver="GTiff") as dataset,
    ):
        if dataset.crs is None:
            raise ProfileError("raster CRS is required")
        if dataset.count != 1:
            raise ProfileError("expected exactly one raster band")
        affine = dataset.transform
        transform = (
            float(affine.a),
            float(affine.b),
            float(affine.c),
            float(affine.d),
            float(affine.e),
            float(affine.f),
        )
        bounds = (
            float(dataset.bounds.left),
            float(dataset.bounds.bottom),
            float(dataset.bounds.right),
            float(dataset.bounds.top),
        )
        if (
            dataset.width <= 0
            or dataset.height <= 0
            or not all(math.isfinite(v) for v in (*transform, *bounds))
            or affine.a * affine.e - affine.b * affine.d == 0
            or bounds[0] >= bounds[2]
            or bounds[1] >= bounds[3]
        ):
            raise ProfileError("invalid raster dimensions, transform or bounds")
        tags = dataset.tags()
        band_tags = dataset.tags(1)
        structure = dataset.tags(ns="IMAGE_STRUCTURE")
        block_shape = tuple(int(v) for v in dataset.block_shapes[0])
        overviews = tuple(int(v) for v in dataset.overviews(1))
        if (
            len(block_shape) != 2
            or min(block_shape) <= 0
            or any(v <= 1 for v in overviews)
        ):
            raise ProfileError("invalid block shape or overview factors")
        scale, offset = float(dataset.scales[0]), float(dataset.offsets[0])
        if not all(math.isfinite(v) for v in (scale, offset)):
            raise ProfileError("invalid scale/offset metadata")
        return RasterProfile(
            driver=str(dataset.driver),
            crs=str(dataset.crs.to_string()),
            transform=transform,
            bounds=bounds,
            width=int(dataset.width),
            height=int(dataset.height),
            band_count=1,
            dtype=str(dataset.dtypes[0]),
            nodata=None if dataset.nodata is None else float(dataset.nodata),
            block_shape=(block_shape[0], block_shape[1]),
            overview_factors=overviews,
            compression=structure.get("COMPRESSION"),
            predictor=int(structure["PREDICTOR"]) if "PREDICTOR" in structure else None,
            band_description=dataset.descriptions[0],
            units=dataset.units[0],
            scale=scale,
            offset=offset,
            polarization=band_tags.get("Polarization"),
            sar_pixel_content=band_tags.get("SARPixelContent"),
            source_scale=band_tags.get("Scale"),
            orbit_direction=tags.get("OrbitDirection"),
            look_direction=tags.get("LookDirection"),
            incidence_near_angle=_optional_float(
                tags.get("IncidenceNearAngle"), "incidence near angle"
            ),
            incidence_far_angle=_optional_float(
                tags.get("IncidenceFarAngle"), "incidence far angle"
            ),
            product_type=tags.get("ProductType"),
        )


@dataclass(frozen=True)
class Criterion:
    passed: bool
    reason: str


@dataclass(frozen=True)
class CompatibilityReport:
    crs: Criterion
    pixel_size: Criterion
    rotation: Criterion
    dtype: Criterion
    nodata: Criterion
    band_count: Criterion
    grid_lattice: Criterion
    identical_grid: Criterion
    offsets_pixels: tuple[float, float] | None
    integer_pixel_offsets: tuple[int, int] | None
    offset_tolerance_pixels: tuple[float, float] | None
    require_identical_grid: bool

    @property
    def compatible(self) -> bool:
        criteria = (
            self.crs,
            self.pixel_size,
            self.rotation,
            self.dtype,
            self.nodata,
            self.band_count,
            self.grid_lattice,
        )
        return all(c.passed for c in criteria) and (
            not self.require_identical_grid or self.identical_grid.passed
        )


def _criterion(passed: bool, yes: str, no: str) -> Criterion:
    return Criterion(passed, yes if passed else no)


def _size_equal(a: float, b: float) -> bool:
    return (
        math.isfinite(a)
        and math.isfinite(b)
        and a > 0
        and b > 0
        and (abs(a - b) <= 8 * math.ulp(max(a, b)))
    )


def compare_profiles(
    a: RasterProfile, b: RasterProfile, *, require_identical_grid: bool = False
) -> CompatibilityReport:
    """Compare mechanics, not observation validity or scientific suitability.

    North-up grids only: a>0, e<0, b=d=0. Offsets are B relative to A using
    signed affine a/e coefficients. Eight coordinate ULPs divided by pixel
    size, plus eight offset ULPs, cover subtraction/division roundoff only.
    If that allowance exceeds 1e-8 pixel, precision is insufficient: fail
    alignment rather than widening the allowed fraction of a pixel.
    VV/VH callers set require_identical_grid=True for exact geometry equality;
    callers, not this function, establish acquisition/polarization identity.
    """
    crs_equal = CRS.from_user_input(a.crs) == CRS.from_user_input(b.crs)
    sizes_equal = all(
        _size_equal(x, y) for x, y in zip(a.pixel_size, b.pixel_size, strict=True)
    )
    north_up = all(
        p.rotation_shear == (0.0, 0.0)
        and p.transform[0] > 0
        and p.transform[4] < 0
        and all(math.isfinite(v) for v in p.transform)
        for p in (a, b)
    )
    nodata_equal = a.nodata == b.nodata or (
        a.nodata is not None
        and b.nodata is not None
        and math.isnan(a.nodata)
        and math.isnan(b.nodata)
    )
    offsets = None
    integer_offsets = None
    tolerances = None
    lattice = Criterion(False, "requires equal CRS/pixel sizes and north-up transforms")
    if crs_equal and sizes_equal and north_up:
        dx = (b.transform[2] - a.transform[2]) / a.transform[0]
        dy = (b.transform[5] - a.transform[5]) / a.transform[4]
        offsets = (dx, dy)
        tolerances = tuple(
            8 * math.ulp(max(abs(origin_a), abs(origin_b))) / abs(step)
            + 8 * math.ulp(delta)
            for origin_a, origin_b, step, delta in (
                (a.transform[2], b.transform[2], a.transform[0], dx),
                (a.transform[5], b.transform[5], a.transform[4], dy),
            )
        )
        aligned = all(
            math.isfinite(delta)
            and tolerance <= 1e-8
            and abs(delta - round(delta)) <= tolerance
            for delta, tolerance in zip(offsets, tolerances, strict=True)
        )
        if aligned:
            integer_offsets = (round(dx), round(dy))
        lattice = _criterion(
            aligned,
            "whole-pixel origin offsets",
            "fractional offsets or insufficient numerical precision",
        )
    identical = (
        crs_equal
        and a.transform == b.transform
        and (a.width, a.height) == (b.width, b.height)
    )
    return CompatibilityReport(
        crs=_criterion(crs_equal, "equal CRS", "different CRS"),
        pixel_size=_criterion(
            sizes_equal, "equal pixel sizes within eight ULPs", "different pixel sizes"
        ),
        rotation=_criterion(
            north_up,
            "both north-up without rotation/shear",
            "requires positive X, negative Y and zero rotation/shear",
        ),
        dtype=_criterion(a.dtype == b.dtype, "equal dtype", "different dtype"),
        nodata=_criterion(
            nodata_equal, "equal nodata (including paired NaNs)", "different nodata"
        ),
        band_count=_criterion(
            a.band_count == b.band_count == 1,
            "both single-band",
            "expected one band per asset",
        ),
        grid_lattice=lattice,
        identical_grid=_criterion(
            identical,
            "equal dimensions, transform and CRS",
            "dimensions, transform or CRS differ",
        ),
        offsets_pixels=offsets,
        integer_pixel_offsets=integer_offsets,
        offset_tolerance_pixels=None
        if tolerances is None
        else (tolerances[0], tolerances[1]),
        require_identical_grid=require_identical_grid,
    )

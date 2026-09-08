"""Offline real-prefix parser checks and hand-computable grid comparisons."""

from __future__ import annotations

import hashlib
import math
import socket
from dataclasses import asdict, replace
from typing import Any

import pytest
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rasterio.transform import Affine

from colonia_flood.raster_profile import (
    ProfileError,
    RasterProfile,
    compare_profiles,
    parse_profile,
)

from .conftest import REPO_ROOT

PREFIX = REPO_ROOT / "tests/fixtures/rasters/hanna_20200727_vv_prefix.tiff"


@pytest.fixture
def grid() -> RasterProfile:
    return RasterProfile(
        driver="GTiff",
        crs="EPSG:32614",
        transform=(10.0, 0.0, 600000.0, 0.0, -10.0, 2900000.0),
        bounds=(600000.0, 2899000.0, 6001000.0, 2900000.0),
        width=100,
        height=100,
        band_count=1,
        dtype="float32",
        nodata=-32768.0,
        block_shape=(16, 16),
        overview_factors=(),
        polarization="VV",
    )


def shifted(p: RasterProfile, x: float, y: float) -> RasterProfile:
    a, b, c, d, e, f = p.transform
    west, south, east, north = p.bounds
    return replace(
        p,
        transform=(a, b, c + x, d, e, f + y),
        bounds=(west + x, south + y, east + x, north + y),
    )


def test_real_hanna_prefix_metadata() -> None:
    raw = PREFIX.read_bytes()
    assert len(raw) == 131072
    assert (
        hashlib.sha256(raw).hexdigest()
        == "1a2ab8b669b5a5b0598609077db36081a86e18db2ffbf34ae07e99023f5bd781"
    )
    p = parse_profile(raw)
    assert p == parse_profile(raw)
    assert p.driver == "GTiff" and p.crs == "EPSG:32614"
    assert p.transform == (10.0, 0.0, 578140.0, 0.0, -10.0, 2993250.0)
    assert p.bounds == (578140.0, 2757000.0, 860500.0, 2993250.0)
    assert (p.width, p.height, p.band_count, p.dtype, p.nodata) == (
        28236,
        23625,
        1,
        "float32",
        -32768.0,
    )
    assert p.pixel_size == (10.0, 10.0) and p.rotation_shear == (0.0, 0.0)
    assert p.block_shape == (512, 512)
    assert p.overview_factors == (2, 4, 8, 16, 32, 64)
    assert p.compression == "DEFLATE" and p.predictor == 3
    assert p.polarization == "VV" and p.sar_pixel_content == "intensity"
    assert p.source_scale == "linear" and p.units is None
    assert p.band_description == "Sentinel-1 Calibrated and Terrain Corrected VV"
    assert p.scale == 1.0 and p.offset == 0.0
    assert p.orbit_direction == "Descending" and p.look_direction == "Right"
    assert p.incidence_near_angle == 30.743120
    assert p.incidence_far_angle == 45.974335 and p.product_type == "ORTHO"
    assert not any(
        s in repr(asdict(p)) for s in ["/vsimem", "http://", "https://", "sig="]
    )


def synthetic_bytes(**updates: Any) -> bytes:
    options = dict(
        driver="GTiff",
        width=16,
        height=16,
        count=1,
        dtype="float32",
        crs="EPSG:32614",
        transform=Affine(10, 0, 600000, 0, -10, 2900000),
    )
    options.update(updates)
    with MemoryFile() as memory:
        with memory.open(**options):
            pass  # metadata only; no pixel write/read
        return bytes(memory.read())


def test_missing_scientific_tags_stay_absent() -> None:
    p = parse_profile(synthetic_bytes())
    assert p.units is None and p.nodata is None
    assert p.polarization is None and p.source_scale is None
    assert p.incidence_near_angle is None and p.sar_pixel_content is None


@pytest.mark.parametrize(
    "raw",
    [b"", b"not a TIFF", b"II*\x00", b'<VRTDataset rasterXSize="1" rasterYSize="1"/>'],
)
def test_bad_bytes_fail_without_exposing_memory_paths(raw: bytes) -> None:
    with pytest.raises(ProfileError) as caught:
        parse_profile(raw)
    assert "/vsimem" not in str(caught.value)


def test_insufficient_prefix_fails() -> None:
    with pytest.raises(ProfileError):
        parse_profile(PREFIX.read_bytes()[:128])


@pytest.mark.parametrize(
    "options",
    [{"crs": None}, {"count": 2}, {"transform": Affine(0, 0, 600000, 0, 0, 2900000)}],
)
def test_structural_defects_fail(options: dict[str, Any]) -> None:
    with pytest.raises(ProfileError):
        parse_profile(synthetic_bytes(**options))


def test_missing_transform_is_not_silently_replaced_with_identity() -> None:
    with pytest.warns(NotGeoreferencedWarning):
        raw = synthetic_bytes(transform=None)
    with pytest.raises(ProfileError):
        parse_profile(raw)


def test_invalid_optional_numeric_tag_fails() -> None:
    # Create the defect through Rasterio, not handwritten TIFF bytes.
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=16,
            height=16,
            count=1,
            dtype="float32",
            crs="EPSG:32614",
            transform=Affine(10, 0, 600000, 0, -10, 2900000),
        ) as ds:
            ds.update_tags(IncidenceNearAngle="not-a-number")
        raw = bytes(memory.read())
    with pytest.raises(ProfileError):
        parse_profile(raw)


@pytest.mark.parametrize(
    ("x", "y", "offsets"),
    [(0, 0, (0, 0)), (10, 0, (1, 0)), (30, -20, (3, 2)), (-30, 20, (-3, -2))],
)
def test_integer_offsets_and_reversal(
    grid: RasterProfile, x: float, y: float, offsets: tuple[int, int]
) -> None:
    other = shifted(grid, x, y)
    report = compare_profiles(grid, other)
    assert report.compatible and report.grid_lattice.passed
    assert report.integer_pixel_offsets == offsets
    assert report == compare_profiles(grid, other)
    reverse = compare_profiles(other, grid)
    assert reverse.compatible
    assert reverse.integer_pixel_offsets == tuple(-v for v in offsets)


@pytest.mark.parametrize(("x", "y"), [(5, 0), (0, 5), (15, -25)])
def test_fractional_offsets_fail(grid: RasterProfile, x: float, y: float) -> None:
    report = compare_profiles(grid, shifted(grid, x, y))
    assert not report.compatible and not report.grid_lattice.passed
    assert report.integer_pixel_offsets is None
    assert report.offsets_pixels == (x / 10, y / -10)


def test_alignment_tolerance_is_only_roundoff(grid: RasterProfile) -> None:
    tiny = shifted(grid, 10 + math.ulp(600000), -20 - math.ulp(2900000))
    assert compare_profiles(grid, tiny).integer_pixel_offsets == (1, 2)
    assert not compare_profiles(grid, shifted(grid, 10.00001, 0)).grid_lattice.passed
    assert compare_profiles(grid, tiny).offset_tolerance_pixels is not None


def test_coarse_coordinate_precision_cannot_hide_fractional_offsets(
    grid: RasterProfile,
) -> None:
    coarse = shifted(grid, 1e15, 0)
    report = compare_profiles(coarse, shifted(coarse, 1, 0))
    assert not report.grid_lattice.passed
    assert report.integer_pixel_offsets is None


@pytest.mark.parametrize(
    ("updates", "criterion"),
    [
        ({"crs": "EPSG:32615"}, "crs"),
        ({"transform": (20.0, 0.0, 600000.0, 0.0, -10.0, 2900000.0)}, "pixel_size"),
        ({"nodata": -9999.0}, "nodata"),
        ({"dtype": "uint16"}, "dtype"),
        ({"band_count": 2}, "band_count"),
        ({"transform": (10.0, 1.0, 600000.0, 0.0, -10.0, 2900000.0)}, "rotation"),
        ({"transform": (10.0, 0.0, 600000.0, 0.0, 10.0, 2900000.0)}, "rotation"),
    ],
)
def test_criteria_fail_independently(
    grid: RasterProfile, updates: dict[str, Any], criterion: str
) -> None:
    report = compare_profiles(grid, replace(grid, **updates))
    assert not report.compatible
    verdict = getattr(report, criterion)
    assert not verdict.passed and verdict.reason


def test_matching_rotation_is_still_unsupported(grid: RasterProfile) -> None:
    rotated = replace(grid, transform=(10.0, 1.0, 600000.0, 0.0, -10.0, 2900000.0))
    report = compare_profiles(rotated, rotated)
    assert not report.rotation.passed and report.offsets_pixels is None


def test_vv_vh_identical_grid_requirement(grid: RasterProfile) -> None:
    vh = replace(grid, polarization="VH")
    assert compare_profiles(grid, vh, require_identical_grid=True).compatible
    shifted_vh = shifted(vh, 10, 0)
    assert compare_profiles(grid, shifted_vh).compatible
    report = compare_profiles(grid, shifted_vh, require_identical_grid=True)
    assert report.grid_lattice.passed and not report.identical_grid.passed
    assert not report.compatible
    assert not compare_profiles(
        grid, replace(vh, width=101), require_identical_grid=True
    ).compatible
    assert not compare_profiles(
        grid, replace(vh, crs="EPSG:32615"), require_identical_grid=True
    ).compatible


@pytest.mark.parametrize("nodata", [None, float("nan")])
def test_matching_absent_or_nan_nodata(
    grid: RasterProfile, nodata: float | None
) -> None:
    a = replace(grid, nodata=nodata)
    b = replace(grid, nodata=nodata)
    assert compare_profiles(a, b).nodata.passed
    assert not compare_profiles(a, grid).nodata.passed


def test_parser_runs_under_existing_socket_block() -> None:
    with (
        socket.socket() as sock,
        pytest.raises(AssertionError, match="offline test attempted"),
    ):
        sock.connect(("127.0.0.1", 1))
    assert parse_profile(PREFIX.read_bytes()).width == 28236

"""End-to-end runs through the CLI with the fake client (plan cases 19, 22, 26)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from colonia_flood.cli import (
    EXIT_EMPTY_WINDOW,
    EXIT_ERROR,
    EXIT_OK,
    build_parser,
    main,
    run,
)
from colonia_flood.manifest import MANIFEST_FILENAME
from colonia_flood.run_record import RUN_RECORD_FILENAME
from colonia_flood.stac_client import CatalogError

from .conftest import REAL_CONFIG_PATH, FakeSearchClient

FIXED_CLOCK = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)


def clock_at(moment: datetime) -> Callable[[], datetime]:
    return lambda: moment


DEFAULT_TEST_CLOCK = clock_at(FIXED_CLOCK)


def invoke(
    tmp_path: Path,
    client: FakeSearchClient,
    *,
    extra: list[str] | None = None,
    clock: Callable[[], datetime] = DEFAULT_TEST_CLOCK,
) -> int:
    args = build_parser().parse_args(
        [
            "--config",
            str(REAL_CONFIG_PATH),
            "--out-dir",
            str(tmp_path),
            *(extra or []),
        ]
    )
    return run(args, client=client, clock=clock, repo_root=tmp_path)


# --- case 26 ----------------------------------------------------------------


def test_cli_writes_both_event_directories(
    tmp_path: Path, fake_client: FakeSearchClient
) -> None:
    assert invoke(tmp_path, fake_client) == EXIT_OK

    for event_id, expected in (("hanna_2020", 14), ("march_2025", 12)):
        manifest_path = tmp_path / event_id / MANIFEST_FILENAME
        run_path = tmp_path / event_id / RUN_RECORD_FILENAME
        assert manifest_path.is_file()
        assert run_path.is_file()

        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert document["event"]["event_id"] == event_id
        assert document["counts"]["acquisitions"] == expected
        assert document["counts"]["event"] == 1

        record = json.loads(run_path.read_text(encoding="utf-8"))
        assert record["retrieved_at_utc"] == "2026-09-02T12:00:00.000000Z"
        assert record["acquisition_count"] == expected
        assert record["config_sha256"] == document["config_sha256"]
        assert len(record["manifest_sha256"]) == 64


def test_single_event_selection(tmp_path: Path, fake_client: FakeSearchClient) -> None:
    assert invoke(tmp_path, fake_client, extra=["--event", "hanna_2020"]) == EXIT_OK
    assert (tmp_path / "hanna_2020").is_dir()
    assert not (tmp_path / "march_2025").exists()


def test_event_order_follows_configuration_not_argv(
    tmp_path: Path, fake_client: FakeSearchClient
) -> None:
    assert (
        invoke(
            tmp_path,
            fake_client,
            extra=["--event", "march_2025", "--event", "hanna_2020"],
        )
        == EXIT_OK
    )
    queried = [call["start"].year for call in fake_client.calls]
    assert queried[:2] == [2020, 2020]


def test_unknown_event_id_exits_with_an_error(
    tmp_path: Path, fake_client: FakeSearchClient
) -> None:
    args = build_parser().parse_args(
        [
            "--config",
            str(REAL_CONFIG_PATH),
            "--out-dir",
            str(tmp_path),
            "--event",
            "nope",
        ]
    )
    with pytest.raises(Exception, match="unknown event id"):
        run(args, client=fake_client, repo_root=tmp_path)


def test_dry_run_writes_nothing(tmp_path: Path, fake_client: FakeSearchClient) -> None:
    assert invoke(tmp_path, fake_client, extra=["--dry-run"]) == EXIT_OK
    assert list(tmp_path.iterdir()) == []
    assert len(fake_client.calls) == 4


# --- case 18 (end-to-end) ---------------------------------------------------


def test_two_runs_at_different_clocks_leave_the_manifest_byte_identical(
    tmp_path: Path, fake_client: FakeSearchClient
) -> None:
    manifest_path = tmp_path / "hanna_2020" / MANIFEST_FILENAME
    run_path = tmp_path / "hanna_2020" / RUN_RECORD_FILENAME
    select = ["--event", "hanna_2020"]

    invoke(tmp_path, fake_client, extra=select, clock=clock_at(FIXED_CLOCK))
    first_manifest = manifest_path.read_bytes()
    first_run = run_path.read_bytes()

    invoke(
        tmp_path,
        fake_client,
        extra=select,
        clock=clock_at(datetime(2027, 1, 1, 3, 4, 5, tzinfo=UTC)),
    )

    assert manifest_path.read_bytes() == first_manifest
    assert run_path.read_bytes() != first_run
    assert (
        json.loads(run_path.read_text(encoding="utf-8"))["manifest_sha256"]
        == (json.loads(first_run.decode("utf-8"))["manifest_sha256"])
    )


# --- case 19 ----------------------------------------------------------------


def test_catalog_failure_leaves_an_existing_manifest_untouched(
    tmp_path: Path, fake_client: FakeSearchClient
) -> None:
    select = ["--event", "hanna_2020"]
    invoke(tmp_path, fake_client, extra=select)
    manifest_path = tmp_path / "hanna_2020" / MANIFEST_FILENAME
    original = manifest_path.read_bytes()

    failing = FakeSearchClient(error=CatalogError("connection timed out"))
    with pytest.raises(CatalogError):
        invoke(tmp_path, failing, extra=select)

    assert manifest_path.read_bytes() == original
    temp_files = [p.name for p in (tmp_path / "hanna_2020").iterdir()]
    assert sorted(temp_files) == [MANIFEST_FILENAME, RUN_RECORD_FILENAME]


def test_main_converts_catalog_errors_into_exit_code_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: Any, **kwargs: Any) -> Any:
        raise CatalogError("connection timed out")

    monkeypatch.setattr("colonia_flood.cli.query_event", explode)
    exit_code = main(["--config", str(REAL_CONFIG_PATH), "--out-dir", str(tmp_path)])
    assert exit_code == EXIT_ERROR
    assert list(tmp_path.iterdir()) == []


def test_main_converts_config_errors_into_exit_code_two(tmp_path: Path) -> None:
    exit_code = main(
        ["--config", str(tmp_path / "absent.toml"), "--out-dir", str(tmp_path)]
    )
    assert exit_code == EXIT_ERROR


# --- case 21 ----------------------------------------------------------------


def test_empty_window_writes_a_manifest_and_exits_non_zero(tmp_path: Path) -> None:
    empty = FakeSearchClient({})
    exit_code = invoke(tmp_path, empty, extra=["--event", "hanna_2020"])

    assert exit_code == EXIT_EMPTY_WINDOW
    document = json.loads(
        (tmp_path / "hanna_2020" / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assert document["acquisitions"] == []


def test_pre_event_only_result_still_exits_non_zero(
    tmp_path: Path, all_window_responses: dict[Any, Any]
) -> None:
    from datetime import date

    partial = FakeSearchClient(
        {date(2020, 6, 24): all_window_responses[date(2020, 6, 24)]}
    )
    assert (
        invoke(tmp_path, partial, extra=["--event", "hanna_2020"]) == EXIT_EMPTY_WINDOW
    )


# --- case 22 ----------------------------------------------------------------


def test_no_raster_is_downloaded_and_only_json_is_written(
    tmp_path: Path, fake_client: FakeSearchClient
) -> None:
    invoke(tmp_path, fake_client)

    # The seam recorded no URL fetch of any kind, asset href or otherwise.
    assert fake_client.requested_urls == []

    written = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    assert written, "expected the run to write something"
    assert {p.suffix for p in written} == {".json"}

    total_bytes = sum(p.stat().st_size for p in written)
    assert total_bytes < 1_000_000, f"output tree is {total_bytes} bytes"

    # No file resembles a raster, by extension or by magic bytes.
    for path in written:
        head = path.read_bytes()[:4]
        assert head[:2] != b"II" and head[:2] != b"MM"  # TIFF byte-order marks


def test_asset_hrefs_are_recorded_but_never_requested(
    tmp_path: Path, fake_client: FakeSearchClient
) -> None:
    invoke(tmp_path, fake_client, extra=["--event", "hanna_2020"])
    document = json.loads(
        (tmp_path / "hanna_2020" / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )

    hrefs = {a["vv_asset_href"] for a in document["acquisitions"]}
    assert all(href.endswith(".tiff") for href in hrefs)
    assert fake_client.requested_urls == []


# --- output hygiene ---------------------------------------------------------


def test_run_record_reports_library_versions_and_tool_version(
    tmp_path: Path, fake_client: FakeSearchClient
) -> None:
    invoke(tmp_path, fake_client, extra=["--event", "hanna_2020"])
    record = json.loads(
        (tmp_path / "hanna_2020" / RUN_RECORD_FILENAME).read_text(encoding="utf-8")
    )
    assert record["tool_version"] == "0.1.0"
    assert set(record["client_library_versions"]) == {
        "pystac-client",
        "pystac",
        "pydantic",
    }
    assert record["catalog_url"].startswith("https://")

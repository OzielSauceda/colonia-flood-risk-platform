"""Ordering, dedupe, determinism, and atomic writes (plan cases 14-25)."""

from __future__ import annotations

import copy
import json
import os
import random
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from colonia_flood.acquisitions import ReasonCode
from colonia_flood.events import EventsConfig
from colonia_flood.manifest import (
    build_manifest,
    collect_event,
    query_event,
    serialize,
    sha256_hex,
    write_atomic,
)
from colonia_flood.stac_client import (
    CatalogError,
    PystacSearchClient,
    format_interval,
    to_rfc3339,
)

from .conftest import FakeSearchClient, load_stac_fixture, with_property


def hanna_items() -> list[dict[str, Any]]:
    return load_stac_fixture("hanna_2020__pre_event") + load_stac_fixture(
        "hanna_2020__event"
    )


def manifest_bytes(
    items: list[dict[str, Any]], config: EventsConfig, *, event_id: str = "hanna_2020"
) -> bytes:
    result = collect_event(items, config=config, event_id=event_id)
    document = build_manifest(
        result, config=config, event_id=event_id, config_sha256="0" * 64
    )
    return serialize(document)


# --- baseline over real captured data ---------------------------------------


def test_real_fixtures_produce_the_expected_window_split(config: EventsConfig) -> None:
    result = collect_event(hanna_items(), config=config, event_id="hanna_2020")

    assert result.window_count("pre_event") == 13
    assert result.window_count("event") == 1
    assert result.excluded == []

    event_acq = next(a for a in result.acquisitions if a.window == "event")
    assert event_acq.datetime_utc == "2020-07-27T12:24:26.862631Z"
    assert event_acq.relative_orbit == 143
    assert event_acq.matches_preferred_orbit is True

    # The feasibility report's confirmed same-orbit pre-event scene must be present.
    same_orbit = [
        a
        for a in result.acquisitions
        if a.window == "pre_event" and a.matches_preferred_orbit
    ]
    assert {a.datetime_utc[:10] for a in same_orbit} == {"2020-07-03", "2020-07-15"}


# --- case 14 ----------------------------------------------------------------


def test_duplicate_item_ids_yield_one_acquisition_and_one_exclusion(
    config: EventsConfig,
) -> None:
    items = load_stac_fixture("hanna_2020__event")
    duplicated = items + copy.deepcopy(items)

    result = collect_event(
        load_stac_fixture("hanna_2020__pre_event") + duplicated,
        config=config,
        event_id="hanna_2020",
    )

    assert result.window_count("event") == 1
    duplicates = [
        e for e in result.excluded if e.reason_code is ReasonCode.DUPLICATE_ITEM_ID
    ]
    assert len(duplicates) == 1
    assert duplicates[0].item_id == items[0]["id"]


def test_duplicate_resolution_is_independent_of_input_order(
    config: EventsConfig,
) -> None:
    """Two distinct records sharing an id must resolve the same way either way round."""
    base = load_stac_fixture("hanna_2020__event")[0]
    variant = with_property(base, "platform", "SENTINEL-1B")

    forward = manifest_bytes(
        [*load_stac_fixture("hanna_2020__pre_event"), base, variant], config
    )
    reverse = manifest_bytes(
        [*load_stac_fixture("hanna_2020__pre_event"), variant, base], config
    )
    assert forward == reverse


# --- case 15 ----------------------------------------------------------------


def test_window_assignment_uses_the_timestamp_not_the_search_that_returned_it(
    config: EventsConfig,
) -> None:
    """An item returned by both searches still lands in exactly one window."""
    event_items = load_stac_fixture("hanna_2020__event")
    result = collect_event(
        load_stac_fixture("hanna_2020__pre_event") + event_items + event_items,
        config=config,
        event_id="hanna_2020",
    )
    windows = {a.item_id: a.window for a in result.acquisitions}
    assert windows[event_items[0]["id"]] == "event"
    assert sum(1 for a in result.acquisitions if a.item_id == event_items[0]["id"]) == 1


def test_item_outside_both_windows_is_excluded(config: EventsConfig) -> None:
    stray = with_property(
        load_stac_fixture("hanna_2020__event")[0],
        "datetime",
        "2020-07-25T00:00:00.000000Z",  # between the two windows
    )
    result = collect_event(
        [*hanna_items(), stray], config=config, event_id="hanna_2020"
    )
    reasons = {e.reason_code for e in result.excluded}
    assert ReasonCode.OUTSIDE_ALL_WINDOWS in reasons


def test_item_without_datetime_is_excluded(config: EventsConfig) -> None:
    broken = copy.deepcopy(load_stac_fixture("hanna_2020__event")[0])
    broken["id"] = "no-datetime-item"
    broken["properties"].pop("datetime")
    result = collect_event(
        [*hanna_items(), broken], config=config, event_id="hanna_2020"
    )
    assert any(
        e.reason_code is ReasonCode.MISSING_DATETIME and e.item_id == "no-datetime-item"
        for e in result.excluded
    )


# --- case 16 ----------------------------------------------------------------


def test_shuffled_input_produces_byte_identical_output(config: EventsConfig) -> None:
    items = hanna_items()
    ordered = manifest_bytes(items, config)

    rng = random.Random(20260902)
    for _ in range(5):
        shuffled = items[:]
        rng.shuffle(shuffled)
        assert manifest_bytes(shuffled, config) == ordered


def test_acquisitions_are_sorted_pre_event_then_event_then_time(
    config: EventsConfig,
) -> None:
    result = collect_event(hanna_items(), config=config, event_id="hanna_2020")
    windows = [a.window for a in result.acquisitions]
    assert windows == ["pre_event"] * 13 + ["event"]

    pre = [a.datetime_utc for a in result.acquisitions if a.window == "pre_event"]
    assert pre == sorted(pre)


def test_excluded_entries_are_sorted_by_item_id(config: EventsConfig) -> None:
    items = hanna_items()
    for suffix in ("zzz", "aaa", "mmm"):
        stray = copy.deepcopy(items[0])
        stray["id"] = f"stray-{suffix}"
        stray["properties"]["datetime"] = "2019-01-01T00:00:00.000000Z"
        items = [*items, stray]

    result = collect_event(items, config=config, event_id="hanna_2020")
    ids = [e.item_id for e in result.excluded]
    assert ids == sorted(ids)


# --- case 17 ----------------------------------------------------------------


def test_rerun_against_the_same_response_is_byte_identical(
    config: EventsConfig,
) -> None:
    first = manifest_bytes(hanna_items(), config)
    second = manifest_bytes(hanna_items(), config)
    assert first == second
    assert json.loads(first)["counts"]["acquisitions"] == 14


def test_rerun_replaces_rather_than_appends(
    tmp_path: Path, config: EventsConfig
) -> None:
    path = tmp_path / "acquisitions.json"
    payload = manifest_bytes(hanna_items(), config)
    write_atomic(path, payload)
    write_atomic(path, payload)
    assert path.read_bytes() == payload
    assert len(json.loads(path.read_text(encoding="utf-8"))["acquisitions"]) == 14


# --- case 18 ----------------------------------------------------------------


def test_manifest_contains_no_wall_clock_value(config: EventsConfig) -> None:
    text = manifest_bytes(hanna_items(), config).decode("utf-8")
    document = json.loads(text)

    assert "retrieved_at_utc" not in text
    # Every timestamp present must be one the configuration or the catalog fixed.
    for stamp in re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", text):
        assert stamp.startswith(("2020-", "2025-"))
    assert set(document["query"]["windows"]) == {"pre_event", "event"}


# --- case 20 ----------------------------------------------------------------


def test_malformed_response_raises_catalog_error_not_key_error(
    config: EventsConfig,
) -> None:
    unkeyed = copy.deepcopy(load_stac_fixture("hanna_2020__event")[0])
    unkeyed.pop("id")
    with pytest.raises(CatalogError):
        collect_event([unkeyed], config=config, event_id="hanna_2020")


def test_client_wraps_transport_failures_as_catalog_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pystac_client

    def explode(*args: Any, **kwargs: Any) -> Any:
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(pystac_client.Client, "open", explode)
    client = PystacSearchClient("https://example.invalid/api/stac/v1")
    with pytest.raises(CatalogError) as excinfo:
        client.search(
            collection="sentinel-1-rtc",
            bbox=[-1.0, -1.0, 1.0, 1.0],
            start=datetime(2020, 7, 26, tzinfo=UTC),
            end_exclusive=datetime(2020, 7, 29, tzinfo=UTC),
        )
    assert "catalog search failed" in str(excinfo.value)


# --- case 21 ----------------------------------------------------------------


def test_empty_result_still_produces_a_well_formed_manifest(
    config: EventsConfig,
) -> None:
    document = json.loads(manifest_bytes([], config).decode("utf-8"))
    assert document["acquisitions"] == []
    assert document["excluded"] == []
    assert document["counts"] == {
        "acquisitions": 0,
        "pre_event": 0,
        "event": 0,
        "excluded": 0,
    }
    assert document["event"]["event_id"] == "hanna_2020"


# --- case 23 ----------------------------------------------------------------


def test_manifest_carries_no_signed_urls_or_secrets(config: EventsConfig) -> None:
    text = manifest_bytes(hanna_items(), config).decode("utf-8")
    for token in ("sig=", "&st=", "&se=", "sv=", "skoid=", "subscription-key"):
        assert token not in text
    assert not re.search(r"(?i)authorization|bearer |api[-_]?key|secret", text)

    document = json.loads(text)
    for acquisition in document["acquisitions"]:
        assert "?" not in acquisition["vv_asset_href"]
        assert "?" not in acquisition["vh_asset_href"]


# --- case 24 ----------------------------------------------------------------


def test_manifest_carries_no_machine_specific_paths(config: EventsConfig) -> None:
    text = manifest_bytes(hanna_items(), config).decode("utf-8")
    assert not re.search(r"[A-Za-z]:\\\\", text)  # Windows drive letter
    assert "\\\\" not in text  # escaped backslash path separator
    assert "/Users/" not in text
    assert "/home/" not in text
    assert os.getlogin().lower() not in text.lower()


# --- case 25 ----------------------------------------------------------------


def test_failed_write_leaves_the_previous_manifest_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "acquisitions.json"
    write_atomic(path, b'{"schema_version": "1"}\n')
    original = path.read_bytes()

    def explode(src: Any, dst: Any) -> None:
        raise OSError("simulated failure during replace")

    monkeypatch.setattr(os, "replace", explode)
    with pytest.raises(OSError, match="simulated failure"):
        write_atomic(path, b'{"schema_version": "2"}\n')

    assert path.read_bytes() == original
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != path.name]
    assert leftovers == []


def test_write_atomic_creates_missing_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "acquisitions.json"
    write_atomic(path, b"{}\n")
    assert path.read_bytes() == b"{}\n"


# --- serialization rules ----------------------------------------------------


def test_serialization_rules(config: EventsConfig) -> None:
    payload = manifest_bytes(hanna_items(), config)
    text = payload.decode("utf-8")

    assert text.endswith("}\n")
    assert "\r\n" not in text
    assert text.count("\n") > 10
    # sort_keys=True means top-level keys appear in sorted order.
    document = json.loads(text)
    assert list(document) == sorted(document)
    assert sha256_hex(payload) == sha256_hex(payload)


def test_manifest_records_resolved_half_open_windows(config: EventsConfig) -> None:
    document = json.loads(manifest_bytes(hanna_items(), config).decode("utf-8"))
    windows = document["query"]["windows"]
    assert windows["pre_event"] == {
        "start": "2020-06-24T00:00:00.000000Z",
        "end": "2020-07-24T00:00:00.000000Z",
    }
    assert windows["event"] == {
        "start": "2020-07-26T00:00:00.000000Z",
        "end": "2020-07-29T00:00:00.000000Z",
    }
    assert document["query"]["window_bounds_convention"] == "half-open: [start, end)"


def test_manifest_records_event_provenance(config: EventsConfig) -> None:
    document = json.loads(manifest_bytes(hanna_items(), config).decode("utf-8"))
    assert document["event"]["event_source_url"].startswith("https://www.weather.gov/")
    assert document["query"]["aoi"]["fips"] == "48215"
    assert document["query"]["aoi"]["source_url"].startswith("https://tigerweb")


# --- query construction -----------------------------------------------------


def test_query_event_searches_both_windows_with_the_aoi_bbox(
    config: EventsConfig,
) -> None:
    client = FakeSearchClient(
        {
            date(2020, 6, 24): load_stac_fixture("hanna_2020__pre_event"),
            date(2020, 7, 26): load_stac_fixture("hanna_2020__event"),
        }
    )
    items = query_event(client, config=config, event_id="hanna_2020")

    assert len(items) == 14
    assert len(client.calls) == 2
    assert [call["collection"] for call in client.calls] == ["sentinel-1-rtc"] * 2
    assert client.calls[0]["bbox"] == list(config.aoi["hidalgo_county"].bbox)
    assert client.calls[0]["start"] == datetime(2020, 6, 24, tzinfo=UTC)
    assert client.calls[1]["end_exclusive"] == datetime(2020, 7, 29, tzinfo=UTC)


def test_interval_closes_one_microsecond_before_the_exclusive_bound() -> None:
    interval = format_interval(
        datetime(2020, 7, 26, tzinfo=UTC), datetime(2020, 7, 29, tzinfo=UTC)
    )
    assert interval == "2020-07-26T00:00:00.000000Z/2020-07-28T23:59:59.999999Z"


def test_rfc3339_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="naive datetime"):
        to_rfc3339(datetime(2020, 7, 26))

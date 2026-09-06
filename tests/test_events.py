"""Configuration parsing and window validation (plan section 7, cases 1-6)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from colonia_flood.events import ConfigError, EventsConfig, load_config

from .conftest import REAL_CONFIG_PATH

BASE_CONFIG = """
schema_version = "1"

[aoi.hidalgo_county]
name       = "Hidalgo County, Texas"
fips       = "48215"
source     = "US Census TIGERweb"
source_url = "https://tigerweb.geo.census.gov/example"
retrieved  = 2026-09-02
bbox       = [-98.586444, 26.036268, -97.861684, 26.783081]

[catalog]
name         = "Microsoft Planetary Computer STAC"
url          = "https://planetarycomputer.microsoft.com/api/stac/v1"
collection   = "sentinel-1-rtc"
vv_asset_key = "vv"
vh_asset_key = "vh"

[[events]]
event_id                  = "hanna_2020"
event_name                = "Hurricane Hanna, 2020"
aoi                       = "hidalgo_county"
event_start               = 2020-07-24
event_end                 = 2020-07-29
event_source              = "NWS Brownsville"
event_source_url          = "https://www.weather.gov/bro/2020event_hanna"
event_source_retrieved    = 2026-09-02
pre_event_window          = {{ start = {pre_start}, end = {pre_end} }}
observation_window        = {{ start = {obs_start}, end = {obs_end} }}
preferred_relative_orbit  = 143
preferred_orbit_direction = "descending"
"""


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "events.toml"
    path.write_text(text, encoding="utf-8")
    return path


def render(
    *,
    pre_start: str = "2020-06-24",
    pre_end: str = "2020-07-23",
    obs_start: str = "2020-07-26",
    obs_end: str = "2020-07-28",
) -> str:
    return BASE_CONFIG.format(
        pre_start=pre_start, pre_end=pre_end, obs_start=obs_start, obs_end=obs_end
    )


# --- case 1 -----------------------------------------------------------------


def test_committed_config_parses_both_events() -> None:
    loaded = load_config(REAL_CONFIG_PATH)
    config = loaded.config

    assert [event.event_id for event in config.events] == ["hanna_2020", "march_2025"]
    assert len(loaded.sha256) == 64
    assert config.catalog.collection == "sentinel-1-rtc"
    assert config.aoi["hidalgo_county"].fips == "48215"


def test_windows_resolve_to_half_open_utc_instants() -> None:
    config = load_config(REAL_CONFIG_PATH).config
    hanna = config.event("hanna_2020")

    assert hanna.pre_event_window.start_instant == datetime(2020, 6, 24, tzinfo=UTC)
    # The inclusive end date 2020-07-23 resolves to an exclusive bound at the
    # start of the following day.
    assert hanna.pre_event_window.end_instant_exclusive == datetime(
        2020, 7, 24, tzinfo=UTC
    )
    assert hanna.observation_window.start_instant == datetime(2020, 7, 26, tzinfo=UTC)
    assert hanna.observation_window.end_instant_exclusive == datetime(
        2020, 7, 29, tzinfo=UTC
    )


def test_confirmed_acquisitions_fall_inside_the_configured_windows() -> None:
    """The dates the feasibility report confirmed must actually be searched."""
    config = load_config(REAL_CONFIG_PATH).config

    hanna = config.event("hanna_2020")
    assert hanna.assign_window(datetime(2020, 7, 15, 12, 24, tzinfo=UTC)) == "pre_event"
    assert hanna.assign_window(datetime(2020, 7, 27, 12, 24, tzinfo=UTC)) == "event"

    march = config.event("march_2025")
    assert march.assign_window(datetime(2025, 3, 15, 12, 24, tzinfo=UTC)) == "pre_event"
    assert march.assign_window(datetime(2025, 3, 27, 12, 24, tzinfo=UTC)) == "event"


def test_half_open_boundary_excludes_the_exclusive_end() -> None:
    config = load_config(REAL_CONFIG_PATH).config
    march = config.event("march_2025")

    # 2025-03-26T00:00:00Z is the pre-event window's exclusive end and the
    # observation window's inclusive start. It must belong to exactly one.
    assert march.assign_window(datetime(2025, 3, 26, tzinfo=UTC)) == "event"
    assert march.assign_window(datetime(2025, 3, 25, 23, 59, 59, tzinfo=UTC)) == (
        "pre_event"
    )


# --- case 2 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "expected_field"),
    [
        ({"pre_start": "2020-07-23", "pre_end": "2020-06-24"}, "pre_event_window"),
        ({"obs_start": "2020-07-28", "obs_end": "2020-07-26"}, "observation_window"),
    ],
)
def test_reversed_window_raises_naming_the_field(
    tmp_path: Path, kwargs: dict[str, str], expected_field: str
) -> None:
    path = write_config(tmp_path, render(**kwargs))
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    message = str(excinfo.value)
    assert expected_field in message
    assert "strictly before" in message


# --- case 3 -----------------------------------------------------------------


def test_overlapping_windows_raise(tmp_path: Path) -> None:
    path = write_config(tmp_path, render(pre_end="2020-07-24", obs_start="2020-07-20"))
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert "must not overlap" in str(excinfo.value)


def test_abutting_windows_are_accepted(tmp_path: Path) -> None:
    """Half-open ranges that touch do not overlap, so they must be allowed."""
    path = write_config(
        tmp_path,
        render(pre_end="2020-07-24", obs_start="2020-07-25", obs_end="2020-07-28"),
    )
    config = load_config(path).config
    assert config.event("hanna_2020").pre_event_window.end.isoformat() == "2020-07-24"


# --- case 4 -----------------------------------------------------------------


def test_pre_event_window_ending_after_event_start_raises(tmp_path: Path) -> None:
    path = write_config(tmp_path, render(pre_end="2020-07-25"))
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    message = str(excinfo.value)
    assert "pre_event_window.end" in message
    assert "event_start" in message


# --- case 5 -----------------------------------------------------------------


SECOND_EVENT_WITH_SAME_ID = """
[[events]]
event_id                  = "hanna_2020"
event_name                = "A second event reusing an existing id"
aoi                       = "hidalgo_county"
event_start               = 2025-03-26
event_end                 = 2025-03-28
event_source              = "NWS Brownsville"
event_source_url          = "https://www.weather.gov/bro/2025event_menu"
event_source_retrieved    = 2026-09-02
pre_event_window          = { start = 2025-02-24, end = 2025-03-25 }
observation_window        = { start = 2025-03-26, end = 2025-03-28 }
"""


def test_duplicate_event_id_raises_at_load(tmp_path: Path) -> None:
    path = write_config(tmp_path, render() + SECOND_EVENT_WITH_SAME_ID)
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert "duplicate event_id" in str(excinfo.value)


# --- case 6 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("bbox", "expected"),
    [
        ("[-97.861684, 26.036268, -98.586444, 26.783081]", "west"),
        ("[-98.586444, 26.783081, -97.861684, 26.036268]", "south"),
        ("[-198.586444, 26.036268, -97.861684, 26.783081]", "longitudes"),
        ("[-98.586444, 26.036268, -97.861684, 96.783081]", "latitudes"),
    ],
)
def test_invalid_bbox_raises(tmp_path: Path, bbox: str, expected: str) -> None:
    text = render().replace(
        "bbox       = [-98.586444, 26.036268, -97.861684, 26.783081]",
        f"bbox       = {bbox}",
    )
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert expected in str(excinfo.value)


# --- additional guards ------------------------------------------------------


def test_unknown_schema_version_is_a_hard_error(tmp_path: Path) -> None:
    text = render().replace('schema_version = "1"', 'schema_version = "99"')
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert "unsupported schema_version" in str(excinfo.value)


def test_event_referencing_undefined_aoi_raises(tmp_path: Path) -> None:
    text = render().replace(
        'aoi                       = "hidalgo_county"',
        'aoi                       = "cameron_county"',
    )
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert "undefined aoi" in str(excinfo.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://planetarycomputer.microsoft.com/api/stac/v1",
        "https://user:secret@planetarycomputer.microsoft.com/api/stac/v1",
        "https://planetarycomputer.microsoft.com/api/stac/v1?subscription-key=abc",
    ],
)
def test_catalog_url_rejects_insecure_or_credentialed_endpoints(
    tmp_path: Path, url: str
) -> None:
    text = render().replace(
        'url          = "https://planetarycomputer.microsoft.com/api/stac/v1"',
        f'url          = "{url}"',
    )
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_config_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(tmp_path / "absent.toml")
    assert "cannot read configuration" in str(excinfo.value)


def test_malformed_toml_raises_config_error(tmp_path: Path) -> None:
    path = write_config(tmp_path, "this is not = = toml")
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert "not valid TOML" in str(excinfo.value)


def test_unknown_event_id_lookup_raises(config: EventsConfig) -> None:
    with pytest.raises(ConfigError) as excinfo:
        config.event("no_such_event")
    assert "no event with event_id" in str(excinfo.value)

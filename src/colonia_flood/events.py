"""Event configuration: TOML parsing, Pydantic models, and window validation.

Every event date, search window, and area-of-interest extent used by this
package originates here. No other module contains an event date.

Calendar dates in the configuration are resolved to half-open UTC instant
ranges ``[start T00:00:00Z, (end + 1 day) T00:00:00Z)``. Doing the conversion
in exactly one place keeps timezone handling out of every other module.
"""

from __future__ import annotations

import hashlib
import tomllib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SUPPORTED_SCHEMA_VERSIONS = frozenset({"1"})

WindowName = Literal["pre_event", "event"]


class ConfigError(Exception):
    """Raised when the event configuration is missing, unreadable, or invalid."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DateWindow(_Strict):
    """An inclusive calendar-date range, resolved to a half-open instant range."""

    start: date
    end: date

    @model_validator(mode="after")
    def _check_order(self) -> DateWindow:
        if self.start >= self.end:
            raise ValueError(
                f"window start ({self.start.isoformat()}) must be strictly before "
                f"window end ({self.end.isoformat()})"
            )
        return self

    @property
    def start_instant(self) -> datetime:
        """Inclusive lower bound of the resolved instant range."""
        return datetime.combine(self.start, datetime.min.time(), tzinfo=UTC)

    @property
    def end_instant_exclusive(self) -> datetime:
        """Exclusive upper bound: midnight at the start of the day after ``end``."""
        return datetime.combine(
            self.end + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )

    def contains(self, moment: datetime) -> bool:
        """Half-open membership test: ``start_instant <= moment < end_exclusive``."""
        return self.start_instant <= moment < self.end_instant_exclusive


class AreaOfInterest(_Strict):
    """A named query extent with the provenance that ``docs/mvp.md`` §5.5 requires."""

    name: Annotated[str, Field(min_length=1)]
    fips: Annotated[str, Field(pattern=r"^\d{5}$")]
    source: Annotated[str, Field(min_length=1)]
    source_url: Annotated[str, Field(min_length=1)]
    retrieved: date
    bbox: Annotated[list[float], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def _check_bbox(self) -> AreaOfInterest:
        west, south, east, north = self.bbox
        if west >= east:
            raise ValueError(f"bbox west ({west}) must be less than east ({east})")
        if south >= north:
            raise ValueError(f"bbox south ({south}) must be less than north ({north})")
        if not (-180.0 <= west <= 180.0 and -180.0 <= east <= 180.0):
            raise ValueError("bbox longitudes must fall within [-180, 180]")
        if not (-90.0 <= south <= 90.0 and -90.0 <= north <= 90.0):
            raise ValueError("bbox latitudes must fall within [-90, 90]")
        return self


class CatalogConfig(_Strict):
    """The STAC endpoint and the asset keys this slice depends on."""

    name: Annotated[str, Field(min_length=1)]
    url: Annotated[str, Field(min_length=1)]
    collection: Annotated[str, Field(min_length=1)]
    vv_asset_key: Annotated[str, Field(min_length=1)]
    vh_asset_key: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def _check_url(self) -> CatalogConfig:
        parsed = urlparse(self.url)
        if parsed.scheme != "https":
            raise ValueError(f"catalog.url must use https, got {parsed.scheme!r}")
        if parsed.query or parsed.fragment:
            raise ValueError("catalog.url must not carry a query string or fragment")
        if parsed.username or parsed.password or "@" in parsed.netloc:
            raise ValueError("catalog.url must not embed credentials")
        return self


class EventConfig(_Strict):
    """One historical rainfall event and the two windows searched for it."""

    event_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    event_name: Annotated[str, Field(min_length=1)]
    aoi: Annotated[str, Field(min_length=1)]
    event_start: date
    event_end: date
    event_source: Annotated[str, Field(min_length=1)]
    event_source_url: Annotated[str, Field(min_length=1)]
    event_source_retrieved: date
    pre_event_window: DateWindow
    observation_window: DateWindow
    preferred_relative_orbit: Annotated[int, Field(ge=1, le=175)] | None = None
    preferred_orbit_direction: Literal["ascending", "descending"] | None = None

    @model_validator(mode="after")
    def _check_windows(self) -> EventConfig:
        if self.event_start > self.event_end:
            raise ValueError(
                f"event_start ({self.event_start.isoformat()}) must not be after "
                f"event_end ({self.event_end.isoformat()})"
            )
        if self.pre_event_window.end > self.event_start:
            raise ValueError(
                f"pre_event_window.end ({self.pre_event_window.end.isoformat()}) must "
                f"not be after event_start ({self.event_start.isoformat()})"
            )
        # Overlap is checked on resolved half-open instants, so that windows which
        # merely abut (one ends the day the next begins) are accepted.
        if (
            self.pre_event_window.start_instant
            < self.observation_window.end_instant_exclusive
            and self.observation_window.start_instant
            < self.pre_event_window.end_instant_exclusive
        ):
            raise ValueError(
                "pre_event_window and observation_window must not overlap "
                f"(pre_event {self.pre_event_window.start.isoformat()}.."
                f"{self.pre_event_window.end.isoformat()}, observation "
                f"{self.observation_window.start.isoformat()}.."
                f"{self.observation_window.end.isoformat()})"
            )
        return self

    def window(self, name: WindowName) -> DateWindow:
        return self.pre_event_window if name == "pre_event" else self.observation_window

    def assign_window(self, moment: datetime) -> WindowName | None:
        """Return the window containing ``moment``, or ``None`` if neither does.

        Window membership is decided by the acquisition timestamp alone, never by
        which search returned the item. That makes it structurally impossible for
        one acquisition to be filed under two windows.
        """
        if self.pre_event_window.contains(moment):
            return "pre_event"
        if self.observation_window.contains(moment):
            return "event"
        return None


class EventsConfig(_Strict):
    """The whole configuration document."""

    schema_version: str
    aoi: dict[str, AreaOfInterest]
    catalog: CatalogConfig
    events: Annotated[list[EventConfig], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_references(self) -> EventsConfig:
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"unsupported schema_version {self.schema_version!r}; "
                f"supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )
        seen: set[str] = set()
        for event in self.events:
            if event.event_id in seen:
                raise ValueError(f"duplicate event_id {event.event_id!r}")
            seen.add(event.event_id)
            if event.aoi not in self.aoi:
                raise ValueError(
                    f"event {event.event_id!r} references undefined aoi "
                    f"{event.aoi!r}; defined: {sorted(self.aoi)}"
                )
        return self

    def event(self, event_id: str) -> EventConfig:
        for event in self.events:
            if event.event_id == event_id:
                return event
        raise ConfigError(
            f"no event with event_id {event_id!r}; "
            f"configured: {sorted(e.event_id for e in self.events)}"
        )

    def aoi_for(self, event: EventConfig) -> AreaOfInterest:
        return self.aoi[event.aoi]


class LoadedConfig(_Strict):
    """A parsed configuration together with the digest of the bytes it came from."""

    config: EventsConfig
    sha256: str


def load_config(path: Path) -> LoadedConfig:
    """Read, parse, and validate the event configuration at ``path``.

    The SHA-256 is taken over the raw file bytes, so a manifest can name exactly
    the configuration that produced it.
    """
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read configuration at {path}: {exc}") from exc

    try:
        document = tomllib.loads(raw_bytes.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"configuration at {path} is not valid TOML: {exc}") from exc

    try:
        config = EventsConfig.model_validate(document)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration at {path}:\n{exc}") from exc

    return LoadedConfig(config=config, sha256=hashlib.sha256(raw_bytes).hexdigest())

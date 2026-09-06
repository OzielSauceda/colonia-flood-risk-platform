"""Manifest assembly, deterministic ordering, and atomic serialization.

Everything in this module is a pure function of ``(configuration, catalog
response)``. No wall-clock value, no path, and no environment detail can reach
the manifest, because none is ever passed in. Run-specific provenance lives in
:mod:`colonia_flood.run_record` instead.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .acquisitions import (
    Acquisition,
    ExcludedItem,
    ReasonCode,
    extract_datetime,
    extract_item_id,
    map_item,
)
from .events import EventsConfig, WindowName
from .stac_client import SearchClient, to_rfc3339

MANIFEST_SCHEMA_VERSION = "1"
MANIFEST_FILENAME = "acquisitions.json"

WINDOW_NAMES: tuple[WindowName, ...] = ("pre_event", "event")
_WINDOW_RANK = {name: index for index, name in enumerate(WINDOW_NAMES)}


class EventResult:
    """The mapped outcome for one event, before serialization."""

    def __init__(
        self, acquisitions: list[Acquisition], excluded: list[ExcludedItem]
    ) -> None:
        self.acquisitions = acquisitions
        self.excluded = excluded

    def window_count(self, window: WindowName) -> int:
        return sum(1 for a in self.acquisitions if a.window == window)


def _canonical(payload: Any) -> str:
    """A stable string form used only for order-independent tie-breaking."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def collect_event(
    raw_items: list[dict[str, Any]], *, config: EventsConfig, event_id: str
) -> EventResult:
    """Map, deduplicate, and order every item returned for one event.

    Deduplication is order-independent: when several items share an ``item_id``,
    the candidate whose canonical form sorts first is retained. Keeping the
    *first-seen* item instead would make the output depend on the catalog's
    response ordering, which is exactly what requirement 7 forbids.
    """
    event = config.event(event_id)
    aoi = config.aoi_for(event)

    candidates: dict[str, list[Acquisition]] = {}
    excluded: list[ExcludedItem] = []

    for raw in raw_items:
        item_id = extract_item_id(raw)

        acquired_at = extract_datetime(raw)
        if acquired_at is None:
            excluded.append(
                ExcludedItem(
                    item_id=item_id,
                    reason_code=ReasonCode.MISSING_DATETIME,
                    detail="item has no parseable 'properties.datetime'",
                )
            )
            continue

        # Window membership follows from the timestamp alone, never from which
        # search returned the item, so no acquisition can land in two windows.
        window = event.assign_window(acquired_at)
        if window is None:
            excluded.append(
                ExcludedItem(
                    item_id=item_id,
                    reason_code=ReasonCode.OUTSIDE_ALL_WINDOWS,
                    detail=(
                        "acquisition timestamp falls outside both the pre-event "
                        "and event windows configured for this event"
                    ),
                )
            )
            continue

        mapped = map_item(
            raw,
            event=event,
            aoi=aoi,
            catalog=config.catalog,
            acquired_at=acquired_at,
            window=window,
        )
        if isinstance(mapped, ExcludedItem):
            excluded.append(mapped)
        else:
            candidates.setdefault(item_id, []).append(mapped)

    acquisitions: list[Acquisition] = []
    for item_id, group in candidates.items():
        ordered = sorted(group, key=lambda a: _canonical(a.model_dump(mode="json")))
        acquisitions.append(ordered[0])
        if len(ordered) > 1:
            excluded.append(
                ExcludedItem(
                    item_id=item_id,
                    reason_code=ReasonCode.DUPLICATE_ITEM_ID,
                    detail=(
                        f"{len(ordered)} catalog items shared this item_id; the "
                        "canonically first record was retained and the remaining "
                        f"{len(ordered) - 1} discarded"
                    ),
                )
            )

    acquisitions.sort(key=lambda a: (_WINDOW_RANK[a.window], a.datetime_utc, a.item_id))
    excluded.sort(key=lambda e: (e.item_id, e.reason_code.value, e.detail))
    return EventResult(acquisitions=acquisitions, excluded=excluded)


def query_event(
    client: SearchClient, *, config: EventsConfig, event_id: str
) -> list[dict[str, Any]]:
    """Run both window searches for one event and return the raw items."""
    event = config.event(event_id)
    aoi = config.aoi_for(event)
    raw_items: list[dict[str, Any]] = []
    for name in WINDOW_NAMES:
        window = event.window(name)
        raw_items.extend(
            client.search(
                collection=config.catalog.collection,
                bbox=list(aoi.bbox),
                start=window.start_instant,
                end_exclusive=window.end_instant_exclusive,
            )
        )
    return raw_items


def build_manifest(
    result: EventResult, *, config: EventsConfig, event_id: str, config_sha256: str
) -> dict[str, Any]:
    """Assemble the manifest document. Contains nothing run-specific."""
    event = config.event(event_id)
    aoi = config.aoi_for(event)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "event": {
            "event_id": event.event_id,
            "event_name": event.event_name,
            "event_start": event.event_start.isoformat(),
            "event_end": event.event_end.isoformat(),
            "event_source": event.event_source,
            "event_source_url": event.event_source_url,
            "event_source_retrieved": event.event_source_retrieved.isoformat(),
        },
        "query": {
            "catalog_url": config.catalog.url,
            "catalog_name": config.catalog.name,
            "collection": config.catalog.collection,
            "aoi": {
                "name": aoi.name,
                "fips": aoi.fips,
                "bbox": [float(value) for value in aoi.bbox],
                "source": aoi.source,
                "source_url": aoi.source_url,
                "retrieved": aoi.retrieved.isoformat(),
            },
            "preferred_relative_orbit": event.preferred_relative_orbit,
            "preferred_orbit_direction": event.preferred_orbit_direction,
            # Ranges are half-open: start is inclusive, end is exclusive.
            "windows": {
                "pre_event": {
                    "start": to_rfc3339(event.pre_event_window.start_instant),
                    "end": to_rfc3339(event.pre_event_window.end_instant_exclusive),
                },
                "event": {
                    "start": to_rfc3339(event.observation_window.start_instant),
                    "end": to_rfc3339(event.observation_window.end_instant_exclusive),
                },
            },
            "window_bounds_convention": "half-open: [start, end)",
        },
        "config_sha256": config_sha256,
        "counts": {
            "acquisitions": len(result.acquisitions),
            "pre_event": result.window_count("pre_event"),
            "event": result.window_count("event"),
            "excluded": len(result.excluded),
        },
        "acquisitions": [a.model_dump(mode="json") for a in result.acquisitions],
        "excluded": [e.model_dump(mode="json") for e in result.excluded],
    }


def serialize(document: dict[str, Any]) -> bytes:
    """Serialize with the fixed rules that actually deliver byte-level determinism."""
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_atomic(path: Path, payload: bytes) -> None:
    """Write via temp file plus ``os.replace``.

    A failed or interrupted write therefore leaves the previous manifest intact
    rather than truncating it, and leaves no temp file behind.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise

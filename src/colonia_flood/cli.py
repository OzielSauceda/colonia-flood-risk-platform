"""Command-line entry point: argument parsing, orchestration, and exit codes.

Every other module stays importable and testable without ``argv`` or stdout.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from .events import ConfigError, EventsConfig, load_config
from .manifest import (
    MANIFEST_FILENAME,
    WINDOW_NAMES,
    EventResult,
    build_manifest,
    collect_event,
    query_event,
    serialize,
    sha256_hex,
    write_atomic,
)
from .run_record import RUN_RECORD_FILENAME, Clock, build_run_record, write_run_record
from .run_record import utc_now as default_clock
from .stac_client import CatalogError, PystacSearchClient, SearchClient

DEFAULT_CONFIG_PATH = Path("config/events.toml")
DEFAULT_OUT_DIR = Path("data/manifests")

EXIT_OK = 0
EXIT_EMPTY_WINDOW = 1
EXIT_ERROR = 2

LOGGER = logging.getLogger("colonia_flood")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="colonia-flood-manifest",
        description=(
            "Query Sentinel-1 RTC catalog metadata for configured Hidalgo County "
            "flood events and write deterministic acquisition manifests. "
            "Downloads no raster assets."
        ),
    )
    parser.add_argument(
        "--event",
        action="append",
        dest="events",
        metavar="EVENT_ID",
        help="Event to process; repeatable. Defaults to every configured event.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Event configuration file (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Manifest output directory (default: {DEFAULT_OUT_DIR}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Query and report, but write no files.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Emit debug-level logging."
    )
    return parser


def _selected_event_ids(
    config: EventsConfig, requested: Sequence[str] | None
) -> list[str]:
    configured = [event.event_id for event in config.events]
    if not requested:
        return configured
    unknown = [event_id for event_id in requested if event_id not in configured]
    if unknown:
        raise ConfigError(
            f"unknown event id(s): {sorted(unknown)}; configured: {configured}"
        )
    # Preserve configuration order so output ordering never depends on argv order.
    return [event_id for event_id in configured if event_id in set(requested)]


def _report(event_id: str, result: EventResult) -> None:
    LOGGER.info(
        "%s: %d acquisitions (pre_event=%d, event=%d), %d excluded",
        event_id,
        len(result.acquisitions),
        result.window_count("pre_event"),
        result.window_count("event"),
        len(result.excluded),
    )
    for excluded in result.excluded:
        LOGGER.debug(
            "%s: excluded %s (%s): %s",
            event_id,
            excluded.item_id,
            excluded.reason_code.value,
            excluded.detail,
        )


def run(
    args: argparse.Namespace,
    *,
    client: SearchClient | None = None,
    clock: Clock = default_clock,
    repo_root: Path | None = None,
) -> int:
    """Execute one invocation. Returns the process exit code."""
    loaded = load_config(args.config)
    config = loaded.config
    event_ids = _selected_event_ids(config, args.events)
    search_client = client or PystacSearchClient(config.catalog.url)
    root = repo_root or Path.cwd()

    exit_code = EXIT_OK
    for event_id in event_ids:
        LOGGER.info("querying catalog for event %s", event_id)
        raw_items = query_event(search_client, config=config, event_id=event_id)
        result = collect_event(raw_items, config=config, event_id=event_id)
        _report(event_id, result)

        for window in WINDOW_NAMES:
            if result.window_count(window) == 0:
                LOGGER.error(
                    "%s: no acquisitions in the %s window; a silently empty "
                    "manifest is the failure mode most likely to go unnoticed",
                    event_id,
                    window,
                )
                exit_code = EXIT_EMPTY_WINDOW

        document = build_manifest(
            result, config=config, event_id=event_id, config_sha256=loaded.sha256
        )
        manifest_bytes = serialize(document)

        if args.dry_run:
            LOGGER.info(
                "%s: dry run, not writing (%d manifest bytes, sha256=%s)",
                event_id,
                len(manifest_bytes),
                sha256_hex(manifest_bytes),
            )
            continue

        event_dir = args.out_dir / event_id
        manifest_path = event_dir / MANIFEST_FILENAME
        write_atomic(manifest_path, manifest_bytes)

        record = build_run_record(
            catalog_url=config.catalog.url,
            config_sha256=loaded.sha256,
            manifest_bytes=manifest_bytes,
            manifest_sha256=sha256_hex(manifest_bytes),
            acquisition_count=len(result.acquisitions),
            excluded_count=len(result.excluded),
            repo_root=root,
            clock=clock,
        )
        write_run_record(event_dir / RUN_RECORD_FILENAME, record)
        LOGGER.info("%s: wrote %s", event_id, manifest_path.as_posix())

    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        return run(args)
    except ConfigError as exc:
        LOGGER.error("configuration error: %s", exc)
        return EXIT_ERROR
    except CatalogError as exc:
        LOGGER.error("catalog error: %s", exc)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

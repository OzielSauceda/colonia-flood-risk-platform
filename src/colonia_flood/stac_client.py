"""The single seam between this package and the network.

Nothing above this module knows that HTTP exists. Unit tests substitute a fake
implementation of :class:`SearchClient` and therefore never touch the network;
only the optional live test constructs :class:`PystacSearchClient`.

This module performs *metadata search only*. It never requests an asset href and
never signs a URL, so no raster byte is transferred and no credential is used.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

DEFAULT_TIMEOUT_SECONDS = 60

# The STAC datetime interval is closed at both ends, while every window in this
# package is half-open. Querying up to one microsecond before the exclusive
# bound makes the two conventions agree.
_INTERVAL_EPSILON = timedelta(microseconds=1)


class CatalogError(Exception):
    """A transport failure, or a catalog response this package cannot interpret.

    Every exception raised by the underlying STAC library is converted to this
    type, so callers depend on one domain exception rather than on whichever
    HTTP client happens to be in use.
    """


@runtime_checkable
class SearchClient(Protocol):
    """Returns raw STAC item dictionaries for one collection, extent, and window."""

    def search(
        self,
        *,
        collection: str,
        bbox: Sequence[float],
        start: datetime,
        end_exclusive: datetime,
    ) -> list[dict[str, Any]]:
        """Return every item in ``[start, end_exclusive)``, following pagination."""
        ...


def format_interval(start: datetime, end_exclusive: datetime) -> str:
    """Render a half-open instant range as the closed RFC 3339 interval STAC wants."""
    closed_end = end_exclusive - _INTERVAL_EPSILON
    return f"{to_rfc3339(start)}/{to_rfc3339(closed_end)}"


def to_rfc3339(moment: datetime) -> str:
    """Render an aware datetime as RFC 3339 in UTC with an explicit ``Z``."""
    if moment.tzinfo is None:
        raise ValueError("refusing to format a naive datetime; supply a timezone")
    return (
        moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


class PystacSearchClient:
    """Production :class:`SearchClient` backed by ``pystac-client``.

    ``pystac-client`` is used specifically because STAC search pagination fails
    *quietly* when hand-rolled: a truncated result set yields a manifest that
    looks correct and is wrong.
    """

    def __init__(
        self, catalog_url: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._catalog_url = catalog_url
        self._timeout = timeout

    def search(
        self,
        *,
        collection: str,
        bbox: Sequence[float],
        start: datetime,
        end_exclusive: datetime,
    ) -> list[dict[str, Any]]:
        try:
            from pystac_client import Client
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise CatalogError(f"pystac-client is not installed: {exc}") from exc

        try:
            client = Client.open(self._catalog_url)
            search = client.search(
                collections=[collection],
                bbox=list(bbox),
                datetime=format_interval(start, end_exclusive),
            )
            items = list(search.items_as_dicts())
        except Exception as exc:
            raise CatalogError(
                f"catalog search failed against {self._catalog_url} "
                f"(collection={collection!r}): {exc}"
            ) from exc

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise CatalogError(
                    f"catalog returned a non-object item at position {index}"
                )
        return items

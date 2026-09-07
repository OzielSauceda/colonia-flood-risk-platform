"""Explicit local-file F2 calculation: python -m colonia_flood.colonia_cli."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .acquisitions import Acquisition
from .colonia import ViabilityReport, viability_report
from .coverage import Polygonal, geometry_from_geojson, load_county_boundary
from .events import load_config


def load_colonias(path: Path) -> list[Polygonal]:
    """Load every source geometry without repair, filtering or snapshot mutation."""
    document = json.loads(path.read_bytes())
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise ValueError("colonias must be a FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("colonias must contain features")
    geometries = []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("expected a colonia Feature")
        geometries.append(geometry_from_geojson(feature.get("geometry")))
    return geometries


def calculate_local(root: Path) -> ViabilityReport:
    """Read configured events and committed local boundaries/manifests only."""
    config = load_config(root / "config/events.toml").config
    county_path = root / "data/boundaries/hidalgo_county.geojson"
    colonia_path = root / "data/boundaries/colonias.geojson"
    aoi = config.aoi_for(config.events[0])
    if aoi.fips != "48215" or any(config.aoi_for(e) != aoi for e in config.events):
        raise ValueError("F2 requires the same Hidalgo County AOI for every event")
    acquisitions = {}
    for event in config.events:
        document = json.loads(
            (
                root / "data/manifests" / event.event_id / "acquisitions.json"
            ).read_bytes()
        )
        acquisitions[event.event_id] = [
            Acquisition.model_validate(a) for a in document["acquisitions"]
        ]
    return viability_report(
        load_county_boundary(county_path, aoi),
        load_colonias(colonia_path),
        acquisitions,
        colonia_source_sha256=hashlib.sha256(colonia_path.read_bytes()).hexdigest(),
        county_boundary_sha256=hashlib.sha256(county_path.read_bytes()).hexdigest(),
    )


def report_json(report: ViabilityReport) -> str:
    """Stable JSON: sorted keys, UTF-8 at the writer, LF and no runtime metadata."""
    return json.dumps(asdict(report), indent=2, sort_keys=True, allow_nan=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    report = calculate_local(args.root)
    output = args.root / "data/analysis/colonia_viability.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(report_json(report).encode("utf-8"))


if __name__ == "__main__":
    main()

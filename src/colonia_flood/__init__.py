"""Sentinel-1 RTC acquisition-manifest tooling for the Colonia Flood Risk Platform.

This package queries STAC catalog *metadata* only. It never downloads raster
assets, and nothing it writes contains credentials, signed URLs, or
machine-specific paths.
"""

__version__ = "0.1.0"

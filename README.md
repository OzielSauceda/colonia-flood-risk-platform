# Colonia Flood Risk Platform

An end-to-end geospatial data and machine-learning platform for exploring
rainfall-driven flood risk in Hidalgo County colonias.

## Project goal

This project will integrate rainfall, terrain, geographic, and historical
flood data to estimate and visualize localized flood risk. The first version
will be a research and decision-support prototype, not an official emergency
warning system.

## Initial MVP

The first working vertical slice will include:

- Hidalgo County geographic coverage
- Colonia boundary overlays
- Rainfall and elevation-derived features
- One defensible flood-label source or a clearly identified susceptibility score
- One baseline model and one gradient-boosted model
- PostgreSQL/PostGIS storage
- A FastAPI backend
- A React and TypeScript interactive map
- Automated testing and a deployed demonstration

## Technology stack

- **Data and machine learning:** Python, GeoPandas, rasterio, scikit-learn, XGBoost
- **Database:** PostgreSQL and PostGIS
- **Backend:** FastAPI, Pydantic, SQLAlchemy
- **Frontend:** React, TypeScript, MapLibre GL
- **Infrastructure:** Docker Compose, GitHub Actions
- **Later enhancements:** Airflow, dbt, MLflow, AWS, Terraform

## Project status

Currently in the feasibility and initial setup phase.

## Disclaimer

This project is an experimental research prototype. It does not replace
official flood forecasts, alerts, evacuation guidance, or emergency services.
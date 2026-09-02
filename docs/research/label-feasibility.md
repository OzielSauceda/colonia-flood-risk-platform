# Flood-label feasibility assessment — Hidalgo County, Texas

**Status:** Independent review complete; satellite-label prototype required before the final model-path decision  
**Investigation date:** 2026-09-01  
**Decision addressed:** `docs/mvp.md` §11 and §13, question 1

## Executive decision

Do **not** train a supervised model from NWS Local Storm Reports (LSRs). They are
valuable corroborating evidence, but they are presence-only, spatially coarse,
reporting-biased, and the IEM archive itself states that it is not complete or
official.

Also, do **not** close Path A yet. The earlier Path B recommendation overlooked
historical satellite observations that directly address its central objection:
the absence of a defensible negative class.

The best current decision is:

> Run one time-boxed satellite-label prototype before choosing Path A or Path B.
> Path A is allowed only if the target is narrowed to **satellite-observed
> persistent surface inundation**, and only if the prototype passes the
> acceptance gate in this document. Otherwise, use Path B.

This is not indecision. It identifies one specific, accessible dataset family,
one exact target, one reproducible experiment, and binary exit criteria. It also
prevents us from prematurely discarding the project's supervised-learning path.

## What the supervised target would mean

If the prototype passes, replace the broad provisional target in `docs/mvp.md`
with:

> Given a 500 m grid cell's terrain features and event rainfall accumulations,
> estimate the probability that persistent new surface inundation is detected
> by satellite in that cell during the event observation window.

This target does **not** mean:

- every flooded street or yard is observed;
- all flooding that occurred and drained between satellite passes is captured;
- a cell labeled negative was inspected on the ground;
- the output is an official warning or a property-level flood probability.

The distinction matters. A model can be scientifically defensible while
predicting a narrower proxy outcome, provided the UI, API, model card, and resume
description all name that outcome accurately.

## Why the previous Path B conclusion was premature

The previous assessment correctly rejected LSRs as the sole label source, but it
extended limitations of one satellite product to the entire remote-sensing
route. Direct catalog and imagery checks produced four important corrections.

### 1. Event-time Sentinel-1 observations do exist

Sentinel-1 radar is useful during storms because it operates day or night and
through clouds. ESA describes the mission as all-weather, day-and-night radar;
NASA documents change detection from terrain-corrected Sentinel-1 data for flood
and other disturbance analysis.

Public Sentinel-1 RTC catalog queries found the following Hidalgo County
acquisitions:

| Event | Event observation | Comparable pre-event observation | Timing |
|---|---|---|---|
| Great June Flood, 2018 | 2018-06-20 12:24 UTC, descending orbit 143 | 2018-06-08, same orbit | Event day |
| June Flood, 2019 | 2019-06-25 00:33 UTC, ascending orbit 107 | 2019-06-13, same orbit | About one day after |
| Hurricane Hanna, 2020 | 2020-07-27 12:24 UTC, descending orbit 143 | 2020-07-15, same orbit | During/just after event |
| March 2025 flood | 2025-03-27 12:24 UTC, descending orbit 143 | 2025-03-15, same orbit | Event day |

Same-orbit pairs reduce differences caused by viewing geometry. The RTC assets
are 10 m, float-valued Cloud-Optimized GeoTIFFs with VV and VH polarization.
They can be spatially aggregated to 500 m cells without inventing finer label
precision than the source supports.

### 2. Satellite coverage can define negatives

Within a valid observation footprint, a satellite product can distinguish:

- observed new water or inundation;
- observed non-water;
- permanent or recurring water;
- cloud, no-data, or otherwise unobservable pixels.

Only the second category is eligible to become a negative. Cloud/no-data pixels
remain missing rather than being silently treated as dry.

This is fundamentally different from LSRs. An LSR archive records where someone
reported an impact; it does not define where anyone looked. A classified
satellite scene has an explicit spatial observation footprint.

NASA's OPERA DSWx-S1 product, for example, differentiates water, no-water, and
inundated vegetation and distributes the layers as GeoTIFFs. Its production
archive is too recent to cover the older events by itself, but the underlying
historical Sentinel-1 RTC scenes are available for a reproducible derived-label
experiment.

### 3. Other historical surface-water products were omitted

The satellite route is not limited to OPERA DSWx-S1:

| Source | Relevant role | Main limitation |
|---|---|---|
| Sentinel-1 RTC | Primary candidate for before/after radar change labels | Urban double-bounce, wet soil, crops, speckle, and partial footprints complicate classification |
| Sentinel-2 Level-2A | Optical validation using water indices and scene classification | Clouds and acquisition footprints can obscure the event |
| NASA MODIS historical flood products | Daily/1–3 day, approximately 250 m corroborating classifications across older events | Coarse pixels, cloud/insufficient-data states, and false-positive risk |
| NOAA/NASA VIIRS flood products | Approximately 375 m corroboration for recent events | Available only for the recent part of the event history and still cloud-sensitive |
| OPERA DSWx-S1 | High-quality operational reference for recent Sentinel-1 acquisitions | Production history does not cover 2018–2020 |

The MODIS historical files for the Hidalgo tile and the required 2018, 2019,
2020, and 2025 dates were verified in the NASA archive. File retrieval requires
a free Earthdata-authenticated request; authentication is an access step, not
evidence that the data do not exist.

### 4. Several claims about the LSR sample need tighter wording

- The IEM LSR archive explicitly warns that it is not complete or official.
- Approximately 47 positive reports across three events cannot be divided by
  the total number of county cells to estimate a class rate. Unreported cells
  have unknown labels, not negative labels.
- Two-decimal coordinates imply a rounding interval of roughly 1 km, not that
  every point has exactly 1 km error. The quantization uncertainty is roughly
  half that interval per axis, with additional uncertainty from how the report
  location was constructed.
- “Only one report names a colonia” measures explicit text mentions. It does
  not establish how many reports spatially intersect colonia polygons. That
  question requires a buffered spatial join and should be reported separately.

These corrections do not make LSRs suitable training labels. They make the
reason for rejecting them more exact.

## Direct data checks performed in this review

This review went beyond checking documentation pages. It queried public
catalogs, fetched county-clipped imagery, and inspected event observations.

### NWS Local Storm Reports

For the March 2025 event, the WFO Brownsville query returned 19 regional
reports, including six Hidalgo County flood/flash-flood reports around McAllen,
Pharr, and Mercedes. The records are timestamped and narratively useful, but
they do not contain a surveyed observation footprint or valid negatives.

The IEM archive is suitable for:

- checking whether a satellite-derived positive is near a known impact;
- event discovery and qualitative error analysis;
- manual-review prioritization;
- documenting reporting bias.

It is not suitable as the binary training target.

### Sentinel-1 RTC before/after test

County-clipped, aligned VV radar crops were fetched for same-orbit pre-event and
event observations. The service output was downsampled to approximately
60–120 m for this feasibility check; these are not final 10 m labels.

| Event | Median VV change | Pixels with decrease ≤ -3 dB | Initial interpretation |
|---|---:|---:|---|
| 2018 | +1.97 dB | 1.19% | Strong event-wide change; simple dark-water threshold captures only a minority |
| 2020 | +1.47 dB | 3.75% | Most promising darkening signal; 1.28% were both very dark and decreased strongly |
| 2025 | +3.66 dB | 0.44% | Strong brightening dominates; likely wet soil, vegetation, agriculture, and/or urban scattering |

These results prove that the event scenes contain substantial change, but they
also reject a naive rule such as “darker after the storm equals flooded.” Open
water commonly reduces radar backscatter, while flooded vegetation or urban
double-bounce can increase it. Wet soil and crop changes can also increase
backscatter. A defensible classifier must use both polarizations, a multi-date
baseline, permanent-water and land-cover masks, and validation data.

### MODIS/VIIRS-style flood-map check for March 2025

Public map-service layers were clipped to the official Hidalgo County boundary.
The event peak was heavily obscured:

| Date/product | Approximate valid county coverage | Rendered flood pixels |
|---|---:|---:|
| 2025-03-27, 1-day | 1.05% | 0 |
| 2025-03-27, 2-day | 0% | 0 |
| 2025-03-27, 3-day | 0.34% | 0 |
| 2025-03-28, 1-day | 59.97% | 2,563 |
| 2025-03-29, 1-day | 82.41% | 375 |
| 2025-03-30, 1-day | 95.09% | 5,446 |

The later scenes contain mapped flood pixels, but most did not coincide with
the small set of city-centered LSR locations. Some rendered flood pixels also
appeared before the official event window. That may reflect earlier rainfall,
agricultural water, recurring water, timing, or classification error. Therefore
this product should be corroborating evidence, not an unquestioned ground-truth
layer.

### Sentinel-2 catalog check

Clear before/after optical scenes exist for parts of several events, including
clear western Hidalgo acquisitions on 2025-03-19 and 2025-03-29. The clear 2025
post-event footprint did not cover the McAllen/Pharr report cluster, while the
event-day full-footprint optical scene was cloud-obscured. For Hurricane Hanna,
fuller same-orbit scenes exist on 2020-07-20 and 2020-07-30 with moderate cloud
cover.

Sentinel-2 is therefore useful for selective validation and manual review, but
cannot be the only label source.

## Assessment against the six MVP criteria

The relevant unit is a **derived multi-source satellite label**, not any single
LSR point.

| Criterion | Current assessment | What must be demonstrated |
|---|---|---|
| Georeferenced | Likely pass | Aggregate 10–30 m classifications to deterministic 500 m cells; preserve missing coverage |
| Temporally attributable | Likely pass | Record acquisition time and a fixed event window matched to rainfall accumulations |
| Sufficient coverage | Unproven | At least three events, multiple county areas, and meaningful colonia-grid coverage must survive QA |
| Known collection process | Conditional pass | Commit the entire derivation, masks, thresholds, versions, and known radar/optical biases |
| Usable negatives | Likely pass | Use only confidently observed non-inundated cells; never convert cloud/no-data or no-report cells to negatives |
| Licensed | Likely pass | Record ESA/Copernicus, NASA, NOAA, and hosting terms for every retained artifact |

Current outcome: **candidate Path A is technically feasible, but the label set
has not yet earned the word defensible.** The next step is label engineering and
validation, not model training.

## Satellite-label prototype

Time-box this to approximately one focused week. It is a data-science and
data-engineering milestone, not throwaway exploration.

### Scope

Use two events first:

1. Hurricane Hanna, 2020 — strongest initial radar-darkening signal and useful
   post-event optical coverage.
2. March 2025 — event-day radar plus the best modern corroborating products.

Add 2018 and 2019 only after the two-event pipeline is deterministic.

### Label construction

1. Create a 500 m Hidalgo County grid.
2. Fetch same-orbit Sentinel-1 RTC VV and VH observations from multiple dry
   pre-event dates and the event window.
3. Convert linear backscatter to decibels and compute robust change relative to
   the multi-date pre-event median, not a single image.
4. Apply permanent/seasonal-water, terrain, land-cover, and valid-observation
   masks.
5. Produce pixel-level candidate water/inundation classes with an established,
   cited method or OPERA-compatible logic.
6. Aggregate to grid-event rows with observed-area fraction, new-water fraction,
   confidence, and provenance fields.
7. Mark ambiguous cells as `unknown`; do not force every cell into positive or
   negative.
8. Validate a stratified sample against Sentinel-2/MODIS/VIIRS imagery, LSR
   buffers, and manual visual review.

The derived table should minimally contain:

| Field | Purpose |
|---|---|
| `cell_id`, `event_id` | Stable unit of supervised learning |
| `label` | `1`, `0`, or `unknown` |
| `label_confidence` | Separates high-confidence labels from ambiguous cells |
| `observed_fraction` | Prevents partial/no-data cells from becoming negatives |
| `new_water_fraction` | Auditable basis for cell assignment |
| `acquisition_start`, `acquisition_end` | Temporal provenance |
| `source_product_ids` | Exact reproducibility |
| `label_method_version` | Re-runnable versioned logic |

### Pass/fail gate

Take Path A only if all of the following are true after the prototype:

- At least three independent storm events yield usable labels.
- At least 100 positive grid-event rows remain after quality filters, spread
  across multiple areas rather than one contiguous water body.
- At least 20 colonia-intersecting cells have valid event observations; colonia
  coverage is reported even if no positive is detected.
- The negative rule requires at least 90% valid observed area within a cell and
  explicitly excludes permanent water, clouds/no-data, and ambiguous change.
- A stratified manual audit of at least 100 labeled cell-events achieves at
  least 80% precision for the positive class, with the audit protocol and
  disagreements retained.
- Results remain materially stable under reasonable changes to water-fraction
  and radar-change thresholds.
- One entire storm is reserved as the final test event; neighboring cells are
  never randomly split across train and test.
- The model target and UI wording explicitly say “satellite-observed persistent
  inundation,” not general flood occurrence or safety risk.

If any criterion fails, take Path B for the MVP and retain the satellite work as
a documented research extension. Do not weaken the gate after seeing the
results.

## Modeling implications if Path A passes

Each row represents one grid cell during one storm event. Terrain values are
static features; rainfall accumulations and antecedent rainfall vary by event.
The label is the satellite-derived outcome.

The first baseline should be logistic regression. The second model can be
XGBoost or LightGBM. A boosted tree is not automatically better; it must beat
the baseline on an unseen storm.

Report at minimum:

- precision-recall AUC because positives will be rare;
- recall and precision at the operational display threshold;
- Brier score and a calibration curve because the UI shows probabilities;
- results by storm and by colonia/non-colonia intersection;
- sensitivity to uncertain labels and assignment thresholds.

Do not use random cell-level train/test splits. Adjacent cells and cells from
the same storm share rainfall and landscape structure, so random splitting
would leak information and overstate performance.

## Final recommendation

1. Keep LSRs as supplemental validation only.
2. Do not implement the susceptibility index yet.
3. Build the two-event satellite-label prototype and apply the fixed gate.
4. If it passes, update `docs/mvp.md` to Path A with the narrowed target.
5. If it fails, update `docs/mvp.md` to Path B without presenting the index as
   a prediction.

For the portfolio, this is stronger than choosing a model first. It demonstrates
label design, observation bias, geospatial ETL, missing-data handling,
remote-sensing validation, leakage prevention, and an evidence-based go/no-go
decision—the substance of real data science and data engineering work.

## Primary references

- [Iowa Environmental Mesonet — Archived Local Storm Reports](https://mesonet.agron.iastate.edu/request/gis/lsrs.phtml)
- [NWS Brownsville — Great June Flood of 2018](https://www.weather.gov/bro/2018event_greatjuneflood)
- [NWS Brownsville — June 24, 2019 flood](https://www.weather.gov/bro/2019event_june24flood)
- [NWS Brownsville — Hurricane Hanna](https://www.weather.gov/bro/2020event_hanna)
- [ESA — Sentinel-1 mission](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-1)
- [NASA Earthdata — Change detection using OPERA Sentinel-1 RTC](https://www.earthdata.nasa.gov/learn/tutorials/change-detection-using-opera-sentinel-1-rtc)
- [NASA Earthdata — OPERA Dynamic Surface Water Extent](https://www.earthdata.nasa.gov/news/new-product-provides-detailed-maps-water-around-landmasses)
- [NASA Earthdata — MODIS and VIIRS global flood products](https://www.earthdata.nasa.gov/data/instruments/viirs/near-real-time-data/nrt-global-flood-products)
- [NOAA NCEI — VIIRS 375 m flood products](https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc:C01476)
- [Copernicus — Sentinel-2 Level-2A](https://sentinels.copernicus.eu/sentinel-data-access/sentinel-products/sentinel-2-data-products/collection-1-level-2a)
- [Microsoft Planetary Computer — Sentinel-1 RTC](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc)
- [Microsoft Planetary Computer — Sentinel-2 Level-2A](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a)

## Reproducibility notes

- The Hidalgo County geometry used for clipping came from the Census TIGERweb
  county service for county FIPS `48215`.
- Public STAC catalog searches were used to enumerate Sentinel-1 RTC and
  Sentinel-2 Level-2A acquisitions by bounding box and event window.
- County-clipped Sentinel-1 crops were fetched through the Planetary Computer
  data API and compared on identical EPSG:4326 grids.
- This feasibility review used downsampled crops to avoid treating an
  exploratory calculation as the final label pipeline. The committed prototype
  must retrieve analysis-resolution assets, preserve exact transforms, and test
  all masks and thresholds.
- Earthdata-authenticated historical MODIS files were not retained during this
  review. Their catalog presence and the Hidalgo tile/date coverage were
  verified; authenticated acquisition belongs in the prototype ingestion step.

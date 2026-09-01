# MVP Definition — Colonia Flood Risk Platform

**Status:** Draft for review
**Scope:** First thin vertical slice only

## MVP versus the complete semester project

This document defines **only the first thin vertical slice**, not the finished
semester project. The two must not be conflated.

- **The MVP** proves that one end-to-end path works: stored geospatial data →
  FastAPI endpoint → risk shading on an interactive map, for Hidalgo County. It
  is an integration and feasibility deliverable. Its success condition is that
  the path is genuine and the numbers flowing through it are honestly
  described.
- **Later semester milestones** deepen what the slice establishes: richer data
  engineering and ingestion, fuller model evaluation and comparison, a
  bilingual (English and Spanish) user experience, workflow orchestration, and
  a hardened deployment.

Section 10 lists what is excluded. Most of those exclusions are *deferrals to
later milestones*, not permanent rejections; each is marked accordingly.
Nothing in this document should be read as a claim that the excluded work is
unimportant to the project — only that it is not required to prove the first
slice.

## How to read this document

Statements are tagged to separate what has been decided from what has not:

- **[CONFIRMED]** — an agreed project decision. Changing it is a scope change.
- **[PROVISIONAL]** — a working assumption adopted so the slice can proceed. It
  may change without renegotiating the MVP, but it must be revisited before the
  MVP is considered complete.
- **[OPEN]** — not yet decided. Tracked in section 13.

No dataset, data source, model, accuracy figure, or user commitment appears in
this document unless it has actually been established. Where a source has not
been selected, the requirement is written against the *category* of data, and
selection is deferred to section 13.

---

## 1. Problem statement

Colonias in Hidalgo County, Texas are residential settlements that frequently
sit on low-lying terrain with limited or incomplete stormwater drainage
infrastructure. Rainfall-driven flooding and prolonged standing water are a
recurring hazard in the region.

Information relevant to that hazard is distributed across separate datasets and
systems: rainfall data, terrain and elevation data, colonia boundary data, and
whatever historical flood records exist. These are published by different
agencies, in different formats, and at different spatial resolutions. Combining
them for a specific location requires locating each source, reconciling their
formats and resolutions, and doing the geospatial work by hand — which puts
that combined view out of practical reach for most people who might want it.

**[OPEN]** No survey of existing tools has been conducted. This document
therefore makes no claim that such a combined view is unavailable elsewhere.
The problem being addressed is the cost of assembling it from distributed
sources, and a review of existing regional and federal flood-mapping tools
should be performed before any claim of novelty is made.

**[CONFIRMED]** The platform is an experimental flood-risk decision-support
prototype. It is explicitly **not** an official emergency-warning system, and
it does not replace official flood forecasts, alerts, evacuation guidance, or
emergency services.

The MVP is deliberately scoped as a *feasibility and integration* deliverable.
Its purpose is to prove that geospatial data can be stored, served, and
rendered as a spatially varying risk surface end to end.

**What this means for accuracy.** Operational and field validation — verifying
outputs against observed flooding in the field, or against the judgment of
local agencies — is outside the first vertical slice. It is not, however,
abandoned:

- Under **Path A**, honest offline evaluation is *required* within the MVP
  (sections 6.1, 6.3, and 11). A model that has not been evaluated offline is
  not an acceptable MVP deliverable.
- Under **Path B**, there is nothing to evaluate against, because the index is
  not fitted to observed outcomes. Its integrity requirement is labeling, not
  evaluation.
- Under **either** path, the system makes **no public-safety reliability
  claim**. Offline evaluation metrics describe performance on held-out
  historical data under stated assumptions. They are not evidence that the
  system is reliable enough to inform decisions about personal safety,
  evacuation, or emergency response, and they must never be presented as such.

## 2. Intended users

**[CONFIRMED]** The only confirmed user of the MVP is the project team itself.
The slice is built to be exercised, reviewed, and evaluated internally.

**[PROVISIONAL]** The following are candidate user groups that motivate the
design. None has been interviewed, recruited, or committed to the project, and
no requirement in this document may be justified solely by an unvalidated claim
about what these groups need:

- Local and county planning or public-works staff evaluating where drainage
  problems concentrate.
- Community organizations and colonia advocacy groups seeking a shared
  reference view of local flood exposure.
- Researchers and students working on regional flood and environmental-justice
  questions.
- Residents seeking non-authoritative context about their area.

**[OPEN]** Whether any of these groups will be engaged for the MVP, and which
one is the primary audience after the MVP, is unresolved. Until at least one
real user has been consulted, all user-experience decisions in this slice are
provisional.

**Design consequence.** Because no user need has been validated, the MVP's
user-facing surface is intentionally minimal and heavily caveated. It presents
a relative risk surface and the inputs behind it; it does not offer advice,
recommendations, or instructions for action.

## 3. Geographic scope

**[CONFIRMED]** The MVP covers **Hidalgo County, Texas**, and only Hidalgo
County. No other county, and no RGV-wide or multi-county coverage, is in scope.

Requirements:

- The analysis extent is the Hidalgo County administrative boundary.
- **[PROVISIONAL]** Data ingestion may pull a buffer beyond the county line
  (suggested: 1–2 km) so that terrain derivatives such as slope are not
  distorted at the boundary. Cells outside the county boundary are computed but
  are not served to the frontend.
- The map's initial view is framed to Hidalgo County.
- **[PROVISIONAL]** Panning outside the county is permitted, but no risk
  shading is rendered outside the county extent; the absence of data must be
  visually distinguishable from low risk.

**[PROVISIONAL]** Analysis is performed in a projected coordinate reference
system appropriate to South Texas so that grid cells have consistent real-world
dimensions; data is served to the frontend in EPSG:4326. The specific projected
CRS is **[OPEN]**.

## 4. Geographic prediction unit

**[CONFIRMED]** Risk is computed for **fixed geographic grid cells**, not for
whole colonias. A single value is never assigned to an entire colonia polygon.

Rationale: colonia polygons vary substantially in size and shape, and flooding
varies within them. A single per-colonia value would hide the intra-colonia
variation that the platform exists to expose, and would imply a uniformity in
the hazard that the input data does not support.

**[CONFIRMED]** Colonia boundaries are rendered as an **overlay** on top of the
grid-based risk surface. They provide geographic context and labeling. They are
not the unit of prediction and are not used to aggregate or smooth risk values
in the MVP.

**[PROVISIONAL]** Cell size is fixed at a single value in the range
**250–500 m** for the entire MVP. A single value must be chosen before
implementation begins and must not vary by area or zoom level.

Constraints on that choice:

- Cell size must be constant across the full county extent.
- Cell size must be recorded in the database and returned in the API response,
  so no consumer has to infer it.
- **The chosen value must be justified in writing against the effective
  resolution of each input**, not against the coarsest input alone. Inputs
  legitimately differ in resolution: a fine DEM can support terrain variation
  well below 250 m, while a rainfall product may be far coarser. Choosing a
  cell finer than the rainfall resolution is defensible when a finer input is
  genuinely driving the variation, and the justification must say which input
  is doing that work.
- **Assigning a coarse value to fine cells does not refine it.** If a rainfall
  measurement covers an area much larger than a grid cell, every cell inside it
  carries the same value, and nothing in the system may imply otherwise. The
  documentation, the API metadata, and the cell inspection panel must expose
  each input's native resolution alongside its value, so a user can see which
  parts of a cell's value carry real spatial detail and which are inherited
  from a coarser source.

**[OPEN]** The exact cell size, and the total resulting cell count for Hidalgo
County, must be computed and recorded once the county boundary is loaded. The
count is expected to fall on the order of 10⁴–10⁵ cells; this must be verified
against the actual boundary rather than assumed, because the count drives the
API payload and rendering requirements in section 9.

## 5. Initial input data

**[CONFIRMED]** The first environmental inputs are **rainfall** and
**elevation-derived terrain features** (elevation and slope). **[CONFIRMED]**
Colonia boundaries are also ingested, for overlay display.

**No specific data provider, product, or file has been selected.** The
following describes what each input must supply. Source selection is **[OPEN]**
and tracked in section 13.

### 5.1 Rainfall

- **Required:** a rainfall quantity that can be attached to each grid cell.
- **[PROVISIONAL]** The MVP uses a small, fixed set of discrete rainfall
  scenarios (for example, a set of rainfall depths over a fixed duration)
  rather than a live or continuously updating feed. This keeps the slice static
  and reproducible.
- **[OPEN]** Whether rainfall enters the MVP as historical event totals,
  design-storm depths, or user-selected scenario values.

### 5.2 Terrain

- **Required:** a digital elevation model covering the county extent, from
  which at minimum **elevation** and **slope** are derived per grid cell.
- **[PROVISIONAL]** Additional terrain derivatives (for example, curvature,
  flow accumulation, or a topographic wetness index) are *not* part of the
  first slice. They may be added later without changing the architecture.
- The DEM's native resolution and vertical units must be recorded, because they
  bound the defensible cell size in section 4.

### 5.3 Colonia boundaries

- **Required:** polygon geometries for colonias within Hidalgo County, with at
  minimum a stable identifier and a name for each polygon.
- Used for display and labeling only in the MVP.

### 5.4 Historical flood observations — conditional

- **Required only if** the labeled-target path in section 11 is taken.
- Must supply georeferenced observations of documented flooding or standing
  water that can be associated with both a location and a time.
- **[OPEN]** Whether any such source exists at usable coverage and quality for
  Hidalgo County. This is the single most consequential unknown in the MVP.

### 5.5 Requirements applying to every input

- Every ingested dataset is recorded in a data-source register within the repo
  with: source name, publisher, URL or access method, retrieval date, native
  CRS, native resolution, license or terms of use, and known limitations.
- Raw inputs are not committed to the repository. (`data/raw/` and
  `data/processed/` are already excluded by `.gitignore`.)
- Ingestion is scripted and re-runnable from the recorded sources. A reviewer
  with access to the same sources must be able to reproduce the processed grid
  without manual steps.
- Any input whose license does not permit the intended use is not ingested.

## 6. Provisional prediction target

The target depends on label availability. Section 11 defines how that decision
is made; this section defines the two candidate targets.

### 6.1 Path A — labeled target (preferred)

**[PROVISIONAL — conditional on section 11]** If defensible historical flood
labels are available, the modeling target is:

> The likelihood that a given grid cell experiences documented flooding or
> standing water under specified rainfall conditions.

- Unit of prediction: one grid cell under one rainfall condition.
- Requires a defined positive class, a defined negative class, and an explicit,
  documented rule for how observations are assigned to cells and to rainfall
  conditions.

#### Model risk score versus calibrated probability

**[CONFIRMED]** A classifier's raw output is **not** a probability. Most
classifiers emit an uncalibrated score that ranks cells correctly while being
systematically wrong in level — a score of 0.7 does not mean the event occurs
in 70% of such cases unless that has been checked. Naming an uncalibrated score
a "probability" overstates what the model established.

Therefore:

- **Default naming: model risk score.** The Path A output is called a *model
  risk score* — a relative, ordinal-strength value — in the UI, the API, the
  database, and the documentation.
- **Promotion to "probability" requires calibration.** The output may be called
  a probability **only if** calibration is both *performed* and *evaluated*,
  and the evaluation is committed to the repository. Performing calibration
  without evaluating it does not qualify.
- **Required calibration evidence**, on held-out data, using the same spatially
  aware split as the rest of the evaluation:
  - a **calibration curve** (reliability diagram) with the binning strategy
    stated, and
  - a **Brier score**, reported against a base-rate reference so the reader can
    tell whether it reflects skill or only the class balance.
- **The calibration method is recorded** (for example, Platt scaling or
  isotonic regression), along with the data it was fitted on, which must be
  disjoint from the data used to train the model.
- **If the calibration curve shows material miscalibration**, the output stays
  a model risk score. Reporting the curve does not by itself earn the
  probability label — the curve has to actually show agreement between
  predicted and observed frequencies.
- **The name in the interface follows the evidence.** If the output is a model
  risk score, no `%` sign, no "probability", no "chance", and no "likelihood of
  flooding" appears next to it anywhere in the system.

### 6.2 Path B — unlabeled fallback

**[CONFIRMED]** If defensible labels are unavailable, the MVP falls back to a
clearly labeled **flood-susceptibility index** and **must not claim to predict
observed flooding**.

- Output: a relative, unitless susceptibility score.
- It is a transparent, documented combination of terrain and rainfall inputs —
  not a trained predictor of observed outcomes.
- It carries **no probabilistic interpretation**. It must not be described,
  labeled, formatted, or colored in any way that implies a probability, a
  likelihood, a percentage, or a validated prediction.
- The scoring formula and every weight in it are documented in the repository.

### 6.3 Applies to both paths

- The MVP's output is **relative within Hidalgo County**. It is not comparable
  to any external flood product and is not transferable to other geographies.
- **No performance figure appears in this document**, because none has been
  measured. Under Path A, offline evaluation is required *within* the MVP
  (section 11) and its results are reported honestly — including when they are
  poor. A poor but honestly reported result is an acceptable MVP outcome; an
  unreported or flattering one is not.
- **Offline evaluation is not a safety warrant.** Whatever the metrics show,
  the system makes no public-safety reliability claim. Held-out historical
  performance under stated assumptions is not evidence of fitness for decisions
  about personal safety, evacuation, or emergency response.
- **[OPEN]** The specific evaluation protocol and reported metrics under
  Path A. Not applicable under Path B.

## 7. User-facing output

**[CONFIRMED]** The user-facing output is an interactive map of Hidalgo County
with **risk shading on grid cells**, plus a **colonia boundary overlay**.

The MVP delivers:

1. **Base map** framed to Hidalgo County.
2. **Risk surface** — grid cells shaded by the section 6 value, using a single
   documented, legible color scale.
3. **Colonia overlay** — boundary outlines drawn above the risk surface,
   distinguishable from it and not obscuring it.
4. **Legend** — maps colors to values, states the units (or states explicitly
   that the value is unitless and relative), and states the cell size.
5. **Cell inspection** — selecting a cell shows its value and the input feature
   values behind it (rainfall, elevation, slope), each with its native
   resolution, so the number is inspectable rather than opaque and a user can
   see which inputs carry cell-level detail and which are inherited from a
   coarser source (section 4).
6. **Rainfall scenario control** — **[PROVISIONAL]** if more than one rainfall
   scenario is served, a control to switch between them, with the active
   scenario always visible on screen.
7. **Persistent disclaimer** — visible without scrolling or interaction,
   stating that this is an experimental prototype and not an official warning
   system, forecast, or source of evacuation guidance.
8. **Provenance statement** — reachable from the main view, naming the data
   sources actually used, their retrieval dates, and the method (Path A or
   Path B) that produced the displayed value.

**The displayed value is named according to what was actually established:**

- **Path A without evaluated calibration** — labeled a *model risk score*
  everywhere it appears, with no percentage formatting (6.1).
- **Path A with evaluated calibration** — may be labeled a probability, and the
  calibration evidence must be reachable from the provenance statement.
- **Path B** — labeled a *flood-susceptibility index* everywhere it appears —
  legend, inspection panel, and provenance — and never presented as a
  probability or a percentage.

**Not included:** search, address lookup, routing, alerts, notifications,
report export, saved locations, or accounts.

## 8. Functional requirements

Each requirement is independently verifiable.

### Data and storage

- **F1.** PostgreSQL with PostGIS stores the county boundary, colonia polygons,
  the grid-cell geometries, and the per-cell feature and risk values.
  **[CONFIRMED]**
- **F2.** Schema is created and migrated by versioned, re-runnable scripts
  committed to the repository. No schema object is created by hand.
- **F3.** Every spatial table has an explicit, recorded CRS and a spatial index.
- **F4.** The grid is generated once by a committed script from the county
  boundary and the chosen cell size, is deterministic, and yields identical
  cell identifiers and geometries on re-run.
- **F5.** The stored data must cover, at minimum, the following, keyed so that
  each item can be traced back to a specific grid cell:
  - a stable cell identifier and the cell geometry;
  - the static terrain features for that cell (elevation, slope);
  - the rainfall value applied, together with the scenario it belongs to;
  - the computed risk or susceptibility value, together with the identifier of
    the method and method version that produced it.

  **These are not required to live in one table, and should not.** Static grid
  geometry and terrain features are computed once and do not vary; rainfall
  values vary by scenario; computed values vary by both scenario *and* method
  version, and any historical flood observations under Path A vary by event and
  location independently of the grid. Collapsing all of these into a single
  wide table would force the static geometry to be duplicated for every
  scenario-and-version combination and would make it impossible to add a
  scenario or re-run a model without rewriting rows that never changed.

  The eventual schema must therefore **separate static grid cells and their
  terrain features from scenario-dependent and versioned prediction outputs**,
  with observations modeled separately again. Exact table names, column names,
  key structure, and the full schema are deliberately **[OPEN]** and are settled
  during implementation, not in this document.
- **F6.** Cells with missing or invalid input data are recorded as missing —
  never defaulted to zero, and never silently dropped.

### Backend

- **F7.** A FastAPI service exposes the risk surface over HTTP.
  **[CONFIRMED]**
- **F8.** An endpoint returns grid cells with geometry and risk value for a
  requested extent, filtered to the Hidalgo County extent.
- **F9.** Every response carries the metadata needed to interpret it: cell size,
  CRS, method identifier (Path A or Path B), the value's name as established by
  F26 (model risk score, calibrated probability, or susceptibility index),
  value range, units (or an explicit unitless flag), and each input's native
  resolution.
- **F10.** Request and response schemas are declared with Pydantic and surfaced
  through the automatically generated OpenAPI documentation.
- **F11.** Invalid requests return a 4xx status with a structured error body;
  they never return an empty success response.
- **F12.** A health endpoint reports service status and database connectivity.
- **F13.** The backend performs no model training at request time. It serves
  precomputed values only.

### Frontend

- **F14.** A React and TypeScript application renders the interactive map.
  **[CONFIRMED]**
- **F15.** The map renders the risk surface from the FastAPI endpoint — not
  from a bundled static file, and not from hardcoded values.
- **F16.** The map renders colonia boundaries as an overlay above the risk
  surface. **[CONFIRMED]**
- **F17.** All eight elements listed in section 7 are present.
- **F18.** Loading, empty, and error states are distinguishable from one another
  and from a genuinely low-risk area. A failed data load never renders as an
  unshaded map with no explanation.
- **F19.** The colonia overlay can be toggled off.

### End-to-end path

- **F20.** **[CONFIRMED]** One complete working path exists from stored
  geospatial data → FastAPI endpoint → risk shading on the interactive map,
  demonstrable in a single session against a running system.
- **F21.** The full stack starts locally from a documented command sequence,
  using Docker Compose for the database.

### Modeling

- **F22.** The section 11 label-feasibility decision is recorded in the
  repository, with its evidence, before any model or index is implemented.
- **F23.** The value-producing step (trained model under Path A, or scoring
  formula under Path B) runs as a committed, re-runnable script that writes its
  output to the database.
- **F24.** Under Path A, a baseline model is implemented and evaluated
  alongside any other model, so that model choice can be justified rather than
  assumed. Offline evaluation runs as committed code against a held-out split,
  and writes its results to a committed evaluation report — including when the
  results are poor.
- **F25.** Under Path B, no code, endpoint field, label, or documentation
  string describes the output as a probability or a prediction of observed
  flooding.
- **F26.** Under Path A, the served value is named a **model risk score**
  throughout the system unless calibration has been performed *and* evaluated
  with a calibration curve and a Brier score, and that evidence is committed
  (6.1). The API metadata states which of the two the value is, so the frontend
  never has to guess how to label it.
- **F27.** No code path, response field, or interface string asserts that the
  system is reliable enough to inform safety, evacuation, or emergency
  decisions, under either path.

## 9. Non-functional requirements

These are requirements to be met and verified — not claims that they have
already been met. The performance numbers in particular are provisional
placeholders; see the note under *Performance*.

### Performance

**[PROVISIONAL] — N1 through N3 are placeholder budgets, not validated
targets.** They were set before the grid-cell count, the payload size, the
rendering strategy, the deployment environment, and the network conditions were
known. Any one of those can move the achievable numbers by an order of
magnitude, in either direction. They exist so that performance is measured
rather than ignored.

- **N1.** The county-extent risk-surface request returns in **under 2 seconds**
  at the 95th percentile.
- **N2.** The map reaches first interactive render of the risk surface in
  **under 5 seconds**.
- **N3.** Pan and zoom remain responsive with the full county grid loaded, with
  no interaction blocked for more than **500 ms**.
- **N4.** **These budgets must be revisited once the following are known**, and
  the revision recorded with its reasoning:
  - the actual grid-cell count for Hidalgo County at the chosen cell size,
  - the actual serialized payload size for a county-extent response,
  - the rendering strategy finally adopted (raw GeoJSON, vector tiles, or
    paginated extents),
  - the deployment environment the measurement targets, and
  - the network conditions assumed.

  Revising a budget upward on this evidence is a legitimate outcome. Silently
  failing it is not.
- **N5.** **The measurement method is documented and reproducible.** Before any
  performance claim is recorded, a committed document states: the hardware and
  environment, the dataset and cell count in play, the exact requests or
  interactions exercised, the number of iterations, whether caches were warm or
  cold, the tool used, and how the percentile was computed. Another developer
  must be able to re-run it and get comparable numbers. A performance figure
  without a recorded method is not accepted as evidence.
- **N6.** If the payload for the full county at the chosen cell size prevents
  N1–N3, the mitigation is server-side tiling, simplification, pagination, or a
  revised budget under N4 — **not** coarsening the cell size below the
  section 4 decision without explicitly revisiting that decision.

### Correctness and reproducibility

- **N7.** The pipeline is deterministic: two runs from the same inputs produce
  identical per-cell values. Any randomness is explicitly seeded.
- **N8.** Every transformation from raw input to served value is traceable
  through committed code. No value in the database originates from a manual
  edit or an uncommitted notebook cell.
- **N9.** All CRS transformations are explicit. No code relies on an implicit
  or default CRS.

### Testing and quality

- **N10.** Automated tests cover: grid generation, feature computation, the
  value-producing step, and every API endpoint.
- **N11.** At least one end-to-end test exercises the F20 path from database
  through API to a rendered response payload.
- **N12.** Tests run in CI on every pull request and must pass before merge.
- **N13.** Python code passes linting and type checks; TypeScript compiles with
  no errors under strict mode.
- **N14.** Tests requiring the database run against a disposable test database,
  never against a developer's working database.

### Transparency and safety

- **N15.** The prototype disclaimer is present in the UI without interaction,
  in the API response metadata, and in the repository documentation.
- **N16.** The active method (Path A or Path B) is discoverable by a user from
  the interface alone, without reading the source code. Under Path A, whether
  the value is a model risk score or a calibrated probability is discoverable
  the same way (6.1).
- **N17.** No language anywhere in the UI, API, or documentation implies
  official status, emergency authority, validated accuracy, or actionable
  safety guidance. Where evaluation results are shown, they are presented as
  offline performance on held-out historical data — never as a public-safety
  reliability claim.

### Operations

- **N18.** No secrets are committed. Configuration is supplied through
  environment variables, with a committed `.env.example` documenting every
  required variable.
- **N19.** A new developer can bring up the full stack from a clean checkout by
  following the README, with no undocumented steps.

### Accessibility

- **N20.** **[PROVISIONAL]** The risk color scale is legible under common forms
  of color-vision deficiency, and no information is conveyed by color alone —
  the inspection panel always exposes the underlying numeric value.

## 10. Explicit non-goals

Each exclusion is marked either **[DEFERRED]** — planned for a later semester
milestone — or **[OUT OF SCOPE]** — not planned for this project at all.

**[CONFIRMED] — not required for the first vertical slice:**

- **Airflow** — **[DEFERRED]**; ingestion and processing run as scripts or a
  manual sequence for now. Orchestration is a later milestone.
- **dbt** — **[DEFERRED]**; transformations are code in the repository.
- **MLflow** — **[DEFERRED]**; experiment tracking is manual and documented in
  the repo.
- **Live alerts** — **[OUT OF SCOPE]**. No notifications, subscriptions, or
  real-time warnings of any kind. This is the line between a prototype and an
  emergency-warning system, and the project does not cross it.
- **AWS** — **[DEFERRED]**; no cloud infrastructure requirement for the slice.
- **Terraform** — **[DEFERRED]**; no infrastructure as code for the slice.
- **Authentication** — **[DEFERRED]**; no accounts, login, roles, or per-user
  state.
- **The LLM assistant** — **[DEFERRED]**; no natural-language interface.
- **RGV-wide coverage** — **[DEFERRED]**; Hidalgo County only.

**Additional exclusions for this slice:**

- **Real-time or forecast rainfall** — **[DEFERRED]**. The MVP is static and
  scenario-based.
- **Hydraulic or hydrodynamic modeling** — **[OUT OF SCOPE]**. No flow routing,
  no inundation-depth simulation, no drainage-network modeling.
- **Flood depth or timing** — **[OUT OF SCOPE]**. The output is a relative
  value per cell, not a depth, an extent, or an arrival time.
- **Operational and field validation** — **[DEFERRED]**. Verifying outputs
  against observed flooding in the field, or against local agency judgment, is
  outside the first slice. This is **not** a blanket exclusion of evaluation:
  under Path A, offline evaluation on held-out historical data is *required*
  within the MVP (sections 6.1, 6.3, 11, F24, F26). What is excluded is the
  operational validation that would be needed before anyone relied on the
  system — and until that exists, **no public-safety reliability claim is
  made**, whatever the offline metrics show.
- **Parcel- or address-level output** — **[OUT OF SCOPE]**. The grid cell is
  the finest unit produced; nothing is reported for an individual property.
- **Public production deployment** — **[DEFERRED]**. A demonstration deployment
  may exist, but hardening, scaling, uptime guarantees, and public promotion
  are later-milestone concerns.
- **Mobile-native applications** — **[OUT OF SCOPE]**.
- **Spanish localization** — **[DEFERRED]**. Excluded from the *first thin
  vertical slice only*. A bilingual English/Spanish experience is a **planned
  semester-project enhancement**, not an optional extra: it matters directly
  for the candidate audiences in section 2. Excluding it here is a sequencing
  decision that keeps the slice thin, and interface strings should be
  structured so that adding a second language later does not require rewriting
  the frontend.

## 11. Model-label feasibility decision

**[CONFIRMED]** The MVP takes one of two paths, decided by evidence, and the
decision is made and recorded **before** modeling begins.

### Decision procedure

1. **Search.** Conduct and document a search for georeferenced historical flood
   or standing-water observations covering Hidalgo County.
2. **Assess.** Evaluate each candidate source against the criteria below.
3. **Record.** Write the decision, the sources examined, and the reasoning to a
   committed document in `docs/`. A negative result is a valid and useful
   outcome and must be recorded with the same rigor as a positive one.
4. **Proceed** down Path A or Path B accordingly.

### Criteria for "defensible" labels

A source qualifies only if **all** of the following hold:

- **Georeferenced** — observations can be located to a point or polygon and
  assigned to grid cells without arbitrary guesswork.
- **Temporally attributable** — each observation can be tied to a date or event
  that can be matched to rainfall conditions.
- **Sufficient coverage** — enough positive observations to be meaningful
  across the county, not confined to a single event or a single neighborhood.
- **Known collection process** — the source's origin and its collection bias
  are documented well enough to be described honestly. Complaint- or
  report-driven data reflects who reports, not only where water stands; if such
  a source is used, that bias is stated in the UI and the documentation.
- **Usable negatives** — a defensible rule exists for what counts as a negative
  observation. Absence of a report is not, by itself, evidence of no flooding,
  and an unexamined absence-as-negative assumption disqualifies the source.
- **Licensed for this use.**

**[CONFIRMED]** If these criteria are not met, **Path B is taken.** Weak or
partial labels are not stretched to fit Path A. The consequences of a wrong
Path A claim — presenting an unvalidated number as a flood probability — are
worse than the reduced ambition of Path B.

### Path A — labeled

- Target as defined in section 6.1.
- Requires a documented cell-assignment rule, a documented rainfall-matching
  rule, a documented negative-class rule, and a spatially aware
  train/test split so that adjacent cells do not leak between splits.
- A baseline model is required (F24).

**Offline evaluation is required, not deferred.** Field and operational
validation are outside the slice (section 10), but a Path A model that has not
been evaluated offline is not an acceptable MVP deliverable. Required:

- Evaluation on a held-out split produced by the spatially aware splitting
  strategy above, so that spatial autocorrelation between neighboring cells does
  not inflate the result.
- Discrimination metrics appropriate to the class balance, reported alongside
  the base rate. Class imbalance is expected, and accuracy alone is not an
  acceptable headline metric.
- **Calibration evaluation** if the output is to be called a probability
  (6.1): a **calibration curve** with its binning strategy stated, and a
  **Brier score** reported against a base-rate reference. Without this
  evidence, the output remains a *model risk score*.
- The evaluation report is committed to the repository, including the
  assumptions and limitations that qualify it — label collection bias, coverage
  gaps, and the number of positive observations the result rests on.
- **Results are reported honestly, including poor ones.** A weak result that is
  accurately described satisfies this requirement. Selecting a favorable
  split, metric, or threshold after seeing the results does not.
- Whatever the metrics show, they are described as offline performance on
  held-out historical data under stated assumptions, and **never** as evidence
  of public-safety reliability (6.3, N17, F27).
- **[OPEN]** The specific discrimination metrics and the exact splitting
  strategy.

### Path B — unlabeled fallback

- Output as defined in section 6.2.
- Formula and weights fully documented and committed.
- Labeled as a susceptibility index everywhere it is shown (F25, N16).
- No evaluation metrics are reported, because the index is not fitted to
  observed outcomes and there is nothing to evaluate it against. The absence of
  metrics is stated plainly rather than left for a user to infer.
- **[PROVISIONAL]** Weights are chosen from documented reasoning about terrain
  and rainfall, and are explicitly acknowledged as not fitted to observed
  outcomes.

### Current state

**[OPEN]** The feasibility assessment **has not been performed**. Path A and
Path B are both live. Everything in this document that depends on the outcome
is tagged accordingly, and the architecture is designed so that only the
value-producing step and the associated labeling differ between paths.

## 12. MVP acceptance criteria

The MVP is complete when **all** of the following are demonstrably true. Each is
a binary check.

**Decision and documentation**

- [ ] **A1.** The section 11 feasibility decision is recorded in `docs/`, with
      the sources examined and the reasoning.
- [ ] **A2.** The data-source register (5.5) is committed and complete for every
      dataset actually used.
- [ ] **A3.** The chosen cell size and the resulting Hidalgo County cell count
      are recorded.

**Data**

- [ ] **A4.** PostGIS holds the county boundary, colonia polygons, and the full
      grid for Hidalgo County.
- [ ] **A5.** Every in-county grid cell has elevation, slope, and rainfall
      values, or is explicitly marked as missing.
- [ ] **A6.** Every in-county grid cell has a risk or susceptibility value, or
      is explicitly marked as missing.
- [ ] **A7.** Re-running the pipeline from raw inputs reproduces identical
      per-cell values (N7).

**Backend**

- [ ] **A8.** The FastAPI service starts and its health endpoint reports
      database connectivity.
- [ ] **A9.** The risk endpoint returns cells with geometry, value, and the
      full metadata set from F9.
- [ ] **A10.** OpenAPI documentation is generated and accurate.
- [ ] **A11.** Invalid requests return structured 4xx errors (F11).

**Frontend**

- [ ] **A12.** The map loads Hidalgo County and renders risk shading sourced
      from the API.
- [ ] **A13.** Colonia boundaries render as an overlay and can be toggled.
- [ ] **A14.** The legend states the value scale, the units or unitless nature,
      and the cell size.
- [ ] **A15.** Selecting a cell shows its value, its input feature values, and
      each input's native resolution.
- [ ] **A16.** The disclaimer is visible without interaction.
- [ ] **A17.** The active method (Path A or Path B) is visible to the user, and
      under Path A, whether the value is a model risk score or a calibrated
      probability.
- [ ] **A18.** Load failures and empty areas are visually distinct from
      low-risk areas.

**End-to-end**

- [ ] **A19.** The complete path — PostGIS → FastAPI → map shading — is
      demonstrated live in one session (F20).
- [ ] **A20.** **An automated integration test proves the PostGIS-to-API path
      is genuine.** The test loads known fixture data into a disposable test
      database, calls the API through its real HTTP interface, and asserts that
      the response contains the values derived from that fixture — so a
      hardcoded, cached, or fixture-file response fails the test. It runs in CI
      (N12), touches no developer or production database (N14), and leaves no
      state behind. Manual modification of a working database is **not** an
      acceptable substitute: it is unrepeatable, unreviewable, and risks
      corrupting real data.

**Quality**

- [ ] **A21.** Automated tests cover the surfaces listed in N10 and pass in CI.
- [ ] **A22.** The end-to-end test (N11) passes.
- [ ] **A23.** Linting and type checks pass for both Python and TypeScript.
- [ ] **A24.** A clean checkout can be brought up following the README with no
      undocumented steps (N19).
- [ ] **A25.** Performance against N1–N3 has been **measured** using a
      documented, reproducible method (N5), and the results are recorded.
      Either the budgets are met, or they have been revisited and revised under
      N4 with the reasoning recorded. An unmeasured budget fails this check;
      a budget that was measured, missed, and consciously revised passes it.

**Modeling — Path A only**

- [ ] **A26.** The offline evaluation report is committed, covers a spatially
      aware held-out split, reports metrics against the base rate, and states
      its limitations (section 11).
- [ ] **A27.** If — and only if — the output is labeled a probability anywhere
      in the system, a calibration curve and a Brier score are committed and
      show acceptable calibration (6.1). Otherwise the output is labeled a
      model risk score throughout.

**Integrity**

- [ ] **A28.** Under Path B, no artifact anywhere in the system describes the
      output as a probability or a prediction of observed flooding.
- [ ] **A29.** No accuracy or performance claim appears in the UI or the
      documentation that is not supported by a recorded evaluation or a
      recorded measurement.
- [ ] **A30.** Nothing in the UI, API, or documentation states or implies that
      the system is reliable enough to inform safety, evacuation, or emergency
      decisions (F27, N17).

## 13. Open questions

Ordered by how much they block the work.

### Blocking — must be resolved before implementation

1. **Do defensible historical flood labels exist for Hidalgo County?**
   Determines Path A vs. Path B (section 11). Everything downstream depends on
   it. **Owner and target date: unassigned.**
2. **Which rainfall data source, and in what form?** Historical event totals,
   design-storm depths, or user-selected scenarios (5.1).
3. **Which DEM source, and at what native resolution?** Its resolution bounds
   the defensible cell size (5.2, section 4).
4. **Which colonia boundary source, and how current is it?** Colonia
   inventories vary in definition and vintage; the chosen definition must be
   stated in the UI (5.3).
5. **Final grid cell size within 250–500 m** (section 4), which cannot be fixed
   until questions 2 and 3 are answered.

### Design — resolvable during implementation

6. **Projected CRS for analysis** (section 3).
7. **How many rainfall scenarios does the MVP serve, and which ones?** Affects
   whether the section 7 scenario control exists at all.
8. **Payload strategy for the full county grid** — raw GeoJSON, vector tiles,
   or extent-based pagination (N4, N6). Depends on the verified cell count.
9. **Color scale and class breaks** for the risk surface, and whether breaks are
   fixed or data-driven (section 7, N20).
10. **Representation of missing data** on the map, distinct from low risk (F6,
    F18, A18).
11. **Schema shape** — how the separation between static grid cells and
    features, scenario-dependent rainfall, and versioned prediction outputs is
    realized in tables and keys (F5). Deliberately not settled here.
12. **Revised performance budgets** once cell count, payload size, rendering
    strategy, deployment environment, and network conditions are known, plus
    the measurement method that will be committed (N1–N6).

### Path A only

13. **Rule for assigning observations to grid cells and to rainfall
    conditions** (6.1).
14. **Definition of the negative class** (section 11).
15. **Evaluation protocol, spatial splitting strategy, and reported
    discrimination metrics** (6.3, section 11).
16. **Whether calibration will be attempted at all**, and by what method — and
    therefore whether the output can be called a probability or stays a model
    risk score (6.1, F26, A27). Given the label limitations expected in
    section 11, the model risk score is the likelier outcome.
17. **Which model beyond the baseline**, and on what grounds it is selected
    (F24).

### Path B only

18. **Which terrain and rainfall factors enter the index, and with what
    weights** (6.2).
19. **How the index is presented numerically** so it is not mistaken for a
    probability — for example, ordinal classes rather than a 0–1 number
    (6.2, F25).

### Product and later milestones

20. **Will any real user from section 2 be engaged before or during the MVP?**
    Until then, every user-experience decision here is provisional.
21. **Where is the demonstration deployed, and is it publicly reachable?** A
    public URL raises the bar on N15–N17.
22. **Spanish localization** — deferred from the first slice but a planned
    semester-project enhancement (section 10). Open questions: which milestone
    it lands in, who provides and reviews the translations (machine-translated
    hazard language is a real risk), and whether the frontend's string handling
    needs to be structured for it from the start.
23. **Sequencing of the remaining semester milestones** — orchestration, deeper
    data engineering, fuller model evaluation, and hardened deployment — and
    which of them depend on the MVP's outcome.
24. **What triggers expansion beyond Hidalgo County?** Not in this slice, but
    the schema should not make it needlessly hard.

# pedsim: Requirements Catalogue for Research Features

**Project:** PedestrianAgents3D / `pedsim` (Python edition)
**Study area:** Göbekli Tepe and the Taş Tepeler cluster, Şanlıurfa province, Türkiye
**Owner:** Gideon Aschwanden
**Status:** v1.1, 2026-11-08. The open questions in section 15 are decided. Section 17 records what is implemented and what is still partial.
**Audience:** the developer implementing these features, and the researcher reviewing the outputs

---

## 0. How to read this document

### 0.1 Purpose

`pedsim` already simulates pedestrians at two scales: the **cluster** (about 80 km, 250 m cells) and the **village** (1.2 km, 6 m cells). It has Tobler slope costs, seasonal rivers, a palaeo-corrected DEM, a sourced site catalogue and georeferencing for published plans. This catalogue says what to build so the tool can (a) test specific archaeological hypotheses, (b) back its results with field calibration and uncertainty, and (c) hand those results to archaeologists in formats they already use, including on site with little or no internet.

### 0.2 Scope

| ID | Feature | In scope |
|---|---|---|
| MAP | Path-density overlay on a web-map basemap (satellite, street or terrain) | ✅ |
| CHR | Chronology: occupation dates, co-occupation rule, start/end time slider (merges aims A1 and A7) | ✅ |
| A1 | Scenario test: residential village vs. gathering place | ✅ |
| A2 | Gathering calendar (seasons, events) | ✅ |
| A6 | Taş Tepeler network analysis | ✅ |
| A7 | Time-range slider (start and end) | ✅ (specified under CHR) |
| A8 | Daily tasks and population classes | ✅ |
| A9 | Regional scale for obsidian exchange | ✅ |
| B10 | Field calibration: walk input, calibration routes, model fitting | ✅ |
| C15 | GIS export (.shp, GeoPackage, GeoTIFF, QGIS project) and Strava/GPX import | ✅ |
| C16 | Building phases as switchable groups, linked to ODs, population and routes | ✅ |
| D20 | Offline-first field version (PWA, edge computing) | ✅ |
| A3 | Megalith hauling | ❌ excluded |
| A4 | Enclosure capacity and egress | ❌ excluded |
| A5 | What visitors saw (iconography visibility) | ❌ excluded |

### 0.3 Conventions

- **Requirement IDs** look like `CHR-03`. Every requirement has a **priority** (MoSCoW: **M**ust, **S**hould, **C**ould) and **acceptance criteria (AC)** a test can check.
- **Dates** are **calibrated BC as positive integers, larger = earlier**, the same as `pedsim.sites.Site.start_bc/end_bc`. An interval is `[end_bc, start_bc]`. Never mix in BP or negative years without explicit conversion (`BP = BC + 1950`).
- **Coordinates:** internally the existing `geo.LocalFrame` (metres east/north of an origin, UTM zone 37N = **EPSG:32637**). Exports are in EPSG:32637 (projected) or EPSG:4326 (GPX, GeoJSON, web map).
- **`ASSUMPTION`** marks a default value that is a modelling choice, not a published fact. Every such value must (1) be a parameter, (2) live in a config file rather than in code, and (3) appear in the run record (see X-01). The researcher will replace these defaults with sourced values.
- **`VERIFY`** marks a literature claim the researcher should check before it goes into a paper.

### 0.4 Guiding principles (apply to every feature)

1. **Interpretations are switchable layers, not facts.** This is already how plans, rivers and the palaeo-DEM work. Phases, population classes, calendars and date ranges follow the same pattern.
2. **Unknown stays unknown.** Missing dates or coordinates are never silently filled in. They are excluded or flagged, and the UI shows which (same principle as `sites.Confidence`).
3. **Every output can be reproduced** from a scenario file plus a random seed (X-01).
4. **Results come with spread.** Any figure meant for publication must be producible as an ensemble with a spread measure (X-03).
5. **Core logic stays in `pedsim` (Python).** The desktop viewer, the web/field version and the export tools are thin clients on top of it. No second implementation of the simulation unless D20 benchmarks force one (D20-04).

---

## 1. Target architecture (overview)

```
python/pedsim/
  ── existing ──
  grid.py  agent.py  simulation.py  topography.py  layers.py  rivers.py
  sites.py paleo.py  geo.py  plans.py  maps.py  scenes.py  app.py  viewer.py
  ── new ──
  scenario.py      # X-01 scenario file (YAML) load/validate/hash, run record
  chronology.py    # CHR: intervals, co-occupation rule, active-set at time range
  phases.py        # C16: Phase entity, membership, activation
  population.py    # A8: population classes, inhabitant estimates
  tasks.py         # A8: task catalogue, daily schedules, task → OD generation
  calendar.py      # A2: month → season/events/task weights
  hypotheses.py    # A1: scenario families + diagnostic metrics + comparison
  network.py       # A6: travel-time matrix, graph metrics, gravity model
  regional.py      # A9: third scale, sources, distance-decay fit
  ensemble.py      # X-03: multi-seed / parameter-sampling runs
  calibration.py   # B10: track segmentation, Tobler fit, route-choice scoring
  tracks.py        # B10/C15: GPX/FIT/TCX/Strava import, GPX export
  gis_export.py    # C15: SHP/GPKG/GeoTIFF/QGIS project export
  webmap/          # MAP: tile pyramid / COG writer, static map renderer
web/               # D20: PWA field client (MapLibre GL JS + packed playback)
data/
  config/          # YAML: population classes, tasks, calendar, phases, obsidian
  routes/          # B10: calibration route library (GeoJSON)
  packs/           # D20: offline data packs (built, gitignored)
```

The paths in that tree live under `python/` in this repository (`python/data/config`, `python/data/routes`, `python/data/schema`). The repository-root `data/` directory is the Java font folder and is not the research config. `python/data/packs/` is gitignored. The field client ships a copy of the synthetic village pack at `web/packs/goebekli/scene.json`.

### 1.1 Changes to existing data structures

| Structure | Change | Needed by |
|---|---|---|
| `sites.Site` | add `phase_ids`, `date_quality` (`radiocarbon` / `typological` / `none`), optional `start_bc_sd`, `end_bc_sd` | CHR, C16 |
| `od.OD` | add `site` (catalogue name), `phase_ids: list[str]`, `kind` (`gate` / `house` / `water` / `quarry` / `resource` / `site` / `gathering`), `capacity` (inhabitants), `tags` | A8, C16, CHR |
| `building.Building` | add `phase_ids`, `function` (`domestic` / `special` / `storage` / `unknown`), `inhabitants` (optional override) | C16, A8 |
| `agent.Agent` | add `pclass` (population class id), `task` (task id), `load_kg`, `speed_factor`, `day_minutes_used` | A8 |
| `Simulation.geometry_dict()` | bump `GEOMETRY_FORMAT`; add `phases`, `population`, `scenario_ref`; **write a migration** for older saves | C16, X-01 |
| `OD.to_line()` text format | keep unchanged for compatibility with the Java tool; new fields go only into the JSON save | C16 |
| `geo.site_ods(group_by_period=…)` | replace the hard-coded PPNA/PPNB grouping with `chronology`-driven groups | CHR |

---

## 2. Cross-cutting requirements (X)

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| X-01 | M | **Scenario file.** Every run is defined by a YAML scenario: scene (`cluster` / `village:<site>` / `regional`), time range, toggles, phase set, population config, task config, calendar month, terrain parameters, number of agents, number of steps, seed(s). `scenario.py` validates it against a JSON Schema and computes a SHA-256 hash of its normalised form. | Loading the same scenario and seed twice gives bit-identical occupancy arrays. An invalid file fails with a message naming the bad key. |
| X-02 | M | **Run record.** Every run writes `<run_id>/run.json` with: scenario hash, full resolved parameters (including all `ASSUMPTION` defaults actually used), git commit of `pedsim`, package versions, input data file hashes (DEM tiles, HydroRIVERS, plans), wall-clock time and seeds. All exports (C15) include `run_id` in their metadata. | Opening any exported layer in QGIS shows `run_id` in its metadata, and that `run.json` alone is enough to reproduce the run. |
| X-03 | M | **Ensembles.** `ensemble.py` runs N seeds (default 30) and, optionally, samples uncertain inputs: palaeo-DEM correction within its uncertainty (`paleo.correct_dem` already returns one), alternative coordinates for `CONFLICTING` sites (`alt_coord`), date bounds within their SD, and `ASSUMPTION` parameters within configured ranges. Outputs per cell: mean, SD, 5th/95th percentile and **exceedance probability** (share of runs where density > threshold). | 30-seed ensemble on the village scene completes in under 10 min on a 2023 laptop. The output GeoTIFF has bands `mean, sd, p05, p95, p_exceed`. |
| X-04 | S | **Sensitivity analysis.** One-at-a-time and Morris screening over a declared parameter set (vision cone, speed, Tobler `slope_factor`/`slope_offset`, layer weights, class speed factors). Output: ranked table and tornado plot. | Running the screening on the cluster scene produces a CSV ranking parameters by influence on (a) total corridor length above the threshold and (b) the travel-time matrix (A6). |
| X-05 | S | **ODD+D documentation.** A `docs/ODD.md` following the ODD protocol (Overview, Design concepts, Details; Grimm et al. 2020, `VERIFY` citation) is generated partly from the scenario schema so it cannot drift from the code. | `python -m pedsim.scenario --odd` regenerates the parameter tables in `ODD.md`. |
| X-06 | M | **Provenance on data entities.** Phases, population classes, tasks, calendar entries and obsidian proportions carry `source` (citation string) and `confidence` (`published` / `inferred` / `assumption`). The UI shows unsourced items with a visible marker. | Any config entry without `source` renders with a "⚠ assumption" badge in both viewers. |
| X-07 | M | **Tests.** Each new module ships pytest tests, and CI runs `pytest tests`. Golden-file tests for exports (C15). Regression tests for the co-occupation rule (CHR) with hand-computed cases. | `pytest tests` passes. Coverage of new modules ≥ 80 %. |
| X-08 | S | **Units and labels.** All outputs state units (min, h, km, persons, trips/cell/day). Times in hours:minutes in the UI and minutes in data. | No unitless numeric column in any CSV export. |

---

## 3. MAP: Path-density overlay on a web-map basemap

**Goal:** show simulated path density over a real basemap (satellite, street map or terrain, like Google Maps) at both scales, interactively and as static figures.

> **Basemap licensing (important for D20).** Google Maps tiles may only be shown through the Google Maps Platform APIs with an API key, and Google's terms **forbid caching or storing tiles for offline use**. Google is therefore only usable as an *online* option. The default must be a licence-compatible stack that can also be packed for offline use: OpenStreetMap-derived vector tiles (e.g. Protomaps PMTiles), OpenTopoMap or own hillshade for terrain, and a satellite layer with an offline-compatible licence (e.g. EOX Sentinel-2 cloudless; check the licence of the chosen year, `VERIFY`). Esri World Imagery is acceptable online with attribution under its terms.

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| MAP-01 | M | **Density raster in geographic space.** Convert `NavGrid` occupancy (and ensemble outputs, X-03) to a georeferenced raster in EPSG:32637 using `LocalFrame` (origin offset plus cell size). Write Cloud-Optimised GeoTIFF (COG). | Raster opens in QGIS aligned with OSM within ½ cell; corner coordinates match `LocalFrame.to_projected` of grid corners. |
| MAP-02 | M | **Normalised density units.** Offer `raw` (agent-visits per cell), `trips_per_day` (normalised by simulated days and agent count), and `relative` (0–1, percentile-stretched). Default `trips_per_day`. | Legend shows unit; switching units changes the legend, not the spatial pattern. |
| MAP-03 | M | **Interactive web map.** A web page (`web/`, shared with D20) using **MapLibre GL JS** shows: basemap switcher (streets / terrain / satellite / none), density overlay with colour ramp (perceptually uniform, e.g. viridis/inferno), opacity slider, linear/log toggle, lower cut-off slider (hide cells below threshold), site markers coloured by `Confidence`, and village ODs. | Overlay loads for the cluster scene in under 2 s from local files. Opacity, log and cut-off respond in under 100 ms. |
| MAP-04 | S | **Corridor vectors.** Extract corridors as polylines: threshold the density (or ensemble `p_exceed ≥ 0.5`), skeletonise and simplify (Douglas–Peucker, tolerance = ½ cell). Line attribute `mean_density`, `p_exceed`. Display as a toggleable line layer. | Corridor lines appear on the map and export with attributes (C15). |
| MAP-05 | S | **Traces on map.** Draw the existing `traces` (sampled agent tracks) as thin lines coloured by group, population class (A8) or task (A8). | Choosing "colour by task" recolours traces and legend. |
| MAP-06 | M | **Static map figures for papers.** `webmap.render_static(run_id, basemap=…, extent=…)` produces PNG/PDF at 300 dpi with basemap, density, sites, scale bar, north arrow, legend, attribution and `run_id` in the footer (matplotlib + `contextily` for online basemaps, or offline from the packed tiles). | Generated figure includes attribution string and scale bar. Reproducible from `run.json`. |
| MAP-07 | C | **Google Maps option (online only).** If a Google Maps Platform key is configured, offer Google Satellite/Roadmap as a basemap via the official JS API. Disabled in offline mode, with a tooltip explaining why. | With no key or no connectivity, the option is greyed out. No Google tiles are ever written to the cache. |
| MAP-08 | S | **Desktop viewer parity.** The pygame `Viewer` gains a `basemap` entry in the Layers tab that draws a pre-rendered basemap raster (from the offline tile pack, D20-06) beneath the analysis. | Toggling `basemap` in the Layers tab shows or hides it; off by default (matches existing "no always-on background" design). |
| MAP-09 | S | **Compare two runs.** Difference map `A − B` (diverging ramp, centred at 0) and side-by-side swipe. Used by A1, A2, C16. | Selecting two run IDs shows a difference overlay with a symmetric legend. |

---

## 4. CHR: Chronology, co-occupation and time-range slider (aims A1 + A7)

**Goal:** movement between sites should only happen when both sites were occupied at the same time. Two sites whose occupations are 500 years apart must not exchange pedestrians. A **global toggle** turns this rule on or off for all sites at once. A **start/end slider** picks the time window being studied.

### 4.1 Definitions

- Site *i* has an occupation interval `O_i = [end_bc_i, start_bc_i]` (from `sites.py`; Göbeklitepe = [8000, 9500]).
- The user picks a **time window** `W = [w_end, w_start]` with the slider (e.g. 8800–8300 cal BC).
- A site is **active in W** if `O_i ∩ W ≠ ∅`.
- Two sites *i*, *j* are **co-occupied in W** if `O_i ∩ O_j ∩ W ≠ ∅`, i.e. there is at least one year in the window when both were inhabited.
- **Tolerance `τ`** (years, default 0): optionally widen each interval by τ on both sides, to allow for dating uncertainty. *Example:* site A 9500–9000 BC, site B 8500–8000 BC → gap 500 years → no trips while τ < 250.
- **Overlap weight** (optional): trips between *i* and *j* weighted by `|O_i ∩ O_j ∩ W| / |W|`, so pairs that overlap only briefly within the window exchange fewer trips.

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| CHR-01 | M | `chronology.py` implements `Interval`, `active(site, W, τ)`, `co_occupied(i, j, W, τ)`, `overlap_years(i, j, W, τ)`, and `pair_matrix(sites, W, τ) → bool[n,n]` plus `float[n,n]` overlap weights. | Unit tests: A=[9000,9500], B=[8000,8500] → not co-occupied for τ ∈ {0, 100, 249}; co-occupied for τ = 250. Overlap years computed correctly for nested, partial and disjoint cases. |
| CHR-02 | M | **Global toggle `respect_chronology`** (default **on**). When **on**, trip generation (`Simulation.draw_trip`) only draws destination *j* for origin *i* if `pair_matrix[i, j]` is true, and inactive sites have origin and destination weight 0. When **off**, all located sites take part regardless of date (current behaviour). The toggle applies to **all sites at once**. | With toggle on and W = 9600–9400, no agent ever travels to or from Gürcütepe (7500–7000). With toggle off, it does. A test counts trips per pair over 2,000 trips. |
| CHR-03 | M | **Time-range slider (A7).** A **dual-handle slider** (start and end) over the span of the catalogue (default 10,000–7,000 cal BC, step 50 years, configurable). Shows the window as text ("8800–8300 cal BC, 500 yrs"). Changing it recomputes the active set and pair matrix and re-weights ODs. Cost fields are reused (they do not depend on time), so this must be fast. | In the desktop viewer and the web client, moving a handle updates the active-site markers in under 200 ms on the cluster scene. Agents already en route to sites that became inactive finish their trip and are then not renewed toward them. |
| CHR-04 | M | **Missing dates.** Sites with `start_bc` or `end_bc` = `None` (e.g. Yoğunburç, Hamzan Tepe, Taşlı Tepe, Kurt Tepesi) follow a policy setting `undated_policy ∈ {exclude (default), include, include_flagged}`. With `include_flagged`, their markers and trips are drawn hatched/dashed. | Policy is shown in the HUD and recorded in `run.json`. With `exclude`, undated sites have zero trips. |
| CHR-05 | S | **Per-site override.** In addition to the global toggle, a site can be pinned `always_on` or `always_off` (for "what if" scenarios). Overrides are listed in the HUD and the run record. | Pinning Göbeklitepe `always_on` with W = 7400–7000 keeps it active. HUD shows "1 override". |
| CHR-06 | S | **Date uncertainty sampling.** If `start_bc_sd` / `end_bc_sd` are given, X-03 ensembles sample interval bounds from normal distributions (truncated so `start ≥ end`) for each run. Output: per-pair probability of co-occupation. | Ensemble outputs `co_occupation_probability.csv` (n×n). |
| CHR-07 | S | **Animation through time.** "Play" moves a window of fixed width (e.g. 300 yrs) in steps (e.g. 50 yrs) from start to end. For each step it runs a short simulation and records density. Exports an MP4/GIF and a multi-band GeoTIFF (one band per step) with band descriptions = window labels. | `pedsim run scenario.yaml --sweep-time 300:50` writes `density_timeseries.tif` with correct band labels. |
| CHR-08 | S | **Chronology chart.** A timeline (Gantt) of all sites with the current window highlighted, sites coloured by date quality. Visible in a side panel of both clients and exportable as SVG. | Timeline updates as the slider moves. |
| CHR-09 | M | **Village scale.** At village scale the same window drives **phases** (C16): phases whose interval intersects W are active. | See C16-04. |

---

## 5. A1: Scenario test, residential village vs. gathering place

**Goal:** turn the debate (permanent settlement with domestic life vs. a place people periodically gathered at from the wider cluster) into two or more **explicitly parameterised scenario families**. Run both, and report **diagnostic metrics** whose difference is larger than the ensemble spread. All runs respect CHR when it is on.

### 5.1 Scenario families (defaults, all `ASSUMPTION`)

| Family | Who moves | Where trips come from | Temporal pattern |
|---|---|---|---|
| **R: Residential** | Resident population of the site, with the population classes and daily tasks from A8 | Houses/domestic buildings (C16) → water, resources, quarries, special buildings | Every day, task schedules (A8), modest seasonal change |
| **G: Gathering** | Small resident core plus visitors from co-occupied sites (CHR) | Cluster-scale trips from other sites → site perimeter gates → special buildings | Event-driven (A2): peaks at gathering events, low otherwise |
| **M: Mixed** (S) | R + G with a mixing parameter `α` (share of trips from visitors) | Both | Both |

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| A1-01 | M | `hypotheses.py` defines scenario families as scenario-file templates (`R`, `G`, `M(α)`) that compose CHR, A2, A8 and C16 settings. Each family has a short written description that appears in the report. | `pedsim hypotheses list` prints families with descriptions. `pedsim hypotheses run R G --site Göbeklitepe` runs both with matched seeds. |
| A1-02 | M | **Cluster ↔ village coupling.** For G and M, cluster-scale arrivals at a site's location are converted into village-scale arrivals at **perimeter gate ODs** (already created by `village_scene`), distributed by the arrival bearing of each cluster trip. The number of arrivals per day comes from the cluster run (or a configured number). | Arrivals per gate in the village run are proportional (±10 %) to the cluster arrivals in each bearing sector. |
| A1-03 | M | **Diagnostic metrics** computed for each run (and as ensemble distributions): (1) **share of movement at special buildings** vs. domestic area; (2) **Gini coefficient** of cell density (concentrated vs. spread); (3) **temporal peak-to-mean ratio** of arrivals over a simulated year; (4) **origin mix**: share of agent-trips starting outside the site; (5) **corridor count and length** into the site from the cluster; (6) **density at water points** per resident. | `metrics.csv` per run with all six columns and units. |
| A1-04 | M | **Comparison report.** For two or more families: per-metric ensemble distributions (box/violin), **effect size** (Cliff's delta) and whether the 90 % intervals overlap. Difference map (MAP-09). Short auto-generated text ("Metric 3 separates R and G clearly; metric 1 does not"). Markdown + PNG output. | `report.md` is generated with figures and a table of separations. Reproducible from run records. |
| A1-05 | S | **Expected archaeological signature.** For each metric, the report contains a column "What evidence would show this" (configurable text in YAML, e.g. "wear/trampling surfaces, path-side discard, lithic density at gates"). This links model output to field evidence. | Column appears in the report. Empty entries are flagged "to be defined". |
| A1-06 | C | **Inverse use.** Given a researcher-provided observed pattern (e.g. a raster of surface lithic density), rank scenarios by agreement (Spearman correlation and AUC of density vs. observed). | With a test raster created from scenario R, R ranks first. |

---

## 6. A2: Gathering calendar

**Goal:** tie the season state (rivers) and gathering events to a **calendar**, so you can study how the network and site use change across the year.

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| A2-01 | M | `calendar.py` + `data/config/calendar.yaml`: 12 months, each with `river_season` (`dry` / `normal` / `spring floods`, mapped to `rivers.Season`), `daylight_minutes`, task weights per task (A8) and a list of `events`. Defaults (all `ASSUMPTION` unless sourced): Mar–Apr = spring floods; May–Jun and Oct–Nov = normal; Jul–Sep = dry; Dec–Feb = normal. | Selecting a month sets the river season and task weights. A test asserts `calendar.month(8).river_season == Season.DRY`. |
| A2-02 | M | **Daylight.** `daylight_minutes` computed from latitude (37.2° N) and day of year with a standard solar formula (roughly 580 min at the winter solstice, 880 min at the summer solstice). Daylight caps the total daily movement budget of each agent (A8-05). | Values within ±10 min of NOAA solar calculator for Şanlıurfa on the solstices. |
| A2-03 | M | **Events.** An event has `name`, `month`(s), `site` (destination), `attendance_share` (fraction of each co-occupied site's population that travels), `duration_days`, `source`. Default example: "late-summer gathering" at Göbeklitepe in Aug–Sep, linked to faunal seasonality studies of gazelle hunting (`VERIFY`: Lang et al. 2013, *World Archaeology* 45(3)). | During an event month, cluster trips toward the event site rise by the configured share. A test verifies the trip count. |
| A2-04 | M | **Month selector and year run.** UI: month dropdown (or a 12-step slider) in both clients. CLI: `--year` runs all 12 months and writes a 12-band density GeoTIFF plus a monthly metrics table (A1-03, A6). | `pedsim run s.yaml --year` produces `density_monthly.tif` (12 bands, labelled Jan–Dec). |
| A2-05 | S | **Seasonal network change.** For each month, compute the A6 travel-time matrix and report which site pairs become unreachable or more than X % slower (e.g. in spring floods). | `network_by_month.csv` lists, per pair and month, travel time and change vs. the annual median. |
| A2-06 | C | **Calendar editor.** Edit `calendar.yaml` entries in the web client (form), validate against schema, save as new version. | Edits create a new version file; the previous version is kept. |

---

## 7. A6: Taş Tepeler network analysis

**Goal:** quantify how the sites were connected (walking-time matrix, centrality, interaction strength) and compare that with shared material culture.

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| A6-01 | M | **Travel-time matrix.** For every pair of active sites (CHR), compute **least walking time** (minutes) from the existing directional Tobler Dijkstra cost fields (`grid.cost_field`), both directions (asymmetric because of slope). Also compute **agent-based empirical travel time** (median and IQR over completed agent trips), because vision-cone agents do not walk the optimal path. | `travel_time.csv` (long format: `from, to, t_lcp_min, t_agent_median_min, t_agent_iqr_min, n_trips, month, window`). Values for Göbeklitepe→Karahantepe are plausible (roughly 35 km at 4–5 km/h ≈ 7–9 h, sanity check only). |
| A6-02 | M | **Graph and metrics.** Build a weighted graph (networkx) with sites as nodes and travel time as edge weight. Compute: weighted degree, closeness, betweenness, eigenvector centrality; **k-nearest-in-time neighbours**; edges under a **day-trip threshold** (default 6 h one way, `ASSUMPTION`); and connected components under that threshold. | `network_metrics.csv` per site. `network.graphml` exports and opens in Gephi/Cytoscape. |
| A6-03 | M | **Gravity / spatial interaction model.** `I_ij = (P_i · P_j) / f(t_ij)` with `f` = power `t^β` or exponential `exp(β·t)`. `P` = population proxy (site `area_ha` by default, `ASSUMPTION`; or A8/C16 inhabitants). β is configurable and can be swept. Interaction strengths drive cluster-scale OD weights as an optional mode `od_mode = gravity`. | With `od_mode = gravity`, trip counts per pair correlate (Pearson r > 0.9) with `I_ij` over 5,000 trips. |
| A6-04 | M | **Network map.** On the MAP view: nodes sized by a chosen centrality, edges drawn as corridor lines (MAP-04), not straight lines, with width ∝ interaction. Edges above the day-trip threshold dashed. | Toggle "network" on the map shows the graph. Clicking a node lists its top-5 links with times. |
| A6-05 | S | **Material-culture comparison.** Import a researcher-provided **similarity matrix** (CSV, sites × sites, e.g. shared motif or T-pillar traits; values 0–1). Compute a **Mantel test** (permutations, default 9,999) between travel time and dissimilarity, and a partial Mantel controlling for straight-line distance. | `mantel.csv` with r, p, permutations. A test with a synthetic similarity = f(travel time) gives r > 0.8. |
| A6-06 | S | **Network over time and season.** Recompute A6-01–03 for each step of a CHR time sweep and each A2 month. Small-multiples figure. | `network_timeseries.csv` and a figure with one panel per window. |
| A6-07 | C | **Uncertain sites.** For `CONFLICTING` sites (Sefertepe), compute metrics for both coordinates and report the difference. Unlocated sites are listed as "not in network" in all outputs. | Report shows both Sefertepe variants and their centrality difference. |

---

## 8. A8: Daily tasks and population classes

**Goal:** replace undifferentiated agents with **population classes** that carry out **daily tasks** with class-specific speed, load and range. Example: children fetch water, walk more slowly and cannot go far.

> **Modelling note for the researcher.** Task allocation by age and sex in PPN societies is **not directly observable**. The defaults below are a starting point drawn from cross-cultural ethnographic patterns and common modelling practice. They are deliberately flagged `ASSUMPTION` and are meant to be varied (X-04) rather than taken as findings. The tool must make it easy to run "all classes do all tasks" as a null model.

### 8.1 Population classes (default `data/config/population.yaml`)

| Class id | Label | Default share | Speed factor vs. Tobler adult | Max one-way range per trip | Max load (kg) | Notes |
|---|---|---|---|---|---|---|
| `child` | Child (approx. 6–11) | 0.20 | 0.75 | 2 km | 8 | `ASSUMPTION` all values |
| `adolescent` | Adolescent (12–17) | 0.15 | 0.95 | 8 km | 15 | `ASSUMPTION` |
| `adult_a` | Adult, group A | 0.25 | 1.00 | 30 km | 20 | Neutral labels on purpose, mappable to sex/gender roles by the researcher |
| `adult_b` | Adult, group B | 0.25 | 1.00 | 30 km | 20 | `ASSUMPTION` |
| `elder` | Elder (60+) | 0.08 | 0.80 | 3 km | 8 | `ASSUMPTION` |
| `carer` | Adult with infant | 0.07 | 0.85 | 5 km | 10 | `ASSUMPTION` |

Shares must sum to 1 (validation error otherwise). Infants and very young children are not modelled as walkers.

### 8.2 Task catalogue (default `data/config/tasks.yaml`)

PPN context: hunting and gathering with **wild** plants (wild einkorn and barley, pistachio, almond; `VERIFY` against Göbekli archaeobotany) and **no domestic herd animals**, so there are **no herding tasks**.

| Task id | Description | Destination kind | Eligible classes (default) | Frequency (default) | Load on return | Season / calendar weight |
|---|---|---|---|---|---|---|
| `water` | Fetch water from cisterns, springs or the nearest seasonal stream (e.g. Mucid Dere ~3 km W of Göbeklitepe) | `water` ODs (cisterns, river banks, springs) | child, adolescent, carer, adult_a, adult_b | 2× / day per household | 10–20 kg (`ASSUMPTION`) | Stream sources unavailable when dry; cisterns preferred in dry season |
| `firewood` | Collect fuel | `resource:wood` zones | adolescent, adult_a, adult_b, elder | 1× / 2 days | 15–20 kg | Higher in winter |
| `plants` | Gather wild cereals, nuts, legumes | `resource:plants` zones (valley floors, slopes) | all except `carer` (reduced) | Seasonal | 5–15 kg | Peak late spring (cereals), autumn (nuts) |
| `hunt` | Hunting trips (gazelle, aurochs, boar) | `resource:hunt` zones, plain edges | adult_a, adult_b, adolescent | Seasonal, multi-day allowed | 0 out / meat back | Peak late summer for gazelle (`VERIFY`, see A2-03) |
| `chert` | Procure flint/chert from local outcrops | `quarry:chert` ODs | adult_a, adult_b, adolescent | 1× / week | 10–20 kg | All year |
| `quarry` | Work limestone quarries on the plateau | `quarry:limestone` ODs | adult_a, adult_b | Linked to construction phases (C16) | n/a (hauling excluded, A3) | All year |
| `ritual` | Visit special buildings / enclosures | `special` buildings' entrance ODs | all | Daily small share; event peaks (A2) | 0 | Events |
| `visit` | Social visit to a co-occupied site | `site` ODs at cluster scale (CHR-filtered) | adolescent, adult_a, adult_b | Low daily rate | 0–5 kg | Higher in dry season (rivers crossable) |
| `home` | Return home / idle | `house` ODs | all | Ends every task chain | – | – |

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| A8-01 | M | `population.py` loads classes (8.1), validates shares, and assigns `pclass` to each agent at creation, by share. Agent speed = `sim.speed × speed_factor × load_factor(load)`. | Over 10,000 agents, class shares are within ±1 % of the configuration. |
| A8-02 | M | **Load effect on speed.** `load_factor(load_kg, body_class)` = `1 − k · load_kg / max_load`, with `k` = 0.2 by default (`ASSUMPTION`, to be calibrated by B10). Loaded agents also use a stricter `max_ascent_slope` (configurable per class). | A loaded child walks more slowly than an unloaded child (test). Path changes visible on steep slopes. |
| A8-03 | M | `tasks.py` loads the task catalogue (8.2). A **task** creates a trip chain `home → destination → home` (or multi-stop). Destination = nearest eligible OD by **cost distance** within the class's `max_range` (uses existing cost fields), with optional random choice among the k nearest (k = 3). | A child never gets a `water` destination beyond 2 km cost-distance. If none is within range, the task is skipped and logged as "unmet demand". |
| A8-04 | M | **New OD kinds.** Users can place or import ODs of kinds `water`, `quarry:chert`, `quarry:limestone`, `resource:<type>` (as polygons → several OD points), `house`, `special`. Imported from GeoJSON/SHP (C15) or drawn in the viewer Edit tab. Göbeklitepe cisterns and the Karahantepe water system (noted in `sites.py`) are prepared as example data. | Edit tab offers an "OD kind" dropdown; JSON save round-trips kinds. |
| A8-05 | M | **Daily time budget.** Each agent has a budget = daylight minutes (A2-02) × `active_share` (default 0.6, `ASSUMPTION`). Tasks are scheduled until the budget is used; walking time counts against it. Over-budget task chains are cut and logged. | Daily log per agent: tasks done, minutes walked, minutes left. |
| A8-06 | M | **Task-coloured output.** Density can be split by **task** and by **class** (separate occupancy arrays per category, memory permitting; else sampled traces). UI filter: "show density for: all / task X / class Y". | Selecting `water` shows only water-trip density. Export provides one band per task (C15). |
| A8-07 | S | **Catchment zones (isochrones).** For each settlement, polygons reachable within 30, 60 and 120 min (per class) from the cost field. Overlay resource zones and report **resource area within each isochrone**. | `catchments.gpkg` with polygons per site/class/threshold. Table of resource areas. |
| A8-08 | S | **Unmet demand and load metrics.** Report per run: share of water demand met within range, mean daily walking minutes per class, peak load-km per class. Used in A1-03. | Metrics in `metrics.csv`. |
| A8-09 | S | **Null model.** Setting `task_allocation: uniform` assigns all tasks to all classes equally, with the same speed. Required in every A1 report as a baseline. | Report contains the null-model column. |
| A8-10 | C | **Task/class editor** in the web client: edit shares, speed factors and task eligibility in a table; validate; save as new config version. | Edits validate (shares sum to 1) and are versioned. |

---

## 9. A9: Regional scale for obsidian exchange

**Goal:** a third scale (regional, several hundred km) to test whether walking-cost corridors from obsidian sources predict the proportions of obsidian from each source found at Taş Tepeler sites.

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| A9-01 | M | **Regional scene.** `regional.py` builds a scene covering the Taş Tepeler cluster and the main East and Central Anatolian obsidian sources (default list `data/config/obsidian_sources.yaml`: e.g. Bingöl A/B, Nemrut Dağ, Göllü Dağ, Nenezi Dağ; coordinates and source groups are `VERIFY`, to be filled in from published characterisation studies). Terrain: Copernicus **GLO-90** at 1 km cells (download script provided). Major rivers (Euphrates, Tigris, Murat) from HydroRIVERS with river-specific crossing costs; Atatürk/Keban reservoirs replaced by pre-dam river channels (a mask polygon of reservoir extent is required, `ASSUMPTION` until sourced). | The scene builds in under 60 s and runs the directional Tobler Dijkstra from each source to every site. |
| A9-02 | M | **Three-scale navigation.** Extend `app.TwoScaleApp` to support `regional → cluster → village`, with the same breadcrumb, caching and save prompts. | Breadcrumb shows `Region › Cluster › Göbeklitepe`. ESC goes up one level. Edits survive round trips. |
| A9-03 | M | **Source → site cost table.** Least-cost travel time (hours and days at a configurable walking day length, default 8 h) from each source to each site. Per-season variant (A2: river crossings). | `obsidian_costs.csv` (`source, site, t_hours, t_days, season`). |
| A9-04 | M | **Observed proportions input.** CSV import of published obsidian sourcing results: `site, source_group, n_pieces, reference`. The tool does not ship these numbers; the researcher enters them from literature. | Import validates names against catalogue and source list; unmatched rows listed. |
| A9-05 | M | **Distance-decay fit and comparison.** Predicted share of source *s* at site *j*: `p_sj ∝ A_s · f(t_sj)`, with source attractiveness `A_s` (default equal) and `f` power or exponential. Fit β (and optional `A_s`) by maximum likelihood (multinomial) to observed counts. Report fit, residuals per site, and comparison against straight-line distance as the null (AIC). | Report shows whether cost-distance beats Euclidean distance (ΔAIC), with residual map. Synthetic test data generated from known β is recovered within ±10 %. |
| A9-06 | S | **Down-the-line vs. direct-access.** Optional agent-based exchange mode where obsidian moves through a chain of co-occupied sites (CHR, A6 graph) with loss per handover. Compare predicted proportions with A9-05 direct-access model. | Two models in the same report with ΔAIC. |
| A9-07 | S | **Regional corridors on map.** Corridor lines (MAP-04) from each source to the cluster, with season variants. | Map layer "obsidian corridors" with per-source colour. |
| A9-08 | C | **Performance.** If the regional grid exceeds ~1 M cells, use a hierarchical or coarse-to-fine Dijkstra, or `scipy.sparse.csgraph`, to keep a single source solve under 10 s. | Benchmark logged in `run.json`. |

---

## 10. B10: Field calibration (walk input, calibration routes, model fitting)

**Goal:** collect your own walking data during the trip (and later from collaborators), import it, and use it to calibrate (1) the **speed–slope function** and (2) **route choice**. The app provides **planned calibration routes** on a map to walk, plus several **input methods**.

### 10.1 Two kinds of calibration walk

| Type | What you do | What it calibrates |
|---|---|---|
| **Transect walk** (speed–slope) | Walk a pre-planned route that crosses a range of gradients (flat, gentle and steep up and down), at a natural pace, optionally with a known load (e.g. 10 L water = 10 kg) | Tobler parameters `base_speed`, `slope_factor`, `slope_offset`; class `speed_factor` and load factor (A8-02) |
| **Free-choice walk** (route choice) | Only start and end are given. Walk the way that feels natural, without looking at a map | Vision cone, layer weights, friction; compare with simulated agent routes between the same points |

### 10.2 Requirements

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| B10-01 | M | **Route library.** `data/routes/*.geojson`: each route has `id`, `type` (`transect` / `free_choice`), geometry (line for transects; start and end points for free-choice), `target_slopes` (for transects), `expected_duration_min`, `access_notes` (public road/track, permission needed, no-go areas), `safety_notes`. | Library loads in both clients. Validation rejects routes without `access_notes`. |
| B10-02 | M | **Route planner tool.** In the viewer/web client, draw a candidate transect. The tool shows its **slope profile** from the DEM and a **slope histogram**, and flags gaps in slope coverage (bins of −30 … +30 % in 5 % steps). It suggests which bins are missing over the set of planned routes. Free-choice route: place start and end; the tool shows the simulated path fan (from 100 agents) so you can pick pairs where the model is **uncertain** (high spread), which are the most informative. | Drawing a route shows its profile in under 1 s. The "coverage" panel shows which slope bins have < 500 m of planned walking. |
| B10-03 | M | **Export routes for walking.** Export selected routes as **GPX** (tracks for transects; start/end waypoints for free-choice) for phone/watch apps (OsmAnd, Organic Maps, Garmin, Komoot; Strava where its route import is available), plus a printable PDF map sheet (MAP-06) with route, profile and notes. | GPX opens in OsmAnd with correct positions. PDF includes scale bar and safety notes. |
| B10-04 | M | **Input method 1: GPS track import.** Import **GPX, FIT, TCX** files and **Strava** data (see C15-07/08). Each imported track gets metadata: `walker_id` (pseudonymous), `class` (A8 class), `load_kg`, `route_id` (optional link to library), `walk_type`, `footwear`, `weather`, `notes`. | Importing a Strava GPX with metadata produces a stored track with all fields. Tracks without timestamps are rejected (cannot compute speed). |
| B10-05 | M | **Input method 2: in-app recording (field client).** The D20 web client records a walk using the browser Geolocation API (positions every 1–5 s), keeps the screen awake (Wake Lock API), and stores the track locally (IndexedDB). Start/stop/pause buttons, the same metadata form as B10-04, and a "mark event" button (e.g. "stopped to rest", "crossed stream"). | A 30-min test walk records ≥ 95 % of expected fixes when the screen is kept on. The track survives an app reload. *Known limitation:* browsers stop GPS when the screen is off or the app is in the background. For long walks, the docs recommend recording with a native app (Strava, OsmAnd) and importing. |
| B10-06 | S | **Input method 3: manual entry.** A form for walks recorded without GPS: start/end on map, start/end clock time, route sketched on map, metadata. Used for collaborators' notes or historical records. | Manual walk saved and used in route-choice scoring (not in the speed fit, as it has no fine timing). |
| B10-07 | M | **Track cleaning.** (1) Reproject to `LocalFrame`. (2) Drop fixes with reported accuracy > 15 m (if available). (3) Remove **stops** (speed < 0.5 km/h for > 30 s) and the user-marked rest events. (4) **Take elevation from the DEM, not GPS** (GPS altitude is too noisy); also store GPS altitude for reference. (5) Split into segments of 20–50 m horizontal length. (6) Compute segment slope (signed, direction of travel) and speed. | Cleaning report per track: fixes kept/removed, stop time removed, number of segments. |
| B10-08 | M | **Speed–slope fit.** Fit `v = a · exp(−b · |s + c|)` (Tobler form) by non-linear least squares (scipy) on all segments, optionally per class and load group. Report `a, b, c` with **bootstrap 95 % CI** (1,000 resamples by track, not by segment, because segments within a track are correlated). Plot data + fitted curve + default Tobler (a = 6 km/h, b = 3.5, c = 0.05). | Fit on a synthetic dataset generated from Tobler parameters recovers them within CI. Plot exported as PNG. |
| B10-09 | M | **Apply calibration.** "Use these parameters" writes the fitted values into a named `TerrainCost` profile in the scenario (`terrain_profile: field_2026_11`). Runs record which profile was used. Previous profiles are kept. | Switching profiles changes cost fields. `run.json` lists profile name and its values. |
| B10-10 | M | **Route-choice scoring.** For each free-choice walk: simulate N agents (default 200) between the same start/end under the current scenario. Metrics: **mean perpendicular distance** of the walked track to the nearest simulated route; **buffer overlap** (share of the walked track within 25 m of the simulated density corridor); **percentile rank** of the walked track among simulated routes (by Fréchet distance to the median route). | Per-walk scores table. A walked track that equals a simulated median route scores overlap ≈ 1. |
| B10-11 | S | **Route-choice calibration.** Grid or Bayesian search (e.g. Optuna) over vision cone, layer weights and step penalty to maximise mean buffer overlap across free-choice walks, with **leave-one-walk-out** cross-validation to avoid overfitting. | Search reports the best parameters and CV score. The baseline (current defaults) score is reported alongside. |
| B10-12 | S | **Calibration dashboard.** One page showing slope coverage achieved, fitted curve, per-walk route-choice scores, and the parameter profile currently in use. | Page renders from stored tracks without internet. |
| B10-13 | M | **Privacy.** Tracks are stored with pseudonymous `walker_id`. The start and end of tracks within 200 m of a configured "private location" (hotel, home) are trimmed on import. Raw files are kept only in a local, gitignored folder. | Test: a track starting at a configured hotel location loses its first 200 m. |

> **Field note.** Excavation areas are fenced and under the Ministry's authority. Calibration walks should stay on public roads, tracks and visitor paths, or have explicit permission. Flying a drone requires Turkish permits. Plan for heat and carry water. These notes belong in `access_notes` / `safety_notes` (B10-01), not only in this document.

---

## 11. C15: GIS export, QGIS import and Strava/GPX import

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| C15-01 | M | **Vector export to Shapefile.** `gis_export.py` writes: `sites` (points: name, confidence, start_bc, end_bc, active_in_window, centralities), `ods` (points: kind, phase_ids joined as text, weights), `buildings` / `obstacles` (polygons: phase_ids, function, height, layer), `rivers` (lines: perennial, crossing_cost, season), `corridors` (lines: MAP-04 attributes), `traces` (lines: class, task, group, duration_min), `network_edges` (lines: t_lcp_min, interaction), `catchments` (polygons, A8-07), `calibration_tracks` (lines). Each `.shp` with `.shx`, `.dbf`, `.prj` (EPSG:32637) and `.cpg` (UTF-8, needed for Turkish characters such as ğ, ı, ş). Field names ≤ 10 characters, with a mapping table in `README_fields.csv`. | All layers open in QGIS 3.x with correct CRS and Turkish names displayed correctly. A golden-file test compares the DBF schema. |
| C15-02 | M | **GeoPackage export (recommended format).** The same layers in a single `.gpkg` (no 10-character limit, multiple layers, metadata table with `run_id`). | `.gpkg` opens in QGIS with all layers. `gpkg_metadata` contains `run.json`. |
| C15-03 | M | **Raster export.** Density (MAP-02 units), ensemble bands (X-03), cost fields per site, elevation (palaeo-corrected) and its uncertainty, friction, per-task density bands (A8-06), and time/month series (CHR-07, A2-04) as **COG GeoTIFF**, EPSG:32637, with band descriptions and nodata set. | `gdalinfo` shows correct CRS, band names and nodata. |
| C15-04 | M | **QGIS project ("QGIS import").** Write a `.qgz` project referencing the exported layers, with **pre-made styles** (`.qml`): density colour ramp, corridors by width, sites by confidence, buildings by phase, plus an OSM basemap XYZ layer. Opening the project shows the result ready-styled. | Double-clicking the `.qgz` opens QGIS with all layers styled. Tested headless with `qgis_process` or by parsing the project XML if QGIS is not installed in CI. |
| C15-05 | S | **QGIS → pedsim import.** Read back edited vector layers (GeoPackage or Shapefile): buildings with `phase_ids`, ODs with kinds, resource zones, rivers. Researchers can digitise in QGIS and run in pedsim. Schema validation reports missing or unknown fields. | Round trip: export → edit one polygon in QGIS → import → building geometry updated. Unknown fields are reported, not dropped silently. |
| C15-06 | S | **GeoJSON / KML export** of sites, corridors and routes (EPSG:4326) for Google Earth and web use. | KML opens in Google Earth at the correct positions. |
| C15-07 | M | **Strava import (file-based, offline).** Import (a) single-activity exports (GPX from Strava's "Export GPX", or original FIT/TCX) and (b) a **Strava bulk account export** (`.zip` with `activities.csv` and an `activities/` folder of `.gpx`, `.fit`, `.tcx`, often gzipped `.gz`). Parse `activities.csv` for activity type, name and date. Filter to walking/hiking activities. Let the user pick activities in a list. Libraries: `gpxpy`, `fitdecode` (or `fitparse`), stdlib XML for TCX. | Importing a sample bulk export lists walks and hikes only by default. Gzipped FIT files parse. Tracks land in the B10 track store with metadata prompts. |
| C15-08 | S | **Strava import (API, online).** Optional OAuth 2.0 connection to Strava API v3 (scope `activity:read`). Fetch activity list and **streams** (`latlng`, `time`, `altitude`, `distance`) for selected activities. Tokens stored locally, never committed. Disabled in offline mode. | With a test token, a chosen activity imports with the same result as its GPX file (±1 fix). Without network, the option is hidden with an explanation. |
| C15-09 | S | **GPX export of simulated routes.** Export corridors, median simulated routes and calibration routes as GPX for walking (B10-03), so model routes can be walked and checked in the field. | GPX opens in OsmAnd. Track names include `run_id`. |
| C15-10 | C | **CSV exports** for all tables (metrics, travel times, network, obsidian), UTF-8 with header and units row (X-08). | Opens in Excel/LibreOffice with Turkish characters intact. |

**New dependencies:** `fiona` or `pyogrio` (vector I/O), `gpxpy`, `fitdecode`, `networkx`, `scipy`, `pyyaml`, `jsonschema`. Optional: `contextily` (static basemaps), `optuna` (B10-11), `requests` (Strava API). Imported lazily, like the existing `rasterio`/`pyproj`, so the core works without them.

---

## 12. C16: Building phases as switchable groups

**Goal:** group buildings (and obstacles) into **phases** matching stratigraphic or architectural periods. Phases can be switched on and off, and they drive **ODs**, **number of inhabitants** and therefore **paths**.

### 12.1 Data model

```yaml
# phases section in <scene>.geometry.json (format bumped)
phases:
  - id: GT-III
    name: "Layer III: large round-oval enclosures (A–D)"
    start_bc: 9500
    end_bc: 8800
    source: "Schmidt; revised Clare et al. (VERIFY)"
    confidence: published   # or inferred / assumption
    colour: "#c0504d"
  - id: GT-II
    name: "Layer II: smaller rectangular buildings"
    start_bc: 8800
    end_bc: 8000
    source: "VERIFY"
    confidence: inferred
buildings:
  - polygon: [...]
    height: 3.0
    layer: BUILDINGS
    phase_ids: [GT-II]
    function: domestic        # domestic / special / storage / unknown
    inhabitants: null         # null = derive from rule
```

A building or OD can belong to **several** phases (it stays in use across phases). An element with no `phase_ids` belongs to **all** phases (backwards compatibility).

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| C16-01 | M | `phases.py`: `Phase` dataclass (8 fields above). Membership on `Building`, obstacle, `OD`, `River` (optional) and resource zones via `phase_ids`. JSON save/load with **migration** from current `GEOMETRY_FORMAT` (missing `phase_ids` → all phases). | Loading an old save works unchanged. A save → load round trip keeps phases and memberships. |
| C16-02 | M | **Phase toggles.** Each phase can be switched on or off individually ("Phases" tab in viewer: one button per phase with colour; same in web client). Active geometry = elements with at least one active phase. Toggling triggers `NavGrid.partial_update` on the affected bounding box, then cost-field rebuild. | Turning off GT-II removes its walls from `walkable` and reroutes agents. Turning it on restores identical arrays (test via hash). |
| C16-03 | M | **Assignment tools.** In the Edit tab: select one or more buildings (click, shift-click, lasso) → "assign to phase…" / "remove from phase…"; create, rename and delete phase; colour buildings by phase ("view by phase"). Also importable from QGIS via an attribute (C15-05). | Lasso-select 10 buildings → assign GT-II → saved file has `phase_ids: [GT-II]` on all 10. |
| C16-04 | M | **Link to the time slider.** Mode `phase_mode ∈ {manual, by_time}`. In `by_time`, a phase is active if its interval intersects the CHR window W (CHR-09). Manual toggles override and are shown as overrides. | Moving the slider to 8500–8300 activates GT-II and deactivates GT-III in `by_time` mode. |
| C16-05 | M | **ODs follow phases.** ODs with `phase_ids` are active only when one of their phases is active. Inactive ODs get origin and destination weight 0 (not deleted). Building entrance ODs can be **auto-generated**: one OD per building on the longest facade's midpoint outside the footprint, inheriting the building's phases (option; manual placement still possible). | Disabling a phase removes its ODs from `draw_trip`. Auto-ODs are placed on walkable cells. |
| C16-06 | M | **Inhabitants from buildings.** Each active `domestic` building gets inhabitants = `override` if set, else `rule(building)`. Rules (selectable, all `ASSUMPTION`): (a) fixed persons per house (default 5); (b) persons per m² of floor area (default 1 per 10 m², a commonly used ethnographic range but `VERIFY`). Site population = sum. Population drives the **number of agents** per simulated day and per-household tasks (A8 water trips per household). | Turning on a phase with 20 domestic houses under rule (a) → population 100 → agent count scales accordingly (configurable agents-per-person ratio). HUD shows "Population: 100 (rule: 5/house, assumption)". |
| C16-07 | M | **Paths change with phases.** Density, traces, metrics and network (A6, using population as `P`) are recomputed per active phase set. A run record lists the active phases. A **phase comparison** creates a difference map (MAP-09) and metrics delta. | `pedsim compare --phases GT-III vs GT-II` produces difference GeoTIFF and metrics table. |
| C16-08 | S | **Construction and backfill states.** A phase can mark buildings as `under_construction` (passable but high friction) or `backfilled` (passable ground, not a wall, i.e. an enclosure that has been infilled). These states are expressed as layers. | A backfilled enclosure no longer blocks movement but appears hatched. |
| C16-09 | S | **Village population feeds the cluster.** Site population from C16-06 (when a village plan exists) replaces the `area_ha` proxy in A6-03 and A1-02 for that site. | Changing phases at village scale changes that site's node size and interaction strengths at cluster scale. |
| C16-10 | C | **Phase matrix view.** A table of buildings × phases (checkboxes) for bulk editing, with sort by phase and function. | Editing a checkbox updates the scene. |

---

## 13. D20: Offline-first field version (PWA, edge computing)

**Goal:** a lightweight version you can reach online but that **runs on the phone/tablet/laptop itself** ("edge computing"), so it works at the sites with no or poor internet. Used to show results on site, run quick what-if scenarios, and record calibration walks (B10-05).

### 13.1 Recommended architecture

```
Before trip (online)                         On site (offline)
────────────────────                         ─────────────────
Static hosting (GitHub Pages /               Installed PWA on tablet/phone/laptop
Cloudflare Pages, HTTPS)                      ├─ Service Worker: serves app + data from cache
 ├─ PWA shell (HTML/JS/CSS, ~1–2 MB)          ├─ MapLibre GL JS: basemap from PMTiles pack
 ├─ Pyodide runtime (~10–20 MB, cached)       ├─ Web Worker running Pyodide + pedsim (numpy)
 ├─ pedsim wheel (pure-Python)                │    → simulation runs locally on the device
 └─ Data packs per area (downloaded):         ├─ IndexedDB: edits, tracks (B10-05), runs
     • PMTiles basemap (vector + hillshade    └─ "Sync" button when back online
       + satellite where licence permits)
     • DEM crop (COG/npz) + palaeo correction
     • Scene JSON (sites, rivers, plans, phases)
     • Precomputed cost fields + results
Optional: laptop as local hub (python -m pedsim.serve) on a phone hotspot, for heavier runs shared to tablets on the same Wi-Fi
```

**Why Pyodide:** the existing simulation is pure Python + numpy, and Pyodide runs that unchanged in the browser. That keeps one implementation (principle 5). If benchmarks fail (D20-04), port only the hot loop (`Agent.vision_scan`, Dijkstra) to Rust → WebAssembly, behind the same interface.

| ID | Pri | Requirement | Acceptance criteria |
|---|---|---|---|
| D20-01 | M | **PWA shell.** `web/` is a Progressive Web App: manifest, icons, service worker (Workbox or hand-written), installable on Android/iOS/desktop. After first load and pack download it runs **fully offline** (airplane mode test). | With airplane mode on, the installed app opens, shows the map, runs a village scene and records a track. |
| D20-02 | M | **Hosting.** Static hosting only (no server needed): GitHub Pages or Cloudflare Pages, HTTPS (required for Geolocation and Service Worker). CI workflow builds and deploys `web/` and the `pedsim` wheel on tag. No user data leaves the device unless the user presses Sync/Export. | Deploy from CI on tag. Site served over HTTPS. Network log shows no requests after offline install other than optional Sync. |
| D20-03 | M | **In-browser simulation.** Pyodide in a **Web Worker** (UI never blocks) loads `pedsim` and runs village-scale scenes. Message API: `loadScene`, `setToggles` (CHR, phases, month, class/task filters), `step(n)`, `getDensity`, `getAgents`. Results rendered on the MapLibre map (agents as a point layer, density as raster). | UI stays responsive (>30 fps panning) while the worker simulates. |
| D20-04 | M | **Performance budget** (mid-range 2022 Android tablet or iPhone 12-class device): village scene 200×200 cells, 250 agents ≥ 10 sim steps/s; cost-field recompute after a phase toggle < 3 s; cold start from cache < 15 s. **Cluster and regional scenes use precomputed cost fields and results from the data pack** (no on-device Dijkstra at 80 km scale required); CHR slider, month and toggles re-weight ODs on device. If the budget fails, port hot loops to WASM (see 13.1). | Benchmark page in the app reports these numbers and they meet the budget on the reference device. |
| D20-05 | M | **Data packs.** `pedsim pack build --area goebekli --zoom 8-17` produces a versioned pack: PMTiles basemap (OSM vector + hillshade from DEM; satellite only if licence permits offline use, MAP note), DEM crop, palaeo correction, scene JSON, precomputed cost fields and default results, route library (B10-01). The app shows pack size before download (target < 150 MB per site area, < 400 MB for the cluster), progress, and storage used. Uses `navigator.storage.persist()` to reduce eviction risk. | Pack for Göbeklitepe village + surroundings < 150 MB. After download, the app reports "available offline". |
| D20-06 | M | **Feature subset in the field client.** Must: map with density overlay (MAP-03), CHR slider + toggle, month (A2), phase toggles (C16-02), class/task filter (A8-06), run/pause, calibration route library + GPX export (B10-03), in-app recording (B10-05), manual walk entry (B10-06), notes with photo attachment and GPS position. Should: route planner (B10-02), simple metrics panel. Not required in field client: regional scene solving, ensembles, sensitivity, full reports (desktop only). | Feature checklist test passes in offline mode. |
| D20-07 | M | **Local storage and sync.** All field data (tracks, notes, photos, edits) in IndexedDB with versioned records. "Export field data" produces a single `.zip` (GeoPackage + GPX + JSON + photos) that can be shared via AirDrop, USB or messaging without internet. "Sync" (optional, online) uploads to a configured storage (e.g. S3-compatible bucket or a Git repo via token). Conflicts are resolved by keeping both versions. | Export zip imports into desktop pedsim (C15-05, B10-04) with no data loss. |
| D20-08 | S | **Local hub mode.** `python -m pedsim.serve --pack goebekli` on a laptop serves the PWA and an HTTP API on the local network, so tablets connected to the laptop's hotspot can request heavier runs (e.g. 30-seed ensemble) from the laptop. Works without internet. | A tablet on the laptop's hotspot loads the app from the laptop and receives ensemble results. |
| D20-09 | S | **Battery and heat.** Simulation pauses automatically when the app is in the background. "Low power" setting caps steps/s and agent count. GPS recording interval configurable (1–10 s). | With low power on, CPU use drops (checked in browser performance tools). |
| D20-10 | S | **Languages.** UI strings in English and German. Turkish (for collaborators and site staff) as Could. | Language switcher works offline. |
| D20-11 | C | **Online-only extras** when connected: Google basemap (MAP-07), Strava API import (C15-08), pack updates. | Extras appear only when `navigator.onLine` and a test request succeeds. |

---

## 14. Delivery plan (suggested order)

Ordered so that features needed **before or during the trip** come first.

| Milestone | Contents | Why this order |
|---|---|---|
| **M0: Foundations** | X-01, X-02, X-07, data-model changes (1.1) with migration, config loading | Everything else depends on scenarios and the extended data model |
| **M1: Pre-trip field kit** | MAP-01–03, MAP-06, CHR-01–04, C16-01–05, B10-01–05, B10-07, B10-13, C15-01–03, C15-07, C15-09, D20-01–07 | Map overlay, chronology, phases, calibration routes and recording must work **offline at the sites** |
| **M2: Post-trip calibration** | B10-06, B10-08–12, C15-04, C15-05, C15-08 | Import trip data, fit Tobler and route choice, hand results to QGIS |
| **M3: Hypotheses** | A8 (all M), A2 (all M), C16-06–07, A1 (all M), X-03 | Tasks and population feed the R vs. G scenario test, with ensembles |
| **M4: Network and region** | A6 (all M), CHR-06–08, A9 (all M), X-04, X-05 | Network and obsidian build on calibrated costs and chronology |
| **M5: Polish** | All S and C items, D20-08–11 | |

---

## 15. Decisions

These were open in v1.0. The implementation uses the following answers. Each one is a default the researcher can replace; none of them is a published result unless a source is named in the config.

1. **Phases for Göbeklitepe.** Classic Layer III (9500–8800 BC) and Layer II (8800–8000 BC), confidence `inferred`, flagged `VERIFY`. This is not the revised DAI phasing.
2. **Co-occupation tolerance τ.** 0 years. Widening both ends of an interval by τ is implemented; τ = 250 just closes a 500-year gap and τ = 249 does not.
3. **Population rule.** 5 persons per house. Persons per m² (0.1) is selectable. Both are `ASSUMPTION`.
4. **Population classes.** Neutral labels `adult_a` and `adult_b` stay. The tool does not ship sex-based labels.
5. **Obsidian.** Source coordinates are shipped as `VERIFY` placeholders. No assemblage proportions are shipped. Counts are an imported CSV.
6. **Basemap.** OSM-compatible styles are the default. Google is online-only in the field client and is never cached or packed.
7. **Reference device.** Not chosen. The performance note in section 17 stands until a device is named.
8. **Sync.** Local export is the default. Cloud sync is optional and unconfigured.
9. **Similarity matrix.** An import, not a shipped table.

Dates are calibrated BC, larger meaning earlier. An interval is the closed range `[end_bc, start_bc]`, so Göbeklitepe is `[8000, 9500]`. The inclusive year count is `start - end + 1`. A bare `Simulation` leaves chronology off so older scenes stay reproducible. A scenario file defaults to `respect_chronology: true`.

Travel cost from the stock Tobler solver is in equivalent flat metres when `TerrainCost.base_speed` is 1. Minutes are `cost * base_speed / TOBLER_FLAT_KMH * 0.06`. The flat pace is `6·exp(−3.5·0.05)` km/h, about 5.036 km/h.

`date_quality` is set from the site table: none when undated, radiocarbon only when the note mentions 14C (Sayburç), otherwise typological. Geometry files are format 3. An empty `phase_ids` list means every phase. OD text lines stay in the Java format; the new fields are only in JSON. The two-level breadcrumb stays `cluster  >  Karahantepe` when there is no regional scene. With a regional scene it is `Region › Cluster › Göbeklitepe`, and Escape goes up one level.

---

## 16. Glossary

| Term | Meaning |
|---|---|
| **cal BC** | Calibrated radiocarbon years before Christ; in this code positive integers, larger = older |
| **Co-occupied** | Two sites inhabited at the same time, at least partly within the selected window |
| **Cost field** | Per-destination raster of cumulative walking cost (time) to that destination |
| **COG** | Cloud-Optimised GeoTIFF: a GeoTIFF that can be read in tiles, also offline |
| **Corridor** | Area or line of persistently high simulated pedestrian density |
| **Edge computing** | Running the computation on the device in the field (phone/tablet/laptop), not on a remote server |
| **Ensemble** | Many runs with different seeds or sampled inputs, summarised as mean and spread |
| **OD** | Origin/destination point where agents start or end trips |
| **PMTiles** | Single-file map tile archive that works offline and from static hosting |
| **PPNA / PPNB** | Pre-Pottery Neolithic A / B |
| **PWA** | Progressive Web App: a website that installs like an app and works offline |
| **Pyodide** | Python (with numpy) compiled to WebAssembly, runs in the browser |
| **Tobler's hiking function** | Walking speed as a function of slope: `v = 6·exp(−3.5·|s + 0.05|)` km/h |

---

## 17. Implementation status (v1.1)

Package version 0.3.0. Tests live in `python/tests/test_research.py` and `python/tests/test_outputs.py`. The protocol text is `docs/ODD.md`, regenerated with `python -m pedsim.scenario --odd`.

| Area | What ships |
|---|---|
| Chronology, phases, population, tasks, calendar | Python modules, YAML in `python/data/config`, viewer Research tab, lasso phase assignment |
| Scenarios and ensembles | `python -m pedsim run`, run records, `python -m pedsim hypotheses` |
| Network and obsidian | Travel-time and gravity tools, distance-decay fit. Hypothesis runs use the synthetic village unless a geodata scene is requested. `scene: synthetic` is the CI scene. |
| Calibration and GIS | GPX/TCX/FIT/Strava-zip import, Tobler fit, shapefile, GeoPackage, QGZ, GeoJSON, KML, COG. Example water ODs in `python/data/examples/water_ods.geojson` are schematic, not surveyed. |
| Field client | `web/` is an installable page with a Java-style red button grid, pitched 3D map, chronology rolling bars, and a **Season** control (dry / normal / spring floods). It plays packed `cluster.json` (settlements + inter-site ODs) and `scene.json` (village / settlement at 2 m cells, with lerped agent playback). Google/Esri satellite is the default online basemap, proxied by `pedsim serve` for WebGL CORS, and never cached by the service worker. OD+ / map-tap destinations and REC (GPS or map-tap track) are live. `python -m pedsim serve` also answers `POST /api/run`. |

The field client does not vendor Pyodide and does not run a second copy of the agent model. It plays `web/packs/goebekli/scene.json`, which `python -m pedsim pack` writes from `pedsim`. Heavier runs go to the laptop hub. These items are specified and only partly built:

- PMTiles and a GLO-90 regional raster are external. `pedsim pack` writes the scene, the config and a note, not a tile archive.
- Strava OAuth, Google tiles, Optuna and a full phase-comparison CLI are not included. `pedsim compare --phases` does not solve a village; it points at `pedsim.phases`.
- GitHub Pages deploy is not wired. `.github/workflows/pytest.yml` runs the test suite. Serve `web/` with `python -m pedsim serve` or any static host.
- The on-device budget in D20-04 (200×200 cells, 250 agents) is not measured here. The packed scene is the synthetic village, 40×40 cells.

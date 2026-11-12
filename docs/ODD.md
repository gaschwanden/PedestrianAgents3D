# ODD protocol for pedsim

Overview, Design concepts, Details, following Grimm et al. 2020
(*Journal of Artificial Societies and Social Simulation*). `VERIFY` the
citation before it goes into a paper. Parameter tables below are
generated from the scenario defaults (`python -m pedsim.scenario --odd`)
so they stay aligned with the code.

## 1. Purpose and patterns

pedsim asks how people moved between and inside the Taş Tepeler sites
under explicit, switchable assumptions about who was there, when, and
what they were walking to do. The patterns it is built to produce are
path density, travel times between sites, and the diagnostic metrics
that separate a residential reading from a gathering-place reading.

## 2. Entities, state variables and scales

Entities are agents, origin/destination places, buildings, phases,
population classes, tasks, rivers and sites. Time in the simulation is
a tick; reported times are minutes of walking from Tobler's function.
Archaeological time is calibrated BC. Space is metres in a local frame
on UTM zone 37N (EPSG:32637).

## 3. Process overview and scheduling

Each tick, every active agent scans a vision cone over the cost field,
steps, and deposits occupancy. A finished agent draws a new trip,
filtered by chronology, phase and (when enabled) the task catalogue.
Cost fields are rebuilt when geometry, season or terrain parameters change,
and reused when only the time window changes.

## 4. Design concepts

Agents do not follow the least-cost path. They walk toward the longest
visible cheaper cell, so the empirical travel time can exceed the
least-cost time. Interaction is indirect, through occupancy and shared
destinations. Stochasticity is the RNG named by the scenario seed.
Observation is the occupancy array, the trip log and the run record.

## 5. Initialisation

The scenario file names the scene, the seed, the agent count and every
toggle. Defaults live in `pedsim.scenario.DEFAULTS` and are copied into
`run.json`.

## 6. Input data

Copernicus DEM, HydroRIVERS, the site catalogue, plan geometry, and the
YAML tables for population, tasks, calendar and phases. Missing dates
and coordinates are not filled in.

## 7. Submodels

Tobler's hiking function; seasonal river friction; co-occupation;
task chains; optional gravity weights. Each `ASSUMPTION` is a parameter.

## Parameter table (generated)

| Parameter | Default | Meaning |
|---|---|---|
| `scene` | `"synthetic"` | Which world to build: synthetic, cluster, village:<site>, regional. |
| `site` | `""` |  |
| `time_window` | `{"start_bc": 10000, "end_bc": 7000}` | Study window [end_bc, start_bc], calibrated BC, larger = earlier. |
| `respect_chronology` | `true` | If true, trips only run between sites co-occupied in the window. |
| `tau_years` | `0` | Years added to both ends of every occupation interval (ASSUMPTION default 0). |
| `undated_policy` | `"exclude"` | exclude / include / include_flagged for sites with no dates. |
| `overlap_weighting` | `false` | Weight a pair by the fraction of the window they share. |
| `pins` | `{}` | Per-site always_on / always_off overrides. |
| `phase_mode` | `"manual"` | manual toggles, or by_time from the window. |
| `active_phases` | `[]` | Phase ids on when phase_mode is manual. |
| `phase_overrides` | `{}` |  |
| `population` | `"population.yaml"` | Path of the population-class table. |
| `tasks` | `"tasks.yaml"` | Path of the task catalogue. |
| `task_allocation` | `"by_class"` | by_class, or uniform (the null model). |
| `calendar_month` | `null` | Month 1–12, or empty for no calendar. |
| `terrain_profile` | `"default"` |  |
| `terrain` | `{"base_speed": 1.0, "slope_factor": 3.5, "slope_offset": 0.05, "impassable_slope": 1.2}` | Tobler base_speed multiplier, slope_factor, slope_offset, impassable_slope. |
| `num_agents` | `40` | Agent pool size. |
| `steps` | `30` | Simulation ticks. |
| `seed` | `1` | RNG seed. Ensembles use seeds. |
| `seeds` | `[]` |  |
| `gridsize` | `10.0` | Cell size in metres. |
| `extent_m` | `400.0` |  |
| `od_mode` | `"uniform"` | uniform trip weights, or gravity (A6). |
| `agents_per_person` | `null` |  |
| `population_rule` | `"per_house"` |  |
| `persons_per_house` | `5` | ASSUMPTION. Domestic inhabitants when a building has no override. |
| `persons_per_m2` | `0.1` | ASSUMPTION. Used when population_rule is per_m2. |
| `active_share` | `0.6` | ASSUMPTION. Fraction of daylight spent moving. |
| `family` | `""` | Hypothesis family R, G or M, when this scenario came from one. |
| `notes` | `""` |  |

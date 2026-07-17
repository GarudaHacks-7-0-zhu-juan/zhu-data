# zhu-data: Jakarta Safety Data Layer

Per-kecamatan crime, street-lighting, and population data for DKI Jakarta, joined into
one model-ready table. Built as the data layer for a personal-safety / dangerzone app.
The numbers here answer one question: how risky is each district, especially at night,
and why?

## The core files

**`data/master_dataset.csv`**: one row per kecamatan (44 rows). This is the file the
app or model reads.

**`data/kecamatan_boundaries.geojson`**: the same 44 districts as map shapes
(MultiPolygon outlines), each carrying the same columns in its properties. Use this to
shade districts on a map (choropleth). Use the CSV for everything else.

**`data/crime_kecamatan_types.csv`**: the historical crime fact table at
`year × kecamatan × jenis_kejahatan` grain. The current refresh contains scoped crime
records for 2024-2026.

**`data/crime_polsek_kecamatan_types.csv`**: the auditable Power BI leaf extract, retaining
Polda, Polres, and Polsek provenance for every positive count. Rows that cannot be mapped
cleanly are listed in **`data/crime_unmatched_locations.csv`**.

**`data/crime_type_severity.csv`**: the reviewed mapping from every known crime type to its
immediate public-safety severity and category. The mapping is joined into
`crime_kecamatan_types.csv` and `crime_types.csv` during a crime refresh.

| Column | Meaning |
|---|---|
| `kecamatan` | District name (uppercase, as published by Polri) |
| `kota` | Administrative city it belongs to |
| `centroid_lat`, `centroid_lng` | Center point of the district, for markers, labels, and distance math. Note: for the two Kepulauan Seribu island districts the centroid falls in the sea between islands |
| `crime_total` | All reported crimes, 2026 year-to-date |
| `street_crime` | Only the 25 physical-risk crime types (theft, robbery, assault, sexual violence, and similar). This is the number a safety heatmap should use |
| `street_crime_evening` | Street crimes in the 18:00-21:59 window (the citywide peak) |
| `crime_year` | Latest discovered year selected for the current risk layer |
| `public_safety_points` | Severity-weighted public-safety incidents; only moderate, high, and critical types contribute |
| `public_safety_points_per_100k` | Severity-weighted incidents per 100k residents |
| `public_safety_evening_points` | Severity-weighted incidents in the 18:00-21:59 window |
| `crime_classification_coverage` | Share of the district's reported crimes with a classified crime type |
| `evening_classification_coverage` | Share of evening reports with a classified crime type |
| `severity_2_count`, `severity_3_count`, `severity_4_count` | Counts of moderate, high, and critical public-safety incident types |
| `evening_share` | `street_crime_evening / street_crime`, how nocturnal the district's crime is |
| `population` | Residents (sum of the district's kelurahan) |
| `area_km2` | Computed from boundary polygons (the source's stored area fields are unreliable) |
| `pop_density_km2` | `population / area_km2` |
| `lamp_count` | Public street lights (PJU) in the district |
| `lamps_per_km2` | Street-light density |
| `street_crime_per_100k` | Street crime per 100k residents |
| `risk_score` | Relative district safety score from 0 (lowest observed risk) to 1 (highest observed risk) |
| `risk_level` | Policy classification: `NONE`, `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` |
| `risk_policy_version` | Version of the score formula and thresholds used to produce the row |

Example, Kemayoran: 366 street crimes (the city's highest), 27% of them in the evening
window, 34,289 people/km2, 740 lamps/km2, centroid at (-6.1627, 106.8558).

## Risk score policy

`risk_score` is an explainable relative ranking for the 44 kecamatan, produced by
`jakarta-kecamatan-v2`. It is not an individual crime probability and does not establish
that every street in a district has the same risk.

The pipeline calculates an average percentile rank for each component. Tied values receive
the same rank. The weighted score is:

```
0.50 * percentile(public_safety_points)
+ 0.30 * percentile(public_safety_points_per_100k)
+ 0.20 * percentile(public_safety_evening_points)
```

`public_safety_points` applies the immediate-public-danger weights below to classified
crime counts: `UNKNOWN=0`, `LOW=0`, `MODERATE=1`, `HIGH=3`, and `CRITICAL=6`.
`UNKNOWN` incidents are excluded rather than assigned an assumed severity. Classification
coverage is reported alongside the score but is not a score component.

| Score range | `risk_level` |
|---|---|
| `< 0.20` | `NONE` |
| `0.20` to `< 0.40` | `LOW` |
| `0.40` to `< 0.70` | `MEDIUM` |
| `0.70` to `< 0.90` | `HIGH` |
| `>= 0.90` | `CRITICAL` |

Use `kecamatan_boundaries.geojson` to color a district-level choropleth by `risk_score` or
`risk_level`. The same score applies throughout each kecamatan because public crime data is
not available at point level. Street-light values remain in the outputs for map context but
are intentionally excluded from this policy: the source does not establish lamp operating
status or complete coverage.

## Crime-type public-safety severity

The crime-type severity answers: "How strongly does this type indicate immediate physical
danger in a public location?" It does not estimate legal penalties, moral seriousness, or
the total harm experienced by a victim. For example, fraud is harmful but is a weak signal
that a person is in immediate physical danger at their current coordinates. Domestic or
other explicitly private-context offenses are also assigned low public-location relevance;
this does not mean their victim harm is low.

| Score | Level | Interpretation |
|---|---|---|
| `0` | `UNKNOWN` | Source type is unclassified and cannot be assessed |
| `1` | `LOW` | Financial, regulatory, administrative, or explicitly private-context offense |
| `2` | `MODERATE` | Nonviolent property crime, public disorder, or indirect safety threat |
| `3` | `HIGH` | Assault, coercive threat, weapons threat, or active violent disorder |
| `4` | `CRITICAL` | Lethal violence, sexual violence, abduction, terrorism, deliberate mass endangerment, or violent robbery |

The mapping is explicit rather than keyword-based. A refresh fails before replacing output
files if Pusiknas returns a new crime type that is absent from `crime_type_severity.csv`.
Severity weights now determine the `jakarta-kecamatan-v2` risk score.

## Where the data comes from

| Layer | File | Source | Method | Vintage |
|---|---|---|---|---|
| Crime | `crime_polsek_kecamatan_types.csv`, `crime_kecamatan_types.csv`, `crime_kecamatan.csv`, `crime_types.csv`, `crime_time_of_day.csv` | **Pusiknas Bareskrim Polri**: [pusiknas.polri.go.id/data_kejahatan](https://pusiknas.polri.go.id/data_kejahatan) | The public dashboard is a Power BI report. The pipeline queries its public semantic API, filters `POLDA METRO JAYA` to incidents located in DKI Jakarta, discovers Polres and Polsek dynamically, and groups positive counts by year, kecamatan, and crime type | Historical scoped rows plus live 2026 YTD |
| Street lights | `street_lights.csv` (277,198 points: lat/lng, lamp type, wattage) | **Jakarta Satu / Dinas Bina Marga DKI**: [ArcGIS FeatureServer `Data_PJU_DBM_View`](https://jakartasatu.jakarta.go.id/server/rest/services/BINAMARGA/Data_PJU_DBM_View/FeatureServer/0) (flagged `access: public`; backs the city's own PJU dashboard) | Paginated export via the official ArcGIS REST query API | As published |
| Population | `population.geojson` (267 kelurahan: polygons plus population, households, gender, age buckets) | **Dukcapil Kemendagri GIS**: [layer `AGR_VISUAL_KEL_FIX`](https://gis.dukcapil.kemendagri.go.id/arcgis/rest/services/AGR_VISUAL_KEL_FIX/MapServer/0) | Paginated GeoJSON export, filtered to DKI Jakarta | Approx. DKB 2024 / early 2025 |

All three are official government sources, openly accessible without credentials.

## How the pipeline works

Everything is one script. The app or model never touches the network; it just reads
`master_dataset.csv`. The network is only used when you explicitly refresh.

```
python3 scripts/pipeline.py                      # rebuild outputs from local data (offline, instant)
python3 scripts/pipeline.py refresh              # re-download all three sources, then rebuild
python3 scripts/pipeline.py refresh crime        # selective: crime | lights | population
```

What `build` does:

1. Loads the three source layers from `data/`.
2. Aggregates kelurahan up to kecamatan: sums population, computes area and the
   area-weighted centroid from the polygon geometry (shoelace formula with latitude
   correction).
3. Aggregates lamps per kecamatan. About 300 lamps carry a junk district label (`'-'`);
   those are placed by point-in-polygon against the kelurahan boundaries instead of
   being dropped.
4. Joins the three layers on normalized district names (verified: all 44 match).
5. Derives the ratio columns, writes `master_dataset.csv`, and writes
   `kecamatan_boundaries.geojson` with the same values attached to each district shape.
   Fails loudly if the result is not exactly 44 districts.

What `refresh crime` does:

1. Discovers every year with positive scoped crime data.
2. Selects `POLDA METRO JAYA` and `DKI JAKARTA`, then enumerates Polres and each Polres's
   Polsek. Null hierarchy members are retained as unassigned branches instead of dropped.
3. Queries positive `Jumlah_CT` values by year, incident kecamatan, and crime type for each
   Polsek. Power BI dictionary encoding is decoded and truncated responses are rejected.
4. Reconciles every leaf total with its Polsek, Polres, and Polda hierarchy totals.
5. Writes the provenance-preserving leaf file and the kecamatan/type aggregation. Blank or
   unknown locations are quarantined. Records with a valid kecamatan but no crime-type
   relationship are retained as `UNCLASSIFIED` so district totals stay complete.
6. Validates every discovered crime type against `crime_type_severity.csv` and enriches the
   kecamatan/type output with severity, level, and public-safety category.
7. Queries typed 18:00-21:59 incidents, calculates severity-weighted evening points, and
   reports current and evening classification coverage by kecamatan.
8. Rebuilds `crime_kecamatan.csv`, `crime_types.csv`, and `crime_time_of_day.csv` from the
   latest discovered year. The risk map therefore uses the latest year only while historical
   rows remain available in `crime_kecamatan_types.csv`.

Refresh is fail-safe: every download is validated (row counts, non-zero totals) and
written to a temp file first. An endpoint outage or bad response can never corrupt the
existing files; the previous version is kept and the failure is printed.

## Caveats: read before using the numbers

- **The latest crime year is a live rolling year-to-date count**, not an annual figure. Absolute values
  grow as the year progresses; the relative ordering between districts is the signal.
  Do not compare against annual publications (different timeframe and scope).
- **`street_crime` is deliberately filtered.** Jakarta's two most-reported crimes are
  fraud and cybercrime, and neither makes a street dangerous to walk through. Only 25
  physical-risk types are counted. The filter lives in the
  committed query payloads.
- **Police hierarchy and incident geography are different fields.** Polres and Polsek are
  retained as source provenance, but the map uses the incident's `Nama_Kecamatan`. A Polsek
  is not assumed to correspond one-to-one with an administrative kecamatan.
- **Some source records cannot be mapped.** The current refresh has 25,630 crimes with a
  blank kecamatan and 16,538 crimes with a valid kecamatan but no matching crime-type
  dimension value. See `crime_unmatched_locations.csv`; the latter are included in district
  totals as `UNCLASSIFIED` but cannot contribute to the selected street-crime taxonomy.
- **Classification coverage is incomplete and uneven.** `UNKNOWN` records receive zero
  severity points, so use `crime_classification_coverage` and
  `evening_classification_coverage` when interpreting a district score. Low coverage is
  uncertainty, not evidence that a district is safer.
- **Police-report data undercounts reality** (not every crime is reported). Treat values
  as a lower bound and a relative signal.
- **`street_crime_per_100k` divides by resident population.** Business and nightlife
  districts (Kebayoran Baru, Menteng, Setiabudi) have huge daytime inflow, so their
  per-resident rates overstate the risk to any one person present. Blend with the raw
  count rather than using the rate alone.
- **Kecamatan is the finest granularity that exists publicly.** No agency publishes
  point-level (lat/lng) crime for Jakarta; within-district variation must come from
  other signals (for example the lighting layer).
- **Risk levels are relative to this dataset.** They can change after a crime-data refresh
  because percentile ranks compare each kecamatan with the other 43 districts. Compare
`risk_policy_version` before comparing generated outputs across policy revisions.

## Visualize the risk map

`risk-map.html` is a standalone Leaflet map that loads all 44 scored kecamatan from
`data/kecamatan_boundaries.geojson`. From the repository root, run:

```
python3 -m http.server
```

Then visit [http://localhost:8000/risk-map.html](http://localhost:8000/risk-map.html).
The page colors polygons by `risk_level` and displays `risk_score` plus its contributing
metrics when a district is selected.

## Attribution

Data belongs to its publishers: Polri (Pusiknas Bareskrim), Pemprov DKI Jakarta
(Jakarta Satu / Dinas Bina Marga), and Kemendagri (Ditjen Dukcapil). This repo only
repackages openly published data; cite the sources above when using it.

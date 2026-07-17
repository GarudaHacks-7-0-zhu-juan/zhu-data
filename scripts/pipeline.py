#!/usr/bin/env python3

import csv, json, math, os, re, sys, tempfile, time, urllib.parse, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
QUERIES = os.path.join(HERE, "queries")

PUSIKNAS_ENDPOINT = ("https://wabi-south-east-asia-b-primary-api.analysis.windows.net"
                     "/public/reports/querydata?synchronous=true")
PUSIKNAS_KEY = "dfe13d87-1d2b-421c-be7b-bf6edd2e1f9d"
PUSIKNAS_MODEL_ID = 5179165
PUSIKNAS_DATASET_ID = "edcee19b-e8fc-4f8a-bdc1-6a3410863eed"
PUSIKNAS_REPORT_ID = "ec40848e-ee84-4f0e-9d4b-5a1016130676"
PUSIKNAS_POLDA = "POLDA METRO JAYA"
PUSIKNAS_PROVINCE = "DKI JAKARTA"
PUSIKNAS_DATE_ENTITY = "LocalDateTable_12add86b-6ca9-411c-b150-5826b6bdf752"

LIGHTS_URL = ("https://jakartasatu.jakarta.go.id/server/rest/services/"
              "BINAMARGA/Data_PJU_DBM_View/FeatureServer/0/query")
LIGHTS_FIELDS = ["ID_PJU", "WADMKK", "WADMKC", "JNSLAMPU", "DAYALAMPU",
                 "LATITUDE", "LONGITUDE", "TAHUN", "ALAMAT"]

POPULATION_URL = ("https://gis.dukcapil.kemendagri.go.id/arcgis/rest/services/"
                  "AGR_VISUAL_KEL_FIX/MapServer/0/query")
POPULATION_FIELDS = ["no_kel", "kode_desa_spatial", "nama_kab", "nama_kec", "nama_kel",
                     "jumlah_penduduk", "jumlah_kk", "pria", "wanita",
                     "u0", "u5", "u10", "u15", "u20", "u25", "u30", "u35", "u40",
                     "u45", "u50", "u55", "u60", "u65", "u70", "u75"]

LIGHTS_KEC_FIX = {"PEGADUNGAN": "KALI DERES"}
LIGHTS_KEC_DROP = {"", "JAKBAR", "JAKARTA BARAT"}

RISK_POLICY_VERSION = "jakarta-kecamatan-v1"
RISK_COMPONENTS = {
    "street_crime": 0.5,
    "street_crime_per_100k": 0.3,
    "street_crime_evening": 0.2,
}
RISK_LEVELS = ("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL")

norm = lambda s: re.sub(r"[^A-Z]", "", str(s).upper())

def run_payload(payload, retries=4):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(PUSIKNAS_ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-PowerBI-ResourceKey": PUSIKNAS_KEY,
        "Origin": "https://app.powerbi.com",
        "User-Agent": "Mozilla/5.0 (zhu-data refresh)",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                response = json.load(r)
            if not response.get("results") or "result" not in response["results"][0]:
                raise RuntimeError(f"unexpected Power BI response: {str(response)[:300]}")
            return response
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))

def parse_rows(resp):
    ds = resp["results"][0]["result"]["data"]["dsr"]["DS"][0]
    if ds.get("IC") is False:
        raise ValueError("Power BI result was truncated; reduce query scope")
    dm = ds.get("PH", [{}])[0].get("DM0", [])
    if not dm:
        return []
    schema = next((item["S"] for item in dm if item.get("S")), None)
    if not schema:
        raise ValueError("Power BI result has no column schema")
    dictionaries = ds.get("ValueDicts", {})
    rows, prev = [], [None] * len(schema)
    for item in dm:
        c = list(item.get("C", []))
        rep = item.get("R", 0)
        nul = item.get("Ø", 0)
        row, ci = [], 0
        for col, descriptor in enumerate(schema):
            bit = 1 << col
            if nul & bit:
                value = None
            elif rep & bit:
                value = prev[col]
            else:
                value = c[ci] if ci < len(c) else None
                ci += 1
                dictionary = dictionaries.get(descriptor.get("DN"))
                if dictionary is not None and isinstance(value, int):
                    if value >= len(dictionary):
                        raise ValueError("Power BI dictionary index is out of range")
                    value = dictionary[value]
            row.append(value)
        rows.append(row)
        prev = row
    return rows

def write_csv(out_path, header, rows):
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, out_path)

def pbi_select(source, entity, field, kind="Column", name=None):
    return {
        kind: {"Expression": {"SourceRef": {"Source": source}}, "Property": field},
        "Name": name or f"{entity}.{field}",
        "NativeReferenceName": field,
    }

def pbi_literal(value):
    if value is None:
        return "null"
    if isinstance(value, int):
        return f"{value}L"
    return "'" + str(value).replace("'", "''") + "'"

def pbi_in(source, field, values):
    return {"Condition": {"In": {
        "Expressions": [{"Column": {
            "Expression": {"SourceRef": {"Source": source}}, "Property": field}}],
        "Values": [[{"Literal": {"Value": pbi_literal(value)}}] for value in values],
    }}}

def pbi_positive_measure():
    return {"Condition": {"Comparison": {
        "ComparisonKind": 1,
        "Left": {"Measure": {
            "Expression": {"SourceRef": {"Source": "v1"}}, "Property": "Jumlah_CT"}},
        "Right": {"Literal": {"Value": "0L"}},
    }}}

def powerbi_payload(select, where, window=30000):
    query = {
        "Version": 2,
        "From": [
            {"Name": "v1", "Entity": "VIEW_DATA_LP", "Type": 0},
            {"Name": "v", "Entity": "VIEW_MASTER_POLRES_POLSEK", "Type": 0},
            {"Name": "j", "Entity": "Jenis Kejahatan", "Type": 0},
            {"Name": "l", "Entity": PUSIKNAS_DATE_ENTITY, "Type": 0},
            {"Name": "w", "Entity": "Waktu Kejahatan", "Type": 0},
        ],
        "Select": select,
        "Where": where,
    }
    command = {
        "SemanticQueryDataShapeCommand": {
            "Query": query,
            "Binding": {
                "Primary": {"Groupings": [{"Projections": list(range(len(select)))}]},
                "DataReduction": {"DataVolume": 6, "Primary": {"Window": {"Count": window}}},
                "Version": 1,
            },
        }
    }
    return {
        "version": "1.0.0",
        "queries": [{
            "Query": {"Commands": [command]},
            "QueryId": "",
            "ApplicationContext": {
                "DatasetId": PUSIKNAS_DATASET_ID,
                "Sources": [{"ReportId": PUSIKNAS_REPORT_ID}],
            },
        }],
        "cancelQueries": [],
        "modelId": PUSIKNAS_MODEL_ID,
    }

def query_powerbi(select, where, window=30000):
    return parse_rows(run_payload(powerbi_payload(select, where, window)))

def crime_base_filters():
    return [
        pbi_in("v", "NamaPolda", [PUSIKNAS_POLDA]),
        pbi_in("v1", "Nama_Propinsi", [PUSIKNAS_PROVINCE]),
        pbi_positive_measure(),
    ]

def load_street_crime_types():
    path = os.path.join(QUERIES, "pusiknas_query_streetcrime_kecamatan.json")
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    where = payload["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]["Query"]["Where"]
    for clause in where:
        condition = clause.get("Condition", {}).get("In", {})
        expressions = condition.get("Expressions", [])
        if expressions and expressions[0].get("Column", {}).get("Property") == "jenis_kejahatan":
            values = condition["Values"]
            return {value[0]["Literal"]["Value"].strip("'") for value in values}
    raise ValueError("street-crime type filter is missing")

def load_district_names():
    names = {}
    master_path = os.path.join(DATA, "master_dataset.csv")
    if os.path.exists(master_path):
        with open(master_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                names[norm(row["kecamatan"])] = row["kecamatan"]
    with open(os.path.join(DATA, "population.geojson"), encoding="utf-8") as f:
        for feature in json.load(f)["features"]:
            name = str(feature["properties"]["nama_kec"]).strip().upper()
            names.setdefault(norm(name), name)
    if len(names) != 44:
        raise ValueError(f"expected 44 known DKI kecamatan, got {len(names)}")
    return names

def query_latest_supporting_data(latest_year, street_types):
    year_filter = pbi_in("l", "Year", [latest_year])
    type_filter = pbi_in("j", "jenis_kejahatan", sorted(street_types))
    evening_rows = query_powerbi([
        pbi_select("v1", "VIEW_DATA_LP", "Nama_Kecamatan"),
        pbi_select("v1", "VIEW_DATA_LP", "Jumlah_CT", "Measure"),
    ], crime_base_filters() + [year_filter, type_filter,
                              pbi_in("w", "Waktu_Kejadian_Update", ["18:00-21:59"])])
    time_rows = query_powerbi([
        pbi_select("w", "Waktu Kejahatan", "Waktu_Kejadian_Update"),
        pbi_select("v1", "VIEW_DATA_LP", "Jumlah_CT", "Measure"),
    ], crime_base_filters() + [year_filter])
    return evening_rows, time_rows

def refresh_crime_hierarchy():
    known_districts = load_district_names()
    street_types = load_street_crime_types()
    base = crime_base_filters()
    measure = pbi_select("v1", "VIEW_DATA_LP", "Jumlah_CT", "Measure")

    year_rows = query_powerbi([
        pbi_select("l", PUSIKNAS_DATE_ENTITY, "Year"), measure,
    ], base)
    years = sorted({int(row[0]) for row in year_rows if isinstance(row[0], (int, float))})
    if not years:
        raise ValueError("Power BI returned no crime years")
    scoped_base = base + [pbi_in("l", "Year", years)]

    polres_rows = query_powerbi([
        pbi_select("v", "VIEW_MASTER_POLRES_POLSEK", "NamaPolres"), measure,
    ], scoped_base)
    polres_totals = {row[0]: int(row[1]) for row in polres_rows if row[1] > 0}
    if not polres_totals:
        raise ValueError("Power BI returned no Polres")

    raw_rows = []
    hierarchy_total = 0
    for polres, polres_total in polres_totals.items():
        polres_filter = pbi_in("v", "NamaPolres", [polres])
        polsek_rows = query_powerbi([
            pbi_select("v", "VIEW_MASTER_POLRES_POLSEK", "NamaPolsek"), measure,
        ], scoped_base + [polres_filter])
        polsek_totals = {row[0]: int(row[1]) for row in polsek_rows if row[1] > 0}
        if sum(polsek_totals.values()) != polres_total:
            raise ValueError(f"{polres or '(unassigned)'}: Polsek totals do not match Polres total")

        branch_total = 0
        for polsek, expected_total in polsek_totals.items():
            leaf_filters = scoped_base + [polres_filter, pbi_in("v", "NamaPolsek", [polsek])]
            location_rows = query_powerbi([
                pbi_select("l", PUSIKNAS_DATE_ENTITY, "Year"),
                pbi_select("v1", "VIEW_DATA_LP", "Nama_Kecamatan"),
                measure,
            ], leaf_filters)
            actual_total = sum(int(row[2]) for row in location_rows if row[2] > 0)
            if actual_total != expected_total:
                label = polsek or "(unassigned Polsek)"
                raise ValueError(f"{label}: leaf total {actual_total:,} != hierarchy total {expected_total:,}")

            typed_rows = query_powerbi([
                pbi_select("l", PUSIKNAS_DATE_ENTITY, "Year"),
                pbi_select("v1", "VIEW_DATA_LP", "Nama_Kecamatan"),
                pbi_select("j", "Jenis Kejahatan", "jenis_kejahatan"),
                measure,
            ], leaf_filters)
            branch_total += actual_total
            typed_by_location = defaultdict(int)
            for year, kecamatan, crime_type, total in typed_rows:
                if total > 0:
                    typed_by_location[(int(year), kecamatan or "")] += int(total)
                    raw_rows.append([int(year), PUSIKNAS_POLDA, polres or "", polsek or "",
                                     kecamatan or "", crime_type or "", int(total)])
            for year, kecamatan, total in location_rows:
                residual = int(total) - typed_by_location[(int(year), kecamatan or "")]
                if residual < 0:
                    label = polsek or "(unassigned Polsek)"
                    raise ValueError(f"{label}: typed crime total exceeds location total")
                if residual:
                    raw_rows.append([int(year), PUSIKNAS_POLDA, polres or "", polsek or "",
                                     kecamatan or "", "", residual])
            time.sleep(0.1)
        hierarchy_total += branch_total
        print(f"    {polres or '(unassigned Polres)'}: {len(polsek_totals)} Polsek, {branch_total:,} crimes",
              flush=True)

    if hierarchy_total != sum(polres_totals.values()):
        raise ValueError("leaf totals do not match Polda hierarchy total")

    aggregated = defaultdict(int)
    unmatched = []
    for row in raw_rows:
        year, _, polres, polsek, kecamatan, crime_type, total = row
        key = norm(kecamatan)
        if not kecamatan:
            unmatched.append(row + ["blank kecamatan"])
        elif key not in known_districts:
            unmatched.append(row + ["kecamatan outside DKI boundary dataset"])
        elif not crime_type:
            unmatched.append(row + ["blank crime type"])
            aggregated[(year, known_districts[key], "UNCLASSIFIED")] += total
        else:
            aggregated[(year, known_districts[key], crime_type)] += total

    latest_year = max(years)
    latest = defaultdict(int)
    latest_types = defaultdict(int)
    for (year, kecamatan, crime_type), total in aggregated.items():
        if year == latest_year:
            latest[(norm(kecamatan), crime_type)] += total
            latest_types[crime_type] += total
    if not latest:
        raise ValueError(f"no matched kecamatan data for latest year {latest_year}")

    evening_rows, time_rows = query_latest_supporting_data(latest_year, street_types)
    evening = defaultdict(int)
    unmatched_evening = 0
    for kecamatan, total in evening_rows:
        key = norm(kecamatan)
        if key not in known_districts:
            unmatched_evening += int(total)
            continue
        evening[key] += int(total)
    if unmatched_evening:
        print(f"    warning: {unmatched_evening:,} evening crimes have no matched kecamatan", flush=True)

    street_type_keys = {crime_type.casefold().strip() for crime_type in street_types}
    summary = []
    for key, name in known_districts.items():
        district_types = {crime_type: total for (district, crime_type), total in latest.items()
                          if district == key}
        total = sum(district_types.values())
        street = sum(value for crime_type, value in district_types.items()
                     if crime_type.casefold().strip() in street_type_keys)
        summary.append([name, total, street, evening.get(key, 0), latest_year])
    summary.sort(key=lambda row: -row[2])

    aggregate_rows = [[year, kecamatan, crime_type, total]
                      for (year, kecamatan, crime_type), total in sorted(aggregated.items())]
    raw_rows.sort(key=lambda row: (row[0], row[2], row[3], row[4], row[5]))
    unmatched.sort(key=lambda row: (row[0], row[2], row[3], row[4], row[5]))
    type_rows = sorted(latest_types.items(), key=lambda item: (-item[1], item[0]))
    clean_time_rows = sorted(((str(row[0]), int(row[1])) for row in time_rows if row[0]),
                             key=lambda item: -item[1])

    raw_header = ["year", "polda", "polres", "polsek", "kecamatan", "jenis_kejahatan", "crime_total"]
    write_csv(os.path.join(DATA, "crime_polsek_kecamatan_types.csv"), raw_header, raw_rows)
    write_csv(os.path.join(DATA, "crime_kecamatan_types.csv"),
              ["year", "kecamatan", "jenis_kejahatan", "crime_total"], aggregate_rows)
    write_csv(os.path.join(DATA, "crime_unmatched_locations.csv"), raw_header + ["reason"], unmatched)
    write_csv(os.path.join(DATA, "crime_kecamatan.csv"),
              ["kecamatan", "crime_total", "street_crime", "street_crime_evening", "crime_year"],
              summary)
    write_csv(os.path.join(DATA, "crime_types.csv"),
              ["jenis_kejahatan", "crime_total"], type_rows)
    write_csv(os.path.join(DATA, "crime_time_of_day.csv"),
              ["waktu_kejadian", "crime_total"], clean_time_rows)
    return {
        "ok": True,
        "rows": len(aggregate_rows),
        "total": sum(row[3] for row in aggregate_rows),
        "years": years,
        "latest_year": latest_year,
        "raw_rows": len(raw_rows),
        "unmatched_rows": len(unmatched),
        "unmatched_total": sum(row[6] for row in unmatched),
    }

def refresh_crime():
    try:
        result = refresh_crime_hierarchy()
        year_range = f"{result['years'][0]}-{result['years'][-1]}"
        print(f"  ✓ crime hierarchy   {result['raw_rows']:,} leaf rows, {result['rows']:,} aggregated rows")
        print(f"    years {year_range}; latest risk year {result['latest_year']}")
        print(f"    unmatched {result['unmatched_rows']:,} rows / {result['unmatched_total']:,} crimes")
        return True
    except Exception as e:
        print(f"  ✗ crime hierarchy   {type(e).__name__}: {e}  → kept previous files")
        return False

def arcgis_page(url, params, retries=4):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": "Mozilla/5.0 (data refresh)"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            if "features" in d:
                return d["features"]
            raise RuntimeError(f"unexpected response: {str(d)[:200]}")
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))

def refresh_lights():
    out_path = os.path.join(DATA, "street_lights.csv")
    tmp = out_path + ".tmp"
    try:
        total, offset = 0, 0
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=LIGHTS_FIELDS)
            w.writeheader()
            while True:
                feats = arcgis_page(LIGHTS_URL, {
                    "where": "1=1", "outFields": ",".join(LIGHTS_FIELDS),
                    "returnGeometry": "false", "orderByFields": "OBJECTID",
                    "resultOffset": offset, "resultRecordCount": 2000, "f": "json"})
                for feat in feats:
                    w.writerow({k: feat["attributes"].get(k) for k in LIGHTS_FIELDS})
                total += len(feats)
                print(f"  lights offset {offset}: +{len(feats)} (total {total:,})", flush=True)
                if len(feats) < 2000:
                    break
                offset += 2000
                time.sleep(0.3)
        if total < 200000:
            raise ValueError(f"only {total} lamps (expected ~277k) — refusing to overwrite")
        os.replace(tmp, out_path)
        print(f"  ✓ street_lights     {total:,} lamps")
        return True
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f"  ✗ street_lights     {type(e).__name__}: {e}  → kept previous file")
        return False

def refresh_population():
    out_path = os.path.join(DATA, "population.geojson")
    tmp = out_path + ".tmp"
    try:
        feats, offset = [], 0
        while True:
            page = arcgis_page(POPULATION_URL, {
                "where": "nama_prop LIKE '%JAKARTA%'",
                "outFields": ",".join(POPULATION_FIELDS),
                "returnGeometry": "true", "outSR": 4326, "orderByFields": "objectid",
                "resultOffset": offset, "resultRecordCount": 100, "f": "geojson"})
            feats.extend(page)
            print(f"  population offset {offset}: +{len(page)} (total {len(feats)})", flush=True)
            if len(page) < 100:
                break
            offset += 100
            time.sleep(0.3)
        if len(feats) != 267:
            raise ValueError(f"expected 267 kelurahan, got {len(feats)} — refusing to overwrite")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False)
        os.replace(tmp, out_path)
        total = sum(ft["properties"].get("jumlah_penduduk") or 0 for ft in feats)
        print(f"  ✓ population        267 kelurahan, {total:,} people")
        return True
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f"  ✗ population        {type(e).__name__}: {e}  → kept previous file")
        return False

def ring_area_km2(ring):
    r = 6371.0088
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    kx = r * math.cos(lat0) * math.pi / 180
    ky = r * math.pi / 180
    a = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0] * kx, ring[i][1] * ky
        x2, y2 = ring[i + 1][0] * kx, ring[i + 1][1] * ky
        a += x1 * y2 - x2 * y1
    return abs(a) / 2

def geom_area_km2(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    total = 0.0
    for rings in polys:
        total += ring_area_km2(rings[0])
        for hole in rings[1:]:
            total -= ring_area_km2(hole)
    return total

def ring_centroid(ring):
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a /= 2
    if a == 0:
        return 0.0, 0.0, 0.0
    return cx / (6 * a), cy / (6 * a), a

def point_in_ring(lng, lat, ring):
    inside = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > lat) != (y2 > lat) and lng < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside

def locate_kecamatan(lng, lat, rings_by_kec):
    for k, rings in rings_by_kec.items():
        for ring in rings:
            if point_in_ring(lng, lat, ring):
                return k
    return None

def load_crime():
    out = {}
    with open(os.path.join(DATA, "crime_kecamatan.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[norm(r["kecamatan"])] = {
                "kecamatan": r["kecamatan"],
                "crime_total": int(r["crime_total"]),
                "street_crime": int(r["street_crime"]),
                "street_crime_evening": int(r["street_crime_evening"]),
                "crime_year": int(r["crime_year"]),
            }
    return out

def load_population():
    out = {}
    rings_by_kec = {}
    polys_by_kec = {}
    gj = json.load(open(os.path.join(DATA, "population.geojson"), encoding="utf-8"))
    for feat in gj["features"]:
        p = feat["properties"]
        k = norm(p["nama_kec"])
        d = out.setdefault(k, {"kota": p["nama_kab"], "population": 0, "area_km2": 0.0,
                               "cw": 0.0, "cx": 0.0, "cy": 0.0})
        d["population"] += p["jumlah_penduduk"]
        d["area_km2"] += geom_area_km2(feat["geometry"])
        g = feat["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for rings in polys:
            for j, ring in enumerate(rings):
                x, y, a = ring_centroid(ring)
                w = abs(a) if j == 0 else -abs(a)
                d["cw"] += w
                d["cx"] += x * w
                d["cy"] += y * w
        rings_by_kec.setdefault(k, []).extend(rings[0] for rings in polys)
        polys_by_kec.setdefault(k, []).extend(polys)
    for d in out.values():
        d["centroid_lng"] = d["cx"] / d["cw"] if d["cw"] else 0.0
        d["centroid_lat"] = d["cy"] / d["cw"] if d["cw"] else 0.0
    return out, rings_by_kec, polys_by_kec

def load_lights(rings_by_kec):
    out = {}
    def add(k, r):
        d = out.setdefault(k, {"lamp_count": 0, "lamp_watt": 0})
        d["lamp_count"] += 1
        try:
            d["lamp_watt"] += int(float(r["DAYALAMPU"]))
        except (ValueError, TypeError):
            pass
    with open(os.path.join(DATA, "street_lights.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            kec = r["WADMKC"].strip().upper()
            if kec in LIGHTS_KEC_DROP:
                continue
            kec = LIGHTS_KEC_FIX.get(kec, kec)
            k = norm(kec)
            if not k:
                k = locate_kecamatan(float(r["LONGITUDE"]), float(r["LATITUDE"]), rings_by_kec)
                if k is None:
                    continue
            add(k, r)
    return out

def percentile_ranks(rows, field):
    """Return average percentile ranks so tied source values score identically."""
    ordered = sorted((float(row[field]), index) for index, row in enumerate(rows))
    denominator = len(ordered) - 1
    ranks = [0.0] * len(rows)
    start = 0
    while start < len(ordered):
        end = start
        while end + 1 < len(ordered) and ordered[end + 1][0] == ordered[start][0]:
            end += 1
        percentile = (start + end) / (2 * denominator) if denominator else 0.0
        for _, index in ordered[start:end + 1]:
            ranks[index] = percentile
        start = end + 1
    return ranks

def risk_level(score):
    if score < 0.2:
        return "NONE"
    if score < 0.4:
        return "LOW"
    if score < 0.7:
        return "MEDIUM"
    if score < 0.9:
        return "HIGH"
    return "CRITICAL"

def score_rows(rows):
    ranks = {field: percentile_ranks(rows, field) for field in RISK_COMPONENTS}
    for index, row in enumerate(rows):
        score = sum(ranks[field][index] * weight
                    for field, weight in RISK_COMPONENTS.items())
        row["risk_score"] = round(score, 4)
        row["risk_level"] = risk_level(score)
        row["risk_policy_version"] = RISK_POLICY_VERSION

def validate_rows(rows):
    if len(rows) != 44:
        raise ValueError(f"expected 44 kecamatan, got {len(rows)}")
    if len({row["kecamatan"] for row in rows}) != len(rows):
        raise ValueError("duplicate kecamatan names")
    for row in rows:
        for field in RISK_COMPONENTS:
            if not isinstance(row.get(field), (int, float)):
                raise ValueError(f"{row['kecamatan']}: invalid {field}")
        score = row.get("risk_score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError(f"{row['kecamatan']}: invalid risk_score")
        if row.get("risk_level") not in RISK_LEVELS:
            raise ValueError(f"{row['kecamatan']}: invalid risk_level")
        if row.get("risk_policy_version") != RISK_POLICY_VERSION:
            raise ValueError(f"{row['kecamatan']}: invalid risk_policy_version")

def build():
    crime = load_crime()
    pop, rings_by_kec, polys_by_kec = load_population()
    lights = load_lights(rings_by_kec)
    rows = []
    keys = []
    for k, c in sorted(crime.items(), key=lambda kv: -kv[1]["street_crime"]):
        if k not in pop:
            print(f"ERROR: kecamatan {c['kecamatan']} missing from population data", file=sys.stderr)
            sys.exit(1)
        p = pop[k]
        l = lights.get(k, {"lamp_count": 0, "lamp_watt": 0})
        area = p["area_km2"]
        keys.append(k)
        rows.append({
            "kecamatan": c["kecamatan"],
            "kota": p["kota"],
            "centroid_lat": round(p["centroid_lat"], 5),
            "centroid_lng": round(p["centroid_lng"], 5),
            "crime_total": c["crime_total"],
            "street_crime": c["street_crime"],
            "street_crime_evening": c["street_crime_evening"],
            "crime_year": c["crime_year"],
            "evening_share": round(c["street_crime_evening"] / c["street_crime"], 4) if c["street_crime"] else 0,
            "population": p["population"],
            "area_km2": round(area, 2),
            "pop_density_km2": round(p["population"] / area, 1) if area else 0,
            "lamp_count": l["lamp_count"],
            "lamps_per_km2": round(l["lamp_count"] / area, 1) if area else 0,
            "street_crime_per_100k": round(c["street_crime"] / p["population"] * 100000, 1) if p["population"] else 0,
        })
    score_rows(rows)
    try:
        validate_rows(rows)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    out_path = os.path.join(DATA, "master_dataset.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    features = []
    for k, row in zip(keys, rows):
        features.append({"type": "Feature",
                         "properties": row,
                         "geometry": {"type": "MultiPolygon", "coordinates": polys_by_kec[k]}})
    geo_path = os.path.join(DATA, "kecamatan_boundaries.geojson")
    with open(geo_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)
    print(f"DONE: {len(rows)} kecamatan -> {out_path}")
    print(f"      boundaries -> {geo_path}")
    print(f"  population {sum(r['population'] for r in rows):,}"
          f" | lamps {sum(r['lamp_count'] for r in rows):,}"
          f" | crime_total {sum(r['crime_total'] for r in rows):,}"
          f" | street_crime {sum(r['street_crime'] for r in rows):,}")

USAGE = """usage:
  python3 scripts/pipeline.py                          build master_dataset.csv from local data
  python3 scripts/pipeline.py refresh                  re-download all sources, then build
  python3 scripts/pipeline.py refresh crime            re-download crime only, then build
  python3 scripts/pipeline.py refresh lights           re-download street lights only, then build
  python3 scripts/pipeline.py refresh population       re-download population only, then build"""

REFRESHERS = {"crime": refresh_crime, "lights": refresh_lights, "population": refresh_population}

def main():
    args = sys.argv[1:]
    if not args:
        build()
        return
    if args[0] != "refresh" or any(a not in REFRESHERS for a in args[1:]):
        print(USAGE)
        sys.exit(1)
    targets = args[1:] or list(REFRESHERS)
    ok = True
    for t in targets:
        print(f"refreshing {t}...")
        ok = REFRESHERS[t]() and ok
    build()
    if not ok:
        print("some refreshes failed — previous files were kept; features built from latest available data")
        sys.exit(1)

if __name__ == "__main__":
    main()

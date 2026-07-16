#!/usr/bin/env python3

import csv, json, math, os, re, sys, tempfile, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
QUERIES = os.path.join(HERE, "queries")

PUSIKNAS_ENDPOINT = ("https://wabi-south-east-asia-b-primary-api.analysis.windows.net"
                     "/public/reports/querydata?synchronous=true")
PUSIKNAS_KEY = "dfe13d87-1d2b-421c-be7b-bf6edd2e1f9d"

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

CRIME_KECAMATAN_PARTS = {
    "crime_total":          ("pusiknas_query_kecamatan_dki.json", 40),
    "street_crime":         ("pusiknas_query_streetcrime_kecamatan.json", 40),
    "street_crime_evening": ("pusiknas_query_streetcrime_kec_evening.json", 35),
}
CRIME_STANDALONE = {
    "crime_types":       ("pusiknas_query_jenis_jakarta.json", ["jenis_kejahatan", "crime_total"], 80),
    "crime_time_of_day": ("pusiknas_query_waktu_jakarta.json", ["waktu_kejadian", "crime_total"], 6),
}

LIGHTS_KEC_FIX = {"PEGADUNGAN": "KALI DERES"}
LIGHTS_KEC_DROP = {"", "JAKBAR", "JAKARTA BARAT"}

norm = lambda s: re.sub(r"[^A-Z]", "", str(s).upper())

def run_query(payload_path):
    body = open(payload_path, "rb").read()
    req = urllib.request.Request(PUSIKNAS_ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-PowerBI-ResourceKey": PUSIKNAS_KEY,
        "Origin": "https://app.powerbi.com",
        "User-Agent": "Mozilla/5.0 (data refresh)",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def parse_rows(resp):
    dm = resp["results"][0]["result"]["data"]["dsr"]["DS"][0]["PH"][0]["DM0"]
    ncols = 0
    for item in dm:
        if "R" not in item and "Ø" not in item and item.get("C"):
            ncols = max(ncols, len(item["C"]))
    rows, prev = [], []
    for item in dm:
        c = list(item.get("C", []))
        rep = item.get("R", 0)
        nul = item.get("Ø", 0)
        row, ci = [], 0
        for col in range(ncols):
            bit = 1 << col
            if nul & bit:
                row.append(None)
            elif rep & bit:
                row.append(prev[col] if col < len(prev) else None)
            else:
                row.append(c[ci] if ci < len(c) else None)
                ci += 1
        rows.append(row)
        prev = row
    return rows

def clean(rows):
    return [r for r in rows
            if r and r[0] and str(r[0]).strip() and isinstance(r[1], (int, float))]

def write_csv(out_path, header, rows):
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, out_path)

def refresh_crime_kecamatan():
    out_path = os.path.join(DATA, "crime_kecamatan.csv")
    try:
        parts = {}
        for col, (payload, min_rows) in CRIME_KECAMATAN_PARTS.items():
            rows = clean(parse_rows(run_query(os.path.join(QUERIES, payload))))
            if len(rows) < min_rows:
                raise ValueError(f"{col}: only {len(rows)} rows (expected >= {min_rows})")
            parts[col] = {norm(r[0]): (str(r[0]).strip(), r[1]) for r in rows}
        combined = []
        for key, (name, total) in sorted(parts["crime_total"].items(),
                                         key=lambda kv: -kv[1][1]):
            if total <= 0:
                continue
            combined.append([name, total,
                             parts["street_crime"].get(key, ("", 0))[1],
                             parts["street_crime_evening"].get(key, ("", 0))[1]])
        if sum(r[1] for r in combined) <= 0:
            raise ValueError("zero total — refusing to overwrite")
        write_csv(out_path, ["kecamatan", "crime_total", "street_crime",
                             "street_crime_evening"], combined)
        return {"ok": True, "rows": len(combined), "total": sum(r[1] for r in combined)}
    except Exception as e:
        kept = "kept previous file" if os.path.exists(out_path) else "NO file exists"
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "fallback": kept}

def refresh_crime_standalone(name):
    payload, cols, min_rows = CRIME_STANDALONE[name]
    out_path = os.path.join(DATA, f"{name}.csv")
    try:
        rows = clean(parse_rows(run_query(os.path.join(QUERIES, payload))))
        if len(rows) < min_rows:
            raise ValueError(f"only {len(rows)} rows (expected >= {min_rows}) — refusing to overwrite")
        if sum(r[1] for r in rows) <= 0:
            raise ValueError("zero total — refusing to overwrite")
        write_csv(out_path, cols, [r[:len(cols)] for r in rows])
        return {"ok": True, "rows": len(rows), "total": sum(r[1] for r in rows)}
    except Exception as e:
        kept = "kept previous file" if os.path.exists(out_path) else "NO file exists"
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "fallback": kept}

def refresh_crime():
    failed = 0
    for label, result in [("crime_kecamatan", refresh_crime_kecamatan()),
                          ("crime_types", refresh_crime_standalone("crime_types")),
                          ("crime_time_of_day", refresh_crime_standalone("crime_time_of_day"))]:
        if result["ok"]:
            print(f"  ✓ {label:18} {result['rows']:>4} rows, total {result['total']:,}")
        else:
            failed += 1
            print(f"  ✗ {label:18} {result['error']}  → {result['fallback']}")
    return failed == 0

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
            }
    return out

def load_population():
    out = {}
    rings_by_kec = {}
    gj = json.load(open(os.path.join(DATA, "population.geojson"), encoding="utf-8"))
    for feat in gj["features"]:
        p = feat["properties"]
        k = norm(p["nama_kec"])
        d = out.setdefault(k, {"kota": p["nama_kab"], "population": 0, "area_km2": 0.0})
        d["population"] += p["jumlah_penduduk"]
        d["area_km2"] += geom_area_km2(feat["geometry"])
        g = feat["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        rings_by_kec.setdefault(k, []).extend(rings[0] for rings in polys)
    return out, rings_by_kec

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

def build():
    crime = load_crime()
    pop, rings_by_kec = load_population()
    lights = load_lights(rings_by_kec)
    rows = []
    for k, c in sorted(crime.items(), key=lambda kv: -kv[1]["street_crime"]):
        if k not in pop:
            print(f"ERROR: kecamatan {c['kecamatan']} missing from population data", file=sys.stderr)
            sys.exit(1)
        p = pop[k]
        l = lights.get(k, {"lamp_count": 0, "lamp_watt": 0})
        area = p["area_km2"]
        rows.append({
            "kecamatan": c["kecamatan"],
            "kota": p["kota"],
            "crime_total": c["crime_total"],
            "street_crime": c["street_crime"],
            "street_crime_evening": c["street_crime_evening"],
            "evening_share": round(c["street_crime_evening"] / c["street_crime"], 4) if c["street_crime"] else 0,
            "population": p["population"],
            "area_km2": round(area, 2),
            "pop_density_km2": round(p["population"] / area, 1) if area else 0,
            "lamp_count": l["lamp_count"],
            "lamps_per_km2": round(l["lamp_count"] / area, 1) if area else 0,
            "street_crime_per_100k": round(c["street_crime"] / p["population"] * 100000, 1) if p["population"] else 0,
        })
    if len(rows) != 44:
        print(f"ERROR: expected 44 kecamatan, got {len(rows)}", file=sys.stderr)
        sys.exit(1)
    out_path = os.path.join(DATA, "master_dataset.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"DONE: {len(rows)} kecamatan -> {out_path}")
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

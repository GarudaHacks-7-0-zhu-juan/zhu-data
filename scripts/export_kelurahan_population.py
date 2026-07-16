#!/usr/bin/env python3

import json, sys, time, urllib.request, urllib.parse

BASE = ("https://gis.dukcapil.kemendagri.go.id/arcgis/rest/services/"
        "AGR_VISUAL_KEL_FIX/MapServer/0/query")
FIELDS = ["no_kel", "kode_desa_spatial", "nama_kab", "nama_kec", "nama_kel",
          "jumlah_penduduk", "jumlah_kk", "pria", "wanita",
          "u0", "u5", "u10", "u15", "u20", "u25", "u30", "u35", "u40",
          "u45", "u50", "u55", "u60", "u65", "u70", "u75"]
PAGE = 100

def fetch(offset, retries=4):
    params = urllib.parse.urlencode({
        "where": "nama_prop LIKE '%JAKARTA%'",
        "outFields": ",".join(FIELDS),
        "returnGeometry": "true",
        "outSR": 4326,
        "orderByFields": "objectid",
        "resultOffset": offset,
        "resultRecordCount": PAGE,
        "f": "geojson",
    })
    req = urllib.request.Request(f"{BASE}?{params}",
                                 headers={"User-Agent": "Mozilla/5.0 (hackathon one-time export)"})
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

def main(out_path):
    feats, offset = [], 0
    while True:
        page = fetch(offset)
        feats.extend(page)
        print(f"offset {offset}: +{len(page)} (total {len(feats)})", flush=True)
        if len(page) < PAGE:
            break
        offset += PAGE
        time.sleep(0.3)
    total = sum(f["properties"].get("jumlah_penduduk") or 0 for f in feats)
    if len(feats) != 267:
        print(f"WARNING: expected 267 kelurahan, got {len(feats)} — check the where clause")
    fc = {"type": "FeatureCollection", "features": feats}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    print(f"DONE: {len(feats)} kelurahan, total population {total:,} -> {out_path}")

if __name__ == "__main__":
    main(sys.argv[1])

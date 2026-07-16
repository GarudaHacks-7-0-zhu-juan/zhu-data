#!/usr/bin/env python3

import csv, json, sys, time, urllib.request, urllib.parse

BASE = "https://jakartasatu.jakarta.go.id/server/rest/services/BINAMARGA/Data_PJU_DBM_View/FeatureServer/0/query"
FIELDS = ["ID_PJU", "WADMKK", "WADMKC", "JNSLAMPU", "DAYALAMPU", "LATITUDE", "LONGITUDE", "TAHUN", "ALAMAT"]
OUT = sys.argv[1]
PAGE = 2000

def fetch(offset, retries=4):
    params = urllib.parse.urlencode({
        "where": "1=1",
        "outFields": ",".join(FIELDS),
        "returnGeometry": "false",
        "orderByFields": "OBJECTID",
        "resultOffset": offset,
        "resultRecordCount": PAGE,
        "f": "json",
    })
    req = urllib.request.Request(f"{BASE}?{params}", headers={"User-Agent": "Mozilla/5.0 (hackathon one-time export)"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            if "features" in d:
                return d["features"]
            raise RuntimeError(f"unexpected response: {str(d)[:200]}")
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))

total = 0
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    offset = 0
    while True:
        feats = fetch(offset)
        for feat in feats:
            w.writerow({k: feat["attributes"].get(k) for k in FIELDS})
        total += len(feats)
        print(f"offset {offset}: +{len(feats)} (total {total})", flush=True)
        if len(feats) < PAGE:
            break
        offset += PAGE
        time.sleep(0.3)
print(f"DONE: {total} records -> {OUT}", flush=True)

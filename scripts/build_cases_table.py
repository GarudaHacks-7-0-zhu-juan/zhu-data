#!/usr/bin/env python3

import csv, json, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
ENDPOINT = ("https://wabi-south-east-asia-b-primary-api.analysis.windows.net"
            "/public/reports/querydata?synchronous=true")
RKEY = "dfe13d87-1d2b-421c-be7b-bf6edd2e1f9d"
DATE_ENTITY = "LocalDateTable_12add86b-6ca9-411c-b150-5826b6bdf752"

WINDOWS = ["05:00-07:59", "08:00-11:59", "12:00-14:59", "15:00-17:59",
           "18:00-21:59", "22:00-23:59", "00:00-04:59", "Korban Tidak Tahu"]

def lit(v):
    return {"Literal": {"Value": "'" + str(v).replace("'", "''") + "'"}}

def build_query(kecamatan, window=None):
    return {"version": "1.0.0", "cancelQueries": [], "modelId": 5179165,
      "queries": [{"ApplicationContext": {"DatasetId": "edcee19b-e8fc-4f8a-bdc1-6a3410863eed",
                    "Sources": [{"ReportId": "ec40848e-ee84-4f0e-9d4b-5a1016130676"}]},
        "Query": {"Commands": [{"SemanticQueryDataShapeCommand": {"Query": {"Version": 2,
          "From": [{"Name": "v1", "Entity": "VIEW_DATA_LP", "Type": 0},
                   {"Name": "j", "Entity": "Jenis Kejahatan", "Type": 0},
                   {"Name": "l", "Entity": DATE_ENTITY, "Type": 0},
                   {"Name": "w", "Entity": "Waktu Kejahatan", "Type": 0}],
          "Select": [{"Column": {"Expression": {"SourceRef": {"Source": "j"}}, "Property": "jenis_kejahatan"},
                      "Name": "jenis", "NativeReferenceName": "jenis"},
                     {"Measure": {"Expression": {"SourceRef": {"Source": "v1"}}, "Property": "Jumlah_CT"},
                      "Name": "ct", "NativeReferenceName": "ct"}],
          "Where": [
            {"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "v1"}}, "Property": "Nama_Propinsi"}}], "Values": [[lit("DKI JAKARTA")]]}}},
            {"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "l"}}, "Property": "Year"}}], "Values": [[{"Literal": {"Value": "2026L"}}]]}}},
            {"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "v1"}}, "Property": "Nama_Kecamatan"}}], "Values": [[lit(kecamatan)]]}}},
          ] + ([{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "w"}}, "Property": "Waktu_Kejadian_Update"}}], "Values": [[lit(window)]]}}}] if window is not None else [])},
          "Binding": {"Primary": {"Groupings": [{"Projections": [0, 1]}]},
                      "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": 2000}}}, "Version": 1}}}]}}]}

def run(payload, retries=4):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-PowerBI-ResourceKey": RKEY,
        "User-Agent": "Mozilla/5.0 (hackathon reconstructed-cases build)"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))

def parse(resp):
    dm = resp["results"][0]["result"]["data"]["dsr"]["DS"][0]["PH"][0]["DM0"]
    prev, out = [], []
    for it in dm:
        c = it.get("C", []); rep = it.get("R", 0); row = []; ci = 0
        for col in range(2):
            if rep & (1 << col):
                row.append(prev[col] if col < len(prev) else None)
            else:
                row.append(c[ci] if ci < len(c) else None); ci += 1
        prev = row
        if row[0] and isinstance(row[1], (int, float)) and row[1] > 0:
            out.append((row[0], int(row[1])))
    return out

def kecamatan_list():
    path = os.path.join(DATA, "pusiknas_crime_kecamatan.csv")
    return [r["kecamatan"] for r in csv.DictReader(open(path, encoding="utf-8"))]

def main():
    kecs = kecamatan_list()
    out_path = os.path.join(DATA, "pusiknas_cases_dki_2026.csv")
    tmp = out_path + ".tmp"
    total_cases = 0; done = 0; jobs = len(kecs) * len(WINDOWS)
    jobs = len(kecs) * (len(WINDOWS) + 1)
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kecamatan", "jenis_kejahatan", "time_window", "year"])
        for kec in kecs:
            windowed = {}
            for window in WINDOWS:
                done += 1
                try:
                    rows = parse(run(build_query(kec, window)))
                except Exception as e:
                    print(f"  [{done}/{jobs}] FAIL {kec}/{window}: {e}", flush=True)
                    continue
                for jenis, count in rows:
                    for _ in range(count):
                        w.writerow([kec, jenis, window, 2026])
                    windowed[jenis] = windowed.get(jenis, 0) + count
                    total_cases += count
                time.sleep(0.2)

            done += 1
            try:
                totals = parse(run(build_query(kec)))
                for jenis, count in totals:
                    missing = count - windowed.get(jenis, 0)
                    for _ in range(missing):
                        w.writerow([kec, jenis, "(tidak tercatat)", 2026])
                    total_cases += max(missing, 0)
            except Exception as e:
                print(f"  [{done}/{jobs}] FAIL {kec}/TOTAL: {e}", flush=True)
            print(f"  [{done}/{jobs}] {kec}: {total_cases:,} cases so far", flush=True)
            time.sleep(0.2)
    os.replace(tmp, out_path)
    print(f"DONE: {total_cases:,} case-rows -> {out_path}")
    print("(reconstructed from counts — not raw police records)")

if __name__ == "__main__":
    main()

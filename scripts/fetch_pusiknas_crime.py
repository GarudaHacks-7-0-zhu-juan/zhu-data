#!/usr/bin/env python3

import json, os, sys, urllib.request

ENDPOINT = ("https://wabi-south-east-asia-b-primary-api.analysis.windows.net"
            "/public/reports/querydata?synchronous=true")

RESOURCE_KEY = "dfe13d87-1d2b-421c-be7b-bf6edd2e1f9d"

def run_query(payload_path):
    body = open(payload_path, "rb").read()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-PowerBI-ResourceKey": RESOURCE_KEY,
        "Origin": "https://app.powerbi.com",
        "User-Agent": "Mozilla/5.0 (hackathon research; one-time snapshot)",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def parse_rows(resp):
    ds = resp["results"][0]["result"]["data"]["dsr"]["DS"][0]
    dm = ds["PH"][0]["DM0"]
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

if __name__ == "__main__":
    payload = sys.argv[1] if len(sys.argv) > 1 else\
        os.path.join(os.path.dirname(__file__), "queries", "pusiknas_query_kecamatan_dki.json")
    resp = run_query(payload)
    for row in parse_rows(resp):
        print(row)

#!/usr/bin/env python3

import csv, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = DATA
QUERIES = os.path.join(HERE, "queries")
sys.path.insert(0, HERE)
from fetch_pusiknas_crime import run_query, parse_rows

KECAMATAN_PARTS = {
    "crime_total":          ("pusiknas_query_kecamatan_dki.json", 40),
    "street_crime":         ("pusiknas_query_streetcrime_kecamatan.json", 40),
    "street_crime_evening": ("pusiknas_query_streetcrime_kec_evening.json", 35),
}

STANDALONE = {
    "jenis_jakarta": ("pusiknas_query_jenis_jakarta.json",
                      ["jenis_kejahatan", "crime_total"], 80),
    "waktu_jakarta": ("pusiknas_query_waktu_jakarta.json",
                      ["waktu_kejadian", "crime_total"], 6),
}

norm = lambda s: re.sub(r"[^A-Z]", "", str(s).upper())

def clean(rows):
    return [r for r in rows
            if r and r[0] and str(r[0]).strip() and isinstance(r[1], (int, float))]

def atomic_write(out_path, header, rows):
    fd, tmp = tempfile.mkstemp(dir=OUT, suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, out_path)

def refresh_kecamatan():
    out_path = os.path.join(OUT, "pusiknas_crime_kecamatan.csv")
    try:
        parts = {}
        for col, (payload, min_rows) in KECAMATAN_PARTS.items():
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
        atomic_write(out_path, ["kecamatan", "crime_total", "street_crime",
                                "street_crime_evening"], combined)
        return {"ok": True, "rows": len(combined),
                "total": sum(r[1] for r in combined)}
    except Exception as e:
        kept = "kept previous snapshot" if os.path.exists(out_path) else "NO snapshot exists"
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "fallback": kept}

def refresh_standalone(name):
    payload, cols, min_rows = STANDALONE[name]
    out_path = os.path.join(OUT, f"pusiknas_{name}.csv")
    try:
        rows = clean(parse_rows(run_query(os.path.join(QUERIES, payload))))
        if len(rows) < min_rows:
            raise ValueError(f"only {len(rows)} rows (expected >= {min_rows}) — refusing to overwrite")
        if sum(r[1] for r in rows) <= 0:
            raise ValueError("zero total — refusing to overwrite")
        atomic_write(out_path, cols, [r[:len(cols)] for r in rows])
        return {"ok": True, "rows": len(rows), "total": sum(r[1] for r in rows)}
    except Exception as e:
        kept = "kept previous snapshot" if os.path.exists(out_path) else "NO snapshot exists"
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "fallback": kept}

def main():
    os.makedirs(OUT, exist_ok=True)
    targets = sys.argv[1:] or ["kecamatan"] + list(STANDALONE)
    failed = 0
    for name in targets:
        if name == "kecamatan":
            r = refresh_kecamatan()
        elif name in STANDALONE:
            r = refresh_standalone(name)
        else:
            print(f"  unknown target '{name}' — options: kecamatan, {', '.join(STANDALONE)}")
            continue
        if r["ok"]:
            print(f"  ✓ {name:16} {r['rows']:>4} rows, total {r['total']:,}")
        else:
            failed += 1
            print(f"  ✗ {name:16} {r['error']}  → {r['fallback']}")
    print(f"\n{'All snapshots refreshed.' if not failed else str(failed) + ' target(s) failed — previous CSVs remain the latest working data.'}")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from fetch_pusiknas_crime import run_query, parse_rows

STREET_CRIME = [
    "Pencurian Dengan Kekerasan",
    "Pencurian Dengan Pemberatan",
    "Pencurian Biasa", "Pencurian Ringan", "Percobaan Pencurian",
    "Curanmor",
    "Penganiayaan",
    "Pengeroyokan",
    "Perampasan",
    "Senjata Tajam",
    "Pemerasan", "Pengancaman",
    "Perkosaan", "Cabul", "Persetubuhan Terhadap Anak", "Kekerasan Seksual",
    "Penculikan", "Penyekapan",
    "Pembunuhan", "Kejahatan Terhadap Jiwa", "Mengakibatkan Orang Mati",
    "Mengakibatkan Orang Luka",
    "Premanisme", "Perkelahian",
]

def is_street(name):
    n = (name or "").lower()
    return any(k.lower() in n for k in STREET_CRIME)

if __name__ == "__main__":
    payload = sys.argv[1] if len(sys.argv) > 1 else\
        os.path.join(os.path.dirname(__file__), "queries", "pusiknas_query_jenis_jakarta.json")
    rows = [(r[0], r[1]) for r in parse_rows(run_query(payload))
            if r[0] is not None and isinstance(r[1], (int, float))]
    street = [(n, v) for n, v in rows if is_street(n)]
    other  = [(n, v) for n, v in rows if not is_street(n)]
    st, ot = sum(v for _, v in street), sum(v for _, v in other)
    print(f"DKI Jakarta crime-type breakdown (rolling 2026 YTD)\n")
    print(f"STREET crime (heatmap-relevant): {st:,} cases across {len(street)} types")
    for n, v in sorted(street, key=lambda x: -x[1]):
        print(f"  {v:>6,}  {n}")
    print(f"\nNON-STREET (excluded from heatmap): {ot:,} cases across {len(other)} types")
    for n, v in sorted(other, key=lambda x: -x[1])[:10]:
        print(f"  {v:>6,}  {n}")
    print(f"  ... (+{max(0,len(other)-10)} more)")
    print(f"\nStreet share of total: {st/(st+ot)*100:.0f}%")

import json, os

STREET = [
    "Pencurian Dengan Pemberatan ( Curat )", "Pencurian Biasa", "Pencurian Ringan",
    "Percobaan Pencurian", "Curanmor R-2", "Penganiayaan", "Penganiayaan Berat ( Anirat )",
    "Pengeroyokan", "Perampasan ( Premanisme )",
    "Kejahatan Terkait Senjata Tajam ( Sajam ) ( Premanisme )",
    "Pemerasan", "Pemerasan Dan Pengancaman", "Pengancaman",
    "Pencurian Dengan Kekerasan ( Curas )", "Perkosaan", "Cabul",
    "Persetubuhan Terhadap Anak / Cabul Terhadap Anak", "Kekerasan Seksual (KDRT)",
    "Penculikan", "Penyekapan", "Pembunuhan", "Kejahatan Terhadap Jiwa Orang / Pembunuhan",
    "Mengakibatkan Orang Mati", "Mengakibatkan Orang Luka", "Perkelahian Pelajar / Mahasiswa",
]

def lit(v):
    return {"Literal": {"Value": "'" + v.replace("'", "''") + "'"}}

q = {
  "version": "1.0.0",
  "queries": [{
    "Query": {"Commands": [{
      "SemanticQueryDataShapeCommand": {
        "Query": {
          "Version": 2,
          "From": [
            {"Name": "v1", "Entity": "VIEW_DATA_LP", "Type": 0},
            {"Name": "j", "Entity": "Jenis Kejahatan", "Type": 0},
            {"Name": "l", "Entity": "LocalDateTable_12add86b-6ca9-411c-b150-5826b6bdf752", "Type": 0},
          ],
          "Select": [
            {"Column": {"Expression": {"SourceRef": {"Source": "v1"}}, "Property": "Nama_Kecamatan"},
             "Name": "VIEW_DATA_LP.Nama_Kecamatan", "NativeReferenceName": "kec"},
            {"Measure": {"Expression": {"SourceRef": {"Source": "v1"}}, "Property": "Jumlah_CT"},
             "Name": "VIEW_DATA_LP.Jumlah_CT", "NativeReferenceName": "Jumlah_CT"},
          ],
          "Where": [
            {"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "v1"}}, "Property": "Nama_Propinsi"}}], "Values": [[lit("DKI JAKARTA")]]}}},
            {"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "l"}}, "Property": "Year"}}], "Values": [[{"Literal": {"Value": "2026L"}}]]}}},
            {"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "j"}}, "Property": "jenis_kejahatan"}}], "Values": [[lit(s)] for s in STREET]}}},
          ],
          "OrderBy": [{"Direction": 2, "Expression": {"Measure": {"Expression": {"SourceRef": {"Source": "v1"}}, "Property": "Jumlah_CT"}}}],
        },
        "Binding": {"Primary": {"Groupings": [{"Projections": [0, 1]}]},
                    "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": 500}}}, "Version": 1},
      }
    }]},
    "QueryId": "",
    "ApplicationContext": {"DatasetId": "edcee19b-e8fc-4f8a-bdc1-6a3410863eed", "Sources": [{"ReportId": "ec40848e-ee84-4f0e-9d4b-5a1016130676"}]},
  }],
  "cancelQueries": [], "modelId": 5179165,
}
open(os.path.join(os.path.dirname(__file__), "queries", "pusiknas_query_streetcrime_kecamatan.json"), "w").write(json.dumps(q))
print("built with", len(STREET), "street types")

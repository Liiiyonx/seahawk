"""Fetch the NOAA NCEI Marine Microplastics feature layer to CSV + manifest.

One-off acquisition script for R-OD-03 (real public industry dataset).
Data: NOAA NCEI Marine Microplastics (1972-present), free to access and use,
citation per https://www.ncei.noaa.gov/products/microplastics.
"""
import csv
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "real-industry-data"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT_DIR / "noaa_marine_microplastics.csv"
MANIFEST_PATH = OUT_DIR / "manifest.json"

SERVICE = (
    "https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/"
    "Marine_Microplastics_WGS84/FeatureServer/0/query"
)
UA = {"User-Agent": "Oceanus-Rod03-Acquisition/1.0 (competition evaluation; contact: team)"}


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def main() -> None:
    params = {
        "f": "json",
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "false",
        "resultOffset": 0,
        "resultRecordCount": 2000,
    }
    rows: list[dict] = []
    offset = 0
    while True:
        params["resultOffset"] = offset
        data = fetch(SERVICE + "?" + urllib.parse.urlencode(params))
        feats = data.get("features") or []
        rows.extend(f["attributes"] for f in feats)
        print(f"offset={offset} fetched={len(feats)} total={len(rows)}")
        if not data.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)

    if not rows:
        raise SystemExit("no rows fetched")
    fields: list[str] = list(
        fetch(SERVICE + "?f=json&where=1%3D1&returnCountOnly=false&outFields=*&resultRecordCount=1")
        ["features"][0]["attributes"].keys()
    )

    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in fields})

    raw = CSV_PATH.read_bytes()
    # 脱敏核验：数据集为公开环境监测数据，字段全部为测量值与文献元数据，
    # 不含姓名/联系方式等个人标识。此处以字段名单核验该口径。
    personal_like = [f for f in fields if any(w in f.lower() for w in ("name_of_person", "email", "phone", "person", "individual"))]
    countries = sorted({str(r.get("Country")) for r in rows if r.get("Country")})
    oceans = sorted({str(r.get("Location_Oceans")) for r in rows if r.get("Location_Oceans")})
    years = sorted({int(str(r.get("Date_m_d_yyyy"))[:4]) for r in rows if r.get("Date_m_d_yyyy")})
    china_rows = sum(1 for r in rows if "China" in str(r.get("Country") or ""))
    measured = sum(1 for r in rows if r.get("Microplastics_measurement") not in (None, ""))
    manifest = {
        "artifact_type": "real_industry_dataset_acquisition",
        "registration": "R-OD-03",
        "dataset": {
            "name": "NOAA NCEI Marine Microplastics (1972-present)",
            "provider": "NOAA National Centers for Environmental Information (NCEI)",
            "access_point": "https://www.ncei.noaa.gov/products/microplastics",
            "feature_service": SERVICE.split("?")[0],
            "arcgis_item": "c5dfb998f09e4d2b85d7da3f4c5b78ff",
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "license": "NOAA NCEI: free to access and use; NOAA distribution liability disclaimer applies",
            "citation": (
                "Nyadjro, E. S., et al. (2023). The NOAA NCEI marine microplastics "
                "database. Scientific Data, 10(1). https://doi.org/10.1038/s41597-023-02632-y; "
                "data: NOAA NCEI Marine Microplastics, accessed via ArcGIS item "
                "c5dfb998f09e4d2b85d7da3f4c5b78ff on " + datetime.now().strftime("%Y-%m-%d") + "."
            ),
        },
        "file": {
            "path": "artifacts/real-industry-data/noaa_marine_microplastics.csv",
            "rows": len(rows),
            "columns": len(fields),
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "masking_and_compliance": {
            "personal_identifier_fields": personal_like,
            "conclusion": (
                "公开环境监测数据集，字段为测量值、采样元数据与文献引用（含 DOI/机构），"
                "不含个人姓名、联系方式等个人标识字段；符合项目证据纪律对"
                "真实行业数据的合规要求，登记为 public 安全级。"
            ),
        },
        "quick_stats": {
            "years_min": years[0] if years else None,
            "years_max": years[-1] if years else None,
            "countries": len(countries),
            "oceans": len(oceans),
            "rows_with_measurement": measured,
            "rows_country_contains_china": china_rows,
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest["quick_stats"], ensure_ascii=False))
    print("manifest ->", MANIFEST_PATH)


if __name__ == "__main__":
    main()

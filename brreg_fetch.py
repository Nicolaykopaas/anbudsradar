"""
Brønnøysundregisteret lead-target fetcher: small businesses (1-20 ansatte) in
Trøndelag that have a registered email address, ready to cold-email with a
Doffin lead as a teaser.

No API key needed - data.brreg.no/enhetsregisteret is a public, unauthenticated
API. Only ~18% of small Trøndelag businesses have epostadresse filled in
(checked live 2026-07-18), so this script keeps only those - no website
scraping fallback for now.

Usage:
    python brreg_fetch.py
"""

import json
import time

import requests

BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
PAGE_SIZE = 100

MIN_ANSATTE = 1
MAX_ANSATTE = 20

# All 38 Trøndelag kommunenummer (fylkenummer 50), confirmed live via
# data.brreg.no/enhetsregisteret/api/kommuner on 2026-07-18.
TRONDELAG_KOMMUNER = [
    "5001", "5006", "5007", "5014", "5020", "5021", "5022", "5025", "5026",
    "5027", "5028", "5029", "5031", "5032", "5033", "5034", "5035", "5036",
    "5037", "5038", "5041", "5042", "5043", "5044", "5045", "5046", "5047",
    "5049", "5052", "5053", "5054", "5055", "5056", "5057", "5058", "5059",
    "5060", "5061",
]


def fetch_kommune(kommunenummer: str) -> list[dict]:
    """Fetch all matching units for a single kommune. Per-kommune keeps each
    result set well under the API's ~10000 deep-pagination limit."""
    enheter: list[dict] = []
    page = 0
    while True:
        params = {
            "kommunenummer": kommunenummer,
            "fraAntallAnsatte": MIN_ANSATTE,
            "tilAntallAnsatte": MAX_ANSATTE,
            "size": PAGE_SIZE,
            "page": page,
        }
        resp = requests.get(BASE_URL, params=params, headers={"Accept": "application/json"}, timeout=30)
        if resp.status_code == 429:
            print("    Rate-limited (429), venter 10s...")
            time.sleep(10)
            continue
        resp.raise_for_status()
        data = resp.json()
        page_enheter = data.get("_embedded", {}).get("enheter", [])
        enheter.extend(page_enheter)

        total_pages = data.get("page", {}).get("totalPages", 1)
        page += 1
        if page >= total_pages or not page_enheter:
            break
        time.sleep(0.2)

    return enheter


def fetch_all() -> list[dict]:
    enheter: list[dict] = []
    for kommunenummer in TRONDELAG_KOMMUNER:
        kommune_enheter = fetch_kommune(kommunenummer)
        enheter.extend(kommune_enheter)
        print(f"  kommune {kommunenummer}: +{len(kommune_enheter)} (totalt sett {len(enheter)})")
    return enheter


def main() -> None:
    print(f"Henter smabedrifter ({MIN_ANSATTE}-{MAX_ANSATTE} ansatte) i {len(TRONDELAG_KOMMUNER)} Trondelag-kommuner ...")
    all_enheter = fetch_all()
    print(f"\nTotalt {len(all_enheter)} enheter hentet.")

    with open("brreg_raw.json", "w", encoding="utf-8") as f:
        json.dump(all_enheter, f, ensure_ascii=False, indent=2)

    with_email = [e for e in all_enheter if e.get("epostadresse")]
    print(f"Herav {len(with_email)} med epostadresse utfylt ({100 * len(with_email) / max(len(all_enheter), 1):.0f}%).")

    try:
        import pandas as pd
    except ImportError:
        print("pandas mangler - kjor: pip install pandas")
        return

    rows = []
    for e in with_email:
        addr = e.get("forretningsadresse") or {}
        naering = e.get("naeringskode1") or {}
        rows.append({
            "orgnr": e.get("organisasjonsnummer"),
            "navn": e.get("navn"),
            "bransje": naering.get("beskrivelse"),
            "naeringskode": naering.get("kode"),
            "kommune": addr.get("kommune"),
            "poststed": addr.get("poststed"),
            "adresse": ", ".join(addr.get("adresse") or []),
            "antall_ansatte": e.get("antallAnsatte"),
            "epost": e.get("epostadresse"),
            "telefon": e.get("telefon"),
            "mobil": e.get("mobil"),
            "hjemmeside": e.get("hjemmeside"),
        })

    df = pd.DataFrame(rows)
    csv_path = "brreg_trondelag_smabedrifter.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"CSV lagret til {csv_path} ({len(df)} rader).")


if __name__ == "__main__":
    main()

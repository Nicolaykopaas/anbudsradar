"""
Brønnøysundregisteret lead-target fetcher: small businesses (1-20 ansatte)
nationwide that have a registered email address, ready to cold-email with a
Doffin lead as a teaser.

No API key needed - data.brreg.no/enhetsregisteret is a public, unauthenticated
API. Only ~30% of small businesses have epostadresse filled in (checked live
against Trøndelag on 2026-07-18), so this script keeps only those - no
website scraping fallback for now.

Fetches kommune-by-kommune (not one big nationwide query) because the API
rejects deep pagination past ~10000 results for a single query - no single
kommune comes close to that.

Usage:
    python brreg_fetch.py
"""

import json
import time

import requests

BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
KOMMUNER_URL = "https://data.brreg.no/enhetsregisteret/api/kommuner"
PAGE_SIZE = 100

MIN_ANSATTE = 1
MAX_ANSATTE = 20


def fetch_all_kommunenumre() -> list[str]:
    resp = requests.get(KOMMUNER_URL, params={"size": 500}, headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    kommuner = resp.json().get("_embedded", {}).get("kommuner", [])
    return [k["nummer"] for k in kommuner if k.get("nummer")]


SAFE_RESULT_LIMIT = 9000  # stay clear of the API's ~10000 deep-pagination ceiling


def count_matches(kommunenummer: str, fra: int, til: int) -> int:
    params = {
        "kommunenummer": kommunenummer,
        "fraAntallAnsatte": fra,
        "tilAntallAnsatte": til,
        "size": 1,
        "page": 0,
    }
    resp = requests.get(BASE_URL, params=params, headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("page", {}).get("totalElements", 0)


def fetch_range(kommunenummer: str, fra: int, til: int) -> list[dict]:
    """Fetch all units in [fra, til] ansatte for one kommune, paginating.
    Caller is responsible for keeping the range small enough to stay under
    the API's deep-pagination ceiling (see fetch_kommune)."""
    enheter: list[dict] = []
    page = 0
    while True:
        params = {
            "kommunenummer": kommunenummer,
            "fraAntallAnsatte": fra,
            "tilAntallAnsatte": til,
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


def fetch_kommune(kommunenummer: str, fra: int = MIN_ANSATTE, til: int = MAX_ANSATTE) -> list[dict]:
    """Fetch all matching units for a single kommune, splitting the ansatte
    range further (binary-search style) whenever a bucket would exceed the
    API's deep-pagination ceiling. Needed for a handful of very large
    kommuner (e.g. Oslo has >10000 businesses with 1-20 ansatte alone)."""
    total = count_matches(kommunenummer, fra, til)
    if total <= SAFE_RESULT_LIMIT or fra >= til:
        return fetch_range(kommunenummer, fra, til)

    mid = (fra + til) // 2
    return fetch_kommune(kommunenummer, fra, mid) + fetch_kommune(kommunenummer, mid + 1, til)


def fetch_all(kommunenumre: list[str]) -> list[dict]:
    enheter: list[dict] = []
    for i, kommunenummer in enumerate(kommunenumre, 1):
        kommune_enheter = fetch_kommune(kommunenummer)
        enheter.extend(kommune_enheter)
        print(f"  [{i}/{len(kommunenumre)}] kommune {kommunenummer}: +{len(kommune_enheter)} (totalt sett {len(enheter)})")
    return enheter


def main() -> None:
    print("Henter liste over alle norske kommuner ...")
    kommunenumre = fetch_all_kommunenumre()
    print(f"Fant {len(kommunenumre)} kommuner.")

    print(f"Henter smabedrifter ({MIN_ANSATTE}-{MAX_ANSATTE} ansatte) nasjonalt ...")
    all_enheter = fetch_all(kommunenumre)
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
    csv_path = "brreg_smabedrifter.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"CSV lagret til {csv_path} ({len(df)} rader).")


if __name__ == "__main__":
    main()

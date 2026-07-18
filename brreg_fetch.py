"""
Brønnøysundregisteret lead-target fetcher: small and medium businesses (SMB)
nationwide that have a registered email address, ready to cold-email with a
Doffin lead as a teaser.

No API key needed - data.brreg.no/enhetsregisteret is a public, unauthenticated
API. Only ~30% of small businesses have epostadresse filled in (checked live
against Trøndelag on 2026-07-18), so this script keeps only those - no
website scraping fallback for now.

Fetches kommune-by-kommune (not one big nationwide query) because the API
rejects deep pagination past ~10000 results for a single query - no single
kommune comes close to that.

The ansatte (employee count) range is configurable via env vars, so the
small-business band (1-20) and the medium-business band (21-100) can be
fetched as separate runs without re-doing already-completed work - each
range gets its own checkpoint/output files, merged afterwards with
merge_brreg_ranges.py.

Usage:
    python brreg_fetch.py                                    # default 1-20
    BRREG_MIN_ANSATTE=21 BRREG_MAX_ANSATTE=100 python brreg_fetch.py
"""

import json
import os
import time

import requests

BASE_URL = "https://data.brreg.no/enhetsregisteret/api/enheter"
KOMMUNER_URL = "https://data.brreg.no/enhetsregisteret/api/kommuner"
ORG_FORMER_URL = "https://data.brreg.no/enhetsregisteret/api/organisasjonsformer"
PAGE_SIZE = 100

MIN_ANSATTE = int(os.environ.get("BRREG_MIN_ANSATTE", 1))
MAX_ANSATTE = int(os.environ.get("BRREG_MAX_ANSATTE", 20))
RANGE_SUFFIX = f"{MIN_ANSATTE}-{MAX_ANSATTE}"
CHECKPOINT_PATH = f"brreg_checkpoint_{RANGE_SUFFIX}.jsonl"

# tilAntallAnsatte/fraAntallAnsatte only accept 0, 4 (til) / 0, 1 (fra), or any
# value > 4 - so the [1,4] band can never be split further by ansatte alone.
# Falls back to organisasjonsform, then naeringskode (2-digit division), for
# the handful of large kommuner where even [1,4] alone exceeds the API's
# deep-pagination ceiling (e.g. Oslo: 17708 units with 1-4 ansatte).
SAFE_RESULT_LIMIT = 9000


def get_with_retry(url: str, params: dict, max_retries: int = 5):
    """GET with retry/backoff for both HTTP 429 and transient network errors
    (connection resets etc. - seen live on long nationwide runs)."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=30)
        except requests.exceptions.RequestException as e:
            if attempt == max_retries:
                raise
            wait = min(30, 2 ** attempt)
            print(f"    Nettverksfeil ({e.__class__.__name__}), forsok {attempt}/{max_retries}, venter {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code == 429:
            print("    Rate-limited (429), venter 10s...")
            time.sleep(10)
            continue

        resp.raise_for_status()
        return resp

    raise RuntimeError(f"Ga opp etter {max_retries} forsok mot {url}")


def fetch_all_kommunenumre() -> list[str]:
    resp = get_with_retry(KOMMUNER_URL, {"size": 500})
    kommuner = resp.json().get("_embedded", {}).get("kommuner", [])
    return [k["nummer"] for k in kommuner if k.get("nummer")]


def fetch_all_organisasjonsformer() -> list[str]:
    resp = get_with_retry(ORG_FORMER_URL, {"size": 100})
    former = resp.json().get("_embedded", {}).get("organisasjonsformer", [])
    return [f["kode"] for f in former if f.get("kode")]


def count_matches(params: dict) -> int:
    resp = get_with_retry(BASE_URL, {**params, "size": 1, "page": 0})
    return resp.json().get("page", {}).get("totalElements", 0)


def fetch_range(params: dict, max_pages: int | None = None) -> list[dict]:
    """Paginate through results for a fully-specified query, stopping early
    at max_pages if given (used to avoid the API's ~10000 deep-pagination
    ceiling for buckets we've given up trying to split further)."""
    enheter: list[dict] = []
    page = 0
    while True:
        resp = get_with_retry(BASE_URL, {**params, "size": PAGE_SIZE, "page": page})
        data = resp.json()
        page_enheter = data.get("_embedded", {}).get("enheter", [])
        enheter.extend(page_enheter)

        total_pages = data.get("page", {}).get("totalPages", 1)
        page += 1
        if page >= total_pages or not page_enheter or (max_pages and page >= max_pages):
            break
        time.sleep(0.2)

    return enheter


def fetch_bucket(params: dict, org_former: list[str]) -> list[dict]:
    total = count_matches(params)
    if total <= SAFE_RESULT_LIMIT:
        return fetch_range(params)

    fra, til = params["fraAntallAnsatte"], params["tilAntallAnsatte"]
    if fra <= 4 < til:
        # split at the only valid boundary inside [1,20]: [1,4] and [5,20]
        return (fetch_bucket({**params, "tilAntallAnsatte": 4}, org_former)
                + fetch_bucket({**params, "fraAntallAnsatte": 5}, org_former))
    if fra > 4 and fra != til:
        mid = max(5, (fra + til) // 2)
        if mid < til:
            return (fetch_bucket({**params, "tilAntallAnsatte": mid}, org_former)
                    + fetch_bucket({**params, "fraAntallAnsatte": mid + 1}, org_former))

    # Ansatte-range is atomic (either exactly [1,4] or a single value >4) but
    # still too big - split by organisasjonsform. If even that isn't enough
    # (rare - e.g. Oslo's ~14500 AS-selskaper with 1-4 ansatte), accept a
    # truncated first page for that specific bucket rather than drilling
    # down further (naeringskode-level splitting was tried and is too slow
    # to run nationally in reasonable time) and flag it clearly.
    if "organisasjonsform" not in params:
        results = []
        for form in org_former:
            results.extend(fetch_bucket({**params, "organisasjonsform": form}, org_former))
        return results

    print(f"    ADVARSEL: {total} treff for {params} - for stort til å dele opp mer, henter kun forste {SAFE_RESULT_LIMIT}.")
    return fetch_range(params, max_pages=SAFE_RESULT_LIMIT // PAGE_SIZE)


def load_checkpoint() -> tuple[list[dict], set[str]]:
    """Resume from brreg_checkpoint.jsonl if a previous run was interrupted -
    one JSON line per completed kommune: {"kommunenummer": ..., "enheter": [...]}"""
    if not os.path.exists(CHECKPOINT_PATH):
        return [], set()

    enheter: list[dict] = []
    done: set[str] = set()
    with open(CHECKPOINT_PATH, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            enheter.extend(record["enheter"])
            done.add(record["kommunenummer"])
    return enheter, done


def fetch_all(kommunenumre: list[str], org_former: list[str]) -> list[dict]:
    enheter, done = load_checkpoint()
    if done:
        print(f"  Gjenopptar: {len(done)} kommuner allerede hentet fra tidligere kjoring ({len(enheter)} enheter).")

    with open(CHECKPOINT_PATH, "a", encoding="utf-8") as checkpoint_file:
        for i, kommunenummer in enumerate(kommunenumre, 1):
            if kommunenummer in done:
                continue
            base_params = {"kommunenummer": kommunenummer, "fraAntallAnsatte": MIN_ANSATTE, "tilAntallAnsatte": MAX_ANSATTE}
            kommune_enheter = fetch_bucket(base_params, org_former)
            enheter.extend(kommune_enheter)
            checkpoint_file.write(json.dumps({"kommunenummer": kommunenummer, "enheter": kommune_enheter}, ensure_ascii=False) + "\n")
            checkpoint_file.flush()
            print(f"  [{i}/{len(kommunenumre)}] kommune {kommunenummer}: +{len(kommune_enheter)} (totalt sett {len(enheter)})")
    return enheter


def main() -> None:
    print("Henter liste over alle norske kommuner ...")
    kommunenumre = fetch_all_kommunenumre()
    print(f"Fant {len(kommunenumre)} kommuner.")

    org_former = fetch_all_organisasjonsformer()

    print(f"Henter bedrifter ({MIN_ANSATTE}-{MAX_ANSATTE} ansatte) nasjonalt ...")
    all_enheter = fetch_all(kommunenumre, org_former)
    print(f"\nTotalt {len(all_enheter)} enheter hentet.")

    with open(f"brreg_raw_{RANGE_SUFFIX}.json", "w", encoding="utf-8") as f:
        json.dump(all_enheter, f, ensure_ascii=False, indent=2)

    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)  # full run succeeded - don't resume stale data next time

    # A business can appear twice across kommune-by-kommune fetches if its
    # forretningsadresse and postadresse are in different kommuner (the
    # kommunenummer filter matches either address) - keep one per orgnr.
    seen_orgnr = set()
    deduped = []
    for e in all_enheter:
        orgnr = e.get("organisasjonsnummer")
        if orgnr in seen_orgnr:
            continue
        seen_orgnr.add(orgnr)
        deduped.append(e)
    if len(deduped) < len(all_enheter):
        print(f"Fjernet {len(all_enheter) - len(deduped)} duplikater (samme orgnr i flere kommunesok).")
    all_enheter = deduped

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
        orgform = e.get("organisasjonsform") or {}
        rows.append({
            "orgnr": e.get("organisasjonsnummer"),
            "navn": e.get("navn"),
            "bransje": naering.get("beskrivelse"),
            "naeringskode": naering.get("kode"),
            "kommune": addr.get("kommune"),
            "kommunenummer": addr.get("kommunenummer"),
            "poststed": addr.get("poststed"),
            "postnummer": addr.get("postnummer"),
            "adresse": ", ".join(addr.get("adresse") or []),
            "antall_ansatte": e.get("antallAnsatte"),
            "organisasjonsform": orgform.get("kode"),
            "stiftelsesdato": e.get("stiftelsesdato"),
            "registreringsdato": e.get("registreringsdatoEnhetsregisteret"),
            "epost": e.get("epostadresse"),
            "telefon": e.get("telefon"),
            "mobil": e.get("mobil"),
            "hjemmeside": e.get("hjemmeside"),
        })

    df = pd.DataFrame(rows)
    csv_path = f"brreg_bedrifter_{RANGE_SUFFIX}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"CSV lagret til {csv_path} ({len(df)} rader).")


if __name__ == "__main__":
    main()

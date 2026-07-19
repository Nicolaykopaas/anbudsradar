"""
Doffin lead scraper: fetch active notices nationwide (all industries) from
the Doffin Public API, with full lead detail (deadline, contact, value).

Pipeline:
    1. /public/v2/search  -> ALL currently active COMPETITION notices,
       all industries, all of Norway (no publish-date window).
    2. /public/v2/download/{id} -> full eForms UBL XML per notice, parsed for:
       buyer contact (name/phone/email), tender deadline, estimated value,
       primary+additional CPV, buyer org.nr/address.

Setup:
    setx DOFFIN_API_KEY "your-subscription-key"     # Windows, restart shell after
    pip install requests pandas

Usage:
    python doffin_fetch.py
"""

import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import requests

SEARCH_URL = "https://api.doffin.no/public/v2/search"
DOWNLOAD_URL = "https://api.doffin.no/public/v2/download/{doffin_id}"
BRREG_ENHET_URL = "https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}"
API_KEY = os.environ.get("DOFFIN_API_KEY")

PAGE_SIZE = 100

NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "efac": "http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1",
}


def die(msg: str) -> None:
    print(f"FEIL: {msg}", file=sys.stderr)
    sys.exit(1)


def api_get_json(url: str, params: dict | None = None) -> dict:
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 429:
            print("  Rate-limited (429), venter 10s...")
            time.sleep(10)
            continue
        if not resp.ok:
            # RuntimeError (not sys.exit) - a bad response here must be
            # catchable by the per-notice try/except in main(). sys.exit()
            # raises SystemExit, which does NOT inherit from Exception, so
            # it would silently skip that except block and kill the whole
            # run instead of just skipping one notice.
            raise RuntimeError(f"API-kall feilet ({resp.status_code}) mot {url}: {resp.text[:500]}")
        return resp.json()


def api_get_xml(url: str) -> str:
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    while True:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 429:
            print("  Rate-limited (429), venter 10s...")
            time.sleep(10)
            continue
        if not resp.ok:
            raise RuntimeError(f"API-kall feilet ({resp.status_code}) mot {url}: {resp.text[:300]}")
        return resp.text


SEARCH_HIT_CEILING = 900  # Doffin rejects page*numHitsPerPage past 1000 - stay under it


def search_page_range(issue_from: str | None, issue_to: str | None) -> list[dict]:
    """Paginate through one date window. Caller must keep the window's
    total under SEARCH_HIT_CEILING."""
    hits: list[dict] = []
    page = 1
    while True:
        params = {
            "numHitsPerPage": PAGE_SIZE,
            "page": page,
            "sortBy": "PUBLICATION_DATE_DESC",
            "status": "ACTIVE",
            "type": "COMPETITION",
        }
        if issue_from:
            params["issueDateFrom"] = issue_from
        if issue_to:
            params["issueDateTo"] = issue_to

        payload = api_get_json(SEARCH_URL, params)
        page_hits = payload.get("hits") or []
        if isinstance(page_hits, dict):
            page_hits = [page_hits]
        hits.extend(page_hits)

        total = payload.get("numHitsTotal", len(page_hits))
        print(f"  side {page}: +{len(page_hits)} treff (totalt sett {len(hits)}/{total})")

        if len(page_hits) < PAGE_SIZE or len(hits) >= total or not page_hits:
            break
        page += 1
        time.sleep(1)

    return hits


def search_window(issue_from: date, issue_to: date) -> list[dict]:
    """Recursively split the publish-date range in half whenever a window
    would exceed Doffin's ~1000-hit deep-pagination ceiling (mirrors the
    same adaptive-splitting pattern used for Brreg's ansatte ranges)."""
    probe = api_get_json(SEARCH_URL, {
        "numHitsPerPage": 1, "page": 1, "status": "ACTIVE", "type": "COMPETITION",
        "issueDateFrom": issue_from.isoformat(), "issueDateTo": issue_to.isoformat(),
    })
    total = probe.get("numHitsTotal", 0)

    if total <= SEARCH_HIT_CEILING or issue_from >= issue_to:
        return search_page_range(issue_from.isoformat(), issue_to.isoformat())

    midt = issue_from + (issue_to - issue_from) / 2
    return (search_window(issue_from, midt) + search_window(midt + timedelta(days=1), issue_to))


def search_all() -> list[dict]:
    """Broad search across ALL currently-active notices (no fixed 7-day
    window - status=ACTIVE already means still open for bids, regardless
    of how long ago it was published). cpvCode is NOT passed server-side -
    filtering happens client-side. Splits by publish-date range as needed
    to stay under Doffin's deep-pagination ceiling."""
    # 2 years back is generous - Norwegian tenders are rarely open longer
    # than that, and status=ACTIVE already excludes anything expired.
    issue_from = date.today() - timedelta(days=730)
    hits = search_window(issue_from, date.today())

    seen_ids = set()
    deduped = []
    for h in hits:
        hid = h.get("id")
        if hid in seen_ids:
            continue
        seen_ids.add(hid)
        deduped.append(h)
    return deduped


def parse_notice_xml(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)

    def text(el, path, default=""):
        found = el.find(path, NS)
        return found.text if found is not None and found.text else default

    # Organizations referenced anywhere in the notice, keyed by ORG-xxxx id
    orgs = {}
    for org in root.findall(".//efac:Organizations/efac:Organization/efac:Company", NS):
        org_id = text(org, "cac:PartyIdentification/cbc:ID")
        name = text(org, "cac:PartyName/cbc:Name[@languageID='NOR']") or text(org, "cac:PartyName/cbc:Name")
        addr = org.find("cac:PostalAddress", NS)
        contact = org.find("cac:Contact", NS)
        orgs[org_id] = {
            "navn": name,
            "orgnr": text(org, "cac:PartyLegalEntity/cbc:CompanyID"),
            "gate": text(addr, "cbc:StreetName") if addr is not None else "",
            "poststed": text(addr, "cbc:CityName") if addr is not None else "",
            "postnr": text(addr, "cbc:PostalZone") if addr is not None else "",
            "nuts": text(addr, "cbc:CountrySubentityCode") if addr is not None else "",
            "kontakt_navn": text(contact, "cbc:Name") if contact is not None else "",
            "kontakt_telefon": text(contact, "cbc:Telephone") if contact is not None else "",
            "kontakt_epost": text(contact, "cbc:ElectronicMail") if contact is not None else "",
        }

    buyer_id = text(root, ".//cac:ContractingParty/cac:Party/cac:PartyIdentification/cbc:ID")
    buyer = orgs.get(buyer_id, {})

    value_el = root.find(".//cac:ProcurementProject/cac:RequestedTenderTotal/cbc:EstimatedOverallContractAmount", NS)

    return {
        "tittel": text(root, ".//cac:ProcurementProject/cbc:Name[@languageID='NOR']")
                  or text(root, ".//cac:ProcurementProject/cbc:Name"),
        "beskrivelse": text(root, ".//cac:ProcurementProject/cbc:Description[@languageID='NOR']")
                       or text(root, ".//cac:ProcurementProject/cbc:Description"),
        "kontrakt_type": text(root, ".//cac:ProcurementProject/cbc:ProcurementTypeCode"),
        "cpv_primaer": text(root, ".//cac:ProcurementProject/cac:MainCommodityClassification/cbc:ItemClassificationCode"),
        "cpv_tillegg": "; ".join(dict.fromkeys(
            e.text for e in root.findall(".//cac:ProcurementProject/cac:AdditionalCommodityClassification/cbc:ItemClassificationCode", NS)
            if e.text
        )),
        "estimert_verdi": value_el.text if value_el is not None else "",
        "valuta": value_el.get("currencyID") if value_el is not None else "",
        "prosedyre_type": text(root, ".//cac:TenderingProcess/cbc:ProcedureCode"),
        # Two-stage restricted procedures ("kvalifikasjonsfase") use
        # ParticipationRequestReceptionPeriod instead of a tender submission
        # deadline - fall back to it so these notices still get a usable
        # frist rather than showing "ikke oppgitt".
        "tilbudsfrist_dato": (text(root, ".//cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndDate")
                              or text(root, ".//cac:TenderingProcess/cac:ParticipationRequestReceptionPeriod/cbc:EndDate")),
        "tilbudsfrist_tid": (text(root, ".//cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndTime")
                             or text(root, ".//cac:TenderingProcess/cac:ParticipationRequestReceptionPeriod/cbc:EndTime")),
        "er_kvalifikasjonsfase": not bool(text(root, ".//cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndDate"))
                                 and bool(text(root, ".//cac:TenderingProcess/cac:ParticipationRequestReceptionPeriod/cbc:EndDate")),
        "sporsmalsfrist_dato": text(root, ".//cac:TenderingProcess/cac:AdditionalInformationRequestPeriod/cbc:EndDate"),
        "sporsmalsfrist_tid": text(root, ".//cac:TenderingProcess/cac:AdditionalInformationRequestPeriod/cbc:EndTime"),
        "oppdragsgiver": buyer.get("navn", ""),
        "oppdragsgiver_orgnr": buyer.get("orgnr", ""),
        "oppdragsgiver_adresse": ", ".join(
            p for p in [buyer.get("gate"), buyer.get("postnr"), buyer.get("poststed")] if p
        ),
        "kontakt_navn": buyer.get("kontakt_navn", ""),
        "kontakt_telefon": buyer.get("kontakt_telefon", ""),
        "kontakt_epost": buyer.get("kontakt_epost", ""),
    }


def fetch_buyer_kommunenummer(orgnr: str, cache: dict) -> tuple[str, str]:
    """Look up a buyer's forretningsadresse.kommunenummer + postnummer via
    Brreg's public, unauthenticated Enhetsregisteret API (already used by
    brreg_fetch.py - same free data source, no new dependency). Cached per
    orgnr within a run since many notices share the same buyer. Returns
    ("", "") if not found (e.g. embassies/foreign bodies or non-standard
    registrations)."""
    if not orgnr:
        return "", ""
    if orgnr in cache:
        return cache[orgnr]

    try:
        resp = requests.get(BRREG_ENHET_URL.format(orgnr=orgnr), headers={"Accept": "application/json"}, timeout=15)
        addr = resp.json().get("forretningsadresse") or {} if resp.ok else {}
        result = (addr.get("kommunenummer", ""), addr.get("postnummer", ""))
    except requests.exceptions.RequestException:
        result = ("", "")

    cache[orgnr] = result
    return result


def format_deadline(dato: str, tid: str) -> str:
    if not dato:
        return "Ikke oppgitt"
    dato_ren = dato.split("+")[0]
    tid_ren = tid.split("+")[0] if tid else ""
    return f"{dato_ren} kl. {tid_ren}" if tid_ren else dato_ren


def write_readable_summary(rows: list[dict], path: str) -> None:
    lines = [
        f"# Aktive offentlige jobber i Norge ({len(rows)} stk)",
        "",
        "Dette er offentlige jobber (anbud) som er lyst ut i Norge, uansett bransje."
        " Bedrifter kan sende inn tilbud for å få jobben. Under hver jobb ligger navnet"
        " og kontaktinfoen til personen hos oppdragsgiver som kan svare på spørsmål om den.",
        "",
    ]
    for r in rows:
        verdi = r.get("estimert_verdi")
        verdi_str = f"ca. {int(float(verdi)):,} kr".replace(",", " ") if verdi and str(verdi) != "nan" else "Ikke oppgitt"
        beskrivelse = (r.get("beskrivelse") or "").strip()
        if len(beskrivelse) > 400:
            beskrivelse = beskrivelse[:400].rsplit(" ", 1)[0] + " ..."

        lines.append(f"## {r.get('tittel', '(uten tittel)')}")
        lines.append("")
        lines.append(f"- **Hvem lyser ut jobben:** {r.get('oppdragsgiver', '')}")
        lines.append(f"- **Hvor:** {r.get('oppdragsgiver_adresse', '')}")
        lines.append(f"- **Hvor stor jobb (ca. verdi):** {verdi_str}")
        frist_label = "Frist for å melde interesse" if r.get("er_kvalifikasjonsfase") else "Frist for å sende tilbud"
        lines.append(f"- **{frist_label}:** {format_deadline(r.get('tilbudsfrist_dato', ''), r.get('tilbudsfrist_tid', ''))}")
        sporsmal = format_deadline(r.get('sporsmalsfrist_dato', ''), r.get('sporsmalsfrist_tid', ''))
        if sporsmal != "Ikke oppgitt":
            lines.append(f"- **Frist for å stille spørsmål:** {sporsmal}")
        lines.append(f"- **Kontaktperson for spørsmål:** {r.get('kontakt_navn', '')} — {r.get('kontakt_telefon', '')} — {r.get('kontakt_epost', '')}")
        lines.append(f"- **Se hele kunngjøringen:** {r.get('lenke', '')}")
        if beskrivelse:
            lines.append("")
            lines.append(f"> {beskrivelse}")
        lines.append("\n---\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    if not API_KEY:
        die("Sett miljøvariabelen DOFFIN_API_KEY med subscription-nøkkelen din først.")

    print("Steg 1: soker bredt etter ALLE aktive kunngjoringer (uansett publiseringsdato) ...")
    try:
        all_hits = search_all()
    except RuntimeError as e:
        die(str(e))  # sok-steget er reelt fatalt - uten det har vi ingenting a jobbe med
    print(f"Totalt {len(all_hits)} aktive COMPETITION-kunngjoringer.")

    with open("doffin_search_raw.json", "w", encoding="utf-8") as f:
        json.dump(all_hits, f, ensure_ascii=False, indent=2)

    try:
        import pandas as pd
    except ImportError:
        die("pandas mangler. Kjor: pip install pandas")

    # Lightweight nationwide CSV (no download calls) - for oversikt/volumsjekk.
    all_rows = [{
        "doffin_id": h.get("id"),
        "tittel": h.get("heading"),
        "oppdragsgiver": "; ".join(b.get("name", "") for b in (h.get("buyer") or [])),
        "cpv_koder": "; ".join(h.get("cpvCodes") or []),
        "estimert_verdi": (h.get("estimatedValue") or {}).get("amount"),
        "valuta": (h.get("estimatedValue") or {}).get("currencyCode"),
        "publisert_dato": h.get("publicationDate"),
        "location_id": "; ".join(h.get("locationId") or []),
        "lenke": f"https://doffin.no/notices/{h.get('id')}" if h.get("id") else "",
    } for h in all_hits]
    pd.DataFrame(all_rows).to_csv("doffin_notices_alle.csv", index=False, encoding="utf-8-sig")
    print(f"Nasjonal oversikt (alle bransjer) lagret til doffin_notices_alle.csv ({len(all_rows)} rader).")

    if not all_hits:
        print("Ingen aktive kunngjoringer funnet - ingen detaljer a hente.")
        return

    print(f"\nSteg 2: henter og parser full detalj for {len(all_hits)} treff ...")
    detailed_rows = []
    for i, h in enumerate(all_hits, 1):
        doffin_id = h.get("id")
        print(f"  [{i}/{len(all_hits)}] {doffin_id}")
        try:
            xml_text = api_get_xml(DOWNLOAD_URL.format(doffin_id=doffin_id))
            parsed = parse_notice_xml(xml_text)
        except Exception as e:
            print(f"    Klarte ikke hente/parse {doffin_id}: {e}")
            parsed = {}
        row = {"doffin_id": doffin_id, "lenke": f"https://doffin.no/notices/{doffin_id}"}
        row.update(parsed)
        detailed_rows.append(row)
        time.sleep(0.5)

    print(f"\nSteg 3: slar opp oppdragsgivers kommunenummer/postnummer (for bedre geografisk matching) ...")
    kommunenummer_cache: dict = {}
    for row in detailed_rows:
        kommunenummer, postnummer = fetch_buyer_kommunenummer(row.get("oppdragsgiver_orgnr", ""), kommunenummer_cache)
        row["oppdragsgiver_kommunenummer"] = kommunenummer
        row["oppdragsgiver_postnummer"] = postnummer
    n_med_kommunenummer = sum(1 for row in detailed_rows if row["oppdragsgiver_kommunenummer"])
    print(f"  {len(kommunenummer_cache)} unike oppdragsgivere slatt opp, {n_med_kommunenummer}/{len(detailed_rows)} kunngjoringer fikk kommunenummer.")

    df = pd.DataFrame(detailed_rows)
    csv_path = "doffin_notices_detaljert.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nDetaljert CSV lagret til {csv_path} ({len(df)} rader).")
    n_with_email = (df["kontakt_epost"] != "").sum() if "kontakt_epost" in df else 0
    print(f"Herav {n_with_email} med kontakt-epost fylt ut.")

    md_path = "doffin_leads.md"
    write_readable_summary(detailed_rows, md_path)
    print(f"Lesbar oppsummering lagret til {md_path} - apne den for et raskt overblikk.")


if __name__ == "__main__":
    main()

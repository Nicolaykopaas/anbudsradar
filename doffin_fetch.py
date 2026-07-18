"""
Doffin lead scraper: fetch bygg-og-anlegg (CPV 45xx) notices in Trøndelag from
the Doffin Public API, with full lead detail (deadline, contact, value).

Pipeline:
    1. /public/v2/search  -> broad list of active COMPETITION notices in the
       date window. cpvCode filtering is NOT trusted server-side (API likely
       wants exact 8-digit codes, not a "45" prefix) - filtered client-side
       on cpvCodes starting with "45" instead.
    2. Client-side filter on locationId == "NO060" (Trøndelag NUTS3 code,
       confirmed against live data - see doffin_search_raw.json).
    3. /public/v2/download/{id} -> full eForms UBL XML per matched notice,
       parsed for: buyer contact (name/phone/email), tender deadline,
       estimated value, primary+additional CPV, buyer org.nr/address.

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
API_KEY = os.environ.get("DOFFIN_API_KEY")

DAYS_BACK = 7
PAGE_SIZE = 100
TRONDELAG_NUTS = "NO060"

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
            die(f"API-kall feilet ({resp.status_code}) mot {url}: {resp.text[:500]}")
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
            die(f"API-kall feilet ({resp.status_code}) mot {url}: {resp.text[:300]}")
        return resp.text


def search_all(issue_date_from: str, issue_date_to: str) -> list[dict]:
    """Broad search across all notice types/CPVs in the date window.
    cpvCode is NOT passed server-side - filtering happens client-side."""
    hits: list[dict] = []
    page = 1

    while True:
        params = {
            "numHitsPerPage": PAGE_SIZE,
            "page": page,
            "sortBy": "PUBLICATION_DATE_DESC",
            "status": "ACTIVE",
            "type": "COMPETITION",
            "issueDateFrom": issue_date_from,
            "issueDateTo": issue_date_to,
        }
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


def is_cpv45(hit: dict) -> bool:
    return any(str(c).startswith("45") for c in (hit.get("cpvCodes") or []))


def is_trondelag(hit: dict) -> bool:
    return TRONDELAG_NUTS in (hit.get("locationId") or [])


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
        "tilbudsfrist_dato": text(root, ".//cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndDate"),
        "tilbudsfrist_tid": text(root, ".//cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndTime"),
        "oppdragsgiver": buyer.get("navn", ""),
        "oppdragsgiver_orgnr": buyer.get("orgnr", ""),
        "oppdragsgiver_adresse": ", ".join(
            p for p in [buyer.get("gate"), buyer.get("postnr"), buyer.get("poststed")] if p
        ),
        "kontakt_navn": buyer.get("kontakt_navn", ""),
        "kontakt_telefon": buyer.get("kontakt_telefon", ""),
        "kontakt_epost": buyer.get("kontakt_epost", ""),
    }


def format_deadline(dato: str, tid: str) -> str:
    if not dato:
        return "Ikke oppgitt"
    dato_ren = dato.split("+")[0]
    tid_ren = tid.split("+")[0] if tid else ""
    return f"{dato_ren} kl. {tid_ren}" if tid_ren else dato_ren


def write_readable_summary(rows: list[dict], path: str) -> None:
    lines = [f"# Bygg-og-anlegg-leads i Trøndelag ({len(rows)} stk)\n"]
    for r in rows:
        verdi = r.get("estimert_verdi")
        verdi_str = f"{int(float(verdi)):,} {r.get('valuta', '')}".replace(",", " ") if verdi and str(verdi) != "nan" else "Ikke oppgitt"
        beskrivelse = (r.get("beskrivelse") or "").strip()
        if len(beskrivelse) > 400:
            beskrivelse = beskrivelse[:400].rsplit(" ", 1)[0] + " ..."

        lines.append(f"## {r.get('tittel', '(uten tittel)')}")
        lines.append("")
        lines.append(f"- **Oppdragsgiver:** {r.get('oppdragsgiver', '')} (org.nr {r.get('oppdragsgiver_orgnr', '')})")
        lines.append(f"- **Adresse:** {r.get('oppdragsgiver_adresse', '')}")
        lines.append(f"- **Estimert verdi:** {verdi_str}")
        lines.append(f"- **Tilbudsfrist:** {format_deadline(r.get('tilbudsfrist_dato', ''), r.get('tilbudsfrist_tid', ''))}")
        lines.append(f"- **CPV (primær):** {r.get('cpv_primaer', '')}")
        if r.get("cpv_tillegg"):
            lines.append(f"- **CPV (tillegg):** {r.get('cpv_tillegg')}")
        lines.append(f"- **Kontakt:** {r.get('kontakt_navn', '')} — {r.get('kontakt_telefon', '')} — {r.get('kontakt_epost', '')}")
        lines.append(f"- **Lenke:** {r.get('lenke', '')}")
        if beskrivelse:
            lines.append("")
            lines.append(f"> {beskrivelse}")
        lines.append("\n---\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    if not API_KEY:
        die("Sett miljøvariabelen DOFFIN_API_KEY med subscription-nøkkelen din først.")

    today = date.today()
    issue_from = (today - timedelta(days=DAYS_BACK)).isoformat()
    issue_to = today.isoformat()

    print(f"Steg 1: soker bredt {issue_from} -> {issue_to} ...")
    all_hits = search_all(issue_from, issue_to)
    print(f"Totalt {len(all_hits)} aktive COMPETITION-kunngjoringer i vinduet.")

    with open("doffin_search_raw.json", "w", encoding="utf-8") as f:
        json.dump(all_hits, f, ensure_ascii=False, indent=2)

    cpv45_hits = [h for h in all_hits if is_cpv45(h)]
    print(f"Herav {len(cpv45_hits)} med CPV-kode som starter pa 45 (bygg og anlegg), hele Norge.")

    trondelag_hits = [h for h in cpv45_hits if is_trondelag(h)]
    print(f"Herav {len(trondelag_hits)} i Trondelag (NUTS {TRONDELAG_NUTS}).")

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
        "er_trondelag": is_trondelag(h),
        "lenke": f"https://www.doffin.no/notice/{h.get('id')}" if h.get("id") else "",
    } for h in cpv45_hits]
    pd.DataFrame(all_rows).to_csv("doffin_notices_alle_cpv45.csv", index=False, encoding="utf-8-sig")
    print(f"Nasjonal CPV45-oversikt lagret til doffin_notices_alle_cpv45.csv ({len(all_rows)} rader).")

    if not trondelag_hits:
        print("Ingen Trondelag-treff denne uka - ingen detaljer a hente.")
        return

    print(f"\nSteg 2: henter og parser full detalj for {len(trondelag_hits)} Trondelag-treff ...")
    detailed_rows = []
    for i, h in enumerate(trondelag_hits, 1):
        doffin_id = h.get("id")
        print(f"  [{i}/{len(trondelag_hits)}] {doffin_id}")
        try:
            xml_text = api_get_xml(DOWNLOAD_URL.format(doffin_id=doffin_id))
            parsed = parse_notice_xml(xml_text)
        except Exception as e:
            print(f"    Klarte ikke hente/parse {doffin_id}: {e}")
            parsed = {}
        row = {"doffin_id": doffin_id, "lenke": f"https://www.doffin.no/notice/{doffin_id}"}
        row.update(parsed)
        detailed_rows.append(row)
        time.sleep(0.5)

    df = pd.DataFrame(detailed_rows)
    csv_path = "doffin_notices_trondelag_detaljert.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nDetaljert Trondelag-CSV lagret til {csv_path} ({len(df)} rader).")
    n_with_email = (df["kontakt_epost"] != "").sum() if "kontakt_epost" in df else 0
    print(f"Herav {n_with_email} med kontakt-epost fylt ut.")

    md_path = "doffin_trondelag_leads.md"
    write_readable_summary(detailed_rows, md_path)
    print(f"Lesbar oppsummering lagret til {md_path} - apne den for et raskt overblikk.")


if __name__ == "__main__":
    main()

"""
Match Doffin leads to relevant Brreg businesses (by bransje + kommune) and
write draft cold-emails to a file for manual review. NOTHING is sent - this
only generates text you can copy into your own email client.

Requires doffin_notices_detaljert.csv and brreg_smabedrifter.csv to already
exist (run doffin_fetch.py and brreg_fetch.py first).

Usage:
    python generate_email_drafts.py
"""

import pandas as pd

MAX_BUSINESSES_PER_LEAD = 5

# CPV (4-digit group) -> NACE overrides, checked BEFORE the 2-digit division
# fallback below. Needed for CPV divisions that internally mix unrelated
# real industries (e.g. division 39 covers both furniture AND cleaning
# products - those need different NACE targets, a 2-digit division match
# can't tell them apart). Only covers groups seen in real Doffin data
# (2026-07-18) that the division-level default got wrong; extend as new
# problem cases show up.
CPV_GROUP_TO_NACE = {
    "3980": ["20", "46"],   # renholdsprodukter -> kjemisk produksjon/engros, ikke mobler
    "9240": ["63"],         # pressetjenester -> informasjonstjenester, ikke kultur/fritid
}

# Rough CPV (2-digit division) -> NACE (2-digit division) crosswalk.
# There is no official CPV<->NACE mapping - this is a manual best-effort
# table built from the CPV divisions actually observed in Doffin data
# (2026-07-18) plus common neighbours. Not exhaustive; extend as new CPV
# divisions show up in doffin_notices_detaljert.csv.
#
# Design rule: for GOODS/equipment CPV codes, map to the industry that
# SUPPLIES the goods (manufacturing/wholesale), not the industry that USES
# them - e.g. a "sanitetsmateriell" tender should reach medical wholesalers,
# not dentists or physiotherapists (who buy such supplies, not sell them).
CPV_TO_NACE = {
    "09": ["06", "19", "35"],              # brensel, olje, energi
    "14": ["05", "07", "08"],              # bergverk
    "15": ["10", "11"],                    # mat og drikke
    "18": ["14"],                          # klaer
    "19": ["13", "15"],                    # tekstil, laer
    "22": ["18"],                          # trykksaker
    "24": ["20"],                          # kjemiske produkter
    "30": ["26", "46", "62"],              # kontormaskiner/IT-utstyr
    "31": ["27"],                          # elektrisk utstyr
    "32": ["26", "61"],                    # radio/TV/kommunikasjon
    "33": ["32", "46"],                    # medisinsk utstyr - produsent/grossist, ikke klinikk
    "34": ["29", "30", "33", "45"],        # kjoretoy - produsent/forhandler/verksted
    "35": ["25", "26", "27", "28", "80"],  # sikkerhet/beredskapsutstyr + vakttjeneste
    "37": ["32"],                          # musikk/sport/spill
    "38": ["26", "32"],                    # lab/maleinstrumenter
    "39": ["31"],                          # mobler/inventar (se CPV_GROUP_TO_NACE for 3980)
    "41": ["36"],                          # vannforsyning
    "42": ["28"],                          # industrimaskiner
    "43": ["28"],                          # gruve-/anleggsmaskiner
    "44": ["23", "24", "25", "43"],        # byggematerialer
    "45": ["41", "42", "43"],              # bygg og anlegg
    "48": ["62"],                          # programvare
    "50": ["43", "33", "45", "95"],        # reparasjon/vedlikehold (rorlegger/elektriker=43)
    "51": ["43"],                          # installasjonstjenester
    "55": ["55", "56"],                    # hotell/servering/catering
    "60": ["49", "52", "53"],              # landtransport
    "63": ["52"],                          # transporttjenester
    "64": ["61"],                          # telekom
    "65": ["35", "36"],                    # offentlig forsyning
    "66": ["64", "65", "66"],              # finans/forsikring
    "70": ["68"],                          # eiendom
    "71": ["71"],                          # arkitekt/ingenior
    "72": ["62", "63"],                    # IT-tjenester
    "73": ["70", "72", "74"],              # FoU/design/konsulent
    "75": ["84"],                          # offentlig forvaltning
    "76": ["06", "09"],                    # olje/gass-tjenester
    "77": ["01", "02"],                    # jordbruk/skogbruk-tjenester
    "79": ["69", "70", "73", "74", "78", "80", "81", "82"],  # forretningstjenester
    "80": ["85"],                          # utdanning
    "85": ["86", "87", "88"],              # helse/omsorg
    "90": ["37", "38", "39", "49", "81"],  # avlop/avfall/miljo/transport
    "92": ["90", "91", "92", "93"],        # kultur/fritid/sport (se CPV_GROUP_TO_NACE for 9240)
    "98": ["43", "81", "95"],              # vaktmester/eiendomsdrift/lasesmed
}


def nace_divisions_for_cpv(cpv_code) -> list[str]:
    if not cpv_code or str(cpv_code) == "nan":
        return []
    cpv8 = str(int(float(cpv_code))).zfill(8)
    if cpv8[:4] in CPV_GROUP_TO_NACE:
        return CPV_GROUP_TO_NACE[cpv8[:4]]
    return CPV_TO_NACE.get(cpv8[:2], [])


def matches_nace(naeringskode: str, divisions: list[str]) -> bool:
    if not isinstance(naeringskode, str) or not divisions:
        return False
    return any(naeringskode.startswith(d) for d in divisions)


def format_verdi(verdi, valuta) -> str:
    if not verdi or str(verdi) == "nan":
        return "ikke oppgitt"
    try:
        return f"ca. {int(float(verdi)):,} kr".replace(",", " ")
    except ValueError:
        return "ikke oppgitt"


def format_frist(dato, tid) -> str:
    if not dato or str(dato) == "nan":
        return "ikke oppgitt"
    dato_ren = str(dato).split("+")[0]
    return dato_ren


def draft_email(business_navn: str, lead: dict) -> str:
    sporsmal_linje = f"Frist for å stille spørsmål: {lead['sporsmalsfrist']}\n" if lead.get("sporsmalsfrist") else ""
    return f"""Emne: Offentlig anbud som kan passe for {business_navn}

Hei,

Jeg fant en offentlig anskaffelse som kan være aktuell for dere:

"{lead['tittel']}"
Oppdragsgiver: {lead['oppdragsgiver']}
Frist for å sende tilbud: {lead['frist']}
{sporsmal_linje}Antatt størrelse: {lead['verdi']}
Hele kunngjøringen: {lead['lenke']}

Jeg sender ut denne typen relevante anbud fortløpende til bedrifter i bransjen.
Ønsker dere å få flere slike tips fremover, bare svar på denne e-posten.

Mvh
[ditt navn]
"""


def main() -> None:
    leads_df = pd.read_csv("doffin_notices_detaljert.csv")
    biz_df = pd.read_csv("brreg_smabedrifter.csv", dtype={"naeringskode": str})

    output_lines = ["# Utkast til lead-eposter (IKKE SENDT - kun utkast for gjennomlesning)\n"]
    n_leads_with_match = 0

    for _, row in leads_df.iterrows():
        divisions = nace_divisions_for_cpv(row.get("cpv_primaer"))
        if not divisions:
            continue

        candidates = biz_df[biz_df["naeringskode"].apply(lambda k: matches_nace(k, divisions))]

        poststed = str(row.get("oppdragsgiver_adresse", "")).split(",")[-1].strip().upper()
        local = candidates[candidates["kommune"].astype(str).str.upper() == poststed]
        chosen = local if len(local) > 0 else candidates
        chosen = chosen.head(MAX_BUSINESSES_PER_LEAD)

        if len(chosen) == 0:
            continue

        n_leads_with_match += 1
        lead = {
            "tittel": row.get("tittel", "(uten tittel)"),
            "oppdragsgiver": row.get("oppdragsgiver", ""),
            "frist": format_frist(row.get("tilbudsfrist_dato"), row.get("tilbudsfrist_tid")),
            "sporsmalsfrist": format_frist(row.get("sporsmalsfrist_dato"), row.get("sporsmalsfrist_tid")),
            "verdi": format_verdi(row.get("estimert_verdi"), row.get("valuta")),
            "lenke": row.get("lenke", ""),
        }
        if lead["sporsmalsfrist"] == "ikke oppgitt":
            lead["sporsmalsfrist"] = ""

        output_lines.append(f"## {lead['tittel']}")
        output_lines.append(f"CPV {row.get('cpv_primaer')} -> næringskode-divisjoner {divisions}"
                             f" | geografisk treff: {'samme kommune' if len(local) > 0 else 'ingen kommunetreff, viser nasjonale bransjetreff'}")
        output_lines.append("")
        output_lines.append(f"**Send til {len(chosen)} bedrifter:**")
        for _, biz in chosen.iterrows():
            output_lines.append(f"- {biz['navn']} ({biz['epost']}) - {biz['bransje']}, {biz['kommune']}")
        output_lines.append("")
        output_lines.append("**Utkast (samme tekst til alle, bytt ut navnet i emnefeltet manuelt):**")
        output_lines.append("```")
        output_lines.append(draft_email(str(chosen.iloc[0]["navn"]), lead))
        output_lines.append("```")
        output_lines.append("\n---\n")

    with open("email_drafts.md", "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"{n_leads_with_match} av {len(leads_df)} leads fikk minst én bransjematch.")
    print("Utkast lagret til email_drafts.md - IKKE sendt noe sted, kun tekst for gjennomlesning.")


if __name__ == "__main__":
    main()

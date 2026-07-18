"""
Match Doffin leads to relevant Brreg businesses (by bransje + kommune) and
write draft cold-emails to a file for manual review. NOTHING is sent - this
only generates text you can copy into your own email client.

Requires doffin_notices_detaljert.csv and brreg_bedrifter.csv to already
exist (run doffin_fetch.py and brreg_fetch.py first).

Usage:
    python generate_email_drafts.py
"""

import pandas as pd

from cpv_nace import nace_divisions_for_cpv, matches_nace

MAX_BUSINESSES_PER_LEAD = 5


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
    frist_label = "Frist for å melde interesse" if lead.get("er_kvalifikasjonsfase") else "Frist for å sende tilbud"
    return f"""Emne: Offentlig anbud som kan passe for {business_navn}

Hei,

Jeg fant en offentlig anskaffelse som kan være aktuell for dere:

"{lead['tittel']}"
Oppdragsgiver: {lead['oppdragsgiver']}
{frist_label}: {lead['frist']}
{sporsmal_linje}Antatt størrelse: {lead['verdi']}
Hele kunngjøringen: {lead['lenke']}

Jeg sender ut denne typen relevante anbud fortløpende til bedrifter i bransjen.
Ønsker dere å få flere slike tips fremover, bare svar på denne e-posten.

Ikke interessert i flere henvendelser som dette? Bare si fra, så fjerner jeg dere fra listen.

Mvh
[ditt navn]
[din bedrift]
[din telefon/epost]
"""


KONTAKTET_PATH = "kontaktet.csv"
KANDIDATER_PATH = "denne_runden_kandidater.csv"


def load_kontaktet() -> set:
    """Businesses already contacted in a previous run - permanently excluded
    so nobody gets re-emailed weekly (whether they replied 'nei takk' or
    just never responded, the rule is the same: contact once, never again
    via this tool)."""
    try:
        return set(pd.read_csv(KONTAKTET_PATH)["orgnr"])
    except FileNotFoundError:
        return set()


def main() -> None:
    leads_df = pd.read_csv("doffin_notices_detaljert.csv")
    biz_df = pd.read_csv("brreg_bedrifter.csv", dtype={"naeringskode": str})
    # A business can appear twice in the Brreg fetch if its forretningsadresse
    # and postadresse are in different kommuner (the kommunenummer filter
    # matches either) - keep one row per orgnr.
    biz_df = biz_df.drop_duplicates(subset="orgnr")

    already_kontaktet = load_kontaktet()
    if already_kontaktet:
        print(f"{len(already_kontaktet)} bedrifter er allerede kontaktet tidligere - utelates fra matching.")
    biz_df = biz_df[~biz_df["orgnr"].isin(already_kontaktet)]

    output_lines = ["# Utkast til lead-eposter (IKKE SENDT - kun utkast for gjennomlesning)\n"]
    n_leads_with_match = 0
    kandidater_denne_runden = []
    # Each business should get exactly ONE lead (the "one lead as a teaser"
    # model) - without this, a business matching several leads would get a
    # separate email per lead (seen live: some businesses matched 7 leads).
    used_orgnr: set = set()

    for _, row in leads_df.iterrows():
        divisions, _presisjon = nace_divisions_for_cpv(row.get("cpv_primaer"))
        if not divisions:
            continue

        candidates = biz_df[biz_df["naeringskode"].apply(lambda k: matches_nace(k, divisions))]
        candidates = candidates[~candidates["orgnr"].isin(used_orgnr)]

        poststed = str(row.get("oppdragsgiver_adresse", "")).split(",")[-1].strip().upper()
        local = candidates[candidates["kommune"].astype(str).str.upper() == poststed]
        if len(local) > 0:
            chosen = local.head(MAX_BUSINESSES_PER_LEAD)
        else:
            # No kommune match - sample randomly from the nationwide bransje
            # match instead of always picking the same alphabetically-first
            # rows (candidates is otherwise returned in fixed CSV order).
            chosen = candidates.sample(n=min(MAX_BUSINESSES_PER_LEAD, len(candidates)))

        if len(chosen) == 0:
            continue

        used_orgnr.update(chosen["orgnr"])
        n_leads_with_match += 1
        lead = {
            "tittel": row.get("tittel", "(uten tittel)"),
            "oppdragsgiver": row.get("oppdragsgiver", ""),
            "frist": format_frist(row.get("tilbudsfrist_dato"), row.get("tilbudsfrist_tid")),
            "sporsmalsfrist": format_frist(row.get("sporsmalsfrist_dato"), row.get("sporsmalsfrist_tid")),
            "verdi": format_verdi(row.get("estimert_verdi"), row.get("valuta")),
            "lenke": row.get("lenke", ""),
            "er_kvalifikasjonsfase": bool(row.get("er_kvalifikasjonsfase")),
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

        for _, biz in chosen.iterrows():
            kandidater_denne_runden.append({
                "orgnr": biz["orgnr"],
                "navn": biz["navn"],
                "epost": biz["epost"],
                "doffin_id": row.get("doffin_id"),
                "tittel": lead["tittel"],
            })

    with open("email_drafts.md", "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    pd.DataFrame(kandidater_denne_runden).to_csv(KANDIDATER_PATH, index=False, encoding="utf-8-sig")

    print(f"{n_leads_with_match} av {len(leads_df)} leads fikk minst én bransjematch.")
    print("Utkast lagret til email_drafts.md - IKKE sendt noe sted, kun tekst for gjennomlesning.")
    print(f"{len(kandidater_denne_runden)} kandidater denne runden lagret til {KANDIDATER_PATH}.")
    print("Nar du faktisk har sendt e-postene: kjor 'python marker_sendt.py' for a logge dem som kontaktet.")


if __name__ == "__main__":
    main()

"""
Write draft cold-emails from the already-scored lead_bedrift_scores.csv
(run compute_scores.py first). NOTHING is sent - this only generates text
you can copy into your own email client.

This is the ONLY place candidate businesses are chosen for outreach - it
reads the same match/realism scores compute_scores.py produces and app.py
displays, rather than re-deriving its own separate (weaker) matching logic.
That used to be two independent systems giving inconsistent results.

Usage:
    python generate_email_drafts.py
"""

import pandas as pd

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

Kontaktinfo er hentet fra Brønnøysundregisteret.

Ikke interessert i flere henvendelser som dette? Bare si fra, så fjerner jeg dere fra listen.

Mvh
[ditt navn]
[din bedrift]
[din telefon/epost]
"""


KANDIDATER_PATH = "denne_runden_kandidater.csv"


def main() -> None:
    try:
        scores_df = pd.read_csv("lead_bedrift_scores.csv")
    except FileNotFoundError:
        print("Fant ikke lead_bedrift_scores.csv - kjor compute_scores.py forst.")
        return

    leads_df = pd.read_csv("doffin_notices_detaljert.csv").set_index("doffin_id")

    # compute_scores.py already excludes kontaktet.csv-bedrifter and sorts
    # candidates loosely - re-sort defensively here so "best first" is
    # guaranteed regardless of upstream ordering.
    scores_df = scores_df[scores_df["realism_tier"] != "Urealistisk"]
    # Hver bedrift skal fa sitt BESTE anbud, ikke det forste loopen traff:
    # sorter globalt pa samlet score og behold ett (beste) par per orgnr.
    scores_df = scores_df.assign(_s=scores_df["match_score"] + scores_df["realism_score"]) \
        .sort_values("_s", ascending=False).drop_duplicates(subset="orgnr")
    scores_df = scores_df.sort_values(["doffin_id", "match_score", "realism_score"], ascending=[True, False, False])

    output_lines = ["# Utkast til lead-eposter (IKKE SENDT - kun utkast for gjennomlesning)\n"]
    n_leads_with_match = 0
    kandidater_denne_runden = []

    for doffin_id, gruppe in scores_df.groupby("doffin_id", sort=False):
        if doffin_id not in leads_df.index:
            continue
        row = leads_df.loc[doffin_id]

        chosen = gruppe.head(MAX_BUSINESSES_PER_LEAD)
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
            "er_kvalifikasjonsfase": bool(row.get("er_kvalifikasjonsfase")),
        }
        if lead["sporsmalsfrist"] == "ikke oppgitt":
            lead["sporsmalsfrist"] = ""

        output_lines.append(f"## {lead['tittel']}")
        output_lines.append("")
        output_lines.append(f"**Send til {len(chosen)} bedrifter (sortert etter matchscore):**")
        for _, biz in chosen.iterrows():
            output_lines.append(
                f"- {biz['navn']} ({biz['epost']}) - {biz['bransje']}, {biz['kommune']}"
                f" | match {biz['match_score']:.0f} ({biz['match_tier']}), realisme {biz['realism_score']:.0f} ({biz['realism_tier']})"
            )
        output_lines.append("")
        # Ett ferdig utkast PER bedrift - manuelt navnebytte i emnefeltet
        # var en garantert feilkilde (feil bedriftsnavn i emnet).
        for _, biz in chosen.iterrows():
            output_lines.append(f"**Til {biz['navn']} ({biz['epost']}):**")
            output_lines.append("```")
            output_lines.append(draft_email(str(biz["navn"]), lead))
            output_lines.append("```")
        output_lines.append("\n---\n")

        for _, biz in chosen.iterrows():
            kandidater_denne_runden.append({
                "orgnr": biz["orgnr"],
                "navn": biz["navn"],
                "epost": biz["epost"],
                "doffin_id": doffin_id,
                "tittel": lead["tittel"],
            })

    with open("email_drafts.md", "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    pd.DataFrame(kandidater_denne_runden).to_csv(KANDIDATER_PATH, index=False, encoding="utf-8-sig")

    print(f"{n_leads_with_match} av {len(leads_df)} leads fikk minst en kandidat.")
    print("Utkast lagret til email_drafts.md - IKKE sendt noe sted, kun tekst for gjennomlesning.")
    print(f"{len(kandidater_denne_runden)} kandidater denne runden lagret til {KANDIDATER_PATH}.")
    print("Nar du faktisk har sendt e-postene: kjor 'python marker_sendt.py' for a logge dem som kontaktet.")


if __name__ == "__main__":
    main()

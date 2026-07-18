"""
Regner ut match- og realismescore for hvert anbud x relevante bedrifter
(filtrert pa bransje, som generate_email_drafts.py allerede gjor), og
skriver ett samlet lead_bedrift_scores.csv som app.py (Streamlit) leser.

Ingenting sendes eller kontaktes her - kun beregning.

Usage:
    python compute_scores.py
"""

from datetime import date

import pandas as pd

from cpv_nace import nace_divisions_for_cpv, matches_nace
from scoring import match_score, realism_score


def dager_til_frist(dato_str) -> int | None:
    if not dato_str or str(dato_str) == "nan":
        return None
    try:
        frist = date.fromisoformat(str(dato_str).split("+")[0])
    except ValueError:
        return None
    return (frist - date.today()).days


def main() -> None:
    leads_df = pd.read_csv("doffin_notices_detaljert.csv", dtype={"oppdragsgiver_kommunenummer": str})
    biz_df = pd.read_csv("brreg_bedrifter.csv", dtype={"naeringskode": str, "kommunenummer": str})
    biz_df = biz_df.drop_duplicates(subset="orgnr")

    try:
        kontaktet = set(pd.read_csv("kontaktet.csv")["orgnr"])
    except FileNotFoundError:
        kontaktet = set()

    rows = []
    for _, lead in leads_df.iterrows():
        divisions, presisjon = nace_divisions_for_cpv(lead.get("cpv_primaer"))
        if not divisions:
            continue

        candidates = biz_df[biz_df["naeringskode"].apply(lambda k: matches_nace(k, divisions))]
        dager_igjen = dager_til_frist(lead.get("tilbudsfrist_dato"))

        for _, biz in candidates.iterrows():
            m = match_score(presisjon, lead.get("oppdragsgiver_kommunenummer"), biz.get("kommunenummer"))
            r = realism_score(
                lead.get("estimert_verdi"), biz.get("antall_ansatte"), dager_igjen,
                biz.get("stiftelsesdato"), biz.get("registreringsdato"), biz.get("organisasjonsform"),
            )
            rows.append({
                "doffin_id": lead.get("doffin_id"),
                "lead_tittel": lead.get("tittel"),
                "lead_oppdragsgiver": lead.get("oppdragsgiver"),
                "lead_verdi": lead.get("estimert_verdi"),
                "lead_valuta": lead.get("valuta"),
                "lead_frist": lead.get("tilbudsfrist_dato"),
                "lead_lenke": lead.get("lenke"),
                "orgnr": biz.get("orgnr"),
                "navn": biz.get("navn"),
                "bransje": biz.get("bransje"),
                "kommune": biz.get("kommune"),
                "epost": biz.get("epost"),
                "telefon": biz.get("telefon"),
                "antall_ansatte": biz.get("antall_ansatte"),
                **m,
                **r,
                "allerede_kontaktet": biz.get("orgnr") in kontaktet,
            })

    df = pd.DataFrame(rows)
    df.to_csv("lead_bedrift_scores.csv", index=False, encoding="utf-8-sig")
    print(f"{len(df)} lead-bedrift-par scoret, lagret til lead_bedrift_scores.csv.")
    if len(df):
        print(df[["match_tier", "realism_tier"]].value_counts().head(10))


if __name__ == "__main__":
    main()

"""
Run this AFTER you have actually sent the emails from the latest
email_drafts.md batch. It appends everyone in denne_runden_kandidater.csv
to kontaktet.csv (with today's date) so generate_email_drafts.py never
suggests them again - whether they reply "nei takk" or never respond at
all, the rule is the same: contact once, never again via this tool.

Does NOT send anything itself - it only updates the log.

Usage:
    python marker_sendt.py
"""

import sys
from datetime import date

import pandas as pd

KANDIDATER_PATH = "denne_runden_kandidater.csv"
KONTAKTET_PATH = "kontaktet.csv"
KOLONNER = ["orgnr", "navn", "epost", "doffin_id", "tittel", "dato_kontaktet"]


def append_to_kontaktet(rader: pd.DataFrame) -> pd.DataFrame:
    """Legger radene til i kontaktet.csv (permanent, deduplisert pa orgnr,
    forste oppforing vinner). Brukes bade av CLI-en under og av app.py sin
    'Marker som sendt'-knapp - selve regelen (kontakt en gang, aldri igjen)
    bor bare finnes ett sted."""
    rader = rader.copy()
    rader["dato_kontaktet"] = date.today().isoformat()
    rader = rader[KOLONNER]

    try:
        eksisterende = pd.read_csv(KONTAKTET_PATH)
        kombinert = pd.concat([eksisterende, rader], ignore_index=True)
        kombinert = kombinert.drop_duplicates(subset="orgnr", keep="first")
    except FileNotFoundError:
        kombinert = rader

    kombinert.to_csv(KONTAKTET_PATH, index=False, encoding="utf-8-sig")
    return kombinert


def main() -> None:
    try:
        kandidater = pd.read_csv(KANDIDATER_PATH, dtype={"orgnr": str})
    except FileNotFoundError:
        print(f"Fant ikke {KANDIDATER_PATH} - kjor generate_email_drafts.py forst.")
        return

    # Delvis utsending: 'python marker_sendt.py 912345678 998765432' markerer
    # kun de orgnr-ene - uten argumenter markeres hele runden (som for).
    valgte = set(sys.argv[1:])
    if valgte:
        kandidater = kandidater[kandidater["orgnr"].isin(valgte)]
        ukjent = valgte - set(kandidater["orgnr"])
        if ukjent:
            print(f"ADVARSEL: fant ikke i runden: {', '.join(sorted(ukjent))}")

    if len(kandidater) == 0:
        print("Ingen kandidater a markere.")
        return

    kombinert = append_to_kontaktet(kandidater)
    print(f"{len(kandidater)} bedrifter lagt til i {KONTAKTET_PATH} (totalt {len(kombinert)} noensinne kontaktet).")
    print("De vil ikke bli foreslatt igjen av generate_email_drafts.py.")


if __name__ == "__main__":
    main()

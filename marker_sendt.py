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

from datetime import date

import pandas as pd

KANDIDATER_PATH = "denne_runden_kandidater.csv"
KONTAKTET_PATH = "kontaktet.csv"


def main() -> None:
    try:
        kandidater = pd.read_csv(KANDIDATER_PATH)
    except FileNotFoundError:
        print(f"Fant ikke {KANDIDATER_PATH} - kjor generate_email_drafts.py forst.")
        return

    if len(kandidater) == 0:
        print("Ingen kandidater a markere.")
        return

    kandidater["dato_kontaktet"] = date.today().isoformat()
    kolonner = ["orgnr", "navn", "epost", "doffin_id", "tittel", "dato_kontaktet"]

    try:
        eksisterende = pd.read_csv(KONTAKTET_PATH)
        kombinert = pd.concat([eksisterende, kandidater[kolonner]], ignore_index=True)
        kombinert = kombinert.drop_duplicates(subset="orgnr", keep="first")
    except FileNotFoundError:
        kombinert = kandidater[kolonner]

    kombinert.to_csv(KONTAKTET_PATH, index=False, encoding="utf-8-sig")
    print(f"{len(kandidater)} bedrifter lagt til i {KONTAKTET_PATH} (totalt {len(kombinert)} noensinne kontaktet).")
    print("De vil ikke bli foreslatt igjen av generate_email_drafts.py.")


if __name__ == "__main__":
    main()

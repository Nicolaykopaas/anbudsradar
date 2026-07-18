"""
Merge the separate brreg_bedrifter_{range}.csv files (one per ansatte-range
fetch, e.g. 1-20 and 21-100) into a single brreg_bedrifter.csv covering all
small and medium businesses (SMB). Dedupes by orgnr in case a business
somehow appears in more than one range file.

Usage:
    python merge_brreg_ranges.py
"""

import glob

import pandas as pd

files = sorted(glob.glob("brreg_bedrifter_*-*.csv"))
if not files:
    print("Ingen brreg_bedrifter_*.csv-filer funnet - kjor brreg_fetch.py forst.")
else:
    frames = [pd.read_csv(f, dtype={"naeringskode": str}) for f in files]
    combined = pd.concat(frames, ignore_index=True).drop_duplicates(subset="orgnr")
    combined.to_csv("brreg_bedrifter.csv", index=False, encoding="utf-8-sig")
    print(f"Slo sammen {files} -> brreg_bedrifter.csv ({len(combined)} unike bedrifter).")

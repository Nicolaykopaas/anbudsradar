"""Kjører hele pipelinen i rekkefølge: Doffin -> Brreg (to ansatte-band) -> merge -> scoring.

Ment for et scheduled CI-kjøring (se .github/workflows/refresh-demo-data.yml)
som holder den offentlige demoen (app.py) oppdatert med ferske data, uten at
noen besøkende trigger et nasjonalt API-søk selv.

Bruk:
    python run_pipeline.py
"""
import os
import subprocess
import sys


def kjor(*args: str, env: dict | None = None) -> None:
    full_env = {**os.environ, **(env or {})}
    print(f"\n=== kjører: {' '.join(args)} ===", flush=True)
    subprocess.run([sys.executable, *args], check=True, env=full_env)


def main() -> None:
    kjor("doffin_fetch.py")
    kjor("brreg_fetch.py", env={"BRREG_MIN_ANSATTE": "1", "BRREG_MAX_ANSATTE": "20"})
    kjor("brreg_fetch.py", env={"BRREG_MIN_ANSATTE": "21", "BRREG_MAX_ANSATTE": "100"})
    kjor("merge_brreg_ranges.py")
    kjor("compute_scores.py")


if __name__ == "__main__":
    main()

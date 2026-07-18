# Doffin Leads

Finner offentlige anbud i Norge og matcher dem mot små og mellomstore bedrifter som kan være interessert — som grunnlag for å sende dem en gratis smakebit og tilby et abonnement på flere.

Alt her er **gratis** å kjøre (offentlige, åpne API-er, ingen nøkler som koster penger).

## Hva scriptene gjør

1. **`doffin_fetch.py`** — henter alle aktive offentlige anbud i Norge fra Doffin, med frist, kontaktperson, verdi og bransje (CPV-kode).
   ```
   setx DOFFIN_API_KEY "din-nokkel"
   python doffin_fetch.py
   ```
   Lager: `doffin_leads.md` (lesbar oversikt), `doffin_notices_detaljert.csv`

2. **`brreg_fetch.py`** — henter små og mellomstore bedrifter fra Brønnøysundregisteret som har registrert e-postadresse.
   ```
   python brreg_fetch.py                                              # 1-20 ansatte
   BRREG_MIN_ANSATTE=21 BRREG_MAX_ANSATTE=100 python brreg_fetch.py   # 21-100 ansatte
   python merge_brreg_ranges.py                                       # sla sammen til én fil
   ```
   Lager: `brreg_bedrifter.csv`

3. **`generate_email_drafts.py`** — matcher hver anbudslead mot relevante bedrifter (bransje + kommune) og skriver ferdige e-postutkast. **Sender ingenting** — bare tekst du kan kopiere selv.
   ```
   python generate_email_drafts.py
   ```
   Lager: `email_drafts.md`

## Rekkefølge

Kjør scriptene i rekkefølgen over, én gang i uka (eller når du vil ha ferske leads).

## Status akkurat nå

- Doffin-henting: fungerer, ferdig testet
- Brreg-henting: fungerer, nasjonal kjøring pågår
- E-postutkast: fungerer, venter på ferdig Brreg-data for et ekte nasjonalt resultat
- Utsending: **ikke bygget ennå** — du sender selv manuelt fra utkastene, ingenting er automatisert

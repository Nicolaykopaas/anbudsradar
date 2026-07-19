# AnbudsRadar

Finner offentlige anbud i Norge og matcher dem mot bedrifter som faktisk kan ta jobben. Bygget fordi små bedrifter sjelden har tid til å lete gjennom Doffin selv, og går glipp av anbud de kunne vunnet.

Kjører på to gratis, offentlige API-er (Doffin og Brønnøysundregisteret). Ingen skraping, ingen betalte tjenester, ingen skyløsning.

<!-- Skjermbilde av dashbordet her -->

## Hva den gjør

1. Henter aktive anbud fra Doffin — frist, verdi, kontaktperson, bransjekode.
2. Henter norske SMB-er fra Brreg — filtrert på antall ansatte og bransje.
3. Regner ut for hvert anbud hvilke bedrifter som passer best, og hvor realistisk det er at de faktisk kan ta jobben.
4. Viser alt i et dashbord: filtrer, se anbefalinger side om side, les ferdige e-postutkast.

Ingenting sendes automatisk. E-postene er utkast du selv leser gjennom.

## Kjøre det

```bash
pip install -r requirements.txt

python doffin_fetch.py          # hent anbud (krever gratis Doffin-API-nøkkel)
python brreg_fetch.py           # hent bedrifter (ingen nøkkel nødvendig)
python compute_scores.py        # regn ut score for hvert anbud-bedrift-par
python generate_email_drafts.py # skriv e-post-utkast

streamlit run app.py            # åpne dashbordet
```

Se toppen av hvert script for oppsett-detaljer.

## Scoringen

Hvert anbud-bedrift-par får to tall, 0–100:

- **Matchscore** — hvor godt bransje og geografi treffer. Presist bransjetreff veier tyngre enn en bred divisjon; samme kommune veier tyngre enn samme fylke.
- **Realismescore** — om bedriften faktisk kan ta jobben. Passer kontraktsstørrelsen til antall ansatte? Nok tid til fristen? Er bedriften etablert? Hvor langt unna er de?

Begge regnes ut i Python, én gang, lagres til fil. Dashbordet gjør ingen matte selv, bare viser resultatet.

## Ting jeg måtte finne ut av underveis

- Det finnes ingen offisiell kobling mellom EU sine anbudskoder (CPV) og norske næringskoder (NACE). `cpv_nace.py` er en håndlaget tabell, justert mot ekte data helt til feilmatcher (en gullsmed som fikk tilbud om et sykehjems-anbud) sluttet å dukke opp.
- Norge følger ikke alltid EU-standarden for NACE. Bilbransjen er det tydeligste eksempelet — EU sier kode 45, men Brreg bruker 46/47 for handel og 95 for verksted. Fant det ved å teste live og se at kode 45 ga null treff i hele Norge.
- Både Brreg og Doffin har en grense på hvor dypt man kan søke (rundt 10 000 og 1000 treff). Løst ved å dele opp søket automatisk — på antall ansatte/selskapsform for Brreg, på publiseringsdato for Doffin — helt til hver bit er liten nok.
- Avstand regnes med et gratis, offline postnummer-datasett i stedet for en betalt geokodings-API.
- En egen logg (`kontaktet.csv`) sørger for at ingen bedrift kontaktes to ganger, uansett hvor mange ganger scriptet kjøres.

## Teknologi

Python, pandas, Streamlit. Ingen database, ingen backend, ingen JavaScript-bygg — kjører lokalt.

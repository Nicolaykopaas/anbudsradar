# 📡 AnbudsRadar

**Offentlig Norge lyser ut anbud for over 500 milliarder kroner i året. De fleste små bedrifter ser aldri de riktige.**

AnbudsRadar fikser det. Den skanner alle aktive offentlige anskaffelser i Norge, regner ut hvilke bedrifter som faktisk har en sjanse til å vinne dem, og gir deg et ferdig dashbord til å finne — og ta kontakt med — de riktige.

Alt kjører på gratis, offentlige data. Ingen betalte API-er, ingen skraping, ingen skyløsning som koster penger.

<!-- 📸 Skjermbilde av dashbordet her -->

## Problemet

Doffin (Norges portal for offentlige anskaffelser) publiserer alt åpent. Men å faktisk finne *det ene anbudet som passer akkurat din bedrift* blant tusenvis av kunngjøringer, i alle bransjer, i hele landet — det er en jobb ingen liten bedrift har tid til. Så de går glipp av kontrakter de faktisk kunne vunnet.

AnbudsRadar gjør den jobben automatisk.

## Hvordan det funker

```
Doffin API  ──►  offentlige anbud (frist, verdi, bransje, kontaktperson)
                                                              │
Brreg API   ──►  norske bedrifter (ansatte, bransje, sted)   │
                                                              ▼
                                                    matching + scoring
                                                              │
                                                              ▼
                                                  Streamlit-dashbord
```

**Steg for steg:**

1. **Hent anbud** (`doffin_fetch.py`) — alle aktive offentlige konkurranser i Norge, med full detalj: frist, oppdragsgiver, kontaktperson, verdi, bransjekode.
2. **Hent bedrifter** (`brreg_fetch.py`) — norske SMB-er filtrert på antall ansatte og bransje.
3. **Match og score** (`compute_scores.py`) — for hvert anbud, finn de mest relevante bedriftene og regn ut to tall: hvor godt de passer, og hvor realistisk det er at de kan levere.
4. **Se det hele** (`app.py`) — et dashbord der du filtrerer, sammenligner og leser gjennom ferdige e-postutkast.

Ingenting sendes automatisk. Hver e-post er et utkast du selv leser gjennom.

## Datakildene — og hvorfor ingenting er skrapt

Alt kommer fra to offisielle, gratis, åpne API-er. **Ingen skraping** — begge er ekte, dokumenterte offentlige tjenester:

- **[Doffin Public API](https://doffin.no)** (`api.doffin.no/public/v2`) — Norges offisielle kunngjøringsportal for offentlige anskaffelser. Søkeendepunktet gir en rask oversikt; et eget nedlastingsendepunkt gir full detalj som XML (EU sitt eForms/UBL-format).
- **[Brønnøysundregistrenes Enhetsregister](https://data.brreg.no)** — Norges offisielle bedriftsregister. Helt åpent, krever ikke engang API-nøkkel.

Begge er myndighetsdata publisert nettopp for at noen skal bygge noe med dem. Det er poenget med åpne data.

## De tekniske knutene som måtte løses

Dette er ikke bare "kall to API-er og slå sammen resultatet". Et par ting overrasket meg underveis:

- **Det finnes ingen offisiell kobling mellom EU:s anbudskoder (CPV) og norske næringskoder (NACE).** `cpv_nace.py` er en håndbygget bro mellom de to, justert og strammet inn mot ekte treningsdata helt til feilmatcher (som en gullsmed som fikk tilbud om et sykehjems-anbud) sluttet å dukke opp.
- **Norge følger ikke alltid EU-standarden for NACE.** Bilbransjen er det klareste eksemplet — EU-standarden sier bilhandel/-verksted skal ligge under kode 45, men Brreg bruker 46/47 (handel) og 95 (verksted) i stedet. Fant det ved å teste live mot API-et og se at "kode 45" ga null treff i hele Norge.
- **Brregs API takler ikke dypere søk enn ~10 000 treff.** Store kommuner (Oslo har over 20 000 småbedrifter alene) løses ved å dele søket automatisk — først på antall ansatte, så på selskapsform — helt til hver bit er liten nok.
- **Avstand uten å betale for geokoding.** Bruker et gratis, offline datasett med koordinater per norsk postnummer i stedet for å ringe en betalt geokodings-API for hvert eneste bedrift-anbud-par.
- **Kontaktet én gang, aldri igjen.** En permanent logg (`kontaktet.csv`) sørger for at ingen bedrift får flere e-poster om samme type anbud, uansett hvor mange ganger scriptet kjøres.

## Scoringen

Hvert anbud-bedrift-par får to tall, begge 0–100:

**Matchscore** — hvor godt bransje og geografi treffer. Presist bransjetreff via en spesifikk næringskode veier tyngre enn et bredt divisjonsnivå-treff; samme kommune veier tyngre enn samme fylke, som veier tyngre enn "bare et sted i Norge".

**Realismescore** — om bedriften faktisk *kan* ta jobben, uavhengig av bransje. Passer kontraktsstørrelsen til antall ansatte? Er det nok tid igjen til fristen? Er bedriften etablert nok? Hvor langt unna er de?

Begge regnes ut i Python, én gang, og lagres til fil — dashbordet gjør ingen matematikk selv, det bare viser resultatet.

## Teknologi — og hvorfor

**Python + pandas + [Streamlit](https://streamlit.io).** Ingen database, ingen backend-server, ingen JavaScript-bygg. Streamlit gir et fullverdig interaktivt nettdashbord rett fra Python-kode — for et soloprosjekt der selve datalogikken er poenget, er det riktig avveining mellom hastighet og kontroll. Et ekte React/HTML-frontend ville gitt penere piksler, men også en helt egen kodebase å vedlikeholde for noe som allerede fungerer.

## Kom i gang

```bash
pip install -r requirements.txt

python doffin_fetch.py          # hent anbud (krever gratis Doffin-API-nøkkel)
python brreg_fetch.py           # hent bedrifter (ingen nøkkel nødvendig)
python compute_scores.py        # regn ut score for hvert anbud-bedrift-par
python generate_email_drafts.py # skriv e-post-utkast

streamlit run app.py            # åpne dashbordet i nettleseren
```

Se kommentarene øverst i hvert script for oppsett-detaljer.

# 📡 AnbudsRadar

Et verktøy som finner offentlige anbud i Norge og matcher dem mot relevante små og mellomstore bedrifter — automatisk, presist og helt gratis.

Tanken: offentlige anskaffelser publiseres åpent på [Doffin](https://doffin.no), men de fleste små bedrifter har ikke tid til å følge med selv. AnbudsRadar finner de riktige anbudene for hver bedrift, regner ut hvor godt de faktisk passer, og gjør det enkelt å ta kontakt.

<!-- 📸 Sett inn et skjermbilde av dashbordet her, f.eks:
![AnbudsRadar dashbord](skjermbilde.png)
-->

## Hva det gjør

1. **Henter anbud** — alle aktive offentlige konkurranser i Norge, med frist, oppdragsgiver, verdi og bransjekode.
2. **Henter bedrifter** — små/mellomstore norske bedrifter fra Brønnøysundregisteret, filtrert på ansatte og bransje.
3. **Regner ut score** for hvert anbud-bedrift-par:
   - **Matchscore** — hvor presist bransje og geografi treffer.
   - **Realismescore** — om bedriften realistisk kan ta kontrakten (størrelse, avstand, tid til frist, alder på selskapet).
4. **Dashbord** — bla gjennom anbud, se anbefalte bedrifter side om side, og hold styr på hvem som er kontaktet.

Ingenting sendes automatisk. Alle e-poster er utkast du selv leser gjennom og sender.

## Teknologi

Python, pandas og [Streamlit](https://streamlit.io) — ingen database, ingen server, ingen bygg-steg. Kjører lokalt på din egen maskin.

## Kom i gang

```bash
pip install -r requirements.txt

python doffin_fetch.py          # hent anbud (krever gratis Doffin-API-nøkkel)
python brreg_fetch.py           # hent bedrifter (ingen nøkkel nødvendig)
python compute_scores.py        # regn ut score for hvert anbud-bedrift-par
python generate_email_drafts.py # skriv e-post-utkast

streamlit run app.py            # åpne dashbordet i nettleseren
```

Se kommentarene øverst i hvert script for detaljer (API-nøkkel-registrering, ansatte-intervall osv.).

## Noen designvalg

- **To gratis registre, én bro mellom dem.** Det finnes ingen offisiell kobling mellom EU:s anbudskoder (CPV) og norske næringskoder (NACE) — `cpv_nace.py` er en håndbygget bro, justert mot ekte anbudsdata. Underveis oppdaget jeg at Norge til og med bruker en annen inndeling enn resten av EU for enkelte bransjer (bilbransjen ligger f.eks. under helt andre koder enn EU-standarden skulle tilsi).
- **Avstand er beregnet, ikke gjettet.** Bruker et gratis, offline norsk postnummer-datasett for koordinater — ingen kall til betalte geokodings-tjenester.
- **Kontaktet én gang, aldri igjen.** En permanent logg sikrer at ingen bedrift blir kontaktet flere ganger, uansett om de svarte eller ikke.

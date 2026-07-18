# Doffin Leads

Finner offentlige anbud (anskaffelser) i Norge og matcher dem mot små og mellomstore bedrifter (SMB) som kan være interessert i å levere tilbud. Tanken er å sende en bedrift ett relevant anbud gratis som smakebit, og tilby et abonnement for å få flere fortløpende — en konkurrent til tjenester som Bradar, men billigere.

Alt her er **gratis** å kjøre. Ingen av API-ene som brukes krever betaling, og det er ikke bygget noe abonnements- eller betalingssystem for produktet selv ennå.

## Hvordan det henger sammen

```
doffin_fetch.py  ──► doffin_notices_detaljert.csv ──┐
                                                      ├─► generate_email_drafts.py ──► email_drafts.md
brreg_fetch.py   ──► brreg_bedrifter.csv        ─────┘
(+ merge_brreg_ranges.py slår sammen flere ansatte-intervaller)
```

Doffin gir deg **hva** (anbudet), Brreg gir deg **hvem** (bedriften du skal tipse), og matching-scriptet kobler dem sammen basert på bransje og kommune.

## 1. `doffin_fetch.py` — hent offentlige anbud

Henter alle aktive konkurranser ("COMPETITION"-type kunngjøringer) i Norge fra Doffins offisielle Public API, siste 7 dager, alle bransjer.

**Datakilde:** `https://api.doffin.no/public/v2/search` (rask oversikt) + `https://api.doffin.no/public/v2/download/{id}` (full detalj som XML, EU eForms/UBL-format).

**Oppsett (én gang):**
```
winget install Python.Python.3.12
pip install requests pandas
```
Registrer deg på `dof-notices-prod-api.developer.azure-api.net`, opprett et abonnement på **Public API**, og hent nøkkelen fra Profile-siden.

**Kjøring:**
```
setx DOFFIN_API_KEY "din-nokkel-her"     # kun forste gang, apne nytt terminalvindu etterpa
python doffin_fetch.py
```

**Genererer:**
- `doffin_leads.md` — lesbar oversikt i vanlig norsk, ingen fagsjargong (bruk denne for a bla gjennom leads selv)
- `doffin_notices_detaljert.csv` — samme data, men som CSV med alle feltnavn (brukes av `generate_email_drafts.py`)
- `doffin_notices_alle.csv` — lettvekts nasjonal oversikt uten full detalj (rask, ingen ekstra API-kall)
- `doffin_search_raw.json` — rådata fra søket, til feilsøking

**Felter du får per anbud:** tittel, beskrivelse, oppdragsgiver (navn/org.nr/adresse), kontaktperson (navn/telefon/e-post), tilbudsfrist, spørsmålsfrist, estimert verdi, CPV-koder (primær + tillegg), lenke til kunngjøringen på doffin.no.

**Kjente kvirker:**
- `/search`-endepunktet er en lettvekts-indeks uten frist eller kontaktinfo — full detalj krever et eget kall til `/download/{id}` per kunngjøring.
- To-stegs kvalifikasjonskonkurranser bruker et annet feltnavn for frist (`ParticipationRequestReceptionPeriod` i stedet for `TenderSubmissionDeadlinePeriod`) — scriptet faller automatisk tilbake til dette og merker leaden som `er_kvalifikasjonsfase`.
- CPV-koder kan ikke filtreres presist server-side (API-et later til a ville ha eksakte 8-sifrede koder, ikke prefiks), sa scriptet henter bredt og filtrerer selv.

## 2. `brreg_fetch.py` — hent bedrifter å tipse

Henter små og mellomstore bedrifter (SMB) fra Brønnøysundregisterets offentlige API, filtrert på antall ansatte, og beholder kun de som har registrert en e-postadresse.

**Datakilde:** `https://data.brreg.no/enhetsregisteret/api/enheter` — helt åpen, ingen nøkkel eller registrering nødvendig.

**Kjøring** (ansatte-intervallet styres med miljøvariabler, siden en full nasjonal kjøring kan ta 30-60+ minutter):
```
python brreg_fetch.py                                              # standard: 1-20 ansatte
BRREG_MIN_ANSATTE=21 BRREG_MAX_ANSATTE=100 python brreg_fetch.py    # 21-100 ansatte
python merge_brreg_ranges.py                                       # sla de to sammen
```

**Genererer:**
- `brreg_bedrifter_{intervall}.csv` — én fil per ansatte-intervall du har kjørt
- `brreg_bedrifter.csv` — den sammenslåtte, endelige filen (denne leses av `generate_email_drafts.py`)
- `brreg_checkpoint_{intervall}.jsonl` — fremdriftslagring per kommune; slettes automatisk når en kjøring fullfører. Krasjer scriptet midtveis, kan du bare kjøre det på nytt — det gjenopptar der det slapp.

**Felter du får per bedrift:** org.nr, navn, bransje + næringskode, kommune/poststed/adresse, antall ansatte, e-post, telefon, mobil, hjemmeside.

**Kjente kvirker:**
- API-et takler ikke dypere paginering enn ~10 000 treff per søk. Store kommuner (Oslo har over 10 000 småbedrifter alene) håndteres ved å automatisk dele opp søket — først etter antall ansatte, så etter selskapsform (AS, ENK, osv.) — helt til hver bit er liten nok.
- Bare **~30 %** av små/mellomstore bedrifter har e-post registrert i Brreg. De uten e-post blir ikke tatt med (ingen skraping av nettsider foreløpig).
- En bedrift kan telles i to ulike kommune-søk hvis forretnings- og postadresse ligger i forskjellige kommuner — scriptet fjerner duplikater automatisk (samme org.nr).
- `fraAntallAnsatte`/`tilAntallAnsatte` godtar kun 0, 4, eller et hvilket som helst tall over 4 — ikke f.eks. 2 eller 3. Scriptet tar hensyn til dette når det deler opp søk.

## 3. `generate_email_drafts.py` — match og skriv utkast

Matcher hvert Doffin-anbud mot relevante Brreg-bedrifter (bransje + kommune), og skriver ferdige e-postutkast. **Sender ingenting** — dette er bare tekst du kan lese gjennom og eventuelt kopiere inn i din egen e-postklient manuelt.

**Kjøring:**
```
python generate_email_drafts.py
```

**Genererer:** `email_drafts.md` — ett avsnitt per anbud, med hvem det foreslås sendt til og et ferdig utkast.

**Hvordan matchingen fungerer:**
1. Anbudets CPV-kode (bransjekode i offentlige anskaffelser) oversettes til tilsvarende næringskode(r) (NACE, brukt av Brreg) via en håndlaget oversettelsestabell (det finnes ingen offisiell CPV↔NACE-nøkkel).
2. Bedrifter i samme kommune som oppdragsgiveren prioriteres. Finnes ingen, velges et tilfeldig utvalg blant nasjonale bransjetreff (for variasjon mellom ulike anbud).
3. Hver bedrift får tildelt maks **ett** anbud totalt, slik at ingen får flere separate e-poster (matcher "send én lead som smakebit"-modellen).

**Kjente begrensninger:**
- CPV→næringskode-oversettelsen er grovkornet for enkelte koder — noen sjeldnere CPV-grupper kan fortsatt gi upresise bransjetreff. Sjekk alltid gjennom utkastene før du sender noe.
- Geografisk matching er enkel tekstsammenligning (kommune-navn), ikke en presis kommunenummer-kobling.

## Rekkefølge og oppdatering

Kjør scriptene i rekkefølgen 1 → 2 → 3, gjerne én gang i uka for ferske leads. Steg 2 (Brreg) tar lengst tid og trenger ikke kjøres like ofte som steg 1 og 3, siden bedriftslisten endrer seg sjelden.

## Filoversikt

| Fil | Hva den er |
|---|---|
| `doffin_fetch.py`, `brreg_fetch.py`, `generate_email_drafts.py`, `merge_brreg_ranges.py` | Scriptene (i git) |
| `doffin_leads.md` | Lesbar liste over ukens anbud |
| `email_drafts.md` | Ferdige e-postutkast, ikke sendt |
| `*.csv`, `*.json` | Rådata/mellomlagring (ikke i git, regenereres av scriptene) |

## Status

- Doffin-henting: ferdig testet, fungerer nasjonalt
- Brreg-henting: fungerer, håndterer nå både små (1-20) og mellomstore (21-100) bedrifter
- E-postutkast: fungerer, forbedret flere ganger (bransjematch, variasjon, én e-post per bedrift)
- Utsending: **ikke bygget** — alt er manuelt fra her. Ingenting er automatisk sendt til noen.

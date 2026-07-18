# Prompt: Plan neste fase av Doffin Leads

Kopier teksten under (alt etter linjen) inn i en ny planleggingsøkt (f.eks. Claude Code i Plan-modus) for å få en konkret, prioritert plan.

---

Jeg har et fungerende Python-pipeline-prosjekt ("Doffin Leads") som finner offentlige anbud i Norge (via Doffin API) og matcher dem mot små/mellomstore bedrifter (via Brønnøysundregisteret) som kan være interessert i å levere tilbud. Målet er å sende en bedrift ett relevant anbud gratis som smakebit, og tilby abonnement for flere.

## Dagens status

Tre Python-script kjører sekvensielt:
1. `doffin_fetch.py` — henter alle aktive offentlige anbud nasjonalt fra Doffin sitt Public API, med full detalj (tittel, beskrivelse, oppdragsgiver, kontaktperson, tilbudsfrist, spørsmålsfrist, estimert verdi, CPV-koder primær+tillegg). Lagres til CSV + en lesbar Markdown-fil.
2. `brreg_fetch.py` — henter små og mellomstore bedrifter (konfigurerbart ansatte-intervall) fra Brønnøysundregisterets åpne API, beholder kun de med registrert e-post (~30% av alle). Lagres til CSV.
3. `generate_email_drafts.py` — matcher hvert anbud mot relevante bedrifter basert på bransje (CPV-kode oversatt til næringskode via en håndlaget tabell) og kommune, og skriver ferdige e-postutkast til en Markdown-fil. Sender ingenting selv. En egen `kontaktet.csv`-logg (oppdatert av `marker_sendt.py` etter faktisk utsending) sikrer at ingen bedrift kontaktes to ganger.

Alt kjøres i dag fra kommandolinjen, leses/redigeres som CSV/Markdown-filer i en tekstredigerer. Alt er gratis å drifte (ingen betalte API-er eller tjenester).

## Hva jeg vil bygge nå

**1. En frontend for å håndtere dataen** — i stedet for å bla i CSV-filer og Markdown-utkast manuelt. Skal kunne:
- Vise alle anbud og deres matchede bedrifter i en oversiktlig liste/tabell
- Filtrere/sortere på bransje, kommune, frist, verdi, score (se under)
- Vise/redigere e-postutkast og markere som sendt (skal kalle `marker_sendt.py`-logikken, ikke duplisere den)
- Vise kontaktet-historikk

**2. En matchscore** — hvor godt en gitt bedrift passer til et gitt anbud. Finn og foreslå konkrete parametere for denne scoren, f.eks. (vurder disse og legg til flere du mener er relevante):
- Presisjon på bransjematch (eksakt næringskode-treff vs. bred divisjon-fallback)
- Geografisk nærhet (samme kommune > samme fylke > landsdekkende)
- Kontraktstype vs. bedriftens registrerte hovedaktivitet
- Tidligere kontaktet samme bedrift med lignende anbud (unngå å foreslå for likt gjentatte ganger)

**3. En realismescore** — hvor sannsynlig er det at *denne konkrete bedriften* faktisk kan/bør ta *denne konkrete kontrakten*, uavhengig av bransjematch. Finn og foreslå konkrete parametere, f.eks.:
- Antall ansatte vs. kontraktens estimerte størrelse (en bedrift med 2 ansatte bør trolig ikke få forslag om en 76 mill. kr totalentreprise alene)
- Tid til frist vs. realistisk tid til å forberede et tilbud av denne størrelsen
- Bedriftens alder/etableringsdato (Brreg har registreringsdato) som grov proxy for erfaring/stabilitet
- Om bedriften har regnskapstall tilgjengelig via Brregs regnskapsregister (omsetning vs. kontraktsverdi, hvis dette er verdt å hente — vurder om det er et eget gratis API å koble på)
- Avstand fra bedriftens adresse til leveringsstedet (praktisk gjennomførbarhet)
- Selskapsform (AS vs. enkeltpersonforetak) som grov kapasitetsindikator

## Rammer og krav

- **Alt må fortsatt være gratis** — ingen betalte APIer, hosting-tjenester, eller SaaS-abonnement. Frontend må kunne kjøre lokalt eller på en gratis hosting-løsning.
- Dataen inneholder reelle bedrifters kontaktinformasjon (navn, e-post, telefon) — skal ikke publiseres offentlig eller eksponeres uten videre.
- Ikke bygg noe som sender e-post automatisk — utsending er og skal fortsatt være en bevisst, manuell handling fra meg.
- Vurder om scorene bør beregnes i Python (utvidelse av `generate_email_drafts.py` eller et nytt script) og leses av frontenden, fremfor å dupliseres i frontend-kode.

## Hva jeg vil ha ut av denne planleggingen

En konkret, prioritert plan (ikke kode ennå) som dekker:
1. Anbefalt frontend-arkitektur/tech-stack (gratis-vennlig)
2. Datamodell for match- og realismescore, med endelig parameterliste og hvordan hver enkelt hentes/beregnes
3. Hvordan scorene vises/brukes i UI-et (f.eks. sortering, fargekoding, terskler)
4. Hvilke av dagens kjente svakheter (grovkornet bransjematching for enkelte CPV-koder, ~30% e-postdekning, ren tekst-basert kommunematching) som bør fikses før eller sammen med dette arbeidet
5. Rekkefølge/faser — hva bygges først for raskest mulig å få noe brukbart å teste

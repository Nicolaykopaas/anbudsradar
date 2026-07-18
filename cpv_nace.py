"""
Shared CPV (offentlige anskaffelser) -> NACE (norsk naeringskode) crosswalk.
Delt mellom generate_email_drafts.py og scoring.py sa den ikke er duplisert
to steder.

Det finnes ingen offisiell CPV<->NACE-nokkel - dette er en handbygget
tabell, justert etter ekte treff i Doffin-data (2026-07-18/19).

Designregel: for VARE-/utstyrs-CPV-koder mappes mot bransjen som LEVERER
varen (produsent/grossist), ikke bransjen som BRUKER den - f.eks. skal en
"sanitetsmateriell"-anskaffelse na medisinske grossister, ikke tannleger.
"""

# CPV (4-sifret gruppe) -> NACE, sjekkes FOR 2-sifret divisjon under.
# Nodvendig for CPV-divisjoner som blander helt ulike reelle bransjer
# (f.eks. divisjon 39 dekker bade mobler OG renholdsprodukter).
CPV_GROUP_TO_NACE = {
    "3980": ["20", "46"],   # renholdsprodukter -> kjemisk produksjon/engros, ikke mobler
    "9240": ["63"],         # pressetjenester -> informasjonstjenester, ikke kultur/fritid
    "7962": ["78"],         # vikartjenester -> utleie av arbeidskraft
    "7963": ["78"],         # ovrig personellformidling
    "7971": ["80"],         # sikkerhetsovervaking -> vakttjeneste
    "7940": ["70"],         # evaluering/utredning -> bedriftsradgivning
    "7941": ["70", "82"],   # konsulent innen anskaffelser -> radgivning/adm.stotte
    "9091": ["81"],         # renholdstjenester -> rengjoringsvirksomhet
    "9062": ["81"],         # snorydding/broyting -> rengjorings-/eiendomsdrift
    "9051": ["38"],         # avfallsbehandling
    "9050": ["38"],         # avhending av utstyr -> avfall/gjenvinning
    "9040": ["37"],         # VA-tjenester -> avlopsrensing
    "3314": ["46.46", "32"],  # dentale/medisinske forbruksvarer -> apotek/medisinsk engros
}

# CPV (2-sifret divisjon) -> NACE (divisjon eller mer spesifikk kode).
CPV_TO_NACE = {
    "09": ["06", "19", "35"],
    "14": ["05", "07", "08"],
    "15": ["10", "11"],
    "18": ["14"],
    "19": ["13", "15"],
    "22": ["18"],
    "24": ["20"],
    "30": ["26", "46", "62"],
    "31": ["27"],
    "32": ["26", "61"],
    "33": ["32", "46.4"],
    "34": ["45", "29", "30"],
    "35": ["25", "26", "27", "28", "80"],
    "37": ["32"],
    "38": ["26", "32.5"],
    "39": ["31"],
    "41": ["36"],
    "42": ["28"],
    "43": ["28"],
    "44": ["23", "24", "25", "43"],
    "45": ["41", "42", "43"],
    "48": ["62"],
    "50": ["43", "33", "45", "95"],
    "51": ["43"],
    "55": ["55", "56"],
    "60": ["49", "52", "53"],
    "63": ["52"],
    "64": ["61"],
    "65": ["35", "36"],
    "66": ["64", "65", "66"],
    "70": ["68"],
    "71": ["71"],
    "72": ["62", "63"],
    "73": ["70", "72", "74"],
    "75": ["84"],
    "76": ["06", "09"],
    "77": ["01", "02"],
    "79": ["69", "70", "73", "74", "78", "80", "81", "82"],
    "80": ["85"],
    "85": ["86", "87", "88"],
    "90": ["37", "38", "39", "49", "81"],
    "92": ["90", "91", "92", "93"],
    "98": ["43", "81", "95"],
}


def nace_divisions_for_cpv(cpv_code) -> tuple[list[str], str]:
    """Returnerer (nace-koder, presisjon) der presisjon er 'gruppe' (presist
    CPV_GROUP_TO_NACE-treff) eller 'divisjon' (bredere CPV_TO_NACE-fallback)."""
    if not cpv_code or str(cpv_code) == "nan":
        return [], ""
    cpv8 = str(int(float(cpv_code))).zfill(8)
    if cpv8[:4] in CPV_GROUP_TO_NACE:
        return CPV_GROUP_TO_NACE[cpv8[:4]], "gruppe"
    if cpv8[:2] in CPV_TO_NACE:
        return CPV_TO_NACE[cpv8[:2]], "divisjon"
    return [], ""


def matches_nace(naeringskode, divisions: list[str]) -> bool:
    if not isinstance(naeringskode, str) or not divisions:
        return False
    return any(naeringskode.startswith(d) for d in divisions)

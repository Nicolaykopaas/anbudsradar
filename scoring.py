"""
Match- og realismescore for et lead(anbud)-bedrift-par.

- Matchscore: hvor godt bransjen/geografien passer.
- Realismescore: hvor sannsynlig det er at akkurat denne bedriften kan/bor
  ta akkurat denne kontrakten, uavhengig av bransjematch.

Begge er 0-100. All beregning skjer her - frontend (app.py) skal bare lese
det ferdige resultatet, aldri regne selv.
"""

from datetime import date, datetime
from math import radians, sin, cos, asin, sqrt


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def match_bransje_score(presisjon: str) -> float:
    return 1.0 if presisjon == "gruppe" else 0.6 if presisjon == "divisjon" else 0.0


def match_geo_score(lead_kommunenummer, biz_kommunenummer) -> float:
    lead_k = str(lead_kommunenummer) if pd_notna(lead_kommunenummer) else ""
    biz_k = str(biz_kommunenummer) if pd_notna(biz_kommunenummer) else ""
    if not lead_k or not biz_k:
        return 0.2
    if lead_k == biz_k:
        return 1.0
    if lead_k[:2] == biz_k[:2]:
        return 0.55
    return 0.2


def pd_notna(v) -> bool:
    """Liten hjelper for a unnga a dra inn hele pandas her bare for na-sjekk."""
    if v is None:
        return False
    if isinstance(v, float) and v != v:  # NaN != NaN
        return False
    return str(v).strip() not in ("", "nan", "None")


def match_score(presisjon: str, lead_kommunenummer, biz_kommunenummer) -> dict:
    # Merk: en tidligere "repetisjon/variasjon"-komponent er fjernet herfra -
    # den var alltid 1.0 (kontaktet.csv ekskluderer allerede alle en gang
    # kontaktet, sa det var ingen reell variasjon a male) og blaste opp
    # scoren med et konstant, misvisende tillegg. Bransje+geo er det
    # matchscoren faktisk maler i dag.
    bransje = match_bransje_score(presisjon)
    geo = match_geo_score(lead_kommunenummer, biz_kommunenummer)
    score = 100 * (0.6 * bransje + 0.4 * geo)
    if geo == 1.0:
        geo_label = "samme kommune"
    elif geo == 0.55:
        geo_label = "samme fylke"
    else:
        geo_label = "kun nasjonalt"
    tier = "Sterk" if score >= 75 else "Middels" if score >= 45 else "Svak"
    return {
        "match_score": round(score, 1),
        "match_tier": tier,
        "match_bransje": bransje,
        "match_geo": geo,
        "match_geo_label": geo_label,
    }


def realism_size_score(estimert_verdi, antall_ansatte) -> tuple[float, str]:
    if not pd_notna(estimert_verdi) or not pd_notna(antall_ansatte) or float(antall_ansatte) <= 0:
        return 0.7, ""
    verdi = float(estimert_verdi)
    ansatte = float(antall_ansatte)
    per_ansatt = verdi / ansatte
    TAK = 4_000_000  # NOK per ansatt - over dette skaleres scoren ned
    if per_ansatt <= TAK:
        return 1.0, ""
    score = _clamp(1.0 - (per_ansatt - TAK) / (TAK * 4), lo=0.2)
    flagg = f"Stor kontrakt ({verdi:,.0f} kr) for {ansatte:.0f} ansatte".replace(",", " ")
    return score, flagg


def realism_time_score(dager_igjen) -> tuple[float, str]:
    if dager_igjen is None:
        return 0.7, ""
    if dager_igjen < 0:
        return 0.1, "Fristen har passert"
    # storrelses-uavhengig enkel terskel (kan finpusses senere): 20 dager
    MIN_DAGER = 20
    if dager_igjen >= MIN_DAGER:
        return 1.0, ""
    score = _clamp(0.1 + 0.9 * (dager_igjen / MIN_DAGER))
    flagg = f"Kun {dager_igjen} dager til frist" if dager_igjen <= 10 else ""
    return score, flagg


def realism_age_score(stiftelsesdato, registreringsdato) -> tuple[float, str]:
    dato_str = stiftelsesdato if pd_notna(stiftelsesdato) else registreringsdato
    if not pd_notna(dato_str):
        return 0.7, ""
    try:
        dato = datetime.fromisoformat(str(dato_str)[:10]).date()
    except ValueError:
        return 0.7, ""
    alder_ar = (date.today() - dato).days / 365.25
    if alder_ar < 1:
        return 0.5, f"Nyregistrert bedrift ({alder_ar * 12:.0f} mnd)"
    if alder_ar < 2:
        return 0.75, ""
    return 1.0, ""


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def realism_distance_score(lead_postnr, biz_postnr, koordinater: dict) -> tuple[float, str, float | None]:
    """koordinater: postnummer (str) -> (lat, lon). Returnerer (score, flagg, km)."""
    lead_k = koordinater.get(str(lead_postnr).zfill(4)) if pd_notna(lead_postnr) else None
    biz_k = koordinater.get(str(biz_postnr).zfill(4)) if pd_notna(biz_postnr) else None
    if not lead_k or not biz_k:
        return 0.7, "", None

    km = haversine_km(lead_k[0], lead_k[1], biz_k[0], biz_k[1])
    if km <= 30:
        score = 1.0
    elif km <= 300:
        score = _clamp(1.0 - (km - 30) / 270 * 0.6, lo=0.4)  # 1.0 -> 0.4 mellom 30-300 km
    else:
        score = _clamp(0.4 - (km - 300) / 1000 * 0.2, lo=0.2)  # 0.4 -> 0.2 videre utover
    flagg = f"{km:.0f} km unna" if km > 150 else ""
    return score, flagg, round(km, 0)


def realism_orgform_score(organisasjonsform, estimert_verdi) -> tuple[float, str]:
    STOR_KONTRAKT = 5_000_000
    if not pd_notna(estimert_verdi) or float(estimert_verdi) < STOR_KONTRAKT:
        return 1.0, ""
    if organisasjonsform in ("AS", "ASA"):
        return 1.0, ""
    if organisasjonsform in ("ENK", "DA", "ANS"):
        return 0.7, f"Stor kontrakt for et {organisasjonsform}"
    return 0.85, ""


def realism_score(estimert_verdi, antall_ansatte, dager_igjen, stiftelsesdato,
                   registreringsdato, organisasjonsform, lead_postnr=None,
                   biz_postnr=None, koordinater: dict | None = None) -> dict:
    size, flagg_size = realism_size_score(estimert_verdi, antall_ansatte)
    time_, flagg_time = realism_time_score(dager_igjen)
    age, flagg_age = realism_age_score(stiftelsesdato, registreringsdato)
    orgform, flagg_orgform = realism_orgform_score(organisasjonsform, estimert_verdi)
    distance, flagg_distance, km = realism_distance_score(lead_postnr, biz_postnr, koordinater or {})

    # Storrelse (kan bedriften i det hele tatt ta jobben) og avstand (kan de
    # praktisk utfore den der) er de to viktigste - vekter derfor tyngst.
    score = 100 * (0.30 * size + 0.20 * distance + 0.25 * time_ + 0.15 * age + 0.10 * orgform)
    tier = "Realistisk" if score >= 70 else "Usikker" if score >= 40 else "Urealistisk"
    flagg = [f for f in (flagg_size, flagg_distance, flagg_time, flagg_age, flagg_orgform) if f]

    return {
        "realism_score": round(score, 1),
        "realism_tier": tier,
        "realism_size": size,
        "realism_distance": distance,
        "realism_distance_km": km,
        "realism_time": time_,
        "realism_age": age,
        "realism_orgform": orgform,
        "flagg": "; ".join(flagg),
    }

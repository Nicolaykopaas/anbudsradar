"""
Match- og realismescore for et lead(anbud)-bedrift-par.

- Matchscore: hvor godt bransjen/geografien passer.
- Realismescore: hvor sannsynlig det er at akkurat denne bedriften kan/bor
  ta akkurat denne kontrakten, uavhengig av bransjematch.

Begge er 0-100. All beregning skjer her - frontend (app.py) skal bare lese
det ferdige resultatet, aldri regne selv.
"""

from datetime import date, datetime


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


def match_score(presisjon: str, lead_kommunenummer, biz_kommunenummer, repetition: float = 1.0) -> dict:
    bransje = match_bransje_score(presisjon)
    geo = match_geo_score(lead_kommunenummer, biz_kommunenummer)
    score = 100 * (0.5 * bransje + 0.35 * geo + 0.15 * repetition)
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
                   registreringsdato, organisasjonsform) -> dict:
    size, flagg_size = realism_size_score(estimert_verdi, antall_ansatte)
    time_, flagg_time = realism_time_score(dager_igjen)
    age, flagg_age = realism_age_score(stiftelsesdato, registreringsdato)
    orgform, flagg_orgform = realism_orgform_score(organisasjonsform, estimert_verdi)

    score = 100 * (0.35 * size + 0.30 * time_ + 0.20 * age + 0.15 * orgform)
    tier = "Realistisk" if score >= 70 else "Usikker" if score >= 40 else "Urealistisk"
    flagg = [f for f in (flagg_size, flagg_time, flagg_age, flagg_orgform) if f]

    return {
        "realism_score": round(score, 1),
        "realism_tier": tier,
        "realism_size": size,
        "realism_time": time_,
        "realism_age": age,
        "realism_orgform": orgform,
        "flagg": "; ".join(flagg),
    }

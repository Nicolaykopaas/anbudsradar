"""
AnbudsRadar - dashbord. Kjor lokalt, apnes i nettleseren:

    pip install streamlit
    streamlit run app.py

Leser kun ferdig beregnede filer (lead_bedrift_scores.csv fra
compute_scores.py, kontaktet.csv). Ingen scoring skjer her. "Marker som
sendt" kaller den eksisterende marker_sendt.append_to_kontaktet-funksjonen
direkte - ingenting sendes noe sted, det oppdaterer kun loggen.
"""

import os

import pandas as pd
import streamlit as st

from marker_sendt import append_to_kontaktet

st.set_page_config(page_title="AnbudsRadar", layout="wide")


@st.cache_data
def last_scores(mtime: float) -> pd.DataFrame:
    return pd.read_csv("lead_bedrift_scores.csv")


def last_data() -> pd.DataFrame:
    try:
        mtime = os.path.getmtime("lead_bedrift_scores.csv")
    except FileNotFoundError:
        st.error("Fant ikke lead_bedrift_scores.csv. Kjor: python compute_scores.py forst.")
        st.stop()
    return last_scores(mtime)


st.title("AnbudsRadar")
st.caption("Ingenting sendes herfra — kun oversikt og utkast.")

df = last_data()  # allerede filtrert bort kontaktede bedrifter i compute_scores.py

STORRELSE_GRENSER = {
    "Alle størrelser": (0, float("inf")),
    "Små, under 5 mill kr": (0, 5_000_000),
    "Middels, 5-50 mill kr": (5_000_000, 50_000_000),
    "Store, over 50 mill kr": (50_000_000, float("inf")),
}

with st.expander("Filtre — hva som teller for match- og realismescoren", expanded=True):
    r1c1, r1c2, r1c3 = st.columns(3)
    with r1c1:
        geo_valg = st.selectbox("Geografisk treff", ["Alle", "Minst samme fylke", "Kun samme kommune"])
    with r1c2:
        kun_presis_bransje = st.checkbox("Kun presis bransjematch")
    with r1c3:
        kun_etablert = st.checkbox("Kun etablerte bedrifter, minst 2 år")

    r2c1, r2c2, r2c3 = st.columns(3)
    with r2c1:
        storrelse_valg = st.selectbox("Oppdragsstørrelse", list(STORRELSE_GRENSER.keys()))
    with r2c2:
        vanskelighet_valg = st.selectbox("Vanskelighetsgrad", ["Alle", "Lett", "Middels", "Vanskelig"])
    with r2c3:
        maks_avstand = st.slider("Maks avstand i km", 0, 800, 800, help="Ukjent avstand vises alltid")

    bransje_filter = st.text_input("Fritekst: bransje")
    kommune_filter = st.text_input("Fritekst: kommune")

filtered = df.copy()
if geo_valg == "Kun samme kommune":
    filtered = filtered[filtered["match_geo_label"] == "samme kommune"]
elif geo_valg == "Minst samme fylke":
    filtered = filtered[filtered["match_geo_label"].isin(["samme kommune", "samme fylke"])]
if kun_presis_bransje:
    filtered = filtered[filtered["match_bransje"] >= 1.0]
if kun_etablert:
    filtered = filtered[filtered["realism_age"] >= 1.0]

storrelse_min, storrelse_maks = STORRELSE_GRENSER[storrelse_valg]
filtered = filtered[(filtered["lead_verdi"] >= storrelse_min) & (filtered["lead_verdi"] <= storrelse_maks)]

vanskelighet_map = {"Lett": "Realistisk", "Middels": "Usikker", "Vanskelig": "Urealistisk"}
if vanskelighet_valg != "Alle":
    filtered = filtered[filtered["realism_tier"] == vanskelighet_map[vanskelighet_valg]]

filtered = filtered[filtered["realism_distance_km"].isna() | (filtered["realism_distance_km"] <= maks_avstand)]
if bransje_filter:
    filtered = filtered[filtered["bransje"].str.contains(bransje_filter, case=False, na=False)]
if kommune_filter:
    filtered = filtered[filtered["kommune"].str.contains(kommune_filter, case=False, na=False)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Anbud", filtered["doffin_id"].nunique())
m2.metric("Foreslåtte bedrifter", len(filtered))
m3.metric("Sterke matcher", int((filtered["match_tier"] == "Sterk").sum()))
m4.metric("Realistiske par", int((filtered["realism_tier"] == "Realistisk").sum()))

tab_oversikt, tab_kontaktet = st.tabs(["Anbud og matcher", "Kontaktet-historikk"])

with tab_oversikt:
    leads = filtered[["doffin_id", "lead_tittel", "lead_oppdragsgiver", "lead_verdi", "lead_frist"]]\
        .drop_duplicates("doffin_id").sort_values("lead_frist").reset_index(drop=True)

    col_venstre, col_hoyre = st.columns(2, gap="medium")

    with col_venstre:
        st.subheader("Anbud")
        valgt = st.dataframe(
            leads,
            height=520,
            use_container_width=True,
            column_config={
                "doffin_id": None,
                "lead_tittel": "Tittel",
                "lead_oppdragsgiver": "Oppdragsgiver",
                "lead_verdi": st.column_config.NumberColumn("Verdi i kr", format="%.0f"),
                "lead_frist": "Frist",
            },
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="lead_tabell",
        )
        valgte_rader = valgt.selection.rows if valgt and valgt.selection else []
        valgt_id = leads.iloc[valgte_rader[0]]["doffin_id"] if valgte_rader else (
            leads.iloc[0]["doffin_id"] if len(leads) else None
        )

    with col_hoyre:
        st.subheader("Anbefalte bedrifter")
        if not valgt_id:
            st.info("Ingen anbud matcher filtrene.")
        else:
            lead_rows = filtered[filtered["doffin_id"] == valgt_id].sort_values("match_score", ascending=False)
            lead = lead_rows.iloc[0]
            st.markdown(f"**{lead['lead_tittel']}**  \n"
                        f"{lead['lead_oppdragsgiver']} · {lead['lead_verdi']:,.0f} kr · frist {lead['lead_frist']}  \n"
                        f"[Se hele kunngjøringen ↗]({lead['lead_lenke']})".replace(",", " "))

            kandidater = lead_rows.head(10)
            st.dataframe(
                kandidater,
                height=340,
                use_container_width=True,
                hide_index=True,
                column_order=["navn", "bransje", "kommune", "match_tier", "realism_tier", "epost", "telefon"],
                column_config={
                    "navn": "Bedrift",
                    "bransje": "Bransje",
                    "kommune": "Kommune",
                    "match_tier": "Match",
                    "realism_tier": "Realisme",
                    "epost": "E-post",
                    "telefon": "Telefon",
                },
            )

            valgt_navn = st.selectbox("Marker en bedrift som sendt", kandidater["navn"], index=None,
                                       placeholder="Velg bedrift ...")
            if valgt_navn and st.button("Marker som sendt"):
                rad = kandidater[kandidater["navn"] == valgt_navn].iloc[0]
                append_to_kontaktet(pd.DataFrame([{
                    "orgnr": rad["orgnr"], "navn": rad["navn"], "epost": rad["epost"],
                    "doffin_id": valgt_id, "tittel": rad["lead_tittel"],
                }]))
                st.success(f"{valgt_navn} markert som kontaktet.")
                st.cache_data.clear()
                st.rerun()

with tab_kontaktet:
    try:
        kontaktet = pd.read_csv("kontaktet.csv")
        st.write(f"{len(kontaktet)} bedrifter kontaktet totalt.")
        st.dataframe(kontaktet.sort_values("dato_kontaktet", ascending=False), use_container_width=True, hide_index=True)
    except FileNotFoundError:
        st.info("Ingen er kontaktet ennå.")

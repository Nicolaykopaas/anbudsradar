"""
Doffin Leads - dashbord. Kjor lokalt, apnes i nettleseren:

    pip install streamlit
    streamlit run app.py

Leser kun ferdig beregnede filer (lead_bedrift_scores.csv fra
compute_scores.py, kontaktet.csv). Ingen scoring skjer her. "Marker som
sendt" kaller den eksisterende marker_sendt.append_to_kontaktet-funksjonen
direkte - ingenting sendes noe sted, det oppdaterer kun loggen.
"""

import pandas as pd
import streamlit as st

from marker_sendt import append_to_kontaktet

st.set_page_config(page_title="Doffin Leads", layout="wide")


@st.cache_data
def last_scores(mtime: float) -> pd.DataFrame:
    return pd.read_csv("lead_bedrift_scores.csv")


def last_data() -> pd.DataFrame:
    import os
    try:
        mtime = os.path.getmtime("lead_bedrift_scores.csv")
    except FileNotFoundError:
        st.error("Fant ikke lead_bedrift_scores.csv. Kjor: python compute_scores.py forst.")
        st.stop()
    return last_scores(mtime)


st.title("📋 Doffin Leads")
st.caption("Offentlige anbud matchet mot bedrifter — ingenting sendes herfra, kun oversikt og utkast.")

df = last_data()  # allerede filtrert bort kontaktede bedrifter i compute_scores.py

k1, k2, k3, k4 = st.columns(4)
k1.metric("Anbud", df["doffin_id"].nunique())
k2.metric("Foreslatte bedrifter", len(df))
k3.metric("Sterke matcher", int((df["match_tier"] == "Sterk").sum()))
k4.metric("Realistiske par", int((df["realism_tier"] == "Realistisk").sum()))

tab_oversikt, tab_kontaktet = st.tabs(["Anbud og matcher", "Kontaktet-historikk"])

with tab_oversikt:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_match = st.slider("Minimum matchscore", 0, 100, 0)
    with col2:
        min_realism = st.slider("Minimum realismescore", 0, 100, 0)
    with col3:
        bransje_filter = st.text_input("Filtrer pa bransje (fritekst)")
    with col4:
        kommune_filter = st.text_input("Filtrer pa kommune")

    filtered = df[(df["match_score"] >= min_match) & (df["realism_score"] >= min_realism)]
    if bransje_filter:
        filtered = filtered[filtered["bransje"].str.contains(bransje_filter, case=False, na=False)]
    if kommune_filter:
        filtered = filtered[filtered["kommune"].str.contains(kommune_filter, case=False, na=False)]

    st.write(f"{filtered['doffin_id'].nunique()} anbud, {len(filtered)} bedrift-treff (av {df['doffin_id'].nunique()} anbud totalt).")

    leads = filtered[["doffin_id", "lead_tittel", "lead_oppdragsgiver", "lead_verdi", "lead_frist"]]\
        .drop_duplicates("doffin_id").sort_values("lead_frist").reset_index(drop=True)

    st.caption("Klikk pa en rad i tabellen for a se anbefalte bedrifter for det anbudet.")
    valgt = st.dataframe(
        leads,
        use_container_width=True,
        column_config={
            "doffin_id": "Anbud-ID",
            "lead_tittel": "Tittel",
            "lead_oppdragsgiver": "Oppdragsgiver",
            "lead_verdi": st.column_config.NumberColumn("Verdi (kr)", format="%.0f"),
            "lead_frist": "Frist",
        },
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="lead_tabell",
    )
    valgte_rader = valgt.selection.rows if valgt and valgt.selection else []
    valgt_id = leads.iloc[valgte_rader[0]]["doffin_id"] if valgte_rader else None

    if valgt_id:
        st.divider()
        lead_rows = filtered[filtered["doffin_id"] == valgt_id].sort_values("match_score", ascending=False)
        lead = lead_rows.iloc[0]
        st.subheader(lead["lead_tittel"])
        st.write(f"**Oppdragsgiver:** {lead['lead_oppdragsgiver']} | **Verdi:** {lead['lead_verdi']:,.0f} kr | **Frist:** {lead['lead_frist']}".replace(",", " "))
        st.write(f"[Se hele kunngjoringen]({lead['lead_lenke']})")

        def vis(v, fallback="ikke oppgitt"):
            return fallback if pd.isna(v) else v

        st.write("**Kandidat-bedrifter (sortert etter matchscore):**")
        for _, rad in lead_rows.head(10).iterrows():
            tier_farge = {"Sterk": "🟢", "Middels": "🟡", "Svak": "🔴"}.get(rad["match_tier"], "")
            realism_farge = {"Realistisk": "🟢", "Usikker": "🟡", "Urealistisk": "🔴"}.get(rad["realism_tier"], "")
            with st.expander(f"{tier_farge} {rad['navn']} — match {rad['match_score']:.0f} ({rad['match_tier']}) | realisme {realism_farge} {rad['realism_score']:.0f} ({rad['realism_tier']})"):
                st.write(f"Bransje: {rad['bransje']} | Kommune: {rad['kommune']} | Ansatte: {vis(rad['antall_ansatte'])}")
                st.write(f"E-post: {vis(rad['epost'])} | Telefon: {vis(rad['telefon'])}")
                if pd.notna(rad.get("flagg")) and str(rad.get("flagg")).strip():
                    st.warning(rad["flagg"])
                if st.button("Marker som sendt", key=f"sendt_{valgt_id}_{rad['orgnr']}"):
                    append_to_kontaktet(pd.DataFrame([{
                        "orgnr": rad["orgnr"], "navn": rad["navn"], "epost": rad["epost"],
                        "doffin_id": valgt_id, "tittel": rad["lead_tittel"],
                    }]))
                    st.success(f"{rad['navn']} markert som kontaktet.")
                    st.cache_data.clear()
                    st.rerun()

with tab_kontaktet:
    try:
        kontaktet = pd.read_csv("kontaktet.csv")
        st.write(f"{len(kontaktet)} bedrifter kontaktet totalt.")
        st.dataframe(kontaktet.sort_values("dato_kontaktet", ascending=False), use_container_width=True, hide_index=True)
    except FileNotFoundError:
        st.info("Ingen er kontaktet ennå.")

# -*- coding: utf-8 -*-
"""
VaxSuivi-Lemba — Tableau de bord de suivi de la collecte de données
Mémoire : « Facteurs associés à l'hésitation vaccinale chez les parents ou
tuteurs d'enfants de 0 à 23 mois en vaccination de routine — Zone de Santé
de Lemba, Kinshasa (RDC), 2026 »

Ce tableau de bord NE calcule ni ne publie aucun résultat scientifique final
du mémoire. Il sert uniquement à suivre l'avancement et la qualité de la
collecte pendant le terrain (progression par aire de santé et par enquêteur,
anomalies de saisie, durée des entretiens). Toute prévalence affichée est
explicitement signalée comme provisoire.
"""
import io
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from data_quality import (
    AIRES_SANTE,
    ENQUETEURS,
    add_sequential_numbers,
    apply_filters,
    eligibility_rate,
    hesitation_prevalence,
    normalize_columns,
    quality_report,
)
from kobo_api import KoboAPIError, fetch_submissions

st.set_page_config(
    page_title="VaxSuivi-Lemba",
    page_icon="💉",
    layout="wide",
)

st.title("💉 VaxSuivi-Lemba")
st.caption(
    "Suivi de la collecte — Hésitation vaccinale chez les parents/tuteurs "
    "d'enfants 0-23 mois, Zone de Santé de Lemba (Kinshasa, 2026)"
)

# ------------------------------------------------------------------
# SOURCE DES DONNÉES
# ------------------------------------------------------------------
st.sidebar.header("Source des données")
source_mode = st.sidebar.radio(
    "Charger les données depuis :",
    ["API KoboToolbox (live)", "Fichier exporté (CSV / XLSX)"],
    index=0,
)

df_raw = pd.DataFrame()

if source_mode == "API KoboToolbox (live)":
    st.sidebar.markdown(
        "Renseignez vos identifiants Kobo, ou configurez-les une fois pour "
        "toutes dans `.streamlit/secrets.toml` (voir le README)."
    )
    default_server = st.secrets.get("kobo", {}).get("server_url", "https://kf.kobotoolbox.org")
    default_uid = st.secrets.get("kobo", {}).get("asset_uid", "")
    default_token = st.secrets.get("kobo", {}).get("api_token", "")

    server_url = st.sidebar.text_input("URL du serveur Kobo", value=default_server)
    asset_uid = st.sidebar.text_input("Identifiant du formulaire (asset UID)", value=default_uid)
    api_token = st.sidebar.text_input("Jeton d'API", value=default_token, type="password")

    if st.sidebar.button("🔄 Actualiser les données", type="primary"):
        st.cache_data.clear()

    @st.cache_data(ttl=300, show_spinner="Récupération des soumissions depuis Kobo...")
    def _load_from_kobo(server_url, asset_uid, api_token):
        return fetch_submissions(server_url, asset_uid, api_token)

    if asset_uid and api_token:
        try:
            df_raw = _load_from_kobo(server_url, asset_uid, api_token)
        except KoboAPIError as e:
            st.error(f"Impossible de récupérer les données Kobo : {e}")
    else:
        st.info(
            "Renseignez l'identifiant du formulaire et le jeton d'API dans la "
            "barre latérale (ou `.streamlit/secrets.toml`) pour charger les "
            "soumissions en direct."
        )

else:
    uploaded = st.sidebar.file_uploader(
        "Export Kobo (CSV ou XLSX)", type=["csv", "xlsx"]
    )
    if uploaded is not None:
        if uploaded.name.endswith(".csv"):
            df_raw = pd.read_csv(uploaded)
        else:
            df_raw = pd.read_excel(uploaded)
    else:
        st.info("Chargez un export Kobo (menu Kobo : Data > Downloads) pour commencer.")

if df_raw.empty:
    st.stop()

df = normalize_columns(df_raw)
df = add_sequential_numbers(df)  # N_FORMULAIRE / N_MENAGE, calculés sur l'ensemble des
                                  # soumissions avant filtrage, pour rester stables

# ------------------------------------------------------------------
# FILTRES
# ------------------------------------------------------------------
st.sidebar.header("Filtres")

aires_present = sorted(df["ID04"].dropna().unique().tolist()) if "ID04" in df.columns else []
aires_sel = st.sidebar.multiselect(
    "Aire de santé",
    options=aires_present,
    format_func=lambda x: AIRES_SANTE.get(x, x),
)

enq_present = sorted(df["ID03"].dropna().unique().tolist()) if "ID03" in df.columns else []
enq_sel = st.sidebar.multiselect(
    "Enquêteur",
    options=enq_present,
    format_func=lambda x: ENQUETEURS.get(x, x),
)

date_min = date_max = None
if "ID02" in df.columns:
    dates_valides = pd.to_datetime(df["ID02"], errors="coerce").dropna()
    if len(dates_valides):
        min_d, max_d = dates_valides.min().date(), dates_valides.max().date()
        date_min, date_max = st.sidebar.date_input(
            "Période de collecte",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
        )

df_f = apply_filters(df, aires=aires_sel or None, enqueteurs=enq_sel or None,
                      date_min=date_min, date_max=date_max)

echantillon_cible = st.sidebar.number_input(
    "Taille d'échantillon cible (objectif)",
    min_value=0, value=0, step=10,
    help="Renseignez l'effectif cible calculé pour le mémoire (formule de Schwartz) "
         "pour afficher le taux d'avancement global.",
)

# ------------------------------------------------------------------
# KPI PRINCIPAUX
# ------------------------------------------------------------------
qr = quality_report(df_f)
elig = eligibility_rate(df_f)
prevalence = hesitation_prevalence(df_f)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Entretiens enregistrés", qr["n_total"])
if echantillon_cible > 0:
    taux_avancement = round(qr["n_total"] / echantillon_cible * 100, 1)
    col2.metric("Avancement vs objectif", f"{taux_avancement} %", f"{qr['n_total']}/{echantillon_cible}")
else:
    col2.metric("Avancement vs objectif", "—", help="Renseigner l'effectif cible dans la barre latérale")
col3.metric("Taux éligibilité+consentement", f"{elig['taux_pct']} %" if elig["taux_pct"] is not None else "—")
col4.metric("Doublons ménage potentiels", qr["doublons_menage"])
col5.metric(
    "Durée moyenne (min)",
    qr["duree_moyenne_min"] if qr["duree_moyenne_min"] is not None else "—",
)

if "N_FORMULAIRE" in df_f.columns and not df_f.empty:
    st.caption(
        f"🔢 Numérotation séquentielle (formulaire = ménage) attribuée après "
        f"centralisation des soumissions — dernier numéro en date : "
        f"**N° {int(df['N_FORMULAIRE'].max())}** sur l'ensemble de la base "
        f"(numéros recalculés à chaque actualisation ; voir §5 du README sur la "
        f"différence avec le code unique généré sur le terrain par le formulaire Kobo)."
    )

if prevalence is not None:
    st.warning(
        f"⚠️ Prévalence provisoire d'hésitation vaccinale sur les entretiens déjà "
        f"saisis : **{prevalence} %**. Indicateur de suivi de terrain uniquement — "
        f"**ne constitue pas un résultat scientifique du mémoire**. La règle de "
        f"calcul de HESITATION et les scores composites (SCORE_CONNAISS, "
        f"SCORE_CONFIANCE, etc.) restent à finaliser après le pré-test, conformément "
        f"à l'Annexe 1 du questionnaire."
    )

st.divider()

# ------------------------------------------------------------------
# PROGRESSION PAR AIRE DE SANTÉ / ENQUÊTEUR
# ------------------------------------------------------------------
c1, c2 = st.columns(2)

with c1:
    st.subheader("Entretiens par aire de santé")
    if "ID04" in df_f.columns and not df_f.empty:
        counts = df_f["ID04"].value_counts().rename_axis("ID04").reset_index(name="n")
        counts["Aire de santé"] = counts["ID04"].map(AIRES_SANTE).fillna(counts["ID04"])
        fig = px.bar(
            counts.sort_values("n", ascending=True),
            x="n", y="Aire de santé", orientation="h",
            text="n", labels={"n": "Entretiens"},
        )
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Champ ID04 (aire de santé) absent des données chargées.")

with c2:
    st.subheader("Entretiens par enquêteur")
    if "ID03" in df_f.columns and not df_f.empty:
        counts = df_f["ID03"].value_counts().rename_axis("ID03").reset_index(name="n")
        counts["Enquêteur"] = counts["ID03"].map(ENQUETEURS).fillna(counts["ID03"])
        fig = px.bar(
            counts.sort_values("n", ascending=True),
            x="n", y="Enquêteur", orientation="h",
            text="n", labels={"n": "Entretiens"},
        )
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Champ ID03 (code enquêteur) absent des données chargées.")

# ------------------------------------------------------------------
# PROGRESSION DANS LE TEMPS
# ------------------------------------------------------------------
st.subheader("Progression de la collecte dans le temps")
if "ID02" in df_f.columns and not df_f.empty:
    tmp = df_f.copy()
    tmp["ID02"] = pd.to_datetime(tmp["ID02"], errors="coerce")
    daily = tmp.dropna(subset=["ID02"]).groupby(tmp["ID02"].dt.date).size().reset_index(name="n")
    daily.columns = ["Date", "Entretiens"]
    daily["Cumulé"] = daily["Entretiens"].cumsum()
    fig = px.bar(daily, x="Date", y="Entretiens")
    fig2 = px.line(daily, x="Date", y="Cumulé")
    fig.add_scatter(x=daily["Date"], y=daily["Cumulé"], name="Cumulé", yaxis="y2", mode="lines+markers")
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", title="Cumulé"),
        height=380, margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Champ ID02 (date d'entretien) absent des données chargées.")

st.divider()

# ------------------------------------------------------------------
# QUALITÉ DES DONNÉES
# ------------------------------------------------------------------
st.subheader("Qualité des données")
qc1, qc2 = st.columns(2)

with qc1:
    st.markdown("**Valeurs manquantes sur les champs clés (%)**")
    if qr["missing_by_field"]:
        miss_df = pd.DataFrame(
            list(qr["missing_by_field"].items()), columns=["Champ", "% manquant"]
        )
        st.dataframe(miss_df, hide_index=True, use_container_width=True)
    else:
        st.info("Champs clés non trouvés dans l'export.")

with qc2:
    st.markdown("**Alertes de terrain**")
    alerts = []
    if qr["doublons_menage"]:
        alerts.append(f"🔴 {qr['doublons_menage']} doublon(s) potentiel(s) de ménage (même aire + quartier + repère enfant).")
    if qr["entretiens_courts_lt5min"]:
        alerts.append(f"🟠 {qr['entretiens_courts_lt5min']} entretien(s) de moins de 5 minutes — à vérifier.")
    if elig.get("taux_pct") is not None and elig["taux_pct"] < 50:
        alerts.append(f"🟠 Taux d'éligibilité/consentement faible ({elig['taux_pct']} %) — vérifier le recrutement sur le terrain.")
    if not alerts:
        st.success("Aucune alerte détectée sur les critères surveillés.")
    else:
        for a in alerts:
            st.write(a)

st.divider()

# ------------------------------------------------------------------
# DONNÉES BRUTES / EXPORT
# ------------------------------------------------------------------
with st.expander("Voir / exporter les données filtrées"):
    num_cols = [c for c in ["N_FORMULAIRE", "N_MENAGE", "N_DANS_AIRE", "N_DANS_ENQUETEUR"] if c in df_f.columns]
    autres_cols = [c for c in df_f.columns if c not in num_cols]
    df_export = df_f[num_cols + autres_cols]
    st.dataframe(df_export, use_container_width=True)
    buf = io.BytesIO()
    df_export.to_csv(buf, index=False)
    st.download_button(
        "⬇️ Télécharger en CSV",
        data=buf.getvalue(),
        file_name=f"vaxsuivi_lemba_export_{date.today().isoformat()}.csv",
        mime="text/csv",
    )

st.caption(
    "VaxSuivi-Lemba — outil de suivi de terrain, pas de publication des résultats du mémoire. "
    "Données traitées localement dans la session Streamlit ; aucune donnée n'est stockée par l'application elle-même."
)

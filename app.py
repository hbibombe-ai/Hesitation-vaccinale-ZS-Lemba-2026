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
import base64
import io
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from data_quality import (
    AIRES_SANTE,
    ENQUETEURS,
    add_sequential_numbers,
    apply_filters,
    eligibility_rate,
    hesitation_prevalence,
    normalize_columns,
    quality_report,
    submission_trend_matrix,
    summary_by_aire,
    summary_by_enqueteur,
)
from kobo_api import KoboAPIError, fetch_submissions


def get_kobo_secrets() -> dict:
    """Lit la section [kobo] des secrets Streamlit sans jamais lever d'exception,
    y compris quand aucun fichier secrets.toml n'existe du tout (cas d'un premier
    déploiement non encore configuré)."""
    try:
        return dict(st.secrets.get("kobo", {}))
    except Exception:
        return {}


st.set_page_config(page_title="VaxSuivi-Lemba", page_icon="💉", layout="wide")

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {theme.SURFACE}; }}
    [data-testid="stMetric"] {{
        background-color: #ffffff;
        border: 1px solid {theme.GRIDLINE};
        border-radius: 10px;
        padding: 14px 16px 10px 16px;
    }}
    [data-testid="stMetricLabel"] {{ color: {theme.INK_SECONDARY}; }}
    [data-testid="stMetricValue"] {{ color: {theme.INK_PRIMARY}; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("💉 VaxSuivi-Lemba")
st.caption(
    "Suivi de la collecte — Hésitation vaccinale chez les parents/tuteurs "
    "d'enfants 0-23 mois, Zone de Santé de Lemba (Kinshasa, 2026)"
)


def render_hero_banner() -> None:
    """Affiche l'illustration d'en-tête (SVG) encodée en base64, pour éviter
    toute dépendance réseau externe : l'image reste 100 % autonome dans le
    dépôt et s'affiche même sans connexion internet sur le poste client."""
    svg_path = Path(__file__).parent / "assets" / "hero_hesitation.svg"
    if not svg_path.exists():
        return
    svg_b64 = base64.b64encode(svg_path.read_bytes()).decode("utf-8")
    st.markdown(
        f"""
        <div style="border-radius:18px; overflow:hidden; margin-bottom:0.6rem;
                    border:1px solid {theme.GRIDLINE}; box-shadow:0 2px 10px rgba(11,11,11,0.06);">
            <img src="data:image/svg+xml;base64,{svg_b64}" style="width:100%; display:block;" />
        </div>
        """,
        unsafe_allow_html=True,
    )


render_hero_banner()

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
    # Le serveur, l'asset UID et le jeton d'API ne sont JAMAIS saisissables dans
    # l'interface : n'importe qui ayant le lien de l'app (publique sur Streamlit
    # Community Cloud) pourrait sinon lire ou remplacer le jeton d'accès à la
    # vraie base de collecte. Ces trois valeurs ne viennent que des secrets
    # configurés par l'administrateur (.streamlit/secrets.toml en local, ou
    # "App settings > Secrets" sur Streamlit Cloud) — voir le README, §3.
    kobo_secrets = get_kobo_secrets()
    server_url = kobo_secrets.get("server_url", "")
    asset_uid = kobo_secrets.get("asset_uid", "")
    api_token = kobo_secrets.get("api_token", "")

    if st.sidebar.button("🔄 Actualiser les données", type="primary"):
        st.cache_data.clear()

    @st.cache_data(ttl=300, show_spinner="Récupération des soumissions depuis Kobo...")
    def _load_from_kobo(server_url, asset_uid, api_token):
        return fetch_submissions(server_url, asset_uid, api_token)

    if server_url and asset_uid and api_token:
        try:
            df_raw = _load_from_kobo(server_url, asset_uid, api_token)
        except KoboAPIError as e:
            st.error(f"Impossible de récupérer les données Kobo : {e}")
    else:
        st.info(
            "La connexion Kobo n'est pas encore configurée pour cette application. "
            "Un administrateur doit renseigner `server_url`, `asset_uid` et `api_token` "
            "dans les secrets de l'app (voir le README, §3) — ces informations ne sont "
            "volontairement pas saisissables ici, pour protéger l'accès à la vraie base "
            "de collecte. En attendant, utilisez l'option « Fichier exporté » ci-dessus."
        )

else:
    uploaded = st.sidebar.file_uploader("Export Kobo (CSV ou XLSX)", type=["csv", "xlsx"])
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
    "Aire de santé", options=aires_present, format_func=lambda x: AIRES_SANTE.get(x, x),
)

enq_present = sorted(df["ID03"].dropna().unique().tolist()) if "ID03" in df.columns else []
enq_sel = st.sidebar.multiselect(
    "Enquêteur", options=enq_present, format_func=lambda x: ENQUETEURS.get(x, x),
)

date_min = date_max = None
if "ID02" in df.columns:
    dates_valides = pd.to_datetime(df["ID02"], errors="coerce").dropna()
    if len(dates_valides):
        min_d, max_d = dates_valides.min().date(), dates_valides.max().date()
        date_min, date_max = st.sidebar.date_input(
            "Période de collecte", value=(min_d, max_d), min_value=min_d, max_value=max_d,
        )

df_f = apply_filters(df, aires=aires_sel or None, enqueteurs=enq_sel or None,
                      date_min=date_min, date_max=date_max)

echantillon_cible = st.sidebar.number_input(
    "Taille d'échantillon cible (objectif)",
    min_value=0, value=0, step=10,
    help="Renseignez l'effectif cible calculé pour le mémoire (formule de Schwartz) "
         "pour afficher le taux d'avancement global.",
)

qr = quality_report(df_f)
elig = eligibility_rate(df_f)
prevalence = hesitation_prevalence(df_f)

# ------------------------------------------------------------------
# KPI PRINCIPAUX
# ------------------------------------------------------------------
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Entretiens enregistrés", qr["n_total"])
if echantillon_cible > 0:
    taux_avancement = round(qr["n_total"] / echantillon_cible * 100, 1)
    col2.metric("Avancement vs objectif", f"{taux_avancement} %", f"{qr['n_total']}/{echantillon_cible}")
else:
    col2.metric("Avancement vs objectif", "—", help="Renseigner l'effectif cible dans la barre latérale")
col3.metric("Éligibilité + consentement", f"{elig['taux_pct']} %" if elig["taux_pct"] is not None else "—")
col4.metric("Doublons potentiels", qr["doublons_menage"])
col5.metric("Durée moyenne", f"{qr['duree_moyenne_min']} min" if qr["duree_moyenne_min"] is not None else "—")

jours_depuis_dernier = None
if "ID02" in df_f.columns and not df_f.empty:
    dates_valides_f = pd.to_datetime(df_f["ID02"], errors="coerce").dropna()
    if len(dates_valides_f):
        jours_depuis_dernier = (pd.Timestamp(date.today()) - dates_valides_f.max()).days
col6.metric(
    "Jours depuis dernière soumission",
    jours_depuis_dernier if jours_depuis_dernier is not None else "—",
)

if "N_FORMULAIRE" in df_f.columns and not df_f.empty:
    st.caption(
        f"🔢 Numérotation séquentielle (formulaire = ménage) attribuée après centralisation des "
        f"soumissions — dernier numéro en date : **N° {int(df['N_FORMULAIRE'].max())}** sur "
        f"l'ensemble de la base (recalculée à chaque actualisation — voir §5 du README)."
    )

if prevalence is not None:
    st.warning(
        f"⚠️ Prévalence provisoire d'hésitation vaccinale sur les entretiens déjà saisis : "
        f"**{prevalence} %**. Indicateur de suivi de terrain uniquement — **ne constitue pas un "
        f"résultat scientifique du mémoire**. La règle de calcul de HESITATION et les scores "
        f"composites (SCORE_CONNAISS, SCORE_CONFIANCE, etc.) restent à finaliser après le "
        f"pré-test, conformément à l'Annexe 1 du questionnaire."
    )

st.divider()

# ------------------------------------------------------------------
# ONGLETS
# ------------------------------------------------------------------
tab_overview, tab_enq, tab_as, tab_quality, tab_data = st.tabs(
    ["📈 Vue d'ensemble", "🧑‍🤝‍🧑 Par enquêteur", "📍 Par aire de santé",
     "✅ Qualité des données", "📋 Données brutes"]
)

# --- Vue d'ensemble -------------------------------------------------
with tab_overview:
    st.subheader("Progression de la collecte dans le temps")
    if "ID02" in df_f.columns and not df_f.empty:
        tmp = df_f.copy()
        tmp["ID02"] = pd.to_datetime(tmp["ID02"], errors="coerce")
        daily = tmp.dropna(subset=["ID02"]).groupby(tmp["ID02"].dt.date).size().reset_index(name="n")
        daily.columns = ["Date", "Entretiens"]
        daily["Cumulé"] = daily["Entretiens"].cumsum()

        fig = go.Figure()
        fig.add_bar(x=daily["Date"], y=daily["Entretiens"], name="Entretiens / jour",
                    marker_color=theme.ACCENT, marker_line_width=0,
                    hovertemplate="%{x}<br>%{y} entretiens<extra></extra>")
        fig.add_scatter(x=daily["Date"], y=daily["Cumulé"], name="Cumulé", mode="lines+markers",
                         line=dict(color=theme.ACCENT_DARK, width=2),
                         marker=dict(size=6), yaxis="y2",
                         hovertemplate="%{x}<br>Cumulé : %{y}<extra></extra>")
        fig.update_layout(
            yaxis=dict(title="Entretiens / jour"),
            yaxis2=dict(title="Cumulé", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        theme.apply_layout(fig, height=360, show_legend=True)
        st.plotly_chart(fig, use_container_width=True, key="chart_trend_global")
    else:
        st.info("Champ ID02 (date d'entretien) absent des données chargées.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Entretiens par aire de santé")
        if "ID04" in df_f.columns and not df_f.empty:
            counts = df_f["ID04"].value_counts().rename_axis("ID04").reset_index(name="n")
            counts["Aire de santé"] = counts["ID04"].map(AIRES_SANTE).fillna(counts["ID04"])
            counts = counts.sort_values("n", ascending=True)
            fig = go.Figure(go.Bar(
                x=counts["n"], y=counts["Aire de santé"], orientation="h",
                text=counts["n"], textposition="outside",
                marker_color=theme.ACCENT, marker_line_width=0,
                hovertemplate="%{y} : %{x} entretiens<extra></extra>",
            ))
            fig.update_xaxes(title="Entretiens")
            theme.apply_layout(fig, height=420)
            st.plotly_chart(fig, use_container_width=True, key="chart_overview_par_as")
        else:
            st.info("Champ ID04 (aire de santé) absent des données chargées.")

    with c2:
        st.subheader("Entretiens par enquêteur")
        if "ID03" in df_f.columns and not df_f.empty:
            counts = df_f["ID03"].value_counts().rename_axis("ID03").reset_index(name="n")
            counts["Enquêteur"] = counts["ID03"].map(ENQUETEURS).fillna(counts["ID03"])
            counts = counts.sort_values("n", ascending=True)
            fig = go.Figure(go.Bar(
                x=counts["n"], y=counts["Enquêteur"], orientation="h",
                text=counts["n"], textposition="outside",
                marker_color=theme.ACCENT, marker_line_width=0,
                hovertemplate="%{y} : %{x} entretiens<extra></extra>",
            ))
            fig.update_xaxes(title="Entretiens")
            theme.apply_layout(fig, height=420)
            st.plotly_chart(fig, use_container_width=True, key="chart_overview_par_enq")
        else:
            st.info("Champ ID03 (code enquêteur) absent des données chargées.")

# --- Par enquêteur ----------------------------------------------------
with tab_enq:
    st.subheader("Tendance des soumissions par enquêteur")
    mat = submission_trend_matrix(df_f)
    if not mat.empty:
        st.caption(
            "Chaque case indique le nombre d'entretiens soumis par cet enquêteur ce jour-là — "
            "lecture rapide des jours actifs, des écarts et des ruptures de rythme par personne."
        )
        fig = go.Figure(go.Heatmap(
            z=mat.values.T,
            x=[d.isoformat() for d in mat.index],
            y=mat.columns.tolist(),
            colorscale=theme.blue_colorscale(),
            colorbar=dict(title="Entretiens", outlinewidth=0),
            hovertemplate="%{y} — %{x}<br>%{z} entretien(s)<extra></extra>",
            xgap=2, ygap=2,
        ))
        fig.update_xaxes(title="Date", type="category")
        fig.update_yaxes(title="")
        theme.apply_layout(fig, height=120 + 28 * len(mat.columns))
        st.plotly_chart(fig, use_container_width=True, key="chart_heatmap_enq")
    else:
        st.info("Pas assez de données (ID02/ID03) pour tracer la tendance par enquêteur.")

    st.subheader("Détail par enquêteur")
    detail_enq = summary_by_enqueteur(df_f)
    if not detail_enq.empty:
        st.dataframe(detail_enq, hide_index=True, use_container_width=True)
    else:
        st.info("Aucune donnée à détailler pour la sélection actuelle.")

# --- Par aire de santé --------------------------------------------------
with tab_as:
    st.subheader("Détail par aire de santé")
    detail_as = summary_by_aire(df_f)
    if not detail_as.empty:
        st.dataframe(detail_as, hide_index=True, use_container_width=True)

        fig = go.Figure(go.Bar(
            x=detail_as.sort_values("Entretiens")["Entretiens"],
            y=detail_as.sort_values("Entretiens")["Aire de santé"],
            orientation="h", text=detail_as.sort_values("Entretiens")["Entretiens"],
            textposition="outside", marker_color=theme.ACCENT, marker_line_width=0,
            hovertemplate="%{y} : %{x} entretiens<extra></extra>",
        ))
        fig.update_xaxes(title="Entretiens")
        theme.apply_layout(fig, height=420)
        st.plotly_chart(fig, use_container_width=True, key="chart_detail_par_as")
    else:
        st.info("Aucune donnée à détailler pour la sélection actuelle.")

# --- Qualité des données --------------------------------------------
with tab_quality:
    st.subheader("Qualité des données")
    qc1, qc2 = st.columns(2)

    with qc1:
        st.markdown("**Valeurs manquantes sur les champs clés (%)**")
        if qr["missing_by_field"]:
            miss_df = pd.DataFrame(list(qr["missing_by_field"].items()), columns=["Champ", "% manquant"])
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
        if jours_depuis_dernier is not None and jours_depuis_dernier >= 3:
            alerts.append(f"🟠 Aucune soumission depuis {jours_depuis_dernier} jours — vérifier que la collecte est toujours active.")
        if not alerts:
            st.success("Aucune alerte détectée sur les critères surveillés.")
        else:
            for a in alerts:
                st.write(a)

# --- Données brutes / export -----------------------------------------
with tab_data:
    st.subheader("Données filtrées")
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

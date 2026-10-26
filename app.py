# -*- coding: utf-8 -*-
"""
VaxSuivi-Lemba — Tableau de bord de suivi de la collecte de données
Mémoire : « Facteurs associés à l'hésitation vaccinale chez les parents ou
tuteurs d'enfants de 0 à 23 mois en vaccination de routine — Zone de Santé
de Lemba, Kinshasa (RDC), 2026 »

Phase en cours : COLLECTE DES DONNÉES (le pré-test est terminé).
Objectif : 424 ménages enquêtés (éligibles et consentants) pour évaluer
l'hésitation vaccinale.

Ce tableau de bord NE calcule ni ne publie aucun résultat scientifique final
du mémoire. Il sert uniquement à suivre l'avancement et la qualité de la
collecte pendant le terrain (progression vers les 424 ménages, par aire de santé et par enquêteur,
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
    evaluated_mask,
    split_complete,
    statut_aires,
    JOURS_INACTIVITE_ALERTE,
    hesitation_prevalence,
    normalize_columns,
    quality_report,
    submission_trend_matrix,
    summary_by_aire,
    summary_by_enqueteur,
)
import analyses as AN
from kobo_api import KoboAPIError, fetch_submissions

# Taille d'échantillon fixée par le protocole du mémoire : nombre de ménages que
# les enquêteurs doivent atteindre pour évaluer l'hésitation vaccinale.
OBJECTIF_MENAGES = 424

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

def hero_image_html() -> str:
    """Illustration d'en-tête (SVG) encodée en base64, sans dépendance réseau externe.
    Affichée en petit format à côté du titre pour ne pas occuper tout l'écran."""
    svg_path = Path(__file__).parent / "assets" / "hero_hesitation.svg"
    if not svg_path.exists():
        return ""
    svg_b64 = base64.b64encode(svg_path.read_bytes()).decode("utf-8")
    return (
        f"<div style='border-radius:14px; overflow:hidden; border:1px solid {theme.GRIDLINE};"
        f" box-shadow:0 2px 8px rgba(11,11,11,0.05); max-width:340px; margin:0.4rem 0 0 auto;'>"
        f"<img src='data:image/svg+xml;base64,{svg_b64}' alt='Illustration : un parent hésite "
        f"entre oui et non face à la vaccination' style='width:100%; max-height:125px;"
        f" object-fit:cover; display:block;' /></div>"
    )


entete_txt, entete_img = st.columns([5, 2], vertical_alignment="center")
with entete_txt:
    st.title("💉 VaxSuivi-Lemba")
    st.caption(
        "Suivi de la collecte — Hésitation vaccinale chez les parents/tuteurs "
        "d'enfants 0-23 mois, Zone de Santé de Lemba (Kinshasa, 2026)"
    )
with entete_img:
    st.markdown(hero_image_html(), unsafe_allow_html=True)
st.success(
    f"📋 **Phase en cours : collecte des données** (le pré-test est terminé). "
    f"Objectif fixé aux enquêteurs : **{OBJECTIF_MENAGES} ménages** enquêtés pour évaluer "
    f"l'hésitation vaccinale."
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

df_all = normalize_columns(df_raw)
df_all = add_sequential_numbers(df_all)  # N_FORMULAIRE / N_MENAGE, calculés sur l'ensemble des
                                          # soumissions avant filtrage, pour rester stables

# Les soumissions incomplètes sont mises de côté : elles n'entrent dans AUCUN
# indicateur (ni dans les 424 ménages) et sont listées dans un onglet dédié
# pour être complétées ou corrigées par les enquêteurs.
df, df_incomplet = split_complete(df_all)

# ------------------------------------------------------------------
# FILTRES
# ------------------------------------------------------------------
st.sidebar.header("Filtres")

aires_present = sorted(df_all["ID04"].dropna().unique().tolist()) if "ID04" in df_all.columns else []
aires_sel = st.sidebar.multiselect(
    "Aire de santé", options=aires_present, format_func=lambda x: AIRES_SANTE.get(x, x),
)

enq_present = sorted(df_all["ID03"].dropna().unique().tolist()) if "ID03" in df_all.columns else []
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
# Pas de filtre de date sur les incomplètes : une date manquante est justement
# un motif de mise de côté, elle ne doit pas les faire disparaître de la liste.
df_inc_f = apply_filters(df_incomplet, aires=aires_sel or None, enqueteurs=enq_sel or None)

st.sidebar.info(
    f"🎯 Objectif de la collecte : **{OBJECTIF_MENAGES} ménages** évalués "
    f"(éligibles et consentants). L'avancement est toujours calculé sur l'ensemble "
    f"de la base, indépendamment des filtres. Les soumissions incomplètes sont mises "
    f"de côté et ne comptent pas."
)

qr = quality_report(df_f)
elig = eligibility_rate(df_f)
prevalence = hesitation_prevalence(df_f)

# ------------------------------------------------------------------
# AVANCEMENT VERS L'OBJECTIF (sur toute la base, hors filtres)
# ------------------------------------------------------------------
champs_elig_presents = all(c in df.columns for c in ["A01", "A02", "A04"])
n_evalues = int(evaluated_mask(df).sum())
n_restants = max(OBJECTIF_MENAGES - n_evalues, 0)
taux_avancement = round(n_evalues / OBJECTIF_MENAGES * 100, 1)

rythme_jour = None
if "ID02" in df.columns:
    dates_eval = pd.to_datetime(df.loc[evaluated_mask(df), "ID02"], errors="coerce").dropna()
    jours_actifs = dates_eval.dt.date.nunique()
    if jours_actifs:
        rythme_jour = round(n_evalues / jours_actifs, 1)

# ------------------------------------------------------------------
# KPI PRINCIPAUX
# ------------------------------------------------------------------
st.subheader(f"Avancement vers l'objectif de {OBJECTIF_MENAGES} ménages")
st.progress(min(n_evalues / OBJECTIF_MENAGES, 1.0),
            text=f"{n_evalues} / {OBJECTIF_MENAGES} ménages évalués — {taux_avancement} %")
pa1, pa2, pa3 = st.columns(3)
pa1.metric("Ménages évalués", f"{n_evalues} / {OBJECTIF_MENAGES}",
           help="Ménages éligibles ET consentants (A01 = A02 = A04 = 1), sur toute la base.")
pa2.metric("Ménages restants à atteindre", n_restants if n_restants else "Objectif atteint ✅")
pa3.metric("Rythme moyen / jour de collecte", f"{rythme_jour} ménages" if rythme_jour else "—",
           help="Ménages évalués divisés par le nombre de jours où au moins un ménage a été évalué.")
if rythme_jour and n_restants:
    st.caption(f"⏳ À ce rythme, il reste environ **{int(-(-n_restants // rythme_jour))} jours de "
               f"collecte** pour atteindre les {OBJECTIF_MENAGES} ménages.")
if not champs_elig_presents:
    st.caption("ℹ️ Champs A01/A02/A04 absents de l'export : tous les formulaires sont comptés "
               "comme ménages évalués.")
if len(df_incomplet):
    st.warning(
        f"⏸️ **{len(df_incomplet)} soumission(s) incomplète(s) mise(s) de côté** sur "
        f"{len(df_all)} reçue(s) : elles ne sont comptées ni dans les {OBJECTIF_MENAGES} ménages "
        f"ni dans les indicateurs ci-dessous. Détail et motifs dans l'onglet "
        f"« ⏸️ Mises de côté »."
    )

# ------------------------------------------------------------------
# NOTIFICATION : AIRES DE SANTÉ COMMENCÉES / PAS ENCORE COMMENCÉES
# (toujours sur toute la base, indépendamment des filtres)
# ------------------------------------------------------------------
statut_as = statut_aires(df, df_incomplet)
STYLE_STATUT = {   # (couleur de fond, couleur du texte, pictogramme)
    "Pas commencée": ("#fbe3e3", "#8f2323", "⛔"),
    "Commencée — incomplètes seulement": ("#fdeadf", "#8a3f1d", "⏸️"),
    "À l'arrêt": ("#fff3d6", "#7a5500", "⚠️"),
    "En cours": ("#e3f1fd", "#174f8c", "▶️"),
    "Cible atteinte": ("#e1f5e1", "#0a5c0a", "✅"),
}


def puces_aires(tableau: pd.DataFrame) -> str:
    puces = []
    for _, r in tableau.iterrows():
        fond, texte, picto = STYLE_STATUT[r["Statut"]]
        detail = f"{r['Ménages évalués']} mén." if r["Statut"] != "Pas commencée" else "0"
        puces.append(
            f"<div style='background:{fond};color:{texte};border-radius:10px;padding:8px 10px;"
            f"font-size:0.86rem;line-height:1.25'><b>{picto} {r['Aire de santé']}</b><br>"
            f"<span style='font-size:0.78rem'>{r['Statut']} · {detail}</span></div>"
        )
    return ("<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(165px,1fr));"
            "gap:8px;margin:4px 0 10px 0'>" + "".join(puces) + "</div>")


n_as = len(statut_as)
commencees = statut_as[statut_as["Statut"] != "Pas commencée"]
pas_commencees = statut_as[statut_as["Statut"] == "Pas commencée"]
incompletes_seules = statut_as[statut_as["Statut"] == "Commencée — incomplètes seulement"]
a_l_arret = statut_as[statut_as["Statut"] == "À l'arrêt"]

st.subheader(f"Aires de santé : {len(commencees)} / {n_as} ont commencé la collecte")
if len(pas_commencees):
    st.error(f"⛔ **{len(pas_commencees)} aire(s) de santé n'ont pas encore commencé** : "
             + ", ".join(pas_commencees["Aire de santé"]) + ".")
else:
    st.success(f"✅ Les {n_as} aires de santé ont commencé la collecte.")
if len(incompletes_seules):
    st.warning("⏸️ Collecte commencée mais **aucune soumission complète** : "
               + ", ".join(incompletes_seules["Aire de santé"])
               + " — à corriger (voir l'onglet « ⏸️ Mises de côté »).")
if len(a_l_arret):
    st.warning(f"⚠️ **Aucune soumission depuis {JOURS_INACTIVITE_ALERTE} jours ou plus** : "
               + ", ".join(f"{r['Aire de santé']} ({int(r['Jours sans soumission'])} j)"
                           for _, r in a_l_arret.iterrows()) + ".")
st.markdown(puces_aires(statut_as), unsafe_allow_html=True)

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Entretiens complets", qr["n_total"],
            help="Formulaires complets (sélection filtrée), y compris non éligibles ou refus. "
                 "Les soumissions incomplètes sont exclues.")
col2.metric("Ménages évalués (sélection)", int(evaluated_mask(df_f).sum()) if not df_f.empty else 0)
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
        f"soumissions — dernier numéro en date : **N° {int(df_all['N_FORMULAIRE'].max())}** sur "
        f"l'ensemble de la base, soumissions mises de côté comprises (recalculée à chaque "
        f"actualisation — voir §5 du README)."
    )

if prevalence is not None:
    st.warning(
        f"⚠️ Prévalence provisoire d'hésitation vaccinale sur les entretiens déjà saisis : "
        f"**{prevalence} %**. Indicateur de suivi de terrain uniquement — **ne constitue pas un "
        f"résultat scientifique du mémoire**. La règle de calcul de HESITATION et les scores "
        f"composites (SCORE_CONNAISS, SCORE_CONFIANCE, etc.) seront calculés à l'analyse finale, "
        f"une fois les {OBJECTIF_MENAGES} ménages atteints, conformément à l'Annexe 1 du questionnaire. "
        f"Projection détaillée (IC95 %, bivariée, multivariée) dans l'onglet « 🔮 Projection des analyses »."
    )

st.divider()

# ------------------------------------------------------------------
# ONGLETS
# ------------------------------------------------------------------
tab_overview, tab_enq, tab_as, tab_proj, tab_quality, tab_inc, tab_data = st.tabs(
    ["📈 Vue d'ensemble", "🧑‍🤝‍🧑 Par enquêteur", "📍 Par aire de santé",
     "🔮 Projection des analyses", "✅ Qualité des données",
     f"⏸️ Mises de côté ({len(df_inc_f)})", "📋 Données brutes"]
)

# --- Vue d'ensemble -------------------------------------------------
with tab_overview:
    st.subheader("Progression de la collecte dans le temps")
    if "ID02" in df_f.columns and not df_f.empty:
        tmp = df_f.copy()
        tmp["ID02"] = pd.to_datetime(tmp["ID02"], errors="coerce")
        tmp["_evalue"] = evaluated_mask(tmp).astype(int)
        tmp = tmp.dropna(subset=["ID02"])
        daily = tmp.groupby(tmp["ID02"].dt.date).agg(n=("ID02", "size"), ev=("_evalue", "sum")).reset_index()
        daily.columns = ["Date", "Entretiens", "Évalués"]
        daily["Cumulé"] = daily["Évalués"].cumsum()

        fig = go.Figure()
        fig.add_bar(x=daily["Date"], y=daily["Entretiens"], name="Entretiens / jour",
                    marker_color=theme.ACCENT, marker_line_width=0,
                    hovertemplate="%{x}<br>%{y} entretiens<extra></extra>")
        fig.add_scatter(x=daily["Date"], y=daily["Cumulé"], name="Ménages évalués (cumulé)",
                         mode="lines+markers",
                         line=dict(color=theme.ACCENT_DARK, width=2),
                         marker=dict(size=6), yaxis="y2",
                         hovertemplate="%{x}<br>Ménages évalués cumulés : %{y}<extra></extra>")
        # Ligne d'objectif (424 ménages) sur l'axe cumulé
        fig.add_scatter(x=[daily["Date"].min(), daily["Date"].max()],
                         y=[OBJECTIF_MENAGES, OBJECTIF_MENAGES],
                         name=f"Objectif ({OBJECTIF_MENAGES} ménages)", mode="lines",
                         line=dict(color=theme.CRITICAL, width=1.5, dash="dash"), yaxis="y2",
                         hovertemplate=f"Objectif : {OBJECTIF_MENAGES} ménages<extra></extra>")
        fig.update_layout(
            yaxis=dict(title="Entretiens / jour"),
            yaxis2=dict(title="Ménages évalués (cumulé)", overlaying="y", side="right",
                        showgrid=False,
                        range=[0, max(OBJECTIF_MENAGES, int(daily["Cumulé"].max())) * 1.08]),
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
    st.subheader(f"Statut de la collecte dans les {n_as} aires de santé")
    st.caption(
        "Sur toute la base (filtres non appliqués). « Pas commencée » : aucune soumission ; "
        "« Commencée — incomplètes seulement » : uniquement des soumissions mises de côté ; "
        f"« À l'arrêt » : rien depuis {JOURS_INACTIVITE_ALERTE} jours ou plus. Les cibles par AS "
        "(allocation proportionnelle du mémoire, § 3.4.3) s'afficheront une fois renseignées dans "
        "`ALLOCATION_AS` (data_quality.py)."
    )
    ordre = list(STYLE_STATUT)
    vue_statut = statut_as.assign(_o=statut_as["Statut"].map(ordre.index)).sort_values(["_o", "Aire de santé"])
    vue_statut = vue_statut.drop(columns=["_o", "Code"])
    vue_statut = vue_statut.astype(object).where(vue_statut.notna(), "—").astype(str)
    st.dataframe(vue_statut, hide_index=True, use_container_width=True,
                 height=38 + 35 * len(vue_statut),
                 column_config={"Statut": st.column_config.TextColumn(width="large"),
                                "Aire de santé": st.column_config.TextColumn(width="medium")})

    st.subheader("Détail par aire de santé (sélection filtrée)")
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

# --- Projection des analyses du mémoire ------------------------------------
def _graphe_forest(tab: pd.DataFrame, col_or: str, titre_x: str, key: str) -> None:
    t = tab.dropna(subset=[col_or, "IC bas", "IC haut"]).iloc[::-1]
    if t.empty:
        return
    fig = go.Figure(go.Scatter(
        x=t[col_or], y=t["Terme"], mode="markers",
        marker=dict(color=theme.ACCENT_DARK, size=9),
        error_x=dict(type="data", symmetric=False, array=t["IC haut"] - t[col_or],
                     arrayminus=t[col_or] - t["IC bas"], color=theme.ACCENT, thickness=1.5),
        hovertemplate="%{y}<br>" + col_or + " = %{x:.2f}<extra></extra>",
    ))
    fig.add_vline(x=1, line_dash="dash", line_color=theme.INK_MUTED)
    fig.update_xaxes(type="log", title=titre_x)
    theme.apply_layout(fig, height=110 + 34 * len(t))
    st.plotly_chart(fig, use_container_width=True, key=key)


with tab_proj:
    st.subheader("Projection des analyses statistiques du mémoire (§ 3.9)")
    st.warning(
        "🔮 **Résultats provisoires**, recalculés à chaque actualisation sur les soumissions complètes "
        "déjà reçues (et selon les filtres actifs). Ils donnent une **tendance** de ce que montreront les "
        f"analyses prévues au mémoire, mais **ne sont pas les résultats du mémoire** : l'analyse finale se "
        f"fera sous SPSS 27 sur la base apurée de {OBJECTIF_MENAGES} ménages, avec la règle de cotation "
        "définitive de l'hésitation et des scores composites (alpha de Cronbach ≥ 0,70)."
    )
    base = AN.base_analyse(df_f)
    if base.empty:
        if not any(c.split("/")[-1] == "HESITATION" for c in df_f.columns):
            st.info("La variable HESITATION est absente de l'export : la projection des analyses "
                    "s'affichera dès qu'elle sera calculée dans le formulaire Kobo.")
        else:
            st.info("Aucun ménage évalué avec la variable HESITATION renseignée pour la sélection actuelle.")
    else:
        vars_qual, vars_quant = AN.variables_candidates(base)
        libelles_mod = {**AIRES_SANTE, **ENQUETEURS}
        nom_var = lambda c: "Aire de santé (ID04)" if c == "ID04" else c.split("/")[-1]  # noqa: E731

        p1, p2, p5, p6, pp = st.tabs(["Obj. 1 · Prévalence", "Obj. 2-4 · Description",
                                       "Obj. 5 · Analyse bivariée", "Obj. 6 · Régression logistique",
                                       "Ponctualité vaccinale"])

        # Objectif 1 ---------------------------------------------------------
        with p1:
            pv = AN.prevalence(base)
            prec_now = AN.precision_projetee(pv["p"], pv["n"])
            prec_424 = AN.precision_projetee(pv["p"], OBJECTIF_MENAGES)
            fr = lambda x: f"{x * 100:.1f}".replace(".", ",")  # noqa: E731
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Ménages analysés", f"{pv['n']} / {OBJECTIF_MENAGES}")
            m2.metric("Parents/tuteurs hésitants", pv["k"])
            m3.metric("Prévalence provisoire", f"{fr(pv['p'])} %",
                      help="Hésitants / ménages évalués avec HESITATION renseignée.")
            m4.metric("Précision projetée à 424", f"± {fr(prec_424)} pts",
                      help="Demi-largeur de l'IC95 % attendue avec 424 ménages si la prévalence reste "
                           "à ce niveau (le mémoire vise ± 5 points, § 3.4.2).")
            st.caption(f"IC95 % (Wilson) : {fr(pv['lo'])} – {fr(pv['hi'])} % · précision actuelle : "
                       f"± {fr(prec_now)} points.")
            st.markdown(
                f"**Lecture provisoire :** sur {pv['n']} ménages, {pv['k']} parents ou tuteurs sont classés "
                f"hésitants, soit **{fr(pv['p'])} %** (IC95 % : {fr(pv['lo'])} – {fr(pv['hi'])} %). "
                f"Avec {OBJECTIF_MENAGES} ménages et une prévalence de ce niveau, l'intervalle se resserrera "
                f"à environ ± {fr(prec_424)} points."
            )
            par_as = AN.prevalence_par(base, "ID04", AIRES_SANTE) if "ID04" in base.columns else pd.DataFrame()
            if not par_as.empty:
                st.markdown("**Prévalence provisoire par aire de santé** — effectifs encore faibles par AS, "
                            "intervalles larges : à lire comme une tendance.")
                t = par_as.sort_values("Prévalence (%)")
                bornes = t["IC95 %"].str.replace(",", ".").str.split(" – ", expand=True).astype(float)
                fig = go.Figure(go.Bar(
                    x=t["Prévalence (%)"], y=t["Modalité"], orientation="h",
                    marker_color=theme.ACCENT, marker_line_width=0,
                    error_x=dict(type="data", symmetric=False, array=bornes[1] - t["Prévalence (%)"],
                                 arrayminus=t["Prévalence (%)"] - bornes[0], color=theme.INK_MUTED),
                    customdata=t[["n", "IC95 %"]],
                    hovertemplate="%{y} : %{x:.1f} % (n = %{customdata[0]}, IC95 % %{customdata[1]})<extra></extra>",
                ))
                fig.add_vline(x=pv["p"] * 100, line_dash="dash", line_color=theme.CRITICAL)
                fig.add_annotation(x=pv["p"] * 100, y=1, yref="paper", yanchor="bottom", xanchor="left",
                                   text=f"ZS Lemba : {fr(pv['p'])} %", showarrow=False,
                                   font=dict(color=theme.CRITICAL, size=12))
                fig.update_xaxes(title="Prévalence de l'hésitation (%)", range=[0, 100])
                theme.apply_layout(fig, height=140 + 30 * len(t))
                fig.update_layout(margin=dict(t=36))
                st.plotly_chart(fig, use_container_width=True, key="chart_prev_as")
                st.dataframe(par_as.rename(columns={"Modalité": "Aire de santé"}), hide_index=True,
                             use_container_width=True)

        # Objectifs 2 à 4 ----------------------------------------------------
        with p2:
            st.caption("Variables qualitatives : effectifs et % ; quantitatives : moyenne ± ET si la "
                       "distribution est symétrique (|asymétrie| < 1), sinon médiane [IQR] (§ 3.9.1).")
            choix_desc = st.multiselect("Variables à décrire", vars_qual + vars_quant,
                                        default=[v for v in vars_qual + vars_quant if v != "ID04"],
                                        format_func=nom_var, key="desc_vars")
            colonnes = st.columns(2)
            for i, v in enumerate(choix_desc):
                with colonnes[i % 2]:
                    st.markdown(f"**{nom_var(v)}**")
                    if v in vars_quant:
                        r = AN.descriptif_quantitatif(base, v)
                        if r:
                            st.write(f"n = {r['n']} · {r['Résumé retenu']}")
                    else:
                        t = AN.descriptif_qualitatif(base, v)
                        if v == "ID04":
                            t["Modalité"] = t["Modalité"].map(lambda m: AIRES_SANTE.get(m, m))
                        st.dataframe(t, hide_index=True, use_container_width=True)
            if not choix_desc:
                st.info("Aucune variable descriptive détectée dans l'export.")

        # Objectif 5 ---------------------------------------------------------
        with p5:
            st.caption("Chi² de Pearson, ou test exact de Fisher si un effectif attendu < 5 dans un "
                       "tableau 2×2 ; t de Student (Welch) ou Mann-Whitney pour les variables quantitatives ; "
                       "ORb avec IC95 % (Woolf), modalité la plus fréquente en référence (§ 3.9.2).")
            choix_bi = st.multiselect("Facteurs à croiser avec l'hésitation", vars_qual + vars_quant,
                                      default=vars_qual + vars_quant, format_func=nom_var, key="bi_vars")
            detail_bi, synth_bi = AN.synthese_bivariee(
                base, [v for v in choix_bi if v in vars_qual], [v for v in choix_bi if v in vars_quant],
                libelles_mod)
            if not synth_bi.empty:
                presel = synth_bi[synth_bi["Présélection (p < 0,20)"] == "Oui"]["Variable"].tolist()
                st.markdown(f"**{len(presel)} facteur(s) présélectionné(s) à p < 0,20** pour le modèle "
                            "multivarié : " + (", ".join(nom_var(v) for v in presel) or "aucun") + ".")
                vue = synth_bi.assign(Variable=synth_bi["Variable"].map(nom_var),
                                      p=synth_bi["p"].map(AN.fmt_p))
                vue = vue[[c for c in vue.columns if c != "Remarque"] + ["Remarque"]]
                st.dataframe(vue, hide_index=True, use_container_width=True)
                st.markdown("**Détail par modalité**")
                st.dataframe(detail_bi, hide_index=True, use_container_width=True)
            else:
                st.info("Choisir au moins un facteur.")

        # Objectif 6 ---------------------------------------------------------
        with p6:
            st.caption("Régression logistique binaire multivariée : ORa avec IC95 % et p ; colinéarité "
                       "(VIF) ; adéquation par le test de Hosmer-Lemeshow (§ 3.9.3). Par défaut, les "
                       "facteurs présélectionnés à p < 0,20 ; ajoutez les variables d'intérêt conceptuel.")
            presel_def = []
            if not synth_bi.empty:
                presel_def = synth_bi[synth_bi["Présélection (p < 0,20)"] == "Oui"]["Variable"].tolist()
            choix_mv = st.multiselect("Variables du modèle", vars_qual + vars_quant, default=presel_def,
                                      format_func=nom_var, key="mv_vars")
            if not choix_mv:
                st.info("Choisir au moins une variable.")
            else:
                res = AN.regression_logistique(base, [v for v in choix_mv if v in vars_qual],
                                               [v for v in choix_mv if v in vars_quant])
                if "erreur" in res:
                    st.error(res["erreur"])
                else:
                    r1, r2, r3, r4 = st.columns(4)
                    r1.metric("Observations", res["n"])
                    r2.metric("Événements par variable", f"{res['epv']:.1f}".replace(".", ","),
                              help="Plus petit des deux groupes (hésitants / non hésitants) divisé par le "
                                   "nombre de termes du modèle. Repère usuel : au moins 10.")
                    r3.metric("Hosmer-Lemeshow", f"p = {AN.fmt_p(res['p_hl'])}",
                              help="p > 0,05 : pas d'inadéquation détectée.")
                    r4.metric("Aire sous la courbe ROC", f"{res['auc']:.2f}".replace(".", ","))
                    if res["epv"] < 10:
                        st.warning(f"Seulement {res['epv']:.1f}".replace(".", ",") + f" événements par variable : le modèle est "
                                   "encore instable. Il se stabilisera à mesure que la collecte avance vers "
                                   f"{OBJECTIF_MENAGES} ménages.")
                    coef = res["coefficients"]
                    st.dataframe(coef[["Terme", "ORa [IC95 %]", "p (affiché)"]].rename(columns={"p (affiché)": "p"}),
                                 hide_index=True, use_container_width=True)
                    st.caption("Références : " + "; ".join(f"{nom_var(k)} = {v}" for k, v in res["references"].items())
                               if res["references"] else "")
                    _graphe_forest(coef, "ORa", "Odds Ratio ajusté (échelle log, IC95 %)", "chart_forest_ora")
                    sig = coef[coef["p"] < AN.SEUIL_SIGNIF]
                    if len(sig):
                        st.markdown("**Facteurs provisoirement associés (p < 0,05)** : " + "; ".join(
                            f"{r['Terme']} (ORa {r['ORa [IC95 %]']})" for _, r in sig.iterrows()) + ".")
                    if res["vif"] is not None and (res["vif"]["VIF"] > 5).any():
                        st.warning("Colinéarité possible (VIF > 5) : "
                                   + ", ".join(res["vif"].loc[res["vif"]["VIF"] > 5, "Terme"]) + ".")
                    st.caption(f"Pseudo-R² de McFadden : {res['pseudo_r2']:.2f}".replace(".", ",")
                               + ("" if res["converge"] else " — ⚠️ le modèle n'a pas convergé."))

        # Ponctualité ----------------------------------------------------------
        with pp:
            st.caption(
                f"Retard si la dose est administrée plus de {AN.DELAI_GRACE_JOURS} jours après l'âge "
                "recommandé (BCG : naissance ; Penta 1 : 6 semaines ; Penta 3 : 14 semaines ; VAR 1 : 9 mois), "
                "chez les enfants dont la carte a été vue (dates recopiées en C11 à C15, § 3.6 et 3.9.1). "
                "Comparaison hésitants / non hésitants par Chi² ou Fisher."
            )
            tab_ponct, manquants = AN.ponctualite(base)
            if manquants:
                st.info("Champs absents de l'export : " + ", ".join(manquants)
                        + ". Si les dates portent d'autres codes, les adapter dans `analyses.py` "
                          "(CHAMP_DATE_NAISSANCE, DOSES_PONCTUALITE).")
            if not tab_ponct.empty:
                st.dataframe(tab_ponct, hide_index=True, use_container_width=True)

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
        if len(df_inc_f):
            alerts.append(f"🟠 {len(df_inc_f)} soumission(s) incomplète(s) mise(s) de côté — voir l'onglet « ⏸️ Mises de côté ».")
        if jours_depuis_dernier is not None and jours_depuis_dernier >= 3:
            alerts.append(f"🟠 Aucune soumission depuis {jours_depuis_dernier} jours — vérifier que la collecte est toujours active.")
        if not alerts:
            st.success("Aucune alerte détectée sur les critères surveillés.")
        else:
            for a in alerts:
                st.write(a)

# --- Soumissions incomplètes mises de côté -----------------------------
with tab_inc:
    st.subheader("Soumissions incomplètes mises de côté")
    st.caption(
        "Ces soumissions sont exclues de tous les indicateurs et de l'objectif de "
        f"{OBJECTIF_MENAGES} ménages. Une soumission est mise de côté si : un champ "
        "d'identification (date, enquêteur, aire de santé) est vide ; l'éligibilité ou le "
        "consentement n'est pas renseigné ; le ménage est éligible et consentant mais le "
        "questionnaire a été interrompu (champ obligatoire vide) ; ou elle a été marquée "
        "« Non approuvée » dans la validation Kobo. Une fois corrigée dans Kobo, elle "
        "réintègre automatiquement les indicateurs à la prochaine actualisation."
    )
    if df_inc_f.empty:
        st.success("Aucune soumission incomplète pour la sélection actuelle.")
    else:
        ic1, ic2 = st.columns(2)
        with ic1:
            st.markdown("**Par enquêteur** (à recontacter en priorité)")
            if "ID03" in df_inc_f.columns:
                par_enq = (df_inc_f["ID03"].map(ENQUETEURS).fillna(df_inc_f["ID03"])
                           .fillna("Enquêteur non renseigné")
                           .value_counts().rename_axis("Enquêteur").reset_index(name="Incomplètes"))
                st.dataframe(par_enq, hide_index=True, use_container_width=True)
        with ic2:
            st.markdown("**Par motif**")
            par_motif = (df_inc_f["MOTIF_MISE_DE_COTE"].str.split(" ; ").explode()
                         .value_counts().rename_axis("Motif").reset_index(name="Soumissions"))
            st.dataframe(par_motif[["Soumissions", "Motif"]], hide_index=True, use_container_width=True)

        st.markdown("**Liste détaillée**")
        cols_inc = [c for c in ["N_FORMULAIRE", "MOTIF_MISE_DE_COTE", "ID01", "ID06", "ID02",
                                "ID03", "ID04", "ID05", "A01", "A02", "A04", "HESITATION"]
                    if c in df_inc_f.columns]
        vue_inc = df_inc_f[cols_inc].copy()
        if "ID02" in vue_inc.columns:
            vue_inc["ID02"] = pd.to_datetime(vue_inc["ID02"], errors="coerce").dt.date
        if "ID03" in vue_inc.columns:
            vue_inc["ID03"] = vue_inc["ID03"].map(ENQUETEURS).fillna(vue_inc["ID03"])
        if "ID04" in vue_inc.columns:
            vue_inc["ID04"] = vue_inc["ID04"].map(AIRES_SANTE).fillna(vue_inc["ID04"])
        vue_inc = vue_inc.rename(columns={"MOTIF_MISE_DE_COTE": "Motif", "ID02": "Date",
                                          "ID03": "Enquêteur", "ID04": "Aire de santé"})
        vue_inc = vue_inc.astype(object).where(vue_inc.notna(), "—").astype(str)
        st.dataframe(vue_inc, hide_index=True, use_container_width=True)
        buf_inc = io.BytesIO()
        df_inc_f.to_csv(buf_inc, index=False)
        st.download_button(
            "⬇️ Télécharger les soumissions mises de côté (CSV)",
            data=buf_inc.getvalue(),
            file_name=f"vaxsuivi_lemba_incompletes_{date.today().isoformat()}.csv",
            mime="text/csv",
        )

# --- Données brutes / export -----------------------------------------
with tab_data:
    st.subheader("Données filtrées (soumissions complètes uniquement)")
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

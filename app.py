# -*- coding: utf-8 -*-
"""
VaxSuivi-Lemba — Tableau de bord de suivi de la collecte de données
Mémoire : « Facteurs associés à l'hésitation vaccinale chez les parents ou
tuteurs d'enfants de 0 à 23 mois en vaccination de routine — Zone de Santé
de Lemba, Kinshasa (RDC), 2026 »

Phase en cours : COLLECTE DES DONNÉES (le pré-test est terminé).
Objectif : 424 ménages enquêtés (éligibles et consentants) pour évaluer
l'hésitation vaccinale.

Navigation par menu latéral : chaque page est rendue indépendamment, de sorte
qu'une erreur sur une page (donnée inattendue de l'export Kobo) n'empêche
jamais l'affichage des autres. Toute prévalence ou analyse affichée est
explicitement signalée comme provisoire.
"""
import base64
import io
import json
import traceback
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analyses as AN
import theme
import ui
from data_quality import (
    AIRES_SANTE,
    ENQUETEURS,
    JOURS_INACTIVITE_ALERTE,
    add_sequential_numbers,
    apply_filters,
    eligibility_rate,
    evaluated_mask,
    hesitation_prevalence,
    normalize_columns,
    quality_report,
    split_complete,
    statut_aires,
    submission_trend_matrix,
    summary_by_aire,
    summary_by_enqueteur,
)
from kobo_api import KoboAPIError, fetch_submissions

# Taille d'échantillon fixée par le protocole du mémoire (§ 3.4.2) : nombre de
# ménages que les enquêteurs doivent atteindre pour évaluer l'hésitation vaccinale.
OBJECTIF_MENAGES = 424
PLOTLY_CONFIG = {"displayModeBar": False, "locale": "fr"}


def get_kobo_secrets() -> dict:
    """Lit la section [kobo] des secrets Streamlit sans jamais lever d'exception."""
    try:
        return dict(st.secrets.get("kobo", {}))
    except Exception:  # noqa: BLE001
        return {}


def svg_b64() -> str:
    p = Path(__file__).parent / "assets" / "hero_hesitation.svg"
    return base64.b64encode(p.read_bytes()).decode("utf-8") if p.exists() else ""


def fr(x, d=1) -> str:
    """Nombre au format français (virgule décimale)."""
    return f"{x:.{d}f}".replace(".", ",")


def cellules_simples(df: pd.DataFrame) -> pd.DataFrame:
    """Convertit les cellules listes/dictionnaires (groupes répétés, pièces jointes,
    géolocalisation renvoyés par l'API Kobo) en texte JSON, pour l'affichage et l'export."""
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object and out[c].map(lambda v: isinstance(v, (list, dict, tuple))).any():
            out[c] = out[c].map(lambda v: json.dumps(v, ensure_ascii=False, default=str)
                                if isinstance(v, (list, dict, tuple)) else v)
    return out


st.set_page_config(page_title="VaxSuivi-Lemba", page_icon="💉", layout="wide",
                   initial_sidebar_state="expanded")
ui.inject_css()

# ------------------------------------------------------------------
# MENU LATÉRAL : marque, navigation, source, filtres
# ------------------------------------------------------------------
PAGES = {
    "Tableau de bord": ":material/space_dashboard:",
    "Aires de santé": ":material/location_on:",
    "Enquêteurs": ":material/groups:",
    "Projection des analyses": ":material/query_stats:",
    "Qualité des données": ":material/fact_check:",
    "Mises de côté": ":material/pause_circle:",
    "Données brutes": ":material/table_view:",
}
with st.sidebar:
    st.markdown(
        "<div class='vs-brand'><div class='vs-logo'>💉</div><div><b>Vax<span>Suivi</span>-Lemba</b>"
        "<small>Hésitation vaccinale · ZS Lemba</small></div></div>", unsafe_allow_html=True)
    page = st.radio("Navigation", list(PAGES), key="nav", label_visibility="collapsed",
                    format_func=lambda p: f"{PAGES[p]} {p}")

with st.sidebar.expander("Source des données", icon=":material/cloud_sync:", expanded=False):
    source_mode = st.radio("Charger les données depuis :",
                           ["API KoboToolbox (live)", "Fichier exporté (CSV / XLSX)"], index=0)

df_raw = pd.DataFrame()
source_label, source_ok = "", False
message_source = None

if source_mode == "API KoboToolbox (live)":
    # Le serveur, l'asset UID et le jeton d'API ne sont JAMAIS saisissables dans
    # l'interface (app publique par lien) : ils viennent uniquement des secrets
    # configurés par l'administrateur — voir le README, §3.
    kobo_secrets = get_kobo_secrets()
    server_url = kobo_secrets.get("server_url", "")
    asset_uid = kobo_secrets.get("asset_uid", "")
    api_token = kobo_secrets.get("api_token", "")

    @st.cache_data(ttl=300, show_spinner="Récupération des soumissions depuis Kobo…")
    def _load_from_kobo(server_url, asset_uid, api_token):
        return fetch_submissions(server_url, asset_uid, api_token)

    if st.sidebar.button("Actualiser les données", icon=":material/refresh:", type="primary",
                         width="stretch"):
        st.cache_data.clear()
    if server_url and asset_uid and api_token:
        try:
            df_raw = _load_from_kobo(server_url, asset_uid, api_token)
            source_label, source_ok = "API KoboToolbox — connectée", True
        except KoboAPIError as e:
            message_source = ("error", f"Impossible de récupérer les données Kobo : {e}")
            source_label = "API KoboToolbox — erreur"
    else:
        source_label = "API KoboToolbox — non configurée"
        message_source = ("info",
                          "La connexion Kobo n'est pas encore configurée pour cette application. Un "
                          "administrateur doit renseigner `server_url`, `asset_uid` et `api_token` dans "
                          "les secrets de l'app (voir le README, §3). En attendant, choisissez « Fichier "
                          "exporté » dans le menu, rubrique « Source des données ».")
else:
    with st.sidebar.expander("Fichier exporté", icon=":material/upload_file:", expanded=True):
        uploaded = st.file_uploader("Export Kobo (CSV ou XLSX)", type=["csv", "xlsx"])
    if uploaded is not None:
        df_raw = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
        source_label, source_ok = f"Fichier — {uploaded.name}", True
    else:
        source_label = "Fichier — aucun fichier chargé"
        message_source = ("info", "Chargez un export Kobo (menu Kobo : Data › Downloads) dans le menu "
                                  "latéral, rubrique « Fichier exporté », pour commencer.")


def carte_statut_source() -> None:
    teinte = "green" if source_ok else "orange"
    _, fg = ui.TONES[teinte]
    st.sidebar.markdown(
        f"<div class='vs-sys'><span style='color:{fg};font-size:1.2rem'>●</span><div>"
        f"<span>Source des données</span><b style='color:{fg};font-size:0.84rem'>{ui.esc(source_label)}</b>"
        f"</div></div>", unsafe_allow_html=True)


if df_raw.empty:
    carte_statut_source()
    ui.page_header("VaxSuivi-Lemba", "Collecte en cours",
                   "Suivi de la collecte — hésitation vaccinale, ZS Lemba (Kinshasa, 2026)", svg_b64())
    if message_source:
        (st.error if message_source[0] == "error" else st.info)(message_source[1])
    st.stop()

df_all = normalize_columns(df_raw)
df_all = add_sequential_numbers(df_all)   # N_FORMULAIRE / N_MENAGE, stables avant filtrage
# Les soumissions incomplètes sont mises de côté : elles n'entrent dans AUCUN
# indicateur (ni dans les 424 ménages) et sont listées sur une page dédiée.
df, df_incomplet = split_complete(df_all)

# ------------------------------------------------------------------
# FILTRES
# ------------------------------------------------------------------
with st.sidebar.expander("Filtres", icon=":material/filter_alt:", expanded=False):
    aires_present = sorted(df_all["ID04"].dropna().unique().tolist()) if "ID04" in df_all.columns else []
    aires_sel = st.multiselect("Aire de santé", options=aires_present,
                               format_func=lambda x: AIRES_SANTE.get(x, x))
    enq_present = sorted(df_all["ID03"].dropna().unique().tolist()) if "ID03" in df_all.columns else []
    enq_sel = st.multiselect("Enquêteur", options=enq_present, format_func=lambda x: ENQUETEURS.get(x, x))
    date_min = date_max = None
    if "ID02" in df.columns:
        dates_valides = pd.to_datetime(df["ID02"], errors="coerce").dropna()
        if len(dates_valides):
            min_d, max_d = dates_valides.min().date(), dates_valides.max().date()
            periode = st.date_input("Période de collecte", value=(min_d, max_d),
                                    min_value=min_d, max_value=max_d)
            # Pendant la sélection d'une plage, Streamlit ne renvoie qu'une date : on l'accepte.
            if isinstance(periode, (tuple, list)):
                date_min = periode[0] if len(periode) >= 1 else None
                date_max = periode[1] if len(periode) >= 2 else None
            else:
                date_min = periode

carte_statut_source()
st.sidebar.markdown(
    f"<div class='vs-sys'><span style='font-size:1.1rem'>🎯</span><div><span>Objectif de la collecte</span>"
    f"<b style='font-size:0.84rem'>{OBJECTIF_MENAGES} ménages évalués</b></div></div>",
    unsafe_allow_html=True)

df_f = apply_filters(df, aires=aires_sel or None, enqueteurs=enq_sel or None,
                     date_min=date_min, date_max=date_max)
# Pas de filtre de date sur les incomplètes : une date manquante est un motif de mise de côté.
df_inc_f = apply_filters(df_incomplet, aires=aires_sel or None, enqueteurs=enq_sel or None)
filtres_actifs = bool(aires_sel or enq_sel)

# ------------------------------------------------------------------
# INDICATEURS PARTAGÉS
# ------------------------------------------------------------------
qr = quality_report(df_f)
elig = eligibility_rate(df_f)
prevalence = hesitation_prevalence(df_f)

champs_elig_presents = all(c in df.columns for c in ["A01", "A02", "A04"])
masque_eval = evaluated_mask(df)
n_evalues = int(masque_eval.sum())
n_restants = max(OBJECTIF_MENAGES - n_evalues, 0)
taux_avancement = n_evalues / OBJECTIF_MENAGES * 100

dates_eval = (pd.to_datetime(df.loc[masque_eval, "ID02"], errors="coerce").dropna()
              if "ID02" in df.columns else pd.Series(dtype="datetime64[ns]"))
rythme_jour = round(n_evalues / dates_eval.dt.date.nunique(), 1) if len(dates_eval) else None
jours_restants = int(-(-n_restants // rythme_jour)) if rythme_jour and n_restants else None

jours_depuis_dernier = None
if "ID02" in df_f.columns and not df_f.empty:
    d_ = pd.to_datetime(df_f["ID02"], errors="coerce").dropna()
    if len(d_):
        jours_depuis_dernier = (pd.Timestamp(date.today()) - d_.max()).days

statut_as = statut_aires(df, df_incomplet)
n_as = len(statut_as)
STYLE_STATUT = {   # pictogramme, teinte (icône + libellé : jamais la couleur seule)
    "Pas commencée": ("⛔", "red"),
    "Commencée — incomplètes seulement": ("⏸️", "orange"),
    "À l'arrêt": ("⚠️", "orange"),
    "En cours": ("▶️", "blue"),
    "Cible atteinte": ("✅", "green"),
}
LIBELLE_COURT = {"Pas commencée": "Pas commencées", "Commencée — incomplètes seulement": "Incomplètes seules",
                 "À l'arrêt": "À l'arrêt", "En cours": "En cours", "Cible atteinte": "Cible atteinte"}
COULEUR_STATUT = {"Pas commencée": theme.CRITICAL, "Commencée — incomplètes seulement": theme.SERIOUS,
                  "À l'arrêt": theme.WARNING, "En cours": theme.ACCENT, "Cible atteinte": theme.GOOD}
commencees = statut_as[statut_as["Statut"] != "Pas commencée"]
pas_commencees = statut_as[statut_as["Statut"] == "Pas commencée"]
incompletes_seules = statut_as[statut_as["Statut"] == "Commencée — incomplètes seulement"]
a_l_arret = statut_as[statut_as["Statut"] == "À l'arrêt"]


def grille_aires(tableau: pd.DataFrame) -> str:
    cases = []
    for _, r in tableau.iterrows():
        picto, teinte = STYLE_STATUT[r["Statut"]]
        bg, fg = ui.TONES[teinte]
        detail = f"{r['Ménages évalués']} ménage(s)" if r["Statut"] != "Pas commencée" else "aucune soumission"
        cases.append(f"<div class='vs-as' style='background:{bg};color:{fg}'><b>{picto} "
                     f"{ui.esc(r['Aire de santé'])}</b>{ui.esc(r['Statut'])} · {detail}</div>")
    return "<div class='vs-as-grid'>" + "".join(cases) + "</div>"


def alertes_aires() -> None:
    if len(pas_commencees):
        st.error(f"**{len(pas_commencees)} aire(s) de santé n'ont pas encore commencé la collecte** : "
                 + ", ".join(pas_commencees["Aire de santé"]) + ".", icon="⛔")
    else:
        st.success(f"Les {n_as} aires de santé ont commencé la collecte.", icon="✅")
    if len(incompletes_seules):
        st.warning("Collecte commencée mais **aucune soumission complète** : "
                   + ", ".join(incompletes_seules["Aire de santé"]) + " — voir « Mises de côté ».", icon="⏸️")
    if len(a_l_arret):
        st.warning(f"**Aucune soumission depuis {JOURS_INACTIVITE_ALERTE} jours ou plus** : "
                   + ", ".join(f"{r['Aire de santé']} ({int(r['Jours sans soumission'])} j)"
                               for _, r in a_l_arret.iterrows()) + ".", icon="⚠️")



@contextmanager
def garde(nom: str):
    """Confine une erreur à la page (ou à la sous-partie) concernée."""
    try:
        yield
    except Exception:  # noqa: BLE001
        st.error(f"« {nom} » n'a pas pu s'afficher entièrement, probablement à cause d'une donnée inattendue "
                 "dans l'export. Les autres pages restent disponibles.", icon="🛠️")
        with st.expander("Détail technique (à transmettre au gestionnaire du tableau de bord)"):
            st.code(traceback.format_exc())


def carte(cle: str):
    """Conteneur stylé en carte blanche (classe CSS st-key-card_…)."""
    return st.container(key=f"card_{cle}")


def bandeau_filtres() -> None:
    if filtres_actifs or date_min is not None:
        st.caption("Filtres du menu appliqués à cette page.")


# ==================================================================
# PAGES
# ==================================================================
def page_tableau_de_bord() -> None:
    maj = datetime.now().strftime("%d/%m/%Y à %H:%M")
    ui.page_header("Collecte — ZS Lemba", "Hésitation vaccinale 0-23 mois",
                   f"Parents/tuteurs d'enfants de 0 à 23 mois · {n_as} aires de santé · mis à jour le {maj}",
                   svg_b64())

    # Frise des phases du mémoire
    ui.stepper([
        {"label": "Protocole approuvé", "detail": "IFRISSE", "state": "done"},
        {"label": "Pré-test terminé", "detail": "Questionnaire ajusté", "state": "done"},
        {"label": "Collecte en cours", "detail": f"{n_evalues}/{OBJECTIF_MENAGES} · {fr(taux_avancement)} %",
         "state": "current", "icon": "⏳"},
        {"label": "Analyse SPSS", "detail": "Après 424 ménages", "state": "todo", "icon": "📊"},
        {"label": "Soutenance", "detail": "À venir", "state": "todo", "icon": "🎓"},
    ])

    c1, c2, c3 = st.columns([1.05, 1, 1.1], gap="medium")
    # --- Avancement
    with c1, carte("avancement"):
        ui.card_title("Avancement vers l'objectif", "toute la base")
        st.markdown(
            f"<div class='vs-big'>{n_evalues} <small>/ {OBJECTIF_MENAGES} ménages</small></div>"
            f"<div class='vs-bar'><div style='width:{min(taux_avancement, 100):.1f}%'></div></div>"
            f"<div class='vs-muted'>{fr(taux_avancement)} % de l'objectif · ménages éligibles et consentants</div>"
            f"<div class='vs-row'><div><span>Restants</span><b>{n_restants}</b></div>"
            f"<div><span>Rythme moyen</span><b>{fr(rythme_jour) if rythme_jour else '—'} / jour</b></div>"
            f"<div><span>Fin estimée</span><b>{f'≈ {jours_restants} j' if jours_restants else '—'}</b></div></div>",
            unsafe_allow_html=True)
        if len(df_incomplet):
            st.markdown(f"<div class='vs-muted' style='margin-top:10px'>⏸️ {len(df_incomplet)} soumission(s) "
                        f"incomplète(s) mise(s) de côté, non comptée(s).</div>", unsafe_allow_html=True)
        if not champs_elig_presents:
            st.caption("Champs A01/A02/A04 absents : tous les formulaires sont comptés.")

    # --- Anneau des aires de santé
    with c2, carte("aires_anneau"):
        ui.card_title("Aires de santé", f"{len(commencees)} / {n_as} commencées")
        comptes = statut_as["Statut"].value_counts()
        ordre = [s for s in STYLE_STATUT if s in comptes.index]
        g1, g2 = st.columns([0.85, 1.3], vertical_alignment="center")
        with g1:
            fig = go.Figure(go.Pie(
                labels=ordre, values=[int(comptes[s]) for s in ordre], hole=0.68, sort=False,
                marker=dict(colors=[COULEUR_STATUT[s] for s in ordre], line=dict(color="#ffffff", width=2)),
                textinfo="none", hovertemplate="%{label} : %{value} AS<extra></extra>"))
            fig.add_annotation(text=f"<b style='font-size:22px'>{len(commencees)}</b><br>"
                                    f"<span style='font-size:11px'>sur {n_as}</span>",
                               showarrow=False, font=dict(color=theme.TEXT))
            theme.apply_layout(fig, height=170)
            fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="donut_as")
        with g2:
            st.markdown("".join(
                f"<div style='display:flex;justify-content:space-between;font-size:0.82rem;padding:3px 0'>"
                f"<span><span style='color:{COULEUR_STATUT[s]}'>●</span> {STYLE_STATUT[s][0]} {ui.esc(LIBELLE_COURT[s])}</span>"
                f"<b>{int(comptes[s])}</b></div>" for s in ordre), unsafe_allow_html=True)
        st.markdown("<span class='vs-link'>Détail : page « Aires de santé » →</span>", unsafe_allow_html=True)

    # --- Activité quotidienne
    with c3, carte("activite"):
        jours = (pd.to_datetime(df.loc[masque_eval, "ID02"], errors="coerce").dropna().dt.normalize()
                 if "ID02" in df.columns else pd.Series(dtype="datetime64[ns]"))
        if len(jours):
            # 14 jours se terminant aujourd'hui (ou au dernier jour d'activité s'il est plus ancien)
            aujourd_hui = pd.Timestamp(date.today()).normalize()
            fin = aujourd_hui if jours.max() >= aujourd_hui - pd.Timedelta(days=13) else jours.max()
            axe = pd.date_range(fin - pd.Timedelta(days=13), fin, freq="D")
            par_jour = jours.value_counts().reindex(axe, fill_value=0)
            sem, sem_prec = int(par_jour.iloc[-7:].sum()), int(par_jour.iloc[:7].sum())
            evol = (f"{'+' if sem >= sem_prec else ''}{fr((sem - sem_prec) / sem_prec * 100, 0)} % vs 7 j précédents"
                    if sem_prec else "")
            ui.card_title("Activité", f"ménages évalués · 14 j au {fin.strftime('%d/%m')}")
            st.markdown(f"<div class='vs-big'>{sem} <small>sur 7 jours</small></div>"
                        f"<div class='vs-muted'>{evol}</div>", unsafe_allow_html=True)
            fig = go.Figure(go.Bar(
                x=axe, y=par_jour.values, marker_color=theme.ACCENT, marker_line_width=0,
                marker_cornerradius=4,
                hovertemplate="%{x|%d/%m} : %{y} ménage(s)<extra></extra>"))
            theme.apply_layout(fig, height=120)
            fig.update_layout(margin=dict(l=0, r=0, t=6, b=0), bargap=0.35)
            fig.update_xaxes(showgrid=False, tickformat="%d/%m", nticks=7, tickfont=dict(size=10))
            fig.update_yaxes(showgrid=False, visible=False)
            st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="mini_activite")
        else:
            ui.card_title("Activité — ménages évalués")
            st.info("Pas encore de date d'entretien (ID02).")

    # --- Alertes aires de santé + grille
    with carte("aires_statut"):
        ui.card_title(f"Statut des {n_as} aires de santé", "notification")
        alertes_aires()
        st.markdown(grille_aires(statut_as), unsafe_allow_html=True)

    # --- Progression cumulée + dernières soumissions
    d1, d2 = st.columns([1.7, 1], gap="medium")
    with d1, carte("cumul"):
        ui.card_title("Progression cumulée vers les 424 ménages", "un seul axe : ménages évalués")
        if len(dates_eval):
            cum = dates_eval.dt.normalize().value_counts().sort_index().cumsum()
            fig = go.Figure()
            fig.add_scatter(x=cum.index, y=cum.values, mode="lines+markers", name="Ménages évalués (cumul)",
                            line=dict(color=theme.ACCENT_DARK, width=2), marker=dict(size=8),
                            fill="tozeroy", fillcolor="rgba(42,120,214,0.08)",
                            hovertemplate="%{x|%d/%m/%Y}<br>%{y} ménages évalués<extra></extra>")
            fig.add_hline(y=OBJECTIF_MENAGES, line_dash="dash", line_color=theme.CRITICAL, line_width=1.5)
            fig.add_annotation(x=cum.index.min(), y=OBJECTIF_MENAGES, yanchor="bottom", xanchor="left",
                               text=f"Objectif : {OBJECTIF_MENAGES} ménages", showarrow=False,
                               font=dict(color=theme.CRITICAL, size=12))
            fig.update_yaxes(range=[0, max(OBJECTIF_MENAGES, int(cum.max())) * 1.1], title="Ménages évalués")
            fig.update_xaxes(tickformat="%d/%m")
            theme.apply_layout(fig, height=300)
            st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="cumul")
        else:
            st.info("Champ ID02 (date d'entretien) absent ou vide.")

    with d2, carte("fil"):
        ui.card_title("Dernières soumissions", "toutes sources")
        tri = df_all.copy()
        col_tri = next((c for c in ["_submission_time", "end", "ID02"] if c in tri.columns), None)
        if col_tri:
            tri["_t"] = pd.to_datetime(tri[col_tri], errors="coerce")
            tri = tri.sort_values("_t", ascending=False, na_position="last")
        ids_inc = set(df_incomplet.index)
        elements = []
        for idx, r in tri.head(6).iterrows():
            aire = AIRES_SANTE.get(r.get("ID04"), r.get("ID04")) if pd.notna(r.get("ID04")) else "AS ?"
            enq = ENQUETEURS.get(r.get("ID03"), r.get("ID03")) if pd.notna(r.get("ID03")) else "enquêteur ?"
            quand = pd.to_datetime(r.get("ID02"), errors="coerce")
            quand_txt = quand.strftime("%d/%m/%Y") if pd.notna(quand) else "date ?"
            if idx in ids_inc:
                ton, ic, etat = "orange", "!", "mise de côté"
            elif bool(evaluated_mask(tri.loc[[idx]]).iloc[0]):
                ton, ic, etat = "green", "✓", "ménage évalué"
            else:
                ton, ic, etat = "grey", "–", "non éligible / refus"
            elements.append({"titre": f"Ménage N° {r.get('N_FORMULAIRE', '?')} · {aire}",
                             "detail": f"{ui.esc(enq)} · {quand_txt} · {etat}", "tone": ton, "icon": ic})
        ui.timeline(elements)

    # --- Indicateurs de qualité et prévalence provisoire
    k = st.columns(5, gap="small")
    blocs = [
        ("Entretiens complets", qr["n_total"], "sélection filtrée", "📝", "blue"),
        ("Éligibilité + consentement", f"{fr(elig['taux_pct'])} %" if elig["taux_pct"] is not None else "—",
         "A01 = A02 = A04 = 1", "🤝", "green"),
        ("Doublons potentiels", qr["doublons_menage"], "même aire + quartier + enfant", "🔁",
         "red" if qr["doublons_menage"] else "grey"),
        ("Durée moyenne", f"{fr(qr['duree_moyenne_min'])} min" if qr["duree_moyenne_min"] is not None else "—",
         f"{qr['entretiens_courts_lt5min'] or 0} entretien(s) < 5 min", "⏱️", "violet"),
        ("Dernière soumission", f"il y a {jours_depuis_dernier} j" if jours_depuis_dernier is not None else "—",
         "sélection filtrée", "📅",
         "orange" if (jours_depuis_dernier or 0) >= JOURS_INACTIVITE_ALERTE else "blue"),
    ]
    for col, (lab, val, sub, ic, ton) in zip(k, blocs):
        with col, carte(f"kpi_{ic}"):
            st.markdown(ui.kpi(lab, val, sub, ic, ton), unsafe_allow_html=True)

    if prevalence is not None:
        with carte("prev"):
            ui.card_title("Prévalence provisoire de l'hésitation vaccinale", ui.pill("provisoire", "orange"))
            st.markdown(
                f"<div class='vs-big'>{fr(prevalence)} %</div><div class='vs-muted'>Sur les ménages évalués déjà "
                f"saisis (sélection filtrée). Indicateur de suivi de terrain — <b>pas un résultat du mémoire</b> : "
                f"la règle de calcul de HESITATION et les scores composites seront fixés à l'analyse finale. "
                f"IC95 %, analyses bivariée et multivariée : page « Projection des analyses ».</div>",
                unsafe_allow_html=True)

    ui.feature_strip()


def page_aires_de_sante() -> None:
    ui.page_header("Aires de santé", f"{len(commencees)} / {n_as} commencées",
                   "Statut de démarrage et avancement de la collecte dans chaque aire de santé (toute la base).")
    with carte("as_alertes"):
        alertes_aires()
        st.markdown(grille_aires(statut_as), unsafe_allow_html=True)
    with carte("as_table"):
        ui.card_title("Tableau de statut", "filtres non appliqués")
        st.caption("« Pas commencée » : aucune soumission ; « Commencée — incomplètes seulement » : uniquement "
                   f"des soumissions mises de côté ; « À l'arrêt » : rien depuis {JOURS_INACTIVITE_ALERTE} jours ou "
                   "plus. Les cibles par AS (allocation proportionnelle, § 3.4.3) s'afficheront une fois "
                   "renseignées dans `ALLOCATION_AS` (data_quality.py).")
        ordre = list(STYLE_STATUT)
        vue = statut_as.assign(_o=statut_as["Statut"].map(ordre.index)).sort_values(["_o", "Aire de santé"])
        vue = vue.drop(columns=["_o", "Code"])
        vue = vue.astype(object).where(vue.notna(), "—").astype(str)
        st.dataframe(vue, hide_index=True, width="stretch", height=38 + 35 * len(vue),
                     column_config={"Statut": st.column_config.TextColumn(width="large"),
                                    "Aire de santé": st.column_config.TextColumn(width="medium")})
    with carte("as_bar"):
        ui.card_title("Ménages évalués par aire de santé")
        t = statut_as.sort_values("Ménages évalués")
        fig = go.Figure(go.Bar(
            x=t["Ménages évalués"], y=t["Aire de santé"], orientation="h", text=t["Ménages évalués"],
            textposition="outside", marker_color=theme.ACCENT, marker_line_width=0, marker_cornerradius=4,
            hovertemplate="%{y} : %{x} ménage(s) évalué(s)<extra></extra>"))
        fig.update_xaxes(title="Ménages évalués")
        theme.apply_layout(fig, height=60 + 28 * len(t))
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="as_bar_chart")
    with carte("as_detail"):
        ui.card_title("Détail par aire de santé", "sélection filtrée")
        detail_as = summary_by_aire(df_f)
        if not detail_as.empty:
            st.dataframe(detail_as, hide_index=True, width="stretch")
        else:
            st.info("Aucune donnée à détailler pour la sélection actuelle.")


def page_enqueteurs() -> None:
    ui.page_header("Enquêteurs", f"{len(ENQUETEURS)} enquêteurs",
                   "Rythme de soumission et qualité par enquêteur (sélection filtrée).")
    with carte("enq_bar"):
        ui.card_title("Entretiens complets par enquêteur")
        if "ID03" in df_f.columns and not df_f.empty:
            counts = df_f["ID03"].value_counts().rename_axis("ID03").reset_index(name="n")
            counts["Enquêteur"] = counts["ID03"].map(ENQUETEURS).fillna(counts["ID03"])
            counts = counts.sort_values("n", ascending=True)
            fig = go.Figure(go.Bar(
                x=counts["n"], y=counts["Enquêteur"], orientation="h", text=counts["n"], textposition="outside",
                marker_color=theme.ACCENT, marker_line_width=0, marker_cornerradius=4,
                hovertemplate="%{y} : %{x} entretiens<extra></extra>"))
            fig.update_xaxes(title="Entretiens")
            theme.apply_layout(fig, height=60 + 30 * len(counts))
            st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="enq_bar_chart")
        else:
            st.info("Champ ID03 (code enquêteur) absent des données chargées.")
    with carte("enq_heat"):
        ui.card_title("Tendance des soumissions par enquêteur", "jour × enquêteur")
        mat = submission_trend_matrix(df_f)
        if not mat.empty:
            st.caption("Nombre d'entretiens soumis par enquêteur et par jour : jours actifs, écarts et ruptures de rythme.")
            fig = go.Figure(go.Heatmap(
                z=mat.values.T, x=[d.strftime("%d/%m") for d in mat.index], y=mat.columns.tolist(),
                colorscale=theme.blue_colorscale(), colorbar=dict(title="Entretiens", outlinewidth=0),
                hovertemplate="%{y} — %{x}<br>%{z} entretien(s)<extra></extra>", xgap=2, ygap=2))
            fig.update_xaxes(title="Date", type="category")
            theme.apply_layout(fig, height=120 + 28 * len(mat.columns))
            st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="enq_heatmap")
        else:
            st.info("Pas assez de données (ID02/ID03) pour tracer la tendance par enquêteur.")
    with carte("enq_detail"):
        ui.card_title("Détail par enquêteur")
        detail_enq = summary_by_enqueteur(df_f)
        if not detail_enq.empty:
            st.dataframe(detail_enq, hide_index=True, width="stretch")
        else:
            st.info("Aucune donnée à détailler pour la sélection actuelle.")


def _graphe_forest(tab: pd.DataFrame, col_or: str, titre_x: str, key: str) -> None:
    t = tab.replace([float("inf"), float("-inf")], float("nan")).dropna(subset=[col_or, "IC bas", "IC haut"])
    if "Terme" in t.columns and "ORa [IC95 %]" in t.columns:
        t = t[t["ORa [IC95 %]"] != "instable"]
    t = t.iloc[::-1]
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
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key=key)


def page_projection() -> None:
    ui.page_header("Projection des analyses", "provisoire",
                   "Analyses prévues au § 3.9 du mémoire, recalculées sur les données déjà reçues.")
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
        with p1, garde("Objectif 1"):
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
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="chart_prev_as")
                st.dataframe(par_as.rename(columns={"Modalité": "Aire de santé"}), hide_index=True,
                             width="stretch")

        # Objectifs 2 à 4 ----------------------------------------------------
        with p2, garde("Objectifs 2 à 4"):
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
                        st.dataframe(t, hide_index=True, width="stretch")
            if not choix_desc:
                st.info("Aucune variable descriptive détectée dans l'export.")

        # Objectif 5 ---------------------------------------------------------
        with p5, garde("Analyse bivariée"):
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
                st.dataframe(vue, hide_index=True, width="stretch")
                st.markdown("**Détail par modalité**")
                st.dataframe(detail_bi, hide_index=True, width="stretch")
            else:
                st.info("Choisir au moins un facteur.")

        # Objectif 6 ---------------------------------------------------------
        with p6, garde("Régression logistique"):
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
                                 hide_index=True, width="stretch")
                    st.caption("Références : " + "; ".join(f"{nom_var(k)} = {v}" for k, v in res["references"].items())
                               if res["references"] else "")
                    _graphe_forest(coef, "ORa", "Odds Ratio ajusté (échelle log, IC95 %)", "chart_forest_ora")
                    if res.get("instables"):
                        st.warning("Estimation instable (séparation quasi complète : une modalité ne contient "
                                   "presque que des hésitants ou des non-hésitants) pour : "
                                   + ", ".join(res["instables"]) + ". Regrouper ces modalités ou attendre "
                                   "davantage de données.", icon="⚠️")
                    sig = coef[(coef["p"] < AN.SEUIL_SIGNIF) & (coef["ORa [IC95 %]"] != "instable")]
                    if len(sig):
                        st.markdown("**Facteurs provisoirement associés (p < 0,05)** : " + "; ".join(
                            f"{r['Terme']} (ORa {r['ORa [IC95 %]']})" for _, r in sig.iterrows()) + ".")
                    if res["vif"] is not None and (res["vif"]["VIF"] > 5).any():
                        st.warning("Colinéarité possible (VIF > 5) : "
                                   + ", ".join(res["vif"].loc[res["vif"]["VIF"] > 5, "Terme"]) + ".")
                    st.caption(f"Pseudo-R² de McFadden : {res['pseudo_r2']:.2f}".replace(".", ",")
                               + ("" if res["converge"] else " — ⚠️ le modèle n'a pas convergé."))

        # Ponctualité ----------------------------------------------------------
        with pp, garde("Ponctualité vaccinale"):
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
                st.dataframe(tab_ponct, hide_index=True, width="stretch")


def page_qualite() -> None:
    ui.page_header("Qualité des données", "contrôle de terrain",
                   "Complétude, doublons, durées d'entretien et alertes (soumissions complètes, sélection filtrée).")
    if df_f.empty:
        st.info("Aucune soumission complète pour la sélection actuelle. Vérifiez les filtres du menu, ou la page "
                f"« Mises de côté » ({len(df_incomplet)} soumission(s) incomplète(s)).")
        return

    k = st.columns(5, gap="small")
    blocs = [
        ("Entretiens complets", qr["n_total"], "sélection filtrée", "📝", "blue"),
        ("Doublons potentiels", qr["doublons_menage"], "même aire + quartier + enfant", "🔁",
         "red" if qr["doublons_menage"] else "green"),
        ("Entretiens < 5 min", qr["entretiens_courts_lt5min"] if qr["entretiens_courts_lt5min"] is not None else "—",
         "à vérifier avec l'enquêteur", "⏱️", "orange" if qr["entretiens_courts_lt5min"] else "green"),
        ("Durée médiane", f"{fr(qr['duree_mediane_min'])} min" if qr["duree_mediane_min"] is not None else "—",
         f"moyenne {fr(qr['duree_moyenne_min'])} min" if qr["duree_moyenne_min"] is not None else "", "⌛", "violet"),
        ("Mises de côté", len(df_inc_f), "soumissions incomplètes", "⏸️", "orange" if len(df_inc_f) else "green"),
    ]
    for col, (lab, val, sub, ic, ton) in zip(k, blocs):
        with col, carte(f"q_kpi_{ic}"):
            st.markdown(ui.kpi(lab, val, sub, ic, ton), unsafe_allow_html=True)

    q1, q2 = st.columns(2, gap="medium")
    with q1, carte("q_manquants"):
        ui.card_title("Valeurs manquantes sur les champs clés", "% des soumissions complètes")
        if qr["missing_by_field"]:
            miss = pd.DataFrame(list(qr["missing_by_field"].items()), columns=["Champ", "% manquant"])
            miss["% manquant"] = miss["% manquant"].astype(float).round(1)
            miss = miss.sort_values("% manquant")
            fig = go.Figure(go.Bar(
                x=miss["% manquant"], y=miss["Champ"], orientation="h", marker_color=theme.ACCENT,
                marker_line_width=0, marker_cornerradius=4, text=miss["% manquant"].map(lambda v: f"{fr(v)} %"),
                textposition="outside", hovertemplate="%{y} : %{x:.1f} % manquant<extra></extra>"))
            fig.update_xaxes(range=[0, max(100, float(miss["% manquant"].max()) * 1.15)], title="% manquant")
            theme.apply_layout(fig, height=70 + 34 * len(miss))
            st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="q_miss")
            st.caption("Un champ peut être vide normalement à cause d'un saut logique (ex. section non posée "
                       "aux ménages non éligibles).")
        else:
            st.info("Champs clés non trouvés dans l'export.")

    with q2, carte("q_alertes"):
        ui.card_title("Alertes de terrain")
        alerts = []
        if qr["doublons_menage"]:
            alerts.append(("error", f"{qr['doublons_menage']} doublon(s) potentiel(s) de ménage "
                                    "(même aire + quartier + repère enfant) — liste ci-dessous."))
        if qr["entretiens_courts_lt5min"]:
            alerts.append(("warning", f"{qr['entretiens_courts_lt5min']} entretien(s) de moins de 5 minutes — à vérifier."))
        if elig.get("taux_pct") is not None and elig["taux_pct"] < 50:
            alerts.append(("warning", f"Taux d'éligibilité/consentement faible ({fr(elig['taux_pct'])} %) — "
                                      "vérifier le recrutement sur le terrain."))
        if len(df_inc_f):
            alerts.append(("warning", f"{len(df_inc_f)} soumission(s) incomplète(s) mise(s) de côté — page "
                                      "« Mises de côté »."))
        if jours_depuis_dernier is not None and jours_depuis_dernier >= JOURS_INACTIVITE_ALERTE:
            alerts.append(("warning", f"Aucune soumission depuis {jours_depuis_dernier} jours — vérifier que la "
                                      "collecte est toujours active."))
        if len(pas_commencees):
            alerts.append(("error", f"{len(pas_commencees)} aire(s) de santé pas encore commencée(s) : "
                                    + ", ".join(pas_commencees["Aire de santé"]) + "."))
        if not alerts:
            st.success("Aucune alerte détectée sur les critères surveillés.", icon="✅")
        for niveau, texte in alerts:
            (st.error if niveau == "error" else st.warning)(texte, icon="🔴" if niveau == "error" else "🟠")

    duree_col = next((c for c in df_f.columns if c.split("/")[-1] == "DUREE_MIN"), None)
    if duree_col:
        with carte("q_durees"):
            ui.card_title("Durée des entretiens", "minutes")
            duree = pd.to_numeric(df_f[duree_col], errors="coerce").dropna()
            if len(duree):
                fig = go.Figure(go.Histogram(x=duree, nbinsx=25, marker_color=theme.ACCENT,
                                             marker_line=dict(color="#ffffff", width=2),
                                             hovertemplate="%{x} min : %{y} entretien(s)<extra></extra>"))
                fig.add_vline(x=5, line_dash="dash", line_color=theme.CRITICAL)
                fig.add_annotation(x=5, y=1, yref="paper", yanchor="bottom", xanchor="left", showarrow=False,
                                   text="seuil 5 min", font=dict(color=theme.CRITICAL, size=12))
                fig.update_xaxes(title="Durée (min)")
                fig.update_yaxes(title="Entretiens")
                theme.apply_layout(fig, height=260)
                fig.update_layout(margin=dict(t=28))
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="q_hist")

    cols_dedup = [c for c in ["ID04", "ID05", "C01", "C03"] if c in df_f.columns]
    if len(cols_dedup) >= 2 and qr["doublons_menage"]:
        with carte("q_doublons"):
            ui.card_title("Doublons potentiels à vérifier", " + ".join(cols_dedup))
            sub = df_f.dropna(subset=cols_dedup, how="all")
            dup = sub[sub.duplicated(subset=cols_dedup, keep=False)].sort_values(cols_dedup)
            cols = [c for c in ["N_FORMULAIRE", "ID01", "ID02", "ID03"] + cols_dedup if c in dup.columns]
            vue = dup[cols].copy()
            if "ID03" in vue.columns:
                vue["ID03"] = vue["ID03"].map(ENQUETEURS).fillna(vue["ID03"])
            if "ID04" in vue.columns:
                vue["ID04"] = vue["ID04"].map(AIRES_SANTE).fillna(vue["ID04"])
            if "ID02" in vue.columns:
                vue["ID02"] = pd.to_datetime(vue["ID02"], errors="coerce").dt.date
            vue = cellules_simples(vue)
            vue = vue.astype(object).where(vue.notna(), "—").astype(str)
            st.dataframe(vue.rename(columns={"ID02": "Date", "ID03": "Enquêteur",
                                                               "ID04": "Aire de santé", "ID05": "Quartier/avenue"}),
                         hide_index=True, width="stretch")


def page_mises_de_cote() -> None:
    ui.page_header("Mises de côté", f"{len(df_inc_f)} soumission(s)",
                   "Soumissions incomplètes exclues de tous les indicateurs et de l'objectif de 424 ménages.")
    with carte("inc"):
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
                    st.dataframe(par_enq, hide_index=True, width="stretch")
            with ic2:
                st.markdown("**Par motif**")
                par_motif = (df_inc_f["MOTIF_MISE_DE_COTE"].str.split(" ; ").explode()
                             .value_counts().rename_axis("Motif").reset_index(name="Soumissions"))
                st.dataframe(par_motif[["Soumissions", "Motif"]], hide_index=True, width="stretch")

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
            st.dataframe(vue_inc, hide_index=True, width="stretch")
            buf_inc = io.BytesIO()
            cellules_simples(df_inc_f).to_csv(buf_inc, index=False)
            st.download_button(
                "Télécharger les soumissions mises de côté (CSV)",
                data=buf_inc.getvalue(), icon=":material/download:", type="primary",
                file_name=f"vaxsuivi_lemba_incompletes_{date.today().isoformat()}.csv",
                mime="text/csv",
            )


def page_donnees_brutes() -> None:
    ui.page_header("Données brutes", "export",
                   "Consultation et téléchargement des soumissions (sélection filtrée).")
    choix = st.segmented_control("Soumissions à afficher", ["Complètes", "Mises de côté", "Toutes"],
                                 default="Complètes", key="brutes_choix")
    if choix == "Mises de côté":
        base_vue = df_inc_f
    elif choix == "Toutes":
        base_vue = pd.concat([df_f, df_inc_f])
    else:
        base_vue = df_f
    with carte("brutes"):
        ui.card_title(f"{len(base_vue)} soumission(s)", f"{base_vue.shape[1]} colonnes")
        if base_vue.empty:
            st.info("Aucune soumission pour ce choix et ces filtres. "
                    + (f"{len(df_incomplet)} soumission(s) sont mises de côté : choisissez « Mises de côté » ou "
                       "« Toutes »." if len(df_incomplet) and choix == "Complètes" else ""))
            return
        num_cols = [c for c in ["N_FORMULAIRE", "N_MENAGE", "N_DANS_AIRE", "N_DANS_ENQUETEUR", "MOTIF_MISE_DE_COTE"]
                    if c in base_vue.columns]
        autres = [c for c in base_vue.columns if c not in num_cols]
        vue = cellules_simples(base_vue[num_cols + autres])
        if "N_FORMULAIRE" in vue.columns:
            vue = vue.sort_values("N_FORMULAIRE")
        st.dataframe(vue, width="stretch", hide_index=True, height=520)
        buf = io.BytesIO()
        vue.to_csv(buf, index=False)
        st.download_button("Télécharger en CSV", data=buf.getvalue(), icon=":material/download:",
                           file_name=f"vaxsuivi_lemba_{choix.lower().replace(' ', '_')}_{date.today().isoformat()}.csv",
                           mime="text/csv", type="primary")
        st.caption("Le champ GPS (ID08) figure dans cet export : retirez-le de tout fichier partagé largement.")


# ==================================================================
# AIGUILLAGE — chaque page est isolée : une erreur reste confinée à sa page
# ==================================================================
FONCTIONS = {
    "Tableau de bord": page_tableau_de_bord,
    "Aires de santé": page_aires_de_sante,
    "Enquêteurs": page_enqueteurs,
    "Projection des analyses": page_projection,
    "Qualité des données": page_qualite,
    "Mises de côté": page_mises_de_cote,
    "Données brutes": page_donnees_brutes,
}
with garde(page):
    FONCTIONS[page]()

st.caption("VaxSuivi-Lemba — outil de suivi de terrain, pas de publication des résultats du mémoire. "
           "Données traitées en mémoire pour la session ; aucune donnée n'est stockée par l'application.")

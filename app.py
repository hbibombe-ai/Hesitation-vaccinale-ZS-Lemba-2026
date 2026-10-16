"""
Tableau de bord — Hésitation vaccinale chez les parents d'enfants de 0-23 mois,
Zone de santé de Lemba (Kinshasa). Données de démonstration entièrement fictives.

Lancement local : streamlit run app.py
"""
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Hésitation vaccinale — ZS Lemba",
    page_icon="💉",
    layout="wide",
)

DATA = Path(__file__).parent / "data.csv"
BLEU = "#1F4E79"
ROUGE = "#C0392B"


@st.cache_data
def charger(chemin: Path) -> pd.DataFrame:
    d = pd.read_csv(chemin, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    for c in ["hesitation", "exposition_rumeur_G03", "rendez_vous_manque_C07"]:
        d[c] = d[c].astype(int)
    d["date_soumission"] = pd.to_datetime(d["date_soumission"])
    d["mois"] = d["date_soumission"].dt.strftime("%Y-%m")
    return d


def pct(part: int, total: int) -> str:
    return f"{part / total * 100:.1f} %".replace(".", ",") if total else "—"


df = charger(DATA)

# ---------------------------------------------------------------- filtres
st.sidebar.header("Filtres")
aires = sorted(df["aire_sante"].unique())
ages = sorted(df["age_enfant"].unique())
mois = sorted(df["mois"].unique())

choix_aire = st.sidebar.multiselect("Aire de santé", aires, default=aires)
choix_age = st.sidebar.multiselect("Âge de l'enfant", ages, default=ages)
choix_mois = st.sidebar.multiselect("Mois de soumission", mois, default=mois)

d = df[
    df["aire_sante"].isin(choix_aire)
    & df["age_enfant"].isin(choix_age)
    & df["mois"].isin(choix_mois)
]

st.sidebar.markdown(
    "---\n**Démo : données entièrement fictives.** Ces chiffres n'expriment pas la "
    "réalité de la population de Lemba."
)

# ---------------------------------------------------------------- en-tête
st.title("Hésitation vaccinale")
st.caption(
    "Suivi des perceptions et expériences des parents d'enfants de 0 à 23 mois · "
    "Zone de santé de Lemba · Août – octobre 2026"
)
st.warning(
    "**Démo — données entièrement fictives.** Ces chiffres illustrent le tableau de bord "
    "et ne décrivent pas la population de Lemba. À remplacer par des données vérifiées "
    "avant toute décision de santé publique."
)

n = len(d)
positifs = int(d["hesitation"].sum())

if n == 0:
    st.info("Aucun formulaire ne correspond aux filtres choisis.")
    st.stop()

# ---------------------------------------------------------------- indicateurs
c1, c2, c3, c4 = st.columns(4)
c1.metric("Formulaires soumis", f"{n:,}".replace(",", " "))
c2.metric("Cas d'hésitation", f"{positifs}")
c3.metric("Taux d'hésitation", pct(positifs, n))
c4.metric("Exposition à des rumeurs", pct(int(d["exposition_rumeur_G03"].sum()), n))
st.caption(
    f"Rendez-vous manqués : {pct(int(d['rendez_vous_manque_C07'].sum()), n)} des formulaires. "
    "Le taux d'hésitation est la proportion de formulaires classés positifs dans la sélection "
    "filtrée ; ce n'est pas une prévalence représentative."
)

# ---------------------------------------------------------------- graphiques
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Évolution hebdomadaire")
    hebdo = d.assign(semaine=d["date_soumission"] - pd.to_timedelta(d["date_soumission"].dt.weekday, unit="D"))
    hebdo = (
        hebdo.groupby("semaine")
        .agg(total=("hesitation", "size"), positifs=("hesitation", "sum"))
        .reset_index()
    )
    hebdo["taux"] = hebdo["positifs"] / hebdo["total"] * 100
    fig = px.line(hebdo, x="semaine", y="taux", markers=True, labels={"semaine": "Semaine", "taux": "Taux (%)"})
    fig.update_traces(line_color=BLEU)
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width='stretch')

with col_b:
    st.subheader("Taux d'hésitation par aire de santé")
    par_aire = (
        d.groupby("aire_sante")
        .agg(total=("hesitation", "size"), positifs=("hesitation", "sum"))
        .reset_index()
    )
    par_aire["taux"] = par_aire["positifs"] / par_aire["total"] * 100
    par_aire = par_aire.sort_values("taux")
    fig = px.bar(par_aire, x="taux", y="aire_sante", orientation="h",
                 labels={"taux": "Taux (%)", "aire_sante": ""})
    fig.update_traces(marker_color=BLEU)
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width='stretch')

col_c, col_d = st.columns(2)

with col_c:
    st.subheader("Motifs principaux d'hésitation")
    motifs = (
        d[d["hesitation"] == 1]["raison_principale"].value_counts().reset_index()
    )
    motifs.columns = ["motif", "effectif"]
    if motifs.empty:
        st.info("Aucun cas d'hésitation dans la sélection.")
    else:
        fig = px.bar(motifs.sort_values("effectif"), x="effectif", y="motif", orientation="h",
                     labels={"effectif": "Effectif", "motif": ""})
        fig.update_traces(marker_color=ROUGE)
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width='stretch')

with col_d:
    st.subheader("Sources d'information principales")
    sources = d["source_information_principale"].value_counts().reset_index()
    sources.columns = ["source", "effectif"]
    fig = px.bar(sources.sort_values("effectif"), x="effectif", y="source", orientation="h",
                 labels={"effectif": "Effectif", "source": ""})
    fig.update_traces(marker_color=BLEU)
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width='stretch')

# ---------------------------------------------------------------- données
st.subheader("Formulaires filtrés")
colonnes = [c for c in d.columns if c != "mois"]
st.dataframe(d[colonnes], width='stretch', hide_index=True)
st.download_button(
    "Exporter la sélection (CSV)",
    data=d[colonnes].to_csv(index=False).encode("utf-8-sig"),
    file_name="lemba_donnees_simulees_filtrees.csv",
    mime="text/csv",
)
st.caption(
    "Aucune coordonnée GPS, nom ni téléphone ne figure dans ces données. "
    "Pour toute publication de données réelles, utilisez un export dé-identifié et restreignez l'accès."
)

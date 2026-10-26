# -*- coding: utf-8 -*-
"""Fonctions de nettoyage, de normalisation de noms de colonnes et de contrôle
qualité pour les soumissions Kobo du mémoire sur l'hésitation vaccinale (ZS Lemba).
"""
from __future__ import annotations

import pandas as pd

AIRES_SANTE = {
    "AS01_Molo": "Molo", "AS02_Kemi": "Kemi", "AS03_Livulu": "Livulu",
    "AS04_MbanzaLemba": "Mbanza Lemba", "AS05_Plateau": "Plateau",
    "AS06_Salongo": "Salongo", "AS07_Echangeur": "Échangeur", "AS08_Ecole": "École",
    "AS09_Madrandele": "Madrandele", "AS10_Foire": "Foire",
    "AS11_Kimpwanza": "Kimpwanza", "AS12_Gombele": "Gombele",
    "AS13_Commercial": "Commercial", "AS14_Masano": "Masano",
}

# Correspondance code -> nom, alignée sur la liste "enqueteur" du XLSForm.
# Les 4 premiers enquêteurs couvrent 2 AS chacun, les 6 suivants 1 AS chacun.
ENQUETEURS = {
    "ENQ01": "Gabriel", "ENQ02": "Edson", "ENQ03": "Richard", "ENQ04": "Dan",
    "ENQ05": "Germain", "ENQ06": "Ange", "ENQ07": "Benjamin", "ENQ08": "Eliezer",
    "ENQ09": "Azaria", "ENQ10": "Evariste",
}

# Colonnes clés attendues, avec leur nom "groupé" possible tel qu'exporté par Kobo
# (Kobo préfixe parfois les champs de groupe, ex. "grp_id/ID04").
KEY_FIELDS = [
    "ID01", "ID02", "ID03", "ID04", "ID05", "ID06", "ID07", "ID09",
    "A01", "A02", "A04",
    "DUREE_MIN", "HESITATION",
]


def _est_oui(s: pd.Series) -> pd.Series:
    """Vrai quand la réponse vaut 1 (« oui »), que Kobo l'exporte en 1, 1.0 ou "1"."""
    return pd.to_numeric(s, errors="coerce") == 1


def _find_col(df: pd.DataFrame, short_name: str) -> str | None:
    """Retrouve une colonne Kobo quel que soit son préfixe de groupe éventuel."""
    if short_name in df.columns:
        return short_name
    candidates = [c for c in df.columns if c.split("/")[-1] == short_name]
    return candidates[0] if candidates else None


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renvoie une copie du DataFrame avec des alias de colonnes simples
    (sans préfixe de groupe) pour les champs clés utilisés par le tableau de bord."""
    if df.empty:
        return df
    out = df.copy()
    for field in KEY_FIELDS:
        col = _find_col(out, field)
        if col and col != field:
            out[field] = out[col]
    return out


def add_sequential_numbers(df: pd.DataFrame) -> pd.DataFrame:
    """Attribue une numérotation séquentielle propre des formulaires/ménages.

    Dans ce protocole, un formulaire = un ménage = un enfant cible : la
    numérotation du formulaire et celle du ménage sont donc la même séquence.

    Pourquoi ici et pas directement dans le formulaire Kobo : un smartphone
    hors-ligne ne connaît jamais le nombre total de formulaires déjà soumis
    par les autres enquêteurs au même moment — aucun XLSForm ne peut garantir
    un numéro 1, 2, 3... strictement séquentiel et sans doublon tant que les
    soumissions de plusieurs téléphones n'ont pas été centralisées. C'est
    pourquoi le formulaire génère déjà un code unique automatique (aire +
    enquêteur + horodatage, voir ID01/ID06) qui ne nécessite aucune saisie et
    ne peut jamais se dupliquer, même hors-ligne ; et c'est ici, une fois les
    soumissions centralisées sur le serveur Kobo, que la vraie numérotation
    séquentielle 1, 2, 3... peut être calculée de façon fiable.
    """
    if df.empty:
        return df
    out = df.copy()

    sort_col = None
    for cand in ["_submission_time", "start", "ID02"]:
        col = _find_col(out, cand)
        if col:
            sort_col = col
            break
    if sort_col:
        out["_tri_chrono"] = pd.to_datetime(out[sort_col], errors="coerce")
        out = out.sort_values("_tri_chrono", kind="stable", na_position="last")
        out = out.drop(columns="_tri_chrono")
    out = out.reset_index(drop=True)

    out["N_FORMULAIRE"] = range(1, len(out) + 1)
    out["N_MENAGE"] = out["N_FORMULAIRE"]  # 1 formulaire = 1 ménage dans ce protocole

    if "ID04" in out.columns:
        out["N_DANS_AIRE"] = out.groupby("ID04").cumcount() + 1
    if "ID03" in out.columns:
        out["N_DANS_ENQUETEUR"] = out.groupby("ID03").cumcount() + 1

    return out


def apply_filters(
    df: pd.DataFrame,
    aires: list[str] | None = None,
    enqueteurs: list[str] | None = None,
    date_min=None,
    date_max=None,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "ID02" in out.columns:
        out["ID02"] = pd.to_datetime(out["ID02"], errors="coerce")
    if aires and "ID04" in out.columns:
        out = out[out["ID04"].isin(aires)]
    if enqueteurs and "ID03" in out.columns:
        out = out[out["ID03"].isin(enqueteurs)]
    if date_min is not None and "ID02" in out.columns:
        out = out[out["ID02"] >= pd.Timestamp(date_min)]
    if date_max is not None and "ID02" in out.columns:
        out = out[out["ID02"] <= pd.Timestamp(date_max)]
    return out


def quality_report(df: pd.DataFrame) -> dict:
    """Calcule quelques indicateurs simples de qualité des données."""
    report = {
        "n_total": len(df),
        "missing_by_field": {},
        "doublons_menage": 0,
        "duree_moyenne_min": None,
        "duree_mediane_min": None,
        "entretiens_courts_lt5min": None,
    }
    if df.empty:
        return report

    for field in ["ID03", "ID04", "ID06", "C03", "B02"]:
        col = _find_col(df, field)
        if col:
            pct_missing = df[col].isna().mean() * 100
            report["missing_by_field"][field] = round(pct_missing, 1)

    # NB : ID06 est désormais un code généré automatiquement (unique par
    # construction), donc inutile pour détecter des doublons. On se base plutôt
    # sur une combinaison "lieu + repère enfant" plus proche d'un vrai doublon
    # de ménage/entretien (même aire, même quartier, même enfant).
    id04_col, id05_col = _find_col(df, "ID04"), _find_col(df, "ID05")
    c01_col, c03_col = _find_col(df, "C01"), _find_col(df, "C03")
    dedup_cols = [c for c in [id04_col, id05_col, c01_col, c03_col] if c]
    if len(dedup_cols) >= 2:
        subset = df[dedup_cols].dropna(how="all")
        report["doublons_menage"] = int(subset.duplicated().sum())

    duree_col = _find_col(df, "DUREE_MIN")
    if duree_col:
        duree = pd.to_numeric(df[duree_col], errors="coerce").dropna()
        if len(duree):
            report["duree_moyenne_min"] = round(duree.mean(), 1)
            report["duree_mediane_min"] = round(duree.median(), 1)
            report["entretiens_courts_lt5min"] = int((duree < 5).sum())

    return report


def hesitation_prevalence(df: pd.DataFrame) -> float | None:
    col = _find_col(df, "HESITATION")
    if not col or df.empty:
        return None
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(vals) == 0:
        return None
    return round(vals.mean() * 100, 1)


def submission_trend_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Matrice jour × enquêteur du nombre de soumissions, pour la heatmap de
    tendance. Index = dates (ordre chronologique), colonnes = noms d'enquêteurs."""
    if df.empty or "ID02" not in df.columns or "ID03" not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["ID02"] = pd.to_datetime(tmp["ID02"], errors="coerce")
    tmp = tmp.dropna(subset=["ID02"])
    if tmp.empty:
        return pd.DataFrame()
    tmp["Enquêteur"] = tmp["ID03"].map(ENQUETEURS).fillna(tmp["ID03"])
    tmp["Jour"] = tmp["ID02"].dt.date
    mat = tmp.pivot_table(index="Jour", columns="Enquêteur", values="ID02", aggfunc="count", fill_value=0)
    mat = mat.sort_index()
    return mat


def summary_by_enqueteur(df: pd.DataFrame) -> pd.DataFrame:
    """Tableau de détail par enquêteur : volume, part du total, durée moyenne,
    taux d'éligibilité, dernière date active."""
    if df.empty or "ID03" not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["Enquêteur"] = tmp["ID03"].map(ENQUETEURS).fillna(tmp["ID03"])
    if "ID02" in tmp.columns:
        tmp["ID02"] = pd.to_datetime(tmp["ID02"], errors="coerce")

    rows = []
    for enq, sub in tmp.groupby("Enquêteur"):
        row = {
            "Enquêteur": enq,
            "Entretiens": len(sub),
            "Part (%)": round(len(sub) / len(tmp) * 100, 1) if len(tmp) else 0,
        }
        duree_col = _find_col(sub, "DUREE_MIN")
        if duree_col:
            d = pd.to_numeric(sub[duree_col], errors="coerce").dropna()
            row["Durée moy. (min)"] = round(d.mean(), 1) if len(d) else None
        elig = eligibility_rate(sub)
        row["Éligibilité (%)"] = elig["taux_pct"]
        if "ID02" in sub.columns and sub["ID02"].notna().any():
            row["Dernière activité"] = sub["ID02"].max().date().isoformat()
            jours_actifs = sub["ID02"].dt.date.nunique()
            row["Moy. / jour actif"] = round(len(sub) / jours_actifs, 1) if jours_actifs else None
        rows.append(row)

    out = pd.DataFrame(rows).sort_values("Entretiens", ascending=False).reset_index(drop=True)
    return out


def summary_by_aire(df: pd.DataFrame) -> pd.DataFrame:
    """Tableau de détail par aire de santé : volume, part du total, durée moyenne,
    taux d'éligibilité."""
    if df.empty or "ID04" not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["Aire de santé"] = tmp["ID04"].map(AIRES_SANTE).fillna(tmp["ID04"])

    rows = []
    for aire, sub in tmp.groupby("Aire de santé"):
        row = {
            "Aire de santé": aire,
            "Entretiens": len(sub),
            "Part (%)": round(len(sub) / len(tmp) * 100, 1) if len(tmp) else 0,
        }
        duree_col = _find_col(sub, "DUREE_MIN")
        if duree_col:
            d = pd.to_numeric(sub[duree_col], errors="coerce").dropna()
            row["Durée moy. (min)"] = round(d.mean(), 1) if len(d) else None
        elig = eligibility_rate(sub)
        row["Éligibilité (%)"] = elig["taux_pct"]
        rows.append(row)

    out = pd.DataFrame(rows).sort_values("Entretiens", ascending=False).reset_index(drop=True)
    return out


# ------------------------------------------------------------------
# STATUT DE LA COLLECTE PAR AIRE DE SANTÉ (14 AS)
# ------------------------------------------------------------------
# Cibles par AS selon l'allocation proportionnelle du mémoire (§ 3.4.3 :
# nᵢ = Nᵢ/N × 424). À renseigner dès que les populations des AS sont fixées,
# ex. {"AS01_Molo": 31, ...} ; tant que le dictionnaire est vide, seuls les
# effectifs atteints sont affichés.
ALLOCATION_AS: dict[str, int] = {}

JOURS_INACTIVITE_ALERTE = 3


def statut_aires(df_complet: pd.DataFrame, df_incomplet: pd.DataFrame | None = None,
                 aujourd_hui=None) -> pd.DataFrame:
    """Une ligne par aire de santé (les 14 AS, même sans aucune soumission) :
    statut de démarrage, ménages évalués, dernière soumission, cible éventuelle.

    Statuts : « Pas commencée » (aucune soumission, complète ou non),
    « Commencée — incomplètes seulement » (seules des soumissions mises de côté),
    « À l'arrêt » (commencée, mais rien depuis JOURS_INACTIVITE_ALERTE jours ou plus),
    « En cours » (commencée et active), « Cible atteinte » (si ALLOCATION_AS renseignée).
    """
    aujourd_hui = pd.Timestamp(aujourd_hui or pd.Timestamp.today().normalize())
    df_incomplet = df_incomplet if df_incomplet is not None else pd.DataFrame()

    def _par_aire(df):
        if df.empty or "ID04" not in df.columns:
            return {}
        return {a: sub for a, sub in df.groupby("ID04")}

    comp, inc = _par_aire(df_complet), _par_aire(df_incomplet)
    lignes = []
    for code, nom in AIRES_SANTE.items():
        sub = comp.get(code, pd.DataFrame())
        n_inc = len(inc.get(code, []))
        n_eval = int(evaluated_mask(sub).sum()) if not sub.empty else 0
        derniere = None
        if not sub.empty and "ID02" in sub.columns:
            d = pd.to_datetime(sub["ID02"], errors="coerce").dropna()
            derniere = d.max().normalize() if len(d) else None
        premiere = None
        if not sub.empty and "ID02" in sub.columns:
            d = pd.to_datetime(sub["ID02"], errors="coerce").dropna()
            premiere = d.min().normalize() if len(d) else None
        jours = int((aujourd_hui - derniere).days) if derniere is not None else None
        cible = ALLOCATION_AS.get(code)

        if sub.empty and n_inc == 0:
            statut = "Pas commencée"
        elif sub.empty:
            statut = "Commencée — incomplètes seulement"
        elif cible and n_eval >= cible:
            statut = "Cible atteinte"
        elif jours is not None and jours >= JOURS_INACTIVITE_ALERTE:
            statut = "À l'arrêt"
        else:
            statut = "En cours"

        lignes.append({
            "Code": code, "Aire de santé": nom, "Statut": statut,
            "Entretiens complets": len(sub), "Ménages évalués": n_eval,
            "Cible": cible, "Mises de côté": n_inc,
            "Début": premiere.date().isoformat() if premiere is not None else None,
            "Dernière soumission": derniere.date().isoformat() if derniere is not None else None,
            "Jours sans soumission": jours,
        })
    out = pd.DataFrame(lignes)
    out["Jours sans soumission"] = out["Jours sans soumission"].astype("Int64")
    if not ALLOCATION_AS:
        out = out.drop(columns="Cible")
    return out


# ------------------------------------------------------------------
# SOUMISSIONS INCOMPLÈTES (mises de côté)
# ------------------------------------------------------------------
# Champs d'identification indispensables pour rattacher un entretien à une
# date, un enquêteur et une aire de santé.
CHAMPS_IDENTIFICATION = {
    "ID02": "date d'entretien", "ID03": "enquêteur", "ID04": "aire de santé",
}
# Champs qui doivent être remplis quand le ménage est éligible ET consentant
# (le questionnaire a donc dû être administré jusqu'au bout). Seuls ceux
# présents dans l'export sont contrôlés : compléter la liste avec d'autres
# variables obligatoires du questionnaire si besoin.
CHAMPS_OBLIGATOIRES_EVALUES = {
    "B02": "section B", "C03": "section C", "HESITATION": "statut d'hésitation",
}


def incomplete_reasons(df: pd.DataFrame) -> pd.Series:
    """Renvoie, pour chaque soumission, le(s) motif(s) d'incomplétude séparés
    par « ; » (chaîne vide = soumission complète). Règles :
      1. un champ d'identification (ID02, ID03, ID04) est vide ;
      2. l'éligibilité (A01) ou, si A01 = 1, le consentement (A04) n'est pas renseigné ;
      3. ménage éligible et consentant, mais un champ obligatoire du
         questionnaire est vide (questionnaire interrompu) ;
      4. soumission marquée « Non approuvée » dans la validation Kobo.
    """
    motifs = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)
    if df.empty:
        return motifs.map(lambda m: "")

    def _vide(col: str) -> pd.Series:
        s = df[col]
        return s.isna() | (s.astype(str).str.strip().isin(["", "nan", "None", "NaT"]))

    def _ajouter(mask: pd.Series, texte: str) -> None:
        for i in df.index[mask.fillna(False)]:
            motifs.at[i].append(texte)

    for field, label in CHAMPS_IDENTIFICATION.items():
        col = _find_col(df, field)
        if col:
            _ajouter(_vide(col), f"{label} manquant(e) ({field})")

    a01, a04 = _find_col(df, "A01"), _find_col(df, "A04")
    if a01:
        _ajouter(_vide(a01), "éligibilité non renseignée (A01)")
        if a04:
            _ajouter(_est_oui(df[a01]) & _vide(a04), "consentement non renseigné (A04)")

    evalues = evaluated_mask(df) if all(_find_col(df, c) for c in ["A01", "A02", "A04"]) \
        else pd.Series(True, index=df.index)
    for field, label in CHAMPS_OBLIGATOIRES_EVALUES.items():
        col = _find_col(df, field)
        if col:
            _ajouter(evalues & _vide(col), f"questionnaire interrompu : {label} vide ({field})")

    for col in ["_validation_status.uid", "_validation_status"]:
        if col in df.columns:
            statut = df[col].astype(str).str.lower()
            _ajouter(statut.str.contains("not_approved|not approved|non approuv", regex=True),
                     "rejetée lors de la validation Kobo")
            break

    return motifs.map(lambda m: " ; ".join(dict.fromkeys(m)))


def split_complete(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sépare les soumissions complètes (utilisées pour tous les indicateurs)
    des soumissions incomplètes (mises de côté, avec leur motif)."""
    if df.empty:
        return df, df.assign(MOTIF_MISE_DE_COTE=pd.Series(dtype=str))
    motifs = incomplete_reasons(df)
    complet = df[motifs == ""].copy()
    incomplet = df[motifs != ""].copy()
    incomplet["MOTIF_MISE_DE_COTE"] = motifs[motifs != ""]
    return complet, incomplet


def evaluated_mask(df: pd.DataFrame) -> pd.Series:
    """Ménages réellement évalués pour l'hésitation vaccinale : éligibles ET
    consentants (A01 = A02 = A04 = 1). Ce sont eux qui comptent pour l'objectif
    de 424 ménages. Si les champs A01/A02/A04 sont absents de l'export, tous
    les formulaires sont comptés (repli prudent signalé dans l'interface)."""
    a01, a02, a04 = _find_col(df, "A01"), _find_col(df, "A02"), _find_col(df, "A04")
    if not (a01 and a02 and a04):
        return pd.Series(True, index=df.index)
    return (
        _est_oui(df[a01])
        & _est_oui(df[a02])
        & _est_oui(df[a04])
    )


def eligibility_rate(df: pd.DataFrame) -> dict:
    """Taux d'éligibilité et de consentement, basé sur A01/A02/A04."""
    out = {"n_total": len(df), "n_eligibles_consentants": None, "taux_pct": None}
    a01, a02, a04 = _find_col(df, "A01"), _find_col(df, "A02"), _find_col(df, "A04")
    if a01 and a02 and a04 and len(df):
        mask = (
            _est_oui(df[a01])
            & _est_oui(df[a02])
            & _est_oui(df[a04])
        )
        out["n_eligibles_consentants"] = int(mask.sum())
        out["taux_pct"] = round(mask.mean() * 100, 1)
    return out

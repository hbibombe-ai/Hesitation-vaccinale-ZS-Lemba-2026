# -*- coding: utf-8 -*-
"""Projection provisoire des analyses statistiques prévues au § 3.9 du mémoire
« Facteurs associés à l'hésitation vaccinale… ZS Lemba, 2026 », calculées sur
les soumissions complètes déjà reçues.

  Objectif 1   prévalence de l'hésitation vaccinale + IC95 % (Wilson)
  Objectifs 2-4  description : effectifs/% ; moyenne/ET ou médiane/IQR selon la symétrie
  Objectif 5   bivariée : Chi² de Pearson ou test exact de Fisher, ORb + IC95 % (Woolf) ;
               variables quantitatives : t de Student (Welch) ou Mann-Whitney
  Objectif 6   régression logistique binaire multivariée : ORa + IC95 %, p,
               colinéarité (VIF), test de Hosmer-Lemeshow, événements par variable
  Ponctualité  BCG, Penta 1, Penta 3, VAR 1 : retard si > 28 jours après l'âge recommandé

Ce ne sont PAS les résultats du mémoire : l'analyse finale reste faite sous SPSS
sur la base apurée, une fois les 424 ménages atteints.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy import stats

from data_quality import _find_col, evaluated_mask

Z95 = 1.959963984540054
SEUIL_PRESELECTION = 0.20   # § 3.9.3 : présélection des variables à p < 0,20
SEUIL_SIGNIF = 0.05

# Colonnes jamais proposées comme facteurs (identification, métadonnées Kobo,
# éligibilité — constante dans la base d'analyse —, variable dépendante).
_EXCLUES_EXACT = {
    "ID01", "ID02", "ID03", "ID05", "ID06", "ID07", "ID08", "ID09",
    "A01", "A02", "A03", "A04", "HESITATION", "DUREE_MIN",
    "N_FORMULAIRE", "N_MENAGE", "N_DANS_AIRE", "N_DANS_ENQUETEUR", "MOTIF_MISE_DE_COTE",
    "start", "end", "today", "deviceid", "username", "phonenumber", "simserial",
    "subscriberid", "audit", "instanceID", "instanceName", "formhub/uuid", "__version__",
}
_EXCLUES_PREFIXES = ("_", "meta/", "formhub/")

# Ponctualité vaccinale (§ 3.6 et 3.9.1) : questions C11 à C15 du questionnaire.
# Adapter les codes si l'export Kobo les nomme autrement.
CHAMP_DATE_NAISSANCE = "C11"
DOSES_PONCTUALITE = {           # dose: (champ de la date, âge recommandé)
    "BCG": ("C12", pd.DateOffset(days=0)),
    "Penta 1": ("C13", pd.DateOffset(weeks=6)),
    "Penta 3": ("C14", pd.DateOffset(weeks=14)),
    "VAR 1": ("C15", pd.DateOffset(months=9)),
}
DELAI_GRACE_JOURS = 28


# ------------------------------------------------------------------ outils
def _court(col: str) -> str:
    return col.split("/")[-1]


def fmt_p(p) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    return "< 0,001" if p < 0.001 else f"{p:.3f}".replace(".", ",")


def fmt_or(o, lo, hi) -> str:
    if o is None or any(isinstance(v, float) and (math.isnan(v) or math.isinf(v)) for v in (o, lo, hi)):
        return "—"
    return f"{o:.2f} [{lo:.2f} – {hi:.2f}]".replace(".", ",")


def variable_dependante(df: pd.DataFrame) -> pd.Series:
    """HESITATION en 0/1 (accepte 0/1, « oui/non », « hésitant/non hésitant »)."""
    col = _find_col(df, "HESITATION")
    if not col:
        return pd.Series(np.nan, index=df.index)
    s = df[col]
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().any():
        return num.where(num.isin([0, 1]))
    txt = s.astype(str).str.strip().str.lower()
    out = pd.Series(np.nan, index=df.index)
    out[txt.str.startswith("non")] = 0
    out[txt.isin(["oui", "1", "hésitant", "hesitant"])] = 1
    return out


def base_analyse(df: pd.DataFrame) -> pd.DataFrame:
    """Ménages évalués (éligibles + consentants) dont HESITATION est renseignée ;
    ajoute la colonne _Y (0/1)."""
    if df.empty:
        return df.assign(_Y=pd.Series(dtype=float))
    out = df[evaluated_mask(df)].copy()
    out["_Y"] = variable_dependante(out)
    return out[out["_Y"].notna()]


# ------------------------------------------------------------------ objectif 1
def ic_wilson(k: int, n: int) -> tuple[float, float, float]:
    if n == 0:
        return (math.nan, math.nan, math.nan)
    p = k / n
    den = 1 + Z95 ** 2 / n
    centre = (p + Z95 ** 2 / (2 * n)) / den
    demi = Z95 * math.sqrt(p * (1 - p) / n + Z95 ** 2 / (4 * n * n)) / den
    return (p, max(0.0, centre - demi), min(1.0, centre + demi))


def prevalence(base: pd.DataFrame) -> dict:
    n, k = len(base), int(base["_Y"].sum()) if len(base) else 0
    p, lo, hi = ic_wilson(k, n)
    return {"n": n, "k": k, "p": p, "lo": lo, "hi": hi}


def precision_projetee(p: float, n: int) -> float:
    """Demi-largeur de l'IC95 % (approximation normale) pour une prévalence p et un effectif n."""
    if not n or p is None or math.isnan(p):
        return math.nan
    return Z95 * math.sqrt(p * (1 - p) / n)


def prevalence_par(base: pd.DataFrame, col: str, libelles: dict | None = None) -> pd.DataFrame:
    if base.empty or col not in base.columns:
        return pd.DataFrame()
    lignes = []
    for mod, sub in base.groupby(col, dropna=True):
        p, lo, hi = ic_wilson(int(sub["_Y"].sum()), len(sub))
        lignes.append({"Modalité": (libelles or {}).get(mod, mod), "n": len(sub),
                       "Hésitants": int(sub["_Y"].sum()), "Prévalence (%)": round(p * 100, 1),
                       "IC95 %": f"{lo * 100:.1f} – {hi * 100:.1f}".replace(".", ",")})
    return pd.DataFrame(lignes).sort_values("n", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------ variables candidates
def variables_candidates(base: pd.DataFrame) -> tuple[list[str], list[str]]:
    """(qualitatives, quantitatives) présentes dans l'export et exploitables."""
    qual, quant = [], []
    for col in base.columns:
        court = _court(col)
        if col == "_Y" or court in _EXCLUES_EXACT or col in _EXCLUES_EXACT \
                or col.startswith(_EXCLUES_PREFIXES) or court.startswith("_"):
            continue
        if court in {"ID04"}:
            qual.append(col)
            continue
        s = base[col].dropna()
        if len(s) < 5 or s.nunique() < 2:
            continue
        num = pd.to_numeric(s, errors="coerce")
        if num.notna().mean() > 0.95 and (s.nunique() > 10 or court.upper().startswith("SCORE")):
            quant.append(col)
        elif s.nunique() <= 10:
            qual.append(col)
    return qual, quant


# ------------------------------------------------------------------ objectifs 2-4
def descriptif_qualitatif(base: pd.DataFrame, col: str) -> pd.DataFrame:
    s = base[col]
    tab = s.value_counts(dropna=False)
    out = pd.DataFrame({"Modalité": tab.index.map(lambda m: "Manquant" if pd.isna(m) else m),
                        "Effectif": tab.values})
    out["%"] = (out["Effectif"] / out["Effectif"].sum() * 100).round(1)
    return out


def descriptif_quantitatif(base: pd.DataFrame, col: str) -> dict:
    x = pd.to_numeric(base[col], errors="coerce").dropna()
    if len(x) < 3:
        return {}
    asym = float(stats.skew(x)) if x.nunique() > 1 else 0.0
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    return {"n": len(x), "Moyenne": x.mean(), "ET": x.std(ddof=1), "Médiane": med,
            "Q1": q1, "Q3": q3, "Asymétrie": asym, "Symétrique": abs(asym) < 1,
            "Résumé retenu": (f"{x.mean():.1f} ± {x.std(ddof=1):.1f} (moyenne ± ET)" if abs(asym) < 1
                              else f"{med:.1f} [{q1:.1f} – {q3:.1f}] (médiane [IQR])").replace(".", ",")}


# ------------------------------------------------------------------ objectif 5 : bivariée
def _or_woolf(a, b, c, d):
    """OR (exposé vs référence) : a = exposés hésitants, b = exposés non hésitants,
    c = référence hésitants, d = référence non hésitants. Correction de Haldane si zéro."""
    if min(a, b, c, d) == 0:
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    o = (a * d) / (b * c)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return o, math.exp(math.log(o) - Z95 * se), math.exp(math.log(o) + Z95 * se)


def bivarie_qualitatif(base: pd.DataFrame, col: str, reference=None) -> dict:
    sub = base[[col, "_Y"]].dropna()
    tab = pd.crosstab(sub[col], sub["_Y"]).reindex(columns=[0, 1], fill_value=0)
    if len(tab) < 2:
        return {"variable": col, "lignes": [], "p": math.nan, "test": "—", "remarque": "une seule modalité"}
    if reference is None or reference not in tab.index:
        reference = tab.sum(axis=1).idxmax()          # modalité la plus fréquente
    chi2, p, _, attendus = stats.chi2_contingency(tab.values, correction=False)
    remarque = ""
    test = "Chi² de Pearson"
    if (attendus < 5).any():
        if tab.shape == (2, 2):
            _, p = stats.fisher_exact(tab.values)
            test = "Test exact de Fisher"
        else:
            remarque = "effectifs attendus < 5 : regrouper des modalités avant l'analyse finale"
    c, d = tab.loc[reference, 1], tab.loc[reference, 0]
    lignes = []
    for mod in tab.index:
        a, b = tab.loc[mod, 1], tab.loc[mod, 0]
        n = a + b
        ligne = {"Modalité": mod, "n": int(n), "Hésitants": int(a),
                 "% hésitants": round(a / n * 100, 1) if n else math.nan}
        if mod == reference:
            ligne.update({"ORb": 1.0, "IC bas": math.nan, "IC haut": math.nan, "ORb [IC95 %]": "1 (référence)"})
        else:
            o, lo, hi = _or_woolf(a, b, c, d)
            ligne.update({"ORb": o, "IC bas": lo, "IC haut": hi, "ORb [IC95 %]": fmt_or(o, lo, hi)})
        lignes.append(ligne)
    return {"variable": col, "lignes": lignes, "p": float(p), "test": test, "remarque": remarque,
            "reference": reference, "n": int(tab.values.sum())}


def bivarie_quantitatif(base: pd.DataFrame, col: str) -> dict:
    x = pd.to_numeric(base[col], errors="coerce")
    sub = pd.DataFrame({"x": x, "y": base["_Y"]}).dropna()
    g1, g0 = sub.loc[sub.y == 1, "x"], sub.loc[sub.y == 0, "x"]
    if len(g1) < 3 or len(g0) < 3:
        return {"variable": col, "p": math.nan, "test": "—", "remarque": "effectifs insuffisants"}
    symetrique = all(abs(stats.skew(g)) < 1 for g in (g1, g0) if g.nunique() > 1)
    if symetrique:
        p = stats.ttest_ind(g1, g0, equal_var=False).pvalue
        test = "t de Student (Welch)"
        res1 = f"{g1.mean():.1f} ± {g1.std(ddof=1):.1f}"
        res0 = f"{g0.mean():.1f} ± {g0.std(ddof=1):.1f}"
    else:
        p = stats.mannwhitneyu(g1, g0, alternative="two-sided").pvalue
        test = "Mann-Whitney"
        res1 = f"{g1.median():.1f} [{g1.quantile(.25):.1f} – {g1.quantile(.75):.1f}]"
        res0 = f"{g0.median():.1f} [{g0.quantile(.25):.1f} – {g0.quantile(.75):.1f}]"
    o = lo = hi = math.nan
    try:
        import statsmodels.api as sm
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = sm.Logit(sub["y"], sm.add_constant(sub["x"])).fit(disp=0)
        o = math.exp(m.params["x"])
        lo, hi = (math.exp(v) for v in m.conf_int().loc["x"])
    except Exception:  # noqa: BLE001
        pass
    return {"variable": col, "p": float(p), "test": test, "remarque": "",
            "Hésitants": res1.replace(".", ","), "Non hésitants": res0.replace(".", ","),
            "ORb [IC95 %]": fmt_or(o, lo, hi) + " par unité" if not math.isnan(o) else "—",
            "n": len(sub)}


def synthese_bivariee(base: pd.DataFrame, qual: list[str], quant: list[str],
                      libelles: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(tableau détaillé par modalité, tableau de synthèse par variable)."""
    detail, synth = [], []
    for col in qual:
        r = bivarie_qualitatif(base, col)
        for li in r["lignes"]:
            mod = li["Modalité"]
            detail.append({"Variable": _court(col), "Modalité": (libelles or {}).get(mod, mod),
                           "n": li["n"], "% hésitants": li["% hésitants"], "ORb [IC95 %]": li["ORb [IC95 %]"],
                           "p": fmt_p(r["p"]) if mod == r.get("reference") else ""})
        synth.append({"Variable": col, "Type": "qualitative", "n": r.get("n"), "Test": r["test"],
                      "p": r["p"], "Remarque": r["remarque"]})
    for col in quant:
        r = bivarie_quantitatif(base, col)
        detail.append({"Variable": _court(col), "Modalité": f"Hésitants : {r.get('Hésitants', '—')} · "
                                                            f"non hésitants : {r.get('Non hésitants', '—')}",
                       "n": r.get("n"), "% hésitants": math.nan, "ORb [IC95 %]": r.get("ORb [IC95 %]", "—"),
                       "p": fmt_p(r["p"])})
        synth.append({"Variable": col, "Type": "quantitative", "n": r.get("n"), "Test": r["test"],
                      "p": r["p"], "Remarque": r["remarque"]})
    synth = pd.DataFrame(synth)
    if not synth.empty:
        synth["Présélection (p < 0,20)"] = synth["p"].apply(lambda p: "Oui" if p == p and p < SEUIL_PRESELECTION else "Non")
        synth["Significatif (p < 0,05)"] = synth["p"].apply(lambda p: "Oui" if p == p and p < SEUIL_SIGNIF else "Non")
    return pd.DataFrame(detail), synth


# ------------------------------------------------------------------ objectif 6 : multivariée
def hosmer_lemeshow(y: np.ndarray, p: np.ndarray, g: int = 10) -> tuple[float, float, int]:
    d = pd.DataFrame({"y": y, "p": p})
    d["groupe"] = pd.qcut(d["p"].rank(method="first"), q=min(g, len(d)), labels=False)
    obs = d.groupby("groupe")["y"].agg(["sum", "count"])
    att = d.groupby("groupe")["p"].sum()
    n_g = len(obs)
    hl = float((((obs["sum"] - att) ** 2) / (att * (1 - att / obs["count"]))).sum())
    ddl = max(n_g - 2, 1)
    return hl, float(stats.chi2.sf(hl, ddl)), ddl


def regression_logistique(base: pd.DataFrame, qual: list[str], quant: list[str]) -> dict:
    import statsmodels.api as sm

    cols = qual + quant
    d = base[cols + ["_Y"]].dropna()
    if d.empty:
        return {"erreur": "aucune observation complète pour les variables choisies"}
    blocs, refs = [], {}
    for col in qual:
        s = d[col].astype(str)
        ref = s.value_counts().idxmax()
        refs[col] = ref
        dum = pd.get_dummies(s, prefix=_court(col), prefix_sep=" = ", dtype=float)
        blocs.append(dum.drop(columns=f"{_court(col)} = {ref}"))
    for col in quant:
        blocs.append(pd.to_numeric(d[col], errors="coerce").rename(_court(col)).to_frame())
    X = pd.concat(blocs, axis=1)
    X = X.loc[:, X.std() > 0]
    y = d["_Y"].astype(float)
    evenements = int(min(y.sum(), len(y) - y.sum()))
    k = X.shape[1]
    if k == 0:
        return {"erreur": "aucune variable exploitable (modalités constantes)"}

    vif = None
    if k > 1:
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        Xc = sm.add_constant(X)
        vif = pd.DataFrame({"Terme": X.columns,
                            "VIF": [variance_inflation_factor(Xc.values, i + 1) for i in range(k)]})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = sm.Logit(y, sm.add_constant(X)).fit(disp=0, maxiter=200)
    except Exception as e:  # noqa: BLE001  (séparation parfaite, matrice singulière…)
        return {"erreur": f"le modèle n'a pas pu être ajusté ({type(e).__name__}) : trop peu de données "
                          f"ou une modalité prédit parfaitement l'issue. Réduire le nombre de variables "
                          f"ou regrouper des modalités.", "n": len(d), "evenements": evenements, "k": k}
    ci = m.conf_int()
    lignes = []
    for terme in X.columns:
        b = m.params[terme]
        lo, hi = ci.loc[terme]
        lignes.append({"Terme": terme, "ORa": math.exp(b), "IC bas": math.exp(lo), "IC haut": math.exp(hi),
                       "ORa [IC95 %]": fmt_or(math.exp(b), math.exp(lo), math.exp(hi)),
                       "p": m.pvalues[terme], "p (affiché)": fmt_p(m.pvalues[terme])})
    hl, p_hl, ddl = hosmer_lemeshow(y.values, m.predict().astype(float))
    auc = _auc(y.values, np.asarray(m.predict(), dtype=float))
    return {"n": len(d), "evenements": evenements, "k": k, "epv": evenements / k,
            "references": refs, "coefficients": pd.DataFrame(lignes), "vif": vif,
            "hl": hl, "p_hl": p_hl, "ddl_hl": ddl, "pseudo_r2": float(m.prsquared), "auc": auc,
            "converge": bool(m.mle_retvals.get("converged", True))}


def _auc(y, p) -> float:
    """Aire sous la courbe ROC (statistique de Mann-Whitney), sans dépendance externe."""
    y, p = np.asarray(y), np.asarray(p)
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return math.nan
    rangs = stats.rankdata(np.concatenate([pos, neg]))
    return float((rangs[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


# ------------------------------------------------------------------ ponctualité
def ponctualite(base: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Proportion de doses retardées (> 28 jours après l'âge recommandé), globale et
    selon le statut d'hésitation. Dénominateur : enfants dont la date de naissance
    et la date de la dose sont recopiées depuis la carte (donc carte vue, âge atteint)."""
    ddn_col = _find_col(base, CHAMP_DATE_NAISSANCE)
    manquants = [CHAMP_DATE_NAISSANCE] if not ddn_col else []
    lignes = []
    for dose, (champ, age) in DOSES_PONCTUALITE.items():
        col = _find_col(base, champ)
        if not col:
            manquants.append(champ)
            continue
        if not ddn_col:
            continue
        ddn = pd.to_datetime(base[ddn_col], errors="coerce")
        dd = pd.to_datetime(base[col], errors="coerce")
        ok = ddn.notna() & dd.notna() & (dd >= ddn)
        if not ok.any():
            continue
        retard = (dd[ok] - (ddn[ok] + age)).dt.days > DELAI_GRACE_JOURS
        y = base.loc[ok, "_Y"]
        n, k = int(ok.sum()), int(retard.sum())
        p, lo, hi = ic_wilson(k, n)
        ligne = {"Dose": dose, "Enfants avec dates": n, "Retardées": k,
                 "% retardées": round(p * 100, 1),
                 "IC95 %": f"{lo * 100:.1f} – {hi * 100:.1f}".replace(".", ",")}
        for lib, val in (("hésitants", 1), ("non hésitants", 0)):
            m = y == val
            ligne[f"% retard ({lib})"] = round(retard[m].mean() * 100, 1) if m.any() else math.nan
        if y.nunique() == 2 and retard.nunique() == 2:
            tab = pd.crosstab(retard, y)
            _, pval, _, att = stats.chi2_contingency(tab.values, correction=False)
            if (att < 5).any() and tab.shape == (2, 2):
                _, pval = stats.fisher_exact(tab.values)
            ligne["p"] = fmt_p(pval)
        else:
            ligne["p"] = "—"
        lignes.append(ligne)
    return pd.DataFrame(lignes), manquants

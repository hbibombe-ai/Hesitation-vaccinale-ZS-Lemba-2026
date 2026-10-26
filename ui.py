# -*- coding: utf-8 -*-
"""Composants d'interface de VaxSuivi-Lemba (style « cartes blanches » sur fond clair,
menu latéral, frise des phases, fil d'activité). HTML/CSS injectés dans Streamlit ;
aucune ressource externe hormis la police Inter (Google Fonts, repli système)."""
from __future__ import annotations

import html

import streamlit as st

import theme as T

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select {{
    font-family: 'Inter', {T.FONT_FAMILY} !important;
}}
.stApp {{ background: {T.BG}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1420px; }}
h1, h2, h3, h4 {{ color: {T.TEXT}; letter-spacing: -0.01em; }}

/* ---------- menu latéral ---------- */
section[data-testid="stSidebar"] {{ background: #ffffff; border-right: 1px solid {T.BORDER}; }}
section[data-testid="stSidebar"] .block-container, section[data-testid="stSidebar"] > div {{ padding-top: 0.6rem; }}
.st-key-nav, .st-key-nav .stRadio, .st-key-nav .stRadio > div {{ width: 100% !important; }}
.st-key-nav div[role="radiogroup"] {{ gap: 3px; width: 100%; align-items: stretch; }}
.st-key-nav div[role="radiogroup"] > div {{ width: 100%; }}
.st-key-nav label[data-testid="stRadioOption"], .st-key-nav label[data-baseweb="radio"] {{
    width: 100%; margin: 0; padding: 9px 12px; border-radius: 10px; cursor: pointer;
    border: 1px solid transparent; transition: background .12s;
}}
/* masque le rond du bouton radio (deux structures Streamlit selon la version) */
.st-key-nav label[data-testid="stRadioOption"] > div > div:first-child,
.st-key-nav label[data-baseweb="radio"] > div:first-child {{ display: none; }}
.st-key-nav label[data-testid="stRadioOption"]:hover, .st-key-nav label[data-baseweb="radio"]:hover {{ background: {T.BG}; }}
.st-key-nav label[data-selected="true"], .st-key-nav label:has(input:checked) {{
    background: {T.PRIMARY_SOFT}; border-color: {T.PRIMARY_BORDER};
}}
.st-key-nav label p {{ font-size: 0.93rem; color: {T.TEXT_SECONDARY}; }}
.st-key-nav label[data-selected="true"] p, .st-key-nav label:has(input:checked) p {{ font-weight: 600; color: {T.PRIMARY}; }}
.st-key-nav label p span[role="img"] {{ margin-right: 6px; font-size: 1.15rem; }}

/* ---------- cartes ---------- */
[class*="st-key-card"] {{
    background: #ffffff; border: 1px solid {T.BORDER}; border-radius: 14px;
    padding: 16px 18px 20px 18px; overflow: hidden;
    box-shadow: 0 1px 2px rgba(16,24,40,.04), 0 6px 16px rgba(16,24,40,.04);
}}
.vs-card-title {{ display:flex; justify-content:space-between; align-items:center;
    font-weight:600; color:{T.TEXT}; font-size:0.98rem; margin-bottom:6px; }}
.vs-card-title .vs-right {{ font-weight:500; color:{T.MUTED}; font-size:0.8rem; }}
.vs-big {{ font-size:2.05rem; font-weight:700; color:{T.TEXT}; line-height:1.1; letter-spacing:-0.02em; }}
.vs-big small {{ font-size:1rem; color:{T.MUTED}; font-weight:500; }}
.vs-muted {{ color:{T.MUTED}; font-size:0.82rem; }}
.vs-row {{ display:flex; gap:22px; margin-top:10px; }}
.vs-row div b {{ display:block; color:{T.TEXT}; font-size:1.02rem; }}
.vs-row div span {{ color:{T.MUTED}; font-size:0.78rem; }}
.vs-bar {{ height:8px; background:{T.BORDER}; border-radius:6px; overflow:hidden; margin:10px 0 4px 0; }}
.vs-bar > div {{ height:100%; background:{T.PRIMARY}; border-radius:6px; }}
.vs-link {{ color:{T.PRIMARY}; font-size:0.84rem; font-weight:500; }}

/* ---------- indicateurs compacts ---------- */
.vs-kpi {{ display:flex; gap:12px; align-items:center; }}
.vs-kpi .vs-ic {{ width:40px; height:40px; border-radius:11px; display:flex; align-items:center;
    justify-content:center; font-size:1.15rem; flex-shrink:0; }}
.vs-kpi .vs-lab {{ color:{T.MUTED}; font-size:0.8rem; }}
.vs-kpi .vs-val {{ color:{T.TEXT}; font-size:1.35rem; font-weight:700; line-height:1.15; }}
.vs-kpi .vs-sub {{ color:{T.MUTED}; font-size:0.74rem; }}

/* ---------- pastilles ---------- */
.vs-pill {{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:0.74rem; font-weight:600; }}

/* ---------- en-tête de page ---------- */
.vs-head {{ display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:14px; }}
.vs-head h1 {{ font-size:1.6rem; margin:0; padding:0; font-weight:700; }}
.vs-head .vs-sub {{ color:{T.MUTED}; font-size:0.86rem; margin-top:2px; }}
.vs-head img {{ height:64px; border-radius:12px; border:1px solid {T.BORDER}; }}

/* ---------- frise des phases ---------- */
.vs-steps {{ display:flex; align-items:stretch; gap:0; margin: 2px 0 16px 0; flex-wrap: wrap; row-gap: 10px; }}
.vs-step {{ flex:1 1 170px; display:flex; gap:11px; align-items:center; background:#fff;
    border:1px solid {T.BORDER}; border-radius:13px; padding:11px 13px; min-width:178px; padding:10px 12px;
    box-shadow:0 1px 2px rgba(16,24,40,.04); }}
.vs-step .vs-ic {{ width:38px; height:38px; border-radius:50%; display:flex; align-items:center;
    justify-content:center; font-size:1.05rem; flex-shrink:0; }}
.vs-step b {{ display:block; font-size:0.86rem; white-space:nowrap; }}
.vs-step span {{ color:{T.MUTED}; font-size:0.74rem; white-space:nowrap; }}
.vs-conn {{ align-self:center; width:22px; height:2px; flex:0 0 22px; }}

/* ---------- fil d'activité ---------- */
.vs-tl {{ list-style:none; margin:4px 0 0 0; padding:0; }}
.vs-tl li {{ display:flex; gap:10px; padding:7px 0; border-bottom:1px dashed {T.BORDER}; }}
.vs-tl li:last-child {{ border-bottom:none; }}
.vs-tl .vs-dot {{ width:22px; height:22px; border-radius:50%; display:flex; align-items:center;
    justify-content:center; font-size:0.72rem; color:#fff; flex-shrink:0; margin-top:2px; }}
.vs-tl b {{ font-size:0.86rem; color:{T.TEXT}; }}
.vs-tl span {{ display:block; color:{T.MUTED}; font-size:0.76rem; }}

/* ---------- grille des aires ---------- */
.vs-as-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:8px; }}
.vs-as {{ border-radius:11px; padding:8px 10px; font-size:0.82rem; line-height:1.3; border:1px solid transparent; }}
.vs-as b {{ display:block; font-size:0.86rem; }}

/* ---------- bandeau de fonctions ---------- */
.vs-feat {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:6px;
    background:#fff; border:1px solid {T.BORDER}; border-radius:14px; padding:14px 18px; margin-top:18px; }}
.vs-feat div {{ display:flex; gap:11px; align-items:center; }}
.vs-feat .vs-ic {{ font-size:1.3rem; color:{T.PRIMARY}; }}
.vs-feat b {{ display:block; font-size:0.9rem; color:{T.TEXT}; }}
.vs-feat span {{ color:{T.MUTED}; font-size:0.78rem; }}

/* ---------- marque & statut (menu) ---------- */
.vs-brand {{ display:flex; align-items:center; gap:10px; margin:4px 0 14px 2px; }}
.vs-brand .vs-logo {{ width:36px; height:36px; border-radius:10px; background:{T.PRIMARY};
    display:flex; align-items:center; justify-content:center; color:#fff; font-size:1.1rem; }}
.vs-brand b {{ font-size:1.12rem; color:{T.TEXT}; }}
.vs-brand b span {{ color:{T.PRIMARY}; }}
.vs-brand small {{ display:block; color:{T.MUTED}; font-size:0.72rem; }}
.vs-sys {{ border:1px solid {T.BORDER}; border-radius:12px; padding:10px 12px; display:flex; gap:10px;
    align-items:center; margin-top:8px; }}
.vs-sys span {{ display:block; color:{T.MUTED}; font-size:0.74rem; }}

/* ---------- divers ---------- */
[data-testid="stMetric"] {{ background:#fff; border:1px solid {T.BORDER}; border-radius:12px; padding:12px 14px; }}
[data-testid="stDataFrame"] {{ border-radius:10px; }}
div[data-testid="stAlert"] {{ border-radius:12px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
</style>
"""

TONES = {   # fond, texte — pastilles et icônes
    "blue": (T.PRIMARY_SOFT, T.PRIMARY),
    "green": ("#e7f6ec", "#137333"),
    "orange": ("#fff3df", "#9a5b00"),
    "red": ("#fdeaea", "#a12b2b"),
    "grey": ("#eef1f5", "#55606e"),
    "violet": ("#f0ecfe", "#5b3fc4"),
}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape(str(x))


def pill(text: str, tone: str = "blue") -> str:
    bg, fg = TONES[tone]
    return f"<span class='vs-pill' style='background:{bg};color:{fg}'>{esc(text)}</span>"


def card_title(title: str, right: str = "") -> None:
    st.markdown(f"<div class='vs-card-title'><span>{title}</span><span class='vs-right'>{right}</span></div>",
                unsafe_allow_html=True)


def kpi(label: str, value, sub: str = "", icon: str = "•", tone: str = "blue") -> str:
    bg, fg = TONES[tone]
    return (f"<div class='vs-kpi'><div class='vs-ic' style='background:{bg};color:{fg}'>{icon}</div>"
            f"<div><div class='vs-lab'>{esc(label)}</div><div class='vs-val'>{esc(value)}</div>"
            f"<div class='vs-sub'>{sub}</div></div></div>")


def page_header(title: str, tag: str = "", subtitle: str = "", image_b64: str = "") -> None:
    img = (f"<img src='data:image/svg+xml;base64,{image_b64}' alt='Illustration : parent hésitant "
           f"face à la vaccination' />") if image_b64 else ""
    st.markdown(
        f"<div class='vs-head'><div><h1>{esc(title)} {pill(tag) if tag else ''}</h1>"
        f"<div class='vs-sub'>{subtitle}</div></div>{img}</div>", unsafe_allow_html=True)


def stepper(steps: list[dict]) -> None:
    """steps : [{label, detail, state: done|current|todo, icon}]"""
    couleurs = {"done": ("#e7f6ec", "#137333"), "current": ("#fff3df", "#b86e00"),
                "todo": ("#eef1f5", "#8a94a3")}
    parts = []
    for i, s in enumerate(steps):
        bg, fg = couleurs[s["state"]]
        icon = "✓" if s["state"] == "done" else s.get("icon", "•")
        if i:
            conn = T.GOOD if steps[i - 1]["state"] == "done" else T.BORDER
            parts.append(f"<div class='vs-conn' style='background:{conn}'></div>")
        parts.append(
            f"<div class='vs-step'><div class='vs-ic' style='background:{bg};color:{fg}'>{icon}</div>"
            f"<div><b style='color:{fg if s['state'] != 'todo' else T.TEXT_SECONDARY}'>{esc(s['label'])}</b>"
            f"<span>{s['detail']}</span></div></div>")
    st.markdown(f"<div class='vs-steps'>{''.join(parts)}</div>", unsafe_allow_html=True)


def timeline(items: list[dict]) -> None:
    """items : [{titre, detail, tone, icon}]"""
    li = []
    for it in items:
        _, fg = TONES[it["tone"]]
        li.append(f"<li><div class='vs-dot' style='background:{fg}'>{it.get('icon', '✓')}</div>"
                  f"<div><b>{esc(it['titre'])}</b><span>{it['detail']}</span></div></li>")
    st.markdown(f"<ul class='vs-tl'>{''.join(li)}</ul>", unsafe_allow_html=True)


def feature_strip() -> None:
    feats = [("📥", "Collecter", "KoboCollect, 14 aires de santé"),
             ("🛰️", "Suivre en temps réel", "Soumissions, enquêteurs, rythme"),
             ("✅", "Contrôler la qualité", "Doublons, incomplètes, durées"),
             ("📊", "Projeter les analyses", "Prévalence, ORb, ORa (§ 3.9)")]
    st.markdown("<div class='vs-feat'>" + "".join(
        f"<div><span class='vs-ic'>{i}</span><div><b>{t}</b><span>{d}</span></div></div>" for i, t, d in feats)
        + "</div>", unsafe_allow_html=True)

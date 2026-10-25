# -*- coding: utf-8 -*-
"""Jetons visuels partagés par tous les graphiques de VaxSuivi-Lemba.

Palette issue d'une palette de référence validée (séparation CVD >= 8 Delta E
OKLab sur les paires adjacentes, contraste >= 3:1 sur la surface claire) :
on n'utilise ici qu'un seul accent catégoriel (bleu, créneau 1) pour les
graphiques à une série, et sa rampe séquentielle complète pour les
encodages de magnitude (heatmap). Cela évite tout problème de distinction
de couleurs : aucun graphique de ce tableau de bord n'encode plus d'une
série par couleur.
"""

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

ACCENT = "#2a78d6"       # bleu — créneau catégoriel 1
ACCENT_DARK = "#1c5cab"

GOOD = "#0ca30c"
WARNING = "#fab219"
SERIOUS = "#ec835a"
CRITICAL = "#d03b3b"

FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"

# Rampe séquentielle bleue (du plus clair = proche de zéro, au plus foncé),
# utilisée pour les encodages de magnitude (heatmap de tendance).
BLUE_SEQUENTIAL = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]


def blue_colorscale():
    n = len(BLUE_SEQUENTIAL)
    return [[i / (n - 1), c] for i, c in enumerate(BLUE_SEQUENTIAL)]


def apply_layout(fig, height=380, show_legend=False):
    """Applique les jetons visuels communs (fond, grille discrète, police,
    pas d'axe double, étiquettes directes) à une figure Plotly."""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT_FAMILY, color=INK_SECONDARY, size=13),
        showlegend=show_legend,
        hoverlabel=dict(
            bgcolor="white", font_family=FONT_FAMILY, font_color=INK_PRIMARY,
            bordercolor=GRIDLINE,
        ),
    )
    fig.update_xaxes(
        gridcolor=GRIDLINE, zeroline=False, linecolor=BASELINE,
        tickfont=dict(color=INK_MUTED),
    )
    fig.update_yaxes(
        gridcolor=GRIDLINE, zeroline=False, linecolor=BASELINE,
        tickfont=dict(color=INK_MUTED),
    )
    return fig

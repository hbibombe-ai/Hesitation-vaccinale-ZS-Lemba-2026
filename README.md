# Hésitation vaccinale — ZS Lemba (tableau de bord Streamlit)

Tableau de bord de **démonstration** en Python (Streamlit) pour le suivi de l'hésitation vaccinale dans les 14 aires de santé de la Zone de santé de Lemba (Kinshasa).

> **Données entièrement fictives (423 formulaires simulés).** Ne pas utiliser ces chiffres pour une décision de santé publique.

## Fichiers

- `app.py` : l'application (filtres, indicateurs, graphiques, export CSV).
- `data.csv` : données simulées.
- `requirements.txt` : dépendances (streamlit, pandas, plotly).

## Lancer en local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Déployer sur Streamlit Community Cloud

1. Placez `app.py`, `data.csv` et `requirements.txt` à la racine du dépôt GitHub.
2. Sur share.streamlit.io, choisissez le dépôt, la branche `main` et le fichier principal `app.py`.
3. Lancez le déploiement.

## Aires de santé

Les 14 aires proviennent du fichier officiel des aires de santé de la RDC : Commercial, Echangeur, Ecole, Foire, Gombele, Kemi, Kimpwanza, Livulu, Madrandele, Masano, Mbanza Lemba, Salongo, Molo, Plateau.

## Confidentialité

Aucune coordonnée GPS, nom ni téléphone n'est présent. Pour toute publication de données réelles, utilisez un export dé-identifié et restreignez l'accès à l'application.

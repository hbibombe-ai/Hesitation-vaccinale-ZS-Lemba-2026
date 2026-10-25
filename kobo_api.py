# -*- coding: utf-8 -*-
"""
Client minimal pour l'API KoboToolbox (v2).

Récupère les soumissions d'un formulaire Kobo et les renvoie sous forme de
DataFrame pandas, prêt à être consommé par le tableau de bord VaxSuivi-Lemba.

Aucune donnée n'est stockée en dur dans ce fichier : l'URL du serveur,
l'identifiant du formulaire (asset UID) et le jeton d'API sont fournis par
l'utilisateur (variables d'environnement / st.secrets / saisie dans la barre
latérale), jamais codés ici.
"""
from __future__ import annotations

import pandas as pd
import requests


class KoboAPIError(RuntimeError):
    pass


def fetch_submissions(
    server_url: str,
    asset_uid: str,
    api_token: str,
    timeout: int = 30,
) -> pd.DataFrame:
    """
    Récupère toutes les soumissions d'un formulaire Kobo via l'API REST v2.

    server_url : ex. "https://kf.kobotoolbox.org" ou l'URL de votre serveur
                 Kobo auto-hébergé (sans slash final).
    asset_uid  : identifiant du formulaire, ex. "aXXXXXXXXXXXXXXXXXXXXXX"
                 (visible dans l'URL du projet sur l'interface Kobo).
    api_token  : jeton d'API personnel (Compte Kobo > Paramètres du compte
                 > Jeton d'API). Ne jamais committer ce jeton dans le dépôt :
                 utilisez st.secrets ou une variable d'environnement.
    """
    server_url = server_url.rstrip("/")
    url = f"{server_url}/api/v2/assets/{asset_uid}/data.json"
    headers = {"Authorization": f"Token {api_token}"}

    results = []
    params = {"format": "json", "limit": 3000}
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        if resp.status_code != 200:
            raise KoboAPIError(
                f"Échec de la requête Kobo (HTTP {resp.status_code}) : {resp.text[:300]}"
            )
        payload = resp.json()
        results.extend(payload.get("results", []))
        url = payload.get("next")
        params = None  # l'URL 'next' contient déjà les paramètres de pagination

    if not results:
        return pd.DataFrame()

    df = pd.json_normalize(results)
    return df


def fetch_asset_summary(server_url: str, asset_uid: str, api_token: str, timeout: int = 30) -> dict:
    """Récupère les métadonnées du formulaire (titre, nombre de soumissions attendu, etc.)."""
    server_url = server_url.rstrip("/")
    url = f"{server_url}/api/v2/assets/{asset_uid}.json"
    headers = {"Authorization": f"Token {api_token}"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise KoboAPIError(
            f"Échec de la requête Kobo (HTTP {resp.status_code}) : {resp.text[:300]}"
        )
    return resp.json()

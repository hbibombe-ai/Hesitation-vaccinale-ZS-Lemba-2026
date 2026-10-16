# VaxSuivi — tableau de bord de démonstration

Application web statique en français pour le suivi illustratif de l’hésitation vaccinale dans la Zone de santé de Lemba. Le dépôt contient l’application et un workflow GitHub Actions qui publie automatiquement le site sur GitHub Pages à chaque mise à jour de `main`.

> **Données entièrement simulées.** Les 423 formulaires et les 95 cas positifs ne sont pas des observations réelles et ne décrivent pas la population de Lemba. Ils servent uniquement à illustrer l’application. Ne pas utiliser ces résultats pour guider une décision de santé publique.

## Mise en ligne sur GitHub

1. Créez un dépôt GitHub et importez le contenu de ce dossier à sa racine (`index.html`, `data.csv`, `assets/`, `.github/` et `.nojekyll`).
2. Dans **Settings → Pages**, réglez **Build and deployment → Source** sur **GitHub Actions**.
3. Poussez le contenu sur la branche `main` (ou lancez manuellement le workflow **Déployer le tableau de bord** depuis **Actions**).
4. À la fin du workflow, récupérez l’adresse du site dans le job `deploy` ou dans **Settings → Pages**.

Le workflow de `.github/workflows/deploy.yml` installe rien et ne construit pas le site : il publie directement les fichiers statiques à la racine du dépôt. Il est possible de choisir un autre nom de branche en modifiant la valeur `main` dans le workflow.

## Utilisation locale

Dans ce dossier, exécutez :

```bash
python3 -m http.server 8000
```

Puis ouvrez `http://localhost:8000`. Le navigateur doit charger `data.csv` via HTTP; l’ouverture directe du fichier HTML peut bloquer cette lecture.

## Fonctionnalités

- Indicateurs clés : formulaires soumis, cas et taux d’hésitation, exposition à des rumeurs et rendez-vous manqués.
- Filtres par aire de santé, âge de l’enfant et mois de soumission.
- Graphiques hebdomadaires, comparaison entre aires, motifs d’hésitation et sources d’information.
- Export CSV du sous-ensemble après filtrage.
- Mise en page adaptée aux écrans mobiles et ordinateur.

Chart.js est chargé depuis jsDelivr et la police DM Sans/Manrope depuis Google Fonts. Une connexion Internet est nécessaire pour les graphiques et polices externes; la page et ses données restent des fichiers statiques servis par GitHub Pages.

## Indicateur d’hésitation et limites

La règle d’opérationnalisation reprend la proposition du questionnaire : `HESITATION=1` si retard intentionnel lié au doute (I02) et/ou refus d’un vaccin disponible (I03), ou hésitation déclarée (I01) avec motif attitudinal documenté (I06), en excluant les situations uniquement pratiques/de service (I07=Oui) et les cas sans motif applicable (I06=99). Les questions I04/I05 sont des indicateurs complémentaires.

La règle devra être finalisée et testée au pré-test avant toute analyse réelle. Les motifs et réponses illustratifs du CSV sont simulés; les scores de connaissances et de confiance ne sont pas des scores validés. Le taux affiché est la proportion de formulaires simulés classés positifs dans la sélection filtrée, pas une prévalence représentative.

## Fichiers

- `index.html` : structure et libellés de l’application.
- `assets/styles.css` : mise en page et styles adaptatifs.
- `assets/app.js` : chargement du CSV, filtres, calculs, graphiques et export.
- `data.csv` : 423 lignes synthétiques, dont 95 étiquetées positives.
- `.github/workflows/deploy.yml` : déploiement GitHub Pages.

Aucun nom, téléphone, GPS, adresse ni identifiant réel ne figure dans la base de démonstration. Pour toute publication de données réelles, n’utilisez qu’un export dé-identifié et contrôlez les accès, les règles de classification et les risques de ré-identification.

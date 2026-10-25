# VaxSuivi-Lemba

Tableau de bord de suivi de la collecte de données (Streamlit) pour le mémoire :

> *Facteurs associés à l'hésitation vaccinale chez les parents ou tuteurs d'enfants de
> 0 à 23 mois en vaccination de routine — Zone de Santé de Lemba, Kinshasa (RDC), 2026*

**Organisation du tableau de bord :** KPI principaux en tête (dont le nombre de jours
depuis la dernière soumission, utile pour repérer une interruption de terrain), puis cinq
onglets — *Vue d'ensemble* (tendance cumulée, volumes par aire/enquêteur), *Par
enquêteur* (heatmap jour × enquêteur + tableau détaillé : volume, part, durée moyenne,
éligibilité, dernière activité), *Par aire de santé* (même détail par AS), *Qualité des
données* et *Données brutes / export*.

**Ce que fait l'outil :** suivre l'avancement du terrain (nombre d'entretiens par aire
de santé et par enquêteur, progression dans le temps), détecter d'éventuelles anomalies
de saisie (doublons de ménage, entretiens trop courts, champs manquants) et afficher une
prévalence **provisoire** de l'hésitation vaccinale, explicitement signalée comme non
définitive.

**Ce que l'outil ne fait pas :** il ne calcule ni ne publie aucun résultat scientifique
final du mémoire. Les scores composites (SCORE_CONNAISS, SCORE_CONFIANCE, etc.) restent à
construire sous SPSS après le pré-test, conformément à l'Annexe 1 du questionnaire
`QUESTIONNAIRE_K-K-A.docx`.

## 1. Structure du projet

```
vaxsuivi_dashboard/
├── app.py                          # Application Streamlit (point d'entrée)
├── kobo_api.py                     # Client minimal pour l'API KoboToolbox
├── data_quality.py                 # Nettoyage, filtres, contrôles qualité
├── requirements.txt
├── .streamlit/
│   ├── config.toml                 # Thème de l'application
│   └── secrets.toml.example        # Modèle de configuration des identifiants Kobo
├── sample_data/
│   └── exemple_fictif_export_kobo.csv   # Données FICTIVES pour tester sans toucher à la vraie base
└── .gitignore
```

## 2. Lancer le tableau de bord en local

```bash
cd vaxsuivi_dashboard
python3 -m venv .venv && source .venv/bin/activate   # optionnel mais recommandé
pip install -r requirements.txt
streamlit run app.py
```

Pour tester immédiatement sans identifiants Kobo : dans la barre latérale, choisissez
**« Fichier exporté (CSV / XLSX) »** et chargez `sample_data/exemple_fictif_export_kobo.csv`
(données entièrement fictives, générées pour la démonstration).

## 3. Connecter la vraie base de collecte Kobo (mode « live »)

1. Dans votre compte KoboToolbox, ouvrez **Paramètres du compte > Jeton d'API** et copiez
   votre jeton personnel.
2. Ouvrez votre formulaire déployé et récupérez son **identifiant (asset UID)** dans l'URL
   du projet (ex. `https://kf.kobotoolbox.org/#/forms/aXXXXXXXXXXXXXXXXXXXXXX/...` → l'UID
   est la partie commençant par `a`).
3. **Ces identifiants ne se saisissent nulle part dans l'interface de l'application** —
   volontairement : l'app, une fois déployée sur Streamlit Community Cloud, est
   accessible par lien à quiconque l'a reçu, et un champ de saisie en clair aurait
   permis à n'importe quel visiteur de lire ou de remplacer le jeton d'accès à la
   vraie base de collecte. Ils se configurent uniquement côté administrateur :
   - **En local**, créez un fichier `.streamlit/secrets.toml` à partir du modèle
     `secrets.toml.example` fourni. **Ce fichier est volontairement exclu du dépôt
     Git (`.gitignore`) — ne le committez jamais.**
   - **Sur Streamlit Community Cloud**, collez le même contenu dans *App settings >
     Secrets* (voir §4b) — c'est l'équivalent cloud du fichier local, lui aussi privé
     et invisible des visiteurs de l'app.

   Tant qu'aucun des deux n'est configuré, le mode « API KoboToolbox (live) » affiche
   un message d'attente et n'expose aucun champ de saisie ; seul le mode « Fichier
   exporté » reste utilisable.

4. Cliquez sur **« 🔄 Actualiser les données »** pour forcer un nouveau chargement
   (les données sont mises en cache 5 minutes par défaut).

## 4. Déploiement sur GitHub + Streamlit Community Cloud

### a) Créer le dépôt GitHub

```bash
cd vaxsuivi_dashboard
git init
git add .
git commit -m "Initial commit — VaxSuivi-Lemba"
git branch -M main
git remote add origin https://github.com/<votre-compte>/vaxsuivi-lemba.git
git push -u origin main
```

> Le fichier `.gitignore` empêche déjà l'envoi de `.streamlit/secrets.toml` et de tout
> export réel (`*.csv`, `*.xlsx`) — seul l'exemple fictif de `sample_data/` est conservé.
> Vérifiez toujours `git status` avant un `git push` si vous avez téléchargé un export
> réel dans ce dossier pour un test local.

### b) Déployer sur Streamlit Community Cloud

1. Allez sur [share.streamlit.io](https://share.streamlit.io) et connectez-vous avec
   votre compte GitHub.
2. Cliquez sur **« New app »**, sélectionnez le dépôt `vaxsuivi-lemba`, la branche `main`
   et le fichier principal `app.py`.
3. Avant (ou après) le premier déploiement, ouvrez **« Advanced settings… » (ou App
   settings > Secrets)** et collez-y le contenu de votre `secrets.toml` (serveur Kobo,
   asset UID, jeton d'API) — c'est l'équivalent cloud du fichier local, lui aussi privé.
4. Cliquez sur **Deploy**. L'application sera accessible à une URL du type
   `https://vaxsuivi-lemba.streamlit.app`, à partager uniquement avec les personnes
   autorisées à suivre la collecte (directeur de mémoire, équipe d'enquêteurs).

### c) Mises à jour ultérieures

Chaque `git push` sur la branche `main` redéploie automatiquement l'application sur
Streamlit Community Cloud.

## 5. Numérotation séquentielle des formulaires et des ménages

Le tableau de bord calcule, à chaque chargement, une numérotation séquentielle propre
(colonnes `N_FORMULAIRE` et `N_MENAGE`, identiques puisque 1 formulaire = 1 ménage dans ce
protocole), ainsi que des rangs par aire de santé (`N_DANS_AIRE`) et par enquêteur
(`N_DANS_ENQUETEUR`), triés chronologiquement par date/heure de soumission.

**Pourquoi cette numérotation n'est pas calculée directement par le téléphone pendant
l'entretien, mais ici :** un smartphone hors-ligne ne peut jamais savoir combien de
formulaires les autres enquêteurs ont déjà soumis au même moment. Aucun formulaire Kobo
ne peut donc garantir un numéro 1, 2, 3… strictement séquentiel et sans doublon tant que
les soumissions de plusieurs téléphones n'ont pas été centralisées sur le serveur. C'est
pourquoi :
- le **formulaire XLSForm** génère déjà, sans aucune saisie, un code unique automatique
  par entretien (aire + enquêteur + horodatage — champs ID01/ID06) qui ne peut jamais se
  dupliquer, même hors ligne ;
- le **tableau de bord**, une fois les soumissions centralisées, calcule la vraie
  numérotation séquentielle 1, 2, 3… — fiable parce qu'à ce stade, l'ordre complet de
  toutes les soumissions est connu.

Ces numéros sont recalculés à chaque actualisation des données (ils peuvent donc changer
de valeur si une soumission réalisée plus tôt arrive en retard, une fois le téléphone
reconnecté) : ils servent de repère de suivi, pas d'identifiant figé — c'est le code
unique ID01/ID06 généré par le formulaire qui reste l'identifiant stable d'un entretien.

## 6. Sécurité et confidentialité des données

- La base Kobo de ce mémoire est une **vraie base de collecte de terrain** (données de
  ménages réels de la ZS Lemba) : ne jamais rendre le tableau de bord public sans
  restriction d'accès si des champs sensibles (GPS, identifiants) sont visibles.
- Le jeton d'API Kobo donne un accès complet aux données du formulaire : ne le partagez
  qu'avec les personnes autorisées, et régénérez-le si vous pensez qu'il a été exposé.
- Le champ GPS (ID08) est volontairement exclu des graphiques et n'est affiché que dans
  l'export brut filtré ; retirez-le manuellement de tout export partagé plus largement.
- Aucune donnée n'est stockée par l'application elle-même : tout est recalculé à la
  demande depuis l'API Kobo (ou le fichier chargé), en mémoire, pour la durée de la
  session du navigateur.

## 7. Prochaines évolutions possibles

- Ajout du calcul `PONCTUALITE` par dose (délai de grâce de 28 jours) une fois les règles
  validées avec le directeur de mémoire.
- Authentification simple (mot de passe partagé) si l'app doit rester accessible sans
  restriction IP sur Streamlit Community Cloud.
- Export automatique périodique (ex. rapport PDF hebdomadaire) si utile pour les points
  d'étape avec le directeur de mémoire.

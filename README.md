# Pia-Pia 🦜  
Bot Discord de transcription pour jeux de rôle (JDR)

Pia-Pia est un bot Discord qui écoute vos parties de JDR (D&D, Cthulhu, etc.), transcrit les échanges audio en texte, et peut générer un PDF de la session.  
Chaque joueur est associé à un personnage, ce qui permet d’obtenir un compte-rendu clair : qui parle, quand, et quoi.

---

## ✨ Fonctionnalités

- 🎙️ **Enregistrement audio** sur un salon vocal Discord
- 🧠 **Transcription locale** avec [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) (mode GPU ou CPU)
- 📝 **Journal de session structuré** :
  - un fichier `.log` JSONL par session (une ligne = une intervention)
  - filtrage des segments vides et de certains bruits (sous-titrage fantôme & co)
- 📚 **Génération de PDF** résumant la session (par ordre chronologique)
- 🎭 **Mapping joueur → personnage** :
  - via un fichier YAML (`player_map.yaml`)
  - mis à jour automatiquement avec `/update_player_map`
- 🎧 **Archivage audio brut (optionnel)** :
  - un fichier WAV par utilisateur, par session
  - utile pour ré-analyser une partie plus tard

---

## 🧩 Prérequis

- **Python 3.11** (recommandé)
- Un compte Discord & un **bot Discord** enregistré  
  → via le portail développeur Discord : https://discord.com/developers/applications
- (Optionnel mais recommandé) Une **carte GPU** compatible CUDA pour Faster-Whisper

### PyTorch + CUDA

Pour utiliser le GPU, installe PyTorch avec la bonne version de CUDA en suivant la doc officielle : https://pytorch.org/get-started/locally/

Exemple (à adapter selon ta config) :

```bash
# Exemple (à adapter !) : CUDA 12.x
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

Ensuite, installe le reste des dépendances normalement.

---

## 📦 Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/<ton-compte>/<ton-repo-pia-pia>.git
cd <ton-repo-pia-pia>
```

### 2. Créer un environnement virtuel

```bash
python -m venv .venv
source .venv/bin/activate  # Linux / macOS
# ou
.\.venv\Scripts\activate   # Windows
```

### 3. Installer les dépendances

Si tu es en **CPU uniquement** :
```bash
pip install -r requirements.txt
```

Si tu veux utiliser le **GPU** :

1. Installe d’abord torch avec la bonne roue CUDA (via la doc PyTorch).
2. Puis installe le reste :

```bash
pip install -r requirements.txt --no-deps
```

(pour éviter de réinstaller torch en version CPU)

---

## ⚙️ Configuration (.env)

Un fichier `.env.example` est fourni à la racine du projet. Commence par le copier :

```bash
cp .env.example .env
```

Ensuite, édite `.env` avec tes valeurs. Les variables principales :

### Discord

- `DISCORD_BOT_TOKEN` (obligatoire) Le token de ton bot, récupérable sur : https://discord.com/developers/applications

### Logs & fichiers

- `LOGS_DIR` : Dossier racine pour les logs (ex: .logs).
- `TRANSCRIPTS_SUBDIR` : Sous-dossier où sont écrits les fichiers de transcription de session (ex: transcripts → .logs/transcripts/).
- `PDF_SUBDIR` : Sous-dossier où sont générés les PDF de sessions (ex: pdfs).
- `AUDIO_ARCHIVE_SUBDIR` : Sous-dossier où sont stockés les WAV par utilisateur/sessions (ex: audio).
- `ARCHIVE_AUDIO` : (true / false) Active ou non l’archivage WAV (prend de la place disque mais très utile pour reprocess).

### Transcription / Whisper

- `TRANSCRIPTION_METHOD`
    - `local` → Faster-Whisper en local (recommandé)
    - `openai` → API OpenAI Whisper (si tu veux tester, nécessite OPENAI_API_KEY)
- `WHISPER_MODEL`

    Nom du modèle, par ex :

    - `large-v3` (très précis, plus lourd)
    - `medium`, `small`, etc.

- `WHISPER_LANGUAGE`

    Code langue ISO (fr, en, …) pour guider la transcription.

- `WHISPER_COMPUTE_TYPE`
    - sur GPU : souvent `float16` ou `bfloat16`
    - sur CPU : `float32` (plus stable si pas de support half precision)

- `SILENCE_THRESHOLD`

    Temps en secondes de silence avant de considérer qu’un locuteur a fini de parler (ex: `1.5`).

- `MIN_AUDIO_DURATION`
    
    Durée minimale en secondes avant d’envoyer un segment à Whisper (ex: `0.3` ou `0.5`).

- `ENABLE_SUBTITLE_NOISE_FILTER` (`true` / `false`)

    Active le filtrage de certaines hallucinations de type “Sous-titrage FR ?”, etc.


### Mapping joueurs / personnages

- `PLAYER_MAP_FILE_PATH`

    Chemin du fichier YAML de mapping (ex: config/player_map.yaml).

Ce YAML ressemble à quelque chose comme :

```yaml
"252171234567891168":
  player: "nom_joueur"
  character: "NomDuPersonnage"
"123456789012345678":
  player: "autre_joueur"
  character: "NomDuPersonnage"
```

La commande `/update_player_map` permet de le générer / mettre à jour automatiquement à partir des membres présents sur la guilde.

---

## 🚀 Lancer Pia-Pia

Une fois l’environnement et le `.env` prêts :
```bash
python -m src.main
```

Pour activer le mode debug (logs plus verbeux) :
```bash
python -m src.main --debug
```

Pia-Pia se connecte alors à Discord et enregistre ses commandes slash.

---

## 🎮 Commandes Discord

### `/help`

Affiche un message d’aide récapitulant ce que sait faire Pia-Pia et les commandes disponibles.

### `/connect`

- Pia-Pia rejoint le **salon vocal** où tu te trouves.
- Il ne commence pas à enregistrer tant que tu n’as pas lancé `/scribe`.

### `/scribe`

- Démarre une session de transcription pour la guilde :
    - création d’un fichier .logs/transcripts/<timestamp>_g<guild>_session.log
    - (optionnel) création des fichiers WAV dans .logs/audio/<session_id>/user_<id>.wav
- Tant que la session est active :
    - Pia-Pia écoute,
    - segmente la parole par locuteur,
    - envoie les segments au modèle Whisper,
    - loggue les transcriptions ligne par ligne dans le fichier de session.

### `/stop`

- Arrête la session de transcription courante pour la guilde :
    - le `DiscordSink` est stoppé proprement,
    - les dernières transcriptions sont flushées.
- Important : le fichier de session `.log` reste disponible pour `/generate_pdf`.

### `/generate_pdf`

- Lit le fichier de session le plus récent pour la guilde.
- Construit une liste d’événements (`TranscriptionEvent`) :
    - ordonnés par temps,
    - filtrés (texte vide, bruit marqué `is_noise`, etc.).
- Génère un PDF (ex: `.logs/pdfs/2025-12-05_20-45-12_session.pdf`).
- Envoie ce PDF dans le canal où la commande a été appelée.

### `/disconnect`

- Pia-Pia quitte le salon vocal.
- Nettoie proprement :
    - les sinks,
    - les états en mémoire liés à la guilde,
    - (optionnel) ferme les fichiers WAV si archivage actif.

### `/update_player_map`

- Récupère les membres de la guilde.
- Met à jour la `player_map` interne :
    - `user_id -> { player: <pseudo>, character: <display_name> }`
- Persiste le tout dans `config/player_map.yaml`.

Pratique si vous avez de nouveaux joueurs ou si quelqu’un change son pseudo / display name.

---

## 🧠 Whisper / Faster-Whisper

Pia-Pia utilise Faster-Whisper, une implémentation optimisée du modèle Whisper d’OpenAI.

- Git Whisper original : https://github.com/openai/whisper
- Git Faster-Whisper : https://github.com/guillaumekln/faster-whisper

Les paramètres principaux contrôlés via `.env` :

- `WHISPER_MODEL` : taille/précision du modèle (`base`, `small`, `medium`, `large-v3`, …).
- `WHISPER_LANGUAGE` : langue principale (`fr`, `en`, …).
- `WHISPER_COMPUTE_TYPE` : type de calcul (`float16`, `float32`, `bfloat16` …).
- `TRANSCRIPTION_METHOD` : `local` ou `openai`.

---

## ⚠️ Limitations connues

- Testé principalement :
    - sur 1 guilde à la fois,
    - avec 4–8 joueurs,
    - en français (`WHISPER_LANGUAGE=fr`).
- Le modèle `large-v3` est précis mais gourmand :
    - prévoir une bonne carte GPU si tu veux suivre plusieurs heures de session.
- Certaines hallucinations de type _“Sous-titrage FR ?”_ sont filtrées, mais il peut en rester quelques-unes selon le bruit et le micro.

---

## 🗺️ Idées / Roadmap (futures versions)

- Nommer les sessions (`/scribe game:"…" session:"…"`)
- Export Markdown / Obsidian des journaux
- Résumés automatiques de sessions (MJ / in-universe)
- Marqueurs de scène (`/bookmark`) durant la partie
- Interface web minimale pour lister les sessions & PDF
- Docker + image publique pour déploiement simplifié

---

## 📜 Licence & crédits

- Whisper © OpenAI
- Faster-Whisper © Guillaume Klein
- MIT license
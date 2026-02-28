# Prometheus AI

Version compiler EXE pour Windows : https://www.avhiral.com/download/Prometheus.zip

Assistant IA local avec interface graphique, conçu pour charger des modèles GGUF via `llama.cpp`

## Aperçu

Prometheus AI est une application légère pensée pour exécuter un chatbot local avec des modèles GGUF. L'interface reprend une logique de discussion simple, avec chargement de modèle, historique de conversations, réponses en streaming et outils pratiques. Le programme fonctionne sur tous systèmes, il n'ai pas nécessaire de disposer AVX ou AVX2.

## Fonctionnalités

- Chargement de modèles **GGUF** locaux
- Prise en charge des fichiers **.gguf** et des archives **.zip** contenant un modèle GGUF
- Interface graphique **Tkinter** de style conversationnel
- Réponses **en streaming**
- Optimisation automatique du chargement selon la machine (threads, contexte, batch, GPU NVIDIA si disponible)
- Historique des conversations avec sauvegarde JSON et tentative de réparation des fichiers corrompus
- Génération orientée **code Python**
- Fenêtres dédiées pour afficher le code avec copie rapide et coloration syntaxique basique
- Pièces jointes simples :
  - **TXT** : contenu injecté dans le message
  - **PDF** : lecture possible via `PyPDF2` si installé
  - **DOC/DOCX** : lecture possible via `python-docx` si installé
  - **Images** : jointes à titre informatif uniquement, sans analyse visuelle
- Bouton d'arrêt de génération
- Barre de progression lors du chargement du modèle

## Limitations actuelles

- Modèle **texte uniquement** : pas de génération d'images
- Pas d'analyse réelle du contenu des images
- Lecture Excel non implémentée
- Les PDF et DOCX nécessitent des dépendances optionnelles
- Le projet repose sur `llama_cpp`; sans cette bibliothèque, aucun modèle ne pourra être chargé

## Arborescence minimale

PrometheusAI/
├── Prometheus.py
├── icon.ico                # facultatif
└── conversations/          # créé automatiquement

## Prérequis

- Python 3.10 ou plus récent recommandé
- Windows conseillé pour cette interface telle qu'elle est actuellement utilisée
- Un modèle local au format **GGUF**

## Installation

### 1. Cloner le dépôt

git clone https://github.com/AVHIRAL/Prometheus-IA_Chatbot.git

cd Prometheus-IA_Chatbot

### 2. Créer un environnement virtuel

python -m venv .venv

Sous Windows :

.venv\Scripts\activate

Sous Linux/macOS :

source .venv/bin/activate

### 3. Installer les dépendances

pip install pillow llama-cpp-python

Dépendances optionnelles :

pip install PyPDF2 python-docx

> `tkinter` est généralement fourni avec Python sur Windows. Selon votre distribution Linux, il peut nécessiter une installation séparée.

## Lancement

python Prometheus.py

## Utilisation

1. Lancer l'application.
2. Cliquer sur **Charger modèle GGUF**.
3. Sélectionner un fichier `.gguf` ou une archive `.zip` contenant un `.gguf`.
4. Attendre la fin du chargement.
5. Saisir un prompt puis cliquer sur **Envoyer**.
6. Utiliser **Stop** pour interrompre une génération si besoin.
7. Les conversations sont enregistrées dans le dossier `conversations/`.

## Types de fichiers joints

| Type | Comportement |
|---|---|
| `.txt` | Le contenu texte est lu et injecté dans le message |
| `.pdf` | Lecture via `PyPDF2` si disponible |
| `.doc` / `.docx` | Lecture via `python-docx` si disponible |
| `.xls` / `.xlsx` | Non implémenté |
| `.png` / `.jpg` / `.jpeg` / `.gif` / `.bmp` | Fichier signalé, mais pas d'analyse visuelle |

## Positionnement du projet

Prometheus AI vise un usage simple et local :

- pas de dépendance à une API distante pour discuter,
- chargement direct de modèles GGUF,
- interface bureau rapide à prendre en main,
- orientation marquée vers l'assistance en programmation Python.

## Pistes d'amélioration

- support réel multimodal,
- meilleure gestion des dépendances et du packaging,
- export des conversations,
- meilleure prise en charge des documents,
- réglages avancés des paramètres d'inférence,
- packaging exécutable Windows avec installateur.

## Licence

AVHIRAL 2026 © - Version Open-Source

DON PAYPAL : https://www.paypal.com/donate/?hosted_button_id=FSX7RHUT4BDRY

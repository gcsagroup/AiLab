# GCSA AI Lab

[简体中文](../../README.md) · [繁體中文](../zh-TW/README.md) · [English](../en/README.md) · [日本語](../ja/README.md) · [한국어](../ko/README.md) · [Français](README.md) · [Português](../pt/README.md)

GCSA AI Lab est une application de bureau pour exécuter des modèles en local, les ajuster avec LoRA, les évaluer et gérer leurs productions. Chaque projet regroupe modèles, données, tâches et résultats pour reprendre le travail et en retrouver les paramètres.

Version actuelle : **Ver2.7 (055), aperçu technique**. L’application native Ver2.7 (054) a été testée via un tunnel SSH avec Qwen2.5-0.5B-Instruct : génération sur Jetson Orin, entraînement LoRA en deux étapes, récupération des résultats et exécution du même adaptateur sur GPU Apple. Cette validation se limite au modèle et à l’environnement indiqués et ne prouve aucune amélioration de qualité. Le déploiement HTTPS direct, l’installation sur un environnement vierge, les tests avec de nouveaux utilisateurs et la validation de distribution restent incomplets. Aucun installateur public validé ni canal de mise à jour automatique n’est disponible. 055 corrige les messages de déconnexion pendant l’envoi et de fin d’exécution. Les vérifications natives couvrent l’interruption, la vérification de l’état et un nouveau transfert réussi ; le parcours complet des modèles entre appareils de 054 n’a pas été répété.

Le travail se poursuit en essai interne. Les vérifications complémentaires de 055 couvrent la restauration de sauvegardes, la mise à jour et le retour au paquet précédent, l’utilisation indépendante des exports, une tâche au clavier et les générations multimédias prévues. L’examen des données métier et les tests par cinq utilisateurs réels restent en attente, sans remplacement par des résultats simulés.

- Génération de texte, ajustement SFT + LoRA et comparaison du modèle de référence avec un candidat.
- Génération d’images, LoRA image expérimental, accès à la génération vidéo, à la synthèse vocale et à la transcription. L’entraînement vidéo et audio n’est pas disponible.
- Import de données, séparation par groupe de provenance, historique, révisions des productions, export, sauvegarde et restauration.

La prise en charge dépend du modèle, de l’appareil, du moteur et de la précision. Vérifiez la configuration avant de démarrer. Des tests de qualité échouent encore : terminer un entraînement ne garantit pas sa qualité. La documentation existe en sept langues ; cela ne signifie pas que l’interface les propose toutes.

[Guide d’utilisation](docs/USER_GUIDE.md) · [Historique des modifications](CHANGELOG.md) · [GitHub](https://github.com/gcsagroup/AiLab)

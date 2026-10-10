# Historique des modifications

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](../en/CHANGELOG.md) · [日本語](../ja/CHANGELOG.md) · [한국어](../ko/CHANGELOG.md) · [Français](CHANGELOG.md) · [Português](../pt/CHANGELOG.md)

2026-10-10 (mise à jour du code source, pas encore intégrée à une application distribuée) : ajout d’un environnement Jetson Orin figé et correction de la libération de l’espace de travail CUDA. Les vérifications avec Qwen2.5-0.5B-Instruct couvrent la génération, deux étapes d’entraînement LoRA et le chargement indépendant du même adaptateur exporté sur un GPU Apple. Elles ne démontrent ni une amélioration de la qualité du modèle ni la validation du parcours complet entre appareils dans l’application.

2026-10-07 : documentation publique en sept langues, retrait des journaux internes de développement et de validation, réécriture des instructions. Aucun nouveau build de l’application.

## Ver2.6 (053)

Version actuelle : **Ver2.6 (053), aperçu technique**. Certains modèles ont été testés en inférence et en ajustement sur Apple Silicon. Les parcours entre appareils NVIDIA et Apple, l’installation sur un environnement vierge, les tests avec de nouveaux utilisateurs et la validation de distribution restent incomplets. Aucun installateur public validé ni canal de mise à jour automatique n’est disponible.

- Le focus clavier reste visible après le chargement d’une page supplémentaire ; la dernière page conserve son indicateur de fin.
- Les champs numériques affichent leurs erreurs et refusent les valeurs invalides ; température et Top-p acceptent les décimales valides.
- Ajout du support expérimental d’un modèle 7B fixe et blocage des combinaisons de cache KV quantifié 7B ayant échoué aux tests de qualité.
- Export des versions, sauvegarde et restauration, récupération des sorties et résumés de diagnostic. La validation de distribution et de qualité métier reste incomplète.

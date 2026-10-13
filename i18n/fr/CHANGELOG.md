# Historique des modifications

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](../en/CHANGELOG.md) · [日本語](../ja/CHANGELOG.md) · [한국어](../ko/CHANGELOG.md) · [Français](CHANGELOG.md) · [Português](../pt/CHANGELOG.md)

## 2026-10-14 · Identité des adaptateurs entre appareils et contrôles de rejet

Le contrôle préalable intégré à 055 a accepté 1 cas compatible et rejeté 7 cas portant sur le modèle de base, le modèle de conversation, la provenance d’entraînement, les modules, les noms de tenseurs, un format déguisé et une base absente ; 56 tests de régression associés ont réussi. La chaîne NVIDIA→Apple existante a été vérifiée sur 9 fichiers et 4 transpositions matricielles, élément par élément, achevant l’essai technique du même adaptateur. Aucun nouvel entraînement ni aucune génération n’a été lancé, et l’App n’a pas été reconstruite. La qualité du modèle, le parcours complet d’admission entre appareils et la validation de publication restent incomplets.

## 2026-10-13 · Vérifications natives supplémentaires

La même version Ver2.7 (055), signée par l’entreprise, a passé les vérifications de reprise après erreur d’importation avec des chemins chinois, de noms longs, d’états vides, de retour du focus après fermeture des dialogues et de refus des sous-titres dépassant la durée vidéo. Les preuves comprennent 11 captures natives et 98 tests frontend associés réussis. Aucun code produit n’a été modifié, l’application n’a pas été reconstruite et aucun entraînement ni aucune inférence n’a été lancé. L’apparence système, la taille de fenêtre et la bibliothèque quotidienne ont été restaurées. Ces vérifications portent sur certaines pages et certains états ; la validation complète de l’interface, de la qualité métier, par cinq utilisateurs réels et de la publication reste inachevée.

## 2026-10-13 · Suivi qualité et maintenance des tests

Point qualité du 2026-10-13 : le modèle Qwen2.5-7B-Instruct existant a exécuté une référence et deux essais de prompts sur 50 comptes rendus synthétiques d’exploitation, en inférence locale autonome, sans entraînement. Certains champs se sont améliorés, mais des faits manquaient et des états restaient erronés. Le prompt révisé a aussi suivi une annotation trompeuse du texte source et inventé une action et un rétablissement. Aucun des deux prompts n’a été adopté. Ces exemples ont servi au développement et n’ont pas fait l’objet d’une revue métier indépendante ; ils ne prouvent ni un test en aveugle ni une validation de qualité en production.

Les échecs des essais autonomes de prompts 7B sont documentés ; aucun prompt n’est devenu un réglage par défaut de l’application. Le test de nouvelle tentative du marché de données attend désormais le bouton de téléchargement avant de l’utiliser. Seuls les tests et la documentation ont changé ; l’App n’a pas été reconstruite et le candidat signé reste Ver2.7 (055). La qualité complète, les essais avec cinq utilisateurs réels et la validation de distribution restent à réaliser.

## Ver2.7 (055) · 2026-10-10

Correction des déconnexions pendant l’envoi distant signalées à tort comme un plantage du service de contrôle. La cause réelle est conservée et la vérification de l’état ne soumet pas à nouveau le calcul. Le test natif a confirmé l’interruption, la vérification de l’état, la reconnexion et un nouveau transfert réussi, avec un contenu identique au retour et la conservation de l’historique.

055 corrige les messages de déconnexion pendant l’envoi et de fin d’exécution. Les vérifications natives couvrent l’interruption, la vérification de l’état et un nouveau transfert réussi ; le parcours complet des modèles entre appareils de 054 n’a pas été répété.

Vérification supplémentaire de 055 : le même adaptateur expérimental entraîné auparavant sur AGX a été exporté depuis l’interface native, puis chargé indépendamment depuis une copie avec le moteur MLX inclus, sur GPU Apple. La génération a réussi, l’empreinte correspond, le modèle de base et les fichiers exportés sont restés inchangés, et le processus s’est terminé naturellement. Aucun nouvel entraînement ; la qualification de qualité et la validation complète de distribution entre appareils restent incomplètes.

Vérifications complémentaires de l’essai interne réussies : restauration d’une sauvegarde historique, annulation d’une migration défaillante, mise à jour 054→055 et retour au paquet précédent. Les 64 fichiers de contenu de douze types d’exports restaurés ont été vérifiés ; les modèles de base et quantifiés ainsi que les adaptateurs texte et image ont été chargés depuis des copies indépendantes. Une tâche native au clavier, la génération d’images, de vidéos et de voix avec le paquet actuel, ainsi que l’annulation après le début du calcul réel ont été vérifiées. Cela ne valide ni la qualité des modèles, ni une installation propre, ni une publication officielle.

## Ver2.7 (054) · 2026-10-10

Version actuelle : **Ver2.7 (054), aperçu technique**. L’application native a été testée via un tunnel SSH avec Qwen2.5-0.5B-Instruct : génération sur Jetson Orin, entraînement LoRA en deux étapes, récupération des résultats et exécution du même adaptateur sur GPU Apple. Cette validation se limite au modèle et à l’environnement indiqués et ne prouve aucune amélioration de qualité. Le déploiement HTTPS direct, l’installation sur un environnement vierge, les tests avec de nouveaux utilisateurs et la validation de distribution restent incomplets. Aucun installateur public validé ni canal de mise à jour automatique n’est disponible.

2026-10-07 : documentation publique en sept langues, retrait des journaux internes de développement et de validation, réécriture des instructions. Aucun nouveau build de l’application.

## Ver2.6 (053)

Version actuelle : **Ver2.6 (053), aperçu technique**. Certains modèles ont été testés en inférence et en ajustement sur Apple Silicon. Les parcours entre appareils NVIDIA et Apple, l’installation sur un environnement vierge, les tests avec de nouveaux utilisateurs et la validation de distribution restent incomplets. Aucun installateur public validé ni canal de mise à jour automatique n’est disponible.

- Le focus clavier reste visible après le chargement d’une page supplémentaire ; la dernière page conserve son indicateur de fin.
- Les champs numériques affichent leurs erreurs et refusent les valeurs invalides ; température et Top-p acceptent les décimales valides.
- Ajout du support expérimental d’un modèle 7B fixe et blocage des combinaisons de cache KV quantifié 7B ayant échoué aux tests de qualité.
- Export des versions, sauvegarde et restauration, récupération des sorties et résumés de diagnostic. La validation de distribution et de qualité métier reste incomplète.

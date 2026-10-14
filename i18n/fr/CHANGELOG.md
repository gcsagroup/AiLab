# Historique des modifications

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](../en/CHANGELOG.md) · [日本語](../ja/CHANGELOG.md) · [한국어](../ko/CHANGELOG.md) · [Français](CHANGELOG.md) · [Português](../pt/CHANGELOG.md)

## Ver2.7 (060) · 2026-10-14 · 060 : messages d’importation et validation des données texte

Les erreurs indiquent la ligne du fichier source et des messages chinois précis pour le JSON invalide et les contenus non textuels. La même App 060 signée par l’entreprise a revérifié cinq refus de modèles et quatre refus de données. Le téléchargement officiel arrêté sur 059 a repris et abouti sur 060, puis a été vérifié et explicitement enregistré avant une génération courte réelle. Un chargement avec poids manquants a réellement échoué. La séparation CPU correspond exactement à la référence et crée deux versions indépendantes. Supervision nulle, invites dupliquées et contrôle périmé après changement de longueur sont refusés. Tests réussis : 86 contrôle, 95 frontend, 70 supervision CPU et 33 contrats de séparation. Aucun entraînement ; bibliothèque originale restaurée. Portée limitée aux fonctions texte locales choisies. Un processus séparé ne constitue pas une isolation par le système ; validation complète des recettes, appareils, qualité, utilisateurs et publication encore inachevée.

## Ver2.7 (059) · 2026-10-14 · 059 : limites des suggestions IA et messages d’état

Correction d’un ancien message affirmant à tort que la tâche n’avait pas été exécutée : il renvoie désormais aux exécutions réelles. Sur 058, cinq générations locales réelles de suggestions ont couvert les quatre champs pris en charge, l’application et l’annulation explicites, les conflits de version et le refus après soumission ; une exécution texte de la tâche cible a vérifié cette dernière limite. La même App 059 signée par l’entreprise a revérifié les messages historiques, le refus après soumission et une nouvelle suggestion réelle avec application et annulation. Les 32 tests de contrôle et les 13 tests frontend après correction ont réussi. La bibliothèque d’origine a été restaurée, sans entraînement. Les preuves conservent leur version réelle. Les suggestions distantes restent indisponibles ; qualité, couverture complète des appareils, utilisateurs réels et publication restent à valider.

## Ver2.7 (058) · 2026-10-14 · 058 : pagination et brouillons par projet

Correction du faux message d’absence de tâches lorsque celles-ci se trouvent sur des pages suivantes. Le chargement supplémentaire révèle les évaluations existantes ; l’état vide apparaît seulement une fois toutes les tâches chargées. Les 76 tests frontend concernés ont réussi. La même App 058 signée par l’entreprise a validé la réouverture des brouillons texte/image de deux projets, les quatre entrées et le retour depuis les résultats existants, ainsi que l’appartenance d’un résultat image au projet d’origine après un changement de projet pendant l’exécution. La bibliothèque d’origine a été rétablie, sans entraînement. Les anciens échecs de qualité restent valables ; la couverture complète des appareils, cinq utilisateurs, l’installation propre et la publication restent à valider.

## 2026-10-14 · 057 : différences du candidat et validations restantes

La comparaison fichier par fichier des paquets signés 055 et 057 et le relevé des lacunes des 27 critères de validation sont terminés. Les 49 tests d’identité des paquets ont réussi. Les preuves des anciens composants restent limitées à leur version ; des sources identiques ne valent pas validation du paquet final entier. Aucun changement produit, aucune reconstruction de l’App ni exécution de modèle. La couverture complète des appareils réels, la qualité, cinq utilisateurs, l’installation propre et la publication officielle restent à valider.

## 2026-10-14 · 057 : validation native du marché de données contrôlé

La même App 057 signée par l’entreprise a validé le téléchargement ouvert, les demandes restreintes en attente, refusées puis approuvées, le rejet des structures invalides et le retour au brouillon d’entraînement initial. Après l’arrêt du fournisseur local de test, les données téléchargées pouvaient encore être vérifiées, importées et appliquées ; le choix persistait après réouverture. La comparaison de chaque champ confirme que seul le jeu de données change, avec maintien du nom, des paramètres, du projet et de l’étape. Les 31 tests d’interface et 73 tests du service de contrôle ont réussi. La bibliothèque et les réglages de source initiaux ont été rétablis, sans entraînement ni exécution de modèle. Cela clôt la validation fonctionnelle AC-05 pour la source contrôlée. Les données synthétiques et décisions de test fixées par l’opérateur ne prouvent ni l’autorisation d’un marché externe, ni la qualité des données ou des modèles, ni l’achèvement complet de M4/M6.

## 2026-10-14 · 057 : vérification des interfaces de gestion des appareils et des données

La même App 057 signée par l’entreprise a été vérifiée en apparence claire et sombre aux largeurs 320, 360, 736 et 1024 pour la page des appareils, et à la largeur 320 pour les formulaires de sauvegarde, restauration, stockage, diagnostic et cible d’exécution. Les contrôles natifs au clavier couvrent le cycle de focus, les onglets, le retour du focus à la fermeture, la limite de 20 exécutions dans le diagnostic, le remplacement d’une sélection et l’annulation de l’aperçu. Les 40 tests d’interface associés ont réussi. Les données d’origine, la taille de fenêtre et l’apparence automatique ont été rétablies. Aucun entraînement, calcul de modèle ni nouvelle connexion distante n’a eu lieu. Ce contrôle reste partiel : AC-23 complet, la validation par de vrais utilisateurs et M6 restent à terminer.

## 2026-10-14 · 057 : flux média et progression atomique dans le même paquet

057 a désormais terminé deux flux image→vidéo→voix chinoise dans la même App signée par l’entreprise. Les six exports séparés ont passé le décodage complet et ont été ouverts ou lus dans des applications externes. Les contrôles natifs couvrent l’état incertain après interruption, la confirmation de sortie, la reprise avec de nouvelles entrées et l’invalidation des étapes suivantes. L’API publique du service intégré a traité des demandes concurrentes lors d’une annulation réelle et d’une fin naturelle : une seule progression a réussi et la répétition a conservé le résultat. Les 42 tests de régression des flux ont réussi. L’échec initial du script de vérification et l’exécution annulée restent consignés. Aucun entraînement n’a eu lieu. Cela valide les fonctions de la combinaison choisie, sans valider la qualité média, M4/M6 dans leur intégralité, les cinq utilisateurs ou la publication.

## 2026-10-14 · Messages d’échec média et vérification de deux flux

056 corrige les messages de vérification de l’exécution locale et d’absence de résultat média. Le même candidat signé par l’entreprise a terminé deux flux image, vidéo et voix chinoise, avec réutilisation explicite, modification des entrées, refus pendant une occupation, annulation et nouvelle exécution après échec. Six médias ont été exportés séparément et ouverts dans des lecteurs indépendants. Les 685 tests de l’interface ont réussi. Aucun entraînement n’a été effectué. Ces résultats ne valident ni la qualité des modèles, ni M4/M6 dans leur intégralité, ni la publication. 057 passe 688 tests de l’interface et corrige aussi la navigation dans l’historique des flux : les tâches en échec, en cours ou en attente de confirmation d’arrêt affichent l’exécution choisie. Les contrôles natifs ont confirmé l’accès à un ancien échec et le retour à l’étape actuelle. Les deux flux de calcul n’ont pas été réexécutés sur 057.

## 2026-10-14 · Vérifications locales des paramètres et de l’annulation

La même App Ver2.7 (055), signée par l’entreprise, a exécuté deux essais d’inférence locale depuis l’interface native : vérification des paramètres saisis, de la recette figée et du résultat réussi, puis annulation pendant la génération avec arrêt du processus confirmé. Les 101 tests associés ont réussi. Les enregistrements existants et la bibliothèque quotidienne sont conservés. Aucun entraînement ni reconstruction de l’App. Le périphérique NVIDIA désigné est actuellement inaccessible ; les contrôles distants restent incomplets. Cela ne valide ni toutes les fonctions, ni la qualité du modèle, ni la publication.

## 2026-10-14 · Socle technique et choix initiaux finalisés

Les preuves techniques de la configuration textuelle initiale sur les deux appareils, du cycle de vie du bureau et du même adaptateur entre appareils ont été consolidées. Les choix actuels et la planification des validations restantes sont documentés. Ver2.7 (055) reste un aperçu technique. Cette mise à jour concerne uniquement les enregistrements, sans reconstruction de l’App ni exécution de modèle. La finalisation de ce socle ne valide ni la qualité, ni la matrice fonctionnelle complète, ni les cinq vrais utilisateurs, ni l’installation propre, ni la publication officielle ; elle ne promet aucune date de sortie.

## 2026-10-14 · Validation du cycle de vie et de la reprise du bureau

La même App Ver2.7 (055), signée par l’entreprise, a passé les vérifications natives du message d’interruption du service, de la reconnexion, de l’arrêt des processus enfants après terminaison forcée de l’hôte, de la réouverture, de l’annulation de la fermeture et de la fermeture normale. Son service intégré a aussi passé les vérifications de démarrage et d’arrêt, de reprise après plantage et des journaux d’échec sur un chemin contenant des caractères chinois et des espaces ; 13 tests associés ont réussi. Tous les enregistrements métier de la bibliothèque de validation sont préservés et la sélection initiale a été restaurée. Aucun modèle n’a été exécuté ni l’App reconstruite. Cette validation technique ne remplace pas la matrice complète de pannes des tâches en cours, la qualité, les vrais utilisateurs, l’installation propre ou la validation de publication.

## 2026-10-14 · Vérification des preuves techniques Apple et NVIDIA

Vérification des entraînements LoRA historiques de quatre étapes sur Apple et de deux étapes sur NVIDIA, de la génération réelle et de 26 fichiers produits pour le modèle Qwen2.5-0.5B-Instruct retenu. Les identités du modèle de base, des fichiers du tokenizer et du modèle de conversation correspondent ; 49 tests de régression associés ont réussi. L’essai technique minimal d’entraînement et d’inférence est validé ; la qualité du modèle reste non évaluée. Aucun nouvel entraînement, aucune génération, connexion distante ou reconstruction de l’App n’a eu lieu. Les preuves restantes du cycle de vie de l’application, la validation complète des jalons et la publication officielle restent en attente.

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

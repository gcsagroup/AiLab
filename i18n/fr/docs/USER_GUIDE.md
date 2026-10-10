# Guide d’utilisation

[简体中文](../../../docs/USER_GUIDE.md) · [繁體中文](../../zh-TW/docs/USER_GUIDE.md) · [English](../../en/docs/USER_GUIDE.md) · [日本語](../../ja/docs/USER_GUIDE.md) · [한국어](../../ko/docs/USER_GUIDE.md) · [Français](USER_GUIDE.md) · [Português](../../pt/docs/USER_GUIDE.md)

Version actuelle : **Ver2.7 (054), aperçu technique**. L’application native a été testée via un tunnel SSH avec Qwen2.5-0.5B-Instruct : génération sur Jetson Orin, entraînement LoRA en deux étapes, récupération des résultats et exécution du même adaptateur sur GPU Apple. Cette validation se limite au modèle et à l’environnement indiqués et ne prouve aucune amélioration de qualité. Le déploiement HTTPS direct, l’installation sur un environnement vierge, les tests avec de nouveaux utilisateurs et la validation de distribution restent incomplets. Aucun installateur public validé ni canal de mise à jour automatique n’est disponible.

La prise en charge dépend du modèle, de l’appareil, du moteur et de la précision. Vérifiez la configuration avant de démarrer. Des tests de qualité échouent encore : terminer un entraînement ne garantit pas sa qualité. La documentation existe en sept langues ; cela ne signifie pas que l’interface les propose toutes.

## 1. Premier résultat

Créez un projet dans l’application dont l’environnement est déjà préparé, puis choisissez un essai de génération de texte. Pour préparer un modèle officiel, consultez sa provenance, sa licence et la liste des fichiers. Après téléchargement, ajoutez-le à la bibliothèque du projet. Vous pouvez aussi importer un dossier local complet. Choisissez le modèle, saisissez le texte et vérifiez la configuration avant de lancer l’exécution. Enregistrez le résultat pour le retrouver dans la bibliothèque des productions. Télécharger, importer ou enregistrer un brouillon ne lance pas le modèle.

## 2. Tâches et paramètres

Reprenez une tâche depuis l’espace de travail ou la file des tâches. Les brouillons sont enregistrés automatiquement ; en cas d’échec, réessayez et confirmez la sauvegarde. Les anciens résultats conservent leur modèle et leurs paramètres. Consultez les différences d’un préréglage avant de l’appliquer, puis relancez la vérification. Les réglages comprennent la limite de sortie, la température, Top-p, la graine, le budget de contexte, les séquences d’arrêt et l’affichage progressif. Le budget inclut le gabarit, l’entrée et la sortie réservée ; tout dépassement est refusé. Une séquence d’arrêt par ligne, au maximum 8 de 128 caractères chacune. Le mode économe en mémoire peut être plus lent. Le cache KV 4-bit est bloqué ; il est distinct de la quantification des poids. Chargez les tâches anciennes en fin de liste ; un indicateur reste visible sur la dernière page.

## 3. Entraînement et données

L’ajustement du langage utilise une recette fixe SFT + LoRA ; le LoRA image est expérimental. Vérifiez le format et les exemples supervisés valides. Séparez entraînement et validation par groupe de provenance pour éviter les fuites, prévisualisez puis appliquez la séparation ; les originaux sont conservés. Toute modification des données, du modèle ou des paramètres impose une nouvelle vérification. Fixez le plan d’évaluation avant l’entraînement et gardez les exemples d’évaluation à part. Comparez modèle de base et adaptateur. Un résultat sous les seuils reste expérimental et ne peut pas être enregistré comme candidat approuvé. Pause et reprise dépendent de la confirmation à l’écran et des points de contrôle disponibles.

## 4. Parcours multimédia

Images, vidéos, synthèse vocale et transcription exigent leurs modèles et environnements compatibles. Le parcours image → vidéo → voix conserve les entrées et résultats de chaque étape. Modifier une entrée en amont rend les anciens résultats suivants obsolètes. Choisissez explicitement de les réutiliser ; ce n’est pas une nouvelle génération. Les exemples actuels ont des limites de qualité : examinez les images, le son et les vidéos.

## 5. Révisions et export

Le texte et le script vocal acceptent chacun 16000 caractères. Les sous-titres acceptent 200 entrées, 16000 caractères au total et 500 par entrée. Les temps sont en secondes, ordonnés, sans chevauchement et dans la durée de la vidéo originale. Modifier le texte ne change pas les paramètres de génération ; modifier le script ne recrée pas l’audio. Les sous-titres sont exportés en VTT séparé, sans incrustation vidéo. Sélectionnez l’original ou une révision précise avant l’export ; l’action d’export de l’original sur une fiche reste liée à l’original. Choisissez le dossier et vérifiez le périmètre. L’export est terminé après écriture et vérification de tous les fichiers. Le paquet d’adaptateur indique le modèle de base exact, sans inclure ses poids par défaut. L’export des données séparées contient textes et identifiants de provenance : vérifiez son contenu avant de continuer.

## 6. Marché de données et aide IA

Respectez les conditions d’accès du fournisseur. Son accord ne remplace ni le contrôle des fichiers ni l’autorisation d’utilisation. Une version entièrement téléchargée peut être vérifiée et importée depuis la liste locale, puis choisie explicitement pour la tâche. L’intégration complète à des marchés commerciaux n’a pas été vérifiée. L’aide IA propose des modifications et leurs différences ; vous décidez de les appliquer. Leur application ne lance pas la tâche.

## 7. Sauvegarde et restauration

Créez une sauvegarde complète dans les paramètres des appareils et de l’environnement, après avoir traité les tâches actives, téléchargements et arrêts non confirmés. Elle inclut la base de données et les ressources référencées ; les grands modèles demandent de l’espace supplémentaire. Restaurez dans un nouveau dossier, puis choisissez explicitement cette bibliothèque. L’originale est conservée. Une copie de migration limitée à la base de données n’est pas une sauvegarde complète. Une ancienne application peut refuser une nouvelle bibliothèque ; un retour en arrière exige une bibliothèque compatible et une sauvegarde antérieure. Le nettoyage affiche son périmètre, ne traite que les ressources non référencées de la bibliothèque courante et permet leur restauration.

## 8. Exécution distante

Enregistrez l’adresse du service, son identifiant d’exécuteur et les identifiants d’accès. Le certificat HTTPS doit être valide et correspondre à l’hôte. Une connexion réussie ne prouve pas que le GPU ou le modèle est prêt. La destination par défaut du projet ne concerne que les nouvelles tâches texte ; les brouillons existants gardent leur destination. Vérifiez la destination, les fichiers et leur taille totale avant de confirmer l’envoi. Le contrôle de configuration ne téléverse rien. L’application native stocke les identifiants dans le trousseau système ; le navigateur de développement les garde seulement dans la session du service de contrôle. Le parcours Jetson Orin indiqué a été testé via un tunnel SSH : génération, entraînement, récupération, sauvegarde de l’adaptateur expérimental puis sélection du GPU Apple local pour l’essai. Le déploiement HTTPS direct reste à valider ; deux étapes d’entraînement prouvent uniquement le fonctionnement du parcours.

## 9. Dépannage

Après une interruption, reconnectez-vous et vérifiez la tâche d’origine. Une déconnexion ne signifie pas que la tâche distante est arrêtée : ne la relancez pas. Si le calcul est terminé mais le transfert a échoué, récupérez les sorties existantes sans recalcul. Les dossiers partiels d’un export échoué ou annulé ne sont pas des paquets complets. Prévisualisez le résumé de diagnostic dans les paramètres avant de l’enregistrer. Il exclut le contenu des tâches, les journaux bruts, les identifiants d’accès et les chemins locaux. Signalez la version, les étapes de reproduction et les diagnostics vérifiés, sans données privées.

[GCSA AI Lab](../README.md)

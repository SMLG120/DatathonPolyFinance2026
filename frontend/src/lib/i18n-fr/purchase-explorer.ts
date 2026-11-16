/** French catalog for the purchase-explorer screens. Keys are the exact English text passed to t() or tf(); values are French. */
export const FR: Record<string, string> = {
  // Stage 3: test an idea
  "Customized fictional portfolio": "Portefeuille fictif personnalisé",
  "This idea is checked against the weights you entered in step 1, not against {name}’s original fictional portfolio.":
    "Cette idée est vérifiée au regard des pondérations que vous avez saisies à l’étape 1, et non du portefeuille fictif d’origine de {name}.",
  "nothing": "rien",
  "The request failed.": "La requête a échoué.",
  "One investigation has already run in this session. Starting again creates a new one; earlier reports stay available.":
    "Une analyse a déjà été effectuée pendant cette session. Relancer en crée une nouvelle ; les rapports précédents restent disponibles.",
  "{count} investigations have already run in this session. Starting again creates a new one; earlier reports stay available.":
    "{count} analyses ont déjà été effectuées pendant cette session. Relancer en crée une nouvelle ; les rapports précédents restent disponibles.",
  "Checking your idea…": "Vérification de votre idée…",
  "Checks your limits. No trade is placed.": "Vérifie vos limites. Aucun ordre n’est passé.",
  "Needs at least one confirmed rule.": "Au moins une règle confirmée est nécessaire.",
  "The request above is not complete yet.": "La demande ci-dessus n’est pas encore complète.",
  "Needs an instrument and a final weight.": "Un instrument et une pondération finale sont nécessaires.",
  "Preview: computed by the service for the request above": "Aperçu : calculé par le service pour la demande ci-dessus",
  "No figure is shown rather than a guessed one. The service refused the request as it was sent, so sending it again unchanged would be refused again, and an investigation of it would be refused for the same reason. Change the request above, or the portfolio in step 1.":
    "Aucun chiffre n’est affiché plutôt qu’un chiffre deviné. Le service a refusé la demande telle qu’elle a été envoyée : renvoyée sans modification, elle serait de nouveau refusée, et une analyse de cette demande serait refusée pour la même raison. Modifiez la demande ci-dessus, ou le portefeuille à l’étape 1.",
  "Set your limits": "Définir vos limites",

  // Stage 4: investigation
  "Each step below is one the investigation actually completed. Steps appear as the job reports them; nothing is scripted in advance.":
    "Chaque étape ci-dessous a réellement été effectuée par l’analyse. Les étapes apparaissent au fur et à mesure que la tâche les signale ; rien n’est prévu à l’avance.",
  "“{words}” (free text, not resolved into a request yet)": "« {words} » (texte libre, pas encore converti en demande)",
  "A model chooses which tool to call next; the final checks are always run by the service.":
    "Un modèle choisit l’outil à appeler ensuite ; les vérifications finales sont toujours effectuées par le service.",
  "The model was unavailable or its output was rejected, so the service ran its fixed sequence of tools.":
    "Le modèle n’était pas disponible ou sa réponse a été rejetée : le service a donc exécuté sa séquence d’outils fixe.",
  "Model: {model}": "Modèle : {model}",
  "not reported": "non indiqué",
  "Deterministic fallback": "Repli déterministe",
  "Go to Test an idea": "Aller à Tester une idée",
  "Confirmed policy: version {version}": "Politique confirmée : version {version}",
  "Portfolio checked": "Portefeuille vérifié",
  "This persona": "Ce profil",
  "The investigation is complete: 1 step reported": "L’analyse est terminée : 1 étape signalée",
  "The investigation is complete: {count} steps reported": "L’analyse est terminée : {count} étapes signalées",
  "See the verdict and evidence": "Voir le résultat et les preuves",
  "See what the investigation needs": "Voir ce dont l’analyse a besoin",
  "Completion says the checks ran, not how they came out.":
    "Une analyse terminée indique que les vérifications ont été effectuées, pas quel en est le résultat.",
  "The request was ambiguous, so nothing was checked: the investigation asks a question instead of guessing.":
    "La demande était ambiguë, donc rien n’a été vérifié : l’analyse pose une question au lieu de deviner.",
  "The job ended without a result and gave no reason.": "La tâche s’est terminée sans résultat et sans indiquer de raison.",
  "No final answer within {seconds} seconds": "Aucune réponse finale en {seconds} secondes",
  "No final status was received within the time limit, so checking was stopped. The investigation may still be running.":
    "Aucun statut final n’a été reçu dans le délai imparti : le suivi a donc été arrêté. L’analyse est peut-être encore en cours.",
  "The investigation did not finish within the time limit, so checking was stopped. It may still be running.":
    "L’analyse ne s’est pas terminée dans le délai imparti : le suivi a donc été arrêté. Elle est peut-être encore en cours.",
  "The request for its status failed.": "La requête de son statut a échoué.",

  // Exposure explorer
  "Held directly": "Détenu directement",
  "Through {fund}": "Par l’intermédiaire de {fund}",
  "Through a fund": "Par l’intermédiaire d’un fonds",
  "up to {value}": "jusqu’à {value}",
  "Draft limit (not confirmed)": "Limite provisoire (non confirmée)",
  "Draft limit": "Limite provisoire",
  "Confirmed limit": "Limite confirmée",
  "None reported": "Aucune déclarée",
  "None": "Aucune",
  "Possible total": "Total possible",
  "Not available": "Non disponible",
  "No limit is drawn.": "Aucune limite n’est tracée.",
  "No holdings file": "Aucun fichier de positions",
  "No source recorded": "Aucune source enregistrée",
  "Not reported": "Non indiqué",
  "Current portfolio: parts": "Portefeuille actuel : composantes",
  "Proposed portfolio: parts": "Portefeuille envisagé : composantes",
  "Draft rules, not a confirmed policy": "Règles provisoires, pas une politique confirmée",
  "Confirmed policy version {version}": "Politique confirmée, version {version}",
  "Show interactive network": "Afficher le réseau interactif",
  "Show simple chart": "Afficher le graphique simple",
  "The check did not run to the end, so it returned no exposure figures.":
    "La vérification n’est pas allée jusqu’au bout : elle n’a renvoyé aucun chiffre d’exposition.",
  "The check returned no exposure section.": "La vérification n’a renvoyé aucune section d’exposition.",
  "The check returned an exposure section that lists no company.":
    "La vérification a renvoyé une section d’exposition qui ne mentionne aucune entreprise.",
  "The check returned no exposure figures for this company.": "La vérification n’a renvoyé aucun chiffre d’exposition pour cette entreprise.",
  "No limit is drawn: this check evaluated no rule that limits exposure to a single company.":
    "Aucune limite n’est tracée : cette vérification n’a évalué aucune règle limitant l’exposition à une seule entreprise.",
  "No limit is drawn: this check evaluated several single-company limits and the result does not say which one applies to this company.":
    "Aucune limite n’est tracée : cette vérification a évalué plusieurs limites par entreprise et le résultat n’indique pas laquelle s’applique à cette entreprise.",
  "A fund's holdings file does not cover the whole fund.": "Le fichier de positions d’un fonds ne couvre pas l’ensemble du fonds.",
  "A fund in the portfolio has no holdings file.": "Un fonds du portefeuille ne dispose d’aucun fichier de positions.",
  "Some holdings carry no sector label.": "Certaines positions n’ont aucune étiquette de secteur.",
  "Some companies have no record in the registry that was consulted.": "Certaines entreprises n’ont aucune fiche dans le registre consulté.",
  "There is not enough price history.": "L’historique des cours est insuffisant.",
  "Complete: the holdings file covers the whole fund": "Complet : le fichier de positions couvre l’ensemble du fonds",
  "Partial: the holdings file does not cover the whole fund": "Partiel : le fichier de positions ne couvre pas l’ensemble du fonds",
  "Missing: the fund has no holdings file": "Manquant : le fonds ne dispose d’aucun fichier de positions",
  "Current": "Actuel",
  "Proposed": "Envisagé",
  "Current portfolio": "Portefeuille actuel",
  "Proposed portfolio": "Portefeuille envisagé",
  "Proposed portfolio (after the purchase)": "Portefeuille envisagé (après l’achat)",
  "Not attributed (could be this company)": "Non attribué (pourrait être cette entreprise)",
  "Not attributed": "Non attribué",
  "Via {fund}": "Via {fund}",
  "Up to {value}": "Jusqu’à {value}",
  "The 3D view is not available in this browser, so the flat chart and the table are shown instead. They carry the same values.":
    "La vue 3D n’est pas disponible dans ce navigateur : le graphique à plat et le tableau sont affichés à la place. Ils présentent les mêmes valeurs.",
  "High-contrast mode is on, so the flat chart and the table are shown instead of the 3D view. They carry the same values.":
    "Le mode à contraste élevé est activé : le graphique à plat et le tableau sont affichés à la place de la vue 3D. Ils présentent les mêmes valeurs.",
  "Reduced motion is turned on, so the flat chart and the table are shown instead of the 3D view. They carry the same values.":
    "La réduction des animations est activée : le graphique à plat et le tableau sont affichés à la place de la vue 3D. Ils présentent les mêmes valeurs.",
  "On a narrow screen the flat chart and the table are shown instead of the 3D view. They carry the same values.":
    "Sur un écran étroit, le graphique à plat et le tableau sont affichés à la place de la vue 3D. Ils présentent les mêmes valeurs.",
  "The 3D view could not be started, so the flat chart and the table are shown instead. They carry the same values.":
    "La vue 3D n’a pas pu être lancée : le graphique à plat et le tableau sont affichés à la place. Ils présentent les mêmes valeurs.",
  "The 3D view stopped (the browser took back its graphics context), so the flat chart and the table are shown instead. They carry the same values.":
    "La vue 3D s’est arrêtée (le navigateur a repris son contexte graphique) : le graphique à plat et le tableau sont affichés à la place. Ils présentent les mêmes valeurs.",
  "{company}: exposure as a share of the portfolio, flat view": "{company} : exposition en part du portefeuille, vue à plat",
  "the exposure shown": "exposition affichée",
  "exposure to {company}": "exposition à {company}",
  "exposure to {company} through {fund}, before the purchase": "exposition à {company} par l’intermédiaire de {fund}, avant l’achat",
  "exposure to {company} through {fund}, after the purchase": "exposition à {company} par l’intermédiaire de {fund}, après l’achat",
  "exposure to {company}, before the purchase": "exposition à {company}, avant l’achat",
  "exposure to {company}, after the purchase": "exposition à {company}, après l’achat",
};

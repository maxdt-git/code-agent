## Étape 0 : mise en place (½ journée)

Crée student/ avec uv init et Python 3.10.
Ajoute les dépendances : pydantic, httpx ou openai, mcp, python-dotenv, pytest.
Copie models_public.py.
Ouvre des comptes gratuits chez 2 ou 3 fournisseurs (OpenRouter, Groq, Google AI Studio…) et mets les clés dans .env, avec .env dans .gitignore.
Dans moulinette/, lance uv sync puis uv run moulinette_eval dump mbpp --output ../cache/t.json.
✅ Terminé quand tu as un fichier de tâche MBPP et que tu comprends chacun de ses champs.

## Étape 1 : client LLM (1 à 2 jours)

Une fonction complete(messages, stop) → réponse, sur un seul fournisseur.
Chaque réponse renvoie le texte, les tokens d'entrée et de sortie (champ usage), la latence en ms et le nombre de retries.
Les retries : sur une erreur 429 ou 5xx ou un timeout, attente progressive (backoff) puis nouvel essai.
La rotation des clés : plusieurs clés par fournisseur (OPENROUTER_API_KEY_1, _2…). On passe à la suivante quand une clé renvoie « rate limit » ou « quota ».
Une abstraction fournisseur : une classe de base plus une configuration. Le repli vers un autre fournisseur est optionnel mais utile.
✅ Terminé quand un petit script appelle 2 fournisseurs différents, qu'une clé invalide bascule sur la suivante, et que les compteurs sont justes.

## Étape 2 : sandbox sans MCP (3 à 5 jours, l' étape la plus délicate)

SandboxConfig chargé depuis un JSON.
L'exécution de code dans un namespace persistant : une variable définie au tour 1 existe encore au tour 2.
La capture de stdout, stderr et des exceptions (traceback lisible).
Les imports : un __import__ personnalisé qui vérifie la liste blanche, en gérant la forme module.*.
Les builtins : un dictionnaire restreint (sans eval, exec, compile, open libre, globals, vars, breakpoint, input…) et un blocage des accès aux attributs __dunder__ dangereux.
Les fichiers : un open contrôlé qui résout le chemin réel (liens symboliques, ..) et le compare aux dossiers autorisés.
Le réseau : il est déjà en grande partie bloqué par les imports, mais il faut une deuxième barrière (neutraliser socket au niveau du processus).
Timeout et mémoire : un processus enfant avec resource.setrlimit(RLIMIT_AS) et un kill au timeout, en renvoyant la sortie partielle et un message clair.
final_answer(x) injecté dans le namespace : il signale « terminé » et renvoie la valeur.
Laisser remonter KeyboardInterrupt et SystemExit.
Le REPL uv run sandbox [config.json] : invite de saisie, exécution, affichage, et sortie propre avec exit ou Ctrl+D.
✅ Terminé quand tu as une batterie de tests pytest « d'attaque » qui échouent toutes proprement : import os, __import__('os'), open('/etc/passwd'), while True: pass, x = 'a' * 10**10, socket, les évasions par __subclasses__… Et le code normal fonctionne toujours.

## Étape 3 : MCP (2 à 3 jours)

Le serveur mcp_tools_mbpp.py avec run_tests(code, test_list), qui exécute dans un sous-processus avec timeout et renvoie {"success", "output"} en JSON.
Le client MCP en stdio : lancer le serveur, initialize, list_tools.
La transformation de chaque outil en fonction Python du sandbox (arguments positionnels ou nommés, d'après le schéma). Comme le SDK mcp est asynchrone, il faut un pont entre asynchrone et synchrone. Si le sandbox est dans un processus enfant, les appels d'outils doivent passer par le parent.
Le transport HTTP (--mcp-server <URL>).
L'exposition des resources et des prompts MCP (le sujet l'exige).
Le manuel généré : nom, signature, types et description de chaque outil, plus final_answer.
La troncature des sorties trop longues, avec un message du type « [sortie tronquée : 12 000 → 4 000 caractères] ».
✅ Terminé quand uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" cfg.json te permet d'appeler run_tests(...) à la main, que ça marche aussi en HTTP, et qu'un serveur MCP « jouet » écrit par toi avec d'autres outils apparaît automatiquement dans le manuel.

## Étape 4 : boucle d'agent et MBPP (2 à 4 jours)

L'extraction : les blocs ```python avec <end_code>, puis les formats XML <invoke>, <tool_call> JSON et ReAct convertis en Python. Chaque cas renvoie aussi une remarque (« aucun code trouvé », « bloc non fermé, interprété comme… »).
La boucle : prompt → LLM (stop=["<end_code>"]) → extraction → sandbox → Observation: → on recommence, jusqu'à final_answer ou max_iterations.
Le suivi : un StepMetrics par tour, puis un SolutionOutput final avec les totaux, le prompt système et l'erreur éventuelle.
Les garde-fous de budget : suivre les tokens cumulés et s'arrêter proprement avant de dépasser les limites. Si le budget est presque épuisé, soumettre la meilleure solution connue.
Le prompt MBPP : court, puisque 6 000 tokens au total. Un exemple minimal, et la consigne « teste puis final_answer dès que ça passe ».
La CLI python -m agent_mbpp --task-file … --output … --model-name … --provider-url ….
Aucun crash : tout est attrapé, et un solution.json est écrit même en cas d'échec.
✅ Terminé quand ./quickstart.sh mbpp … passe régulièrement. Vise au moins 9/10 sur une vingtaine de tâches au hasard, puisqu'il faut 4/5 à l'examen.

## Étape 5 : outils SWE-bench (3 à 5 jours)

Le cycle de vie Docker : télécharger l'image, lancer le conteneur, docker exec, puis le supprimer via try/finally, un gestionnaire SIGTERM et atexit.
Le choix de l'architecture : outils MCP sur l'hôte qui font un pont vers Docker (le plus simple), ou sandbox dans le conteneur.
Le serveur mcp_tools_swebench.py avec les 9 outils aux formats exacts du sujet. Ils lisent TESTBED_PATH.
read_file au format n: ligne ; search_code au format /chemin/absolu:n contenu ;
edit_file : échoue si old_str est absent ou présent plusieurs fois, et vérifie la syntaxe après modification (py_compile ou ruff) ;
search_function_or_class_definition_in_code et find_references (grep avec une regex, ou ast / jedi) ;
run_tests exécute eval_script ; get_patch fait git -c core.fileMode=false diff ; run_command(command, workdir).
Des tests unitaires pour chaque outil sur un petit dépôt git local, sans agent : c'est exactement ce que fera la moulinette.
✅ Terminé quand chaque outil passe tes tests seul, et que tu résous sympy__sympy-14711 à la main dans le REPL du sandbox connecté à ces outils.

## Étape 6 : agent SWE-bench (1 à 2 semaines, beaucoup
d'itérations)
python -m agent_swebench : même boucle, autre prompt, autres outils.
Un prompt qui décrit une méthode : localiser → reproduire → corriger → tester → soumettre.
La gestion du contexte : 300 000 tokens au total sur 30 tours, soit environ 10 000 par tour en moyenne. Il faut tronquer ou résumer les anciennes observations longues.
L'itération : lancer les 3 tâches faciles, lire les traces, corriger le prompt ou les outils, recommencer. Élargir ensuite à des tâches au hasard.
Vérifier le timeout de 900 s avec moulinette_eval run-agent 900 "…" et contrôler que le conteneur disparaît bien quand le processus est tué.
✅ Terminé quand tu réussis environ 2 tâches sur 3 de façon stable, sur des tâches au hasard.

## Étape 7 : benchmark et README (3 à 5 jours, à commencer tôt à cause des quotas)

Un petit script qui lance N modèles × 3 tâches et range les solution.json.
Au moins 5 modèles et 2 fournisseurs. Remplis les tableaux et mesure au moins 2 métriques intermédiaires.
Une ablation : par exemple, un prompt avec ou sans exemple, ou un jeu d'outils complet contre un jeu réduit.
Les conclusions, puis le README.md avec toutes les sections demandées.

## Étape 8 : répétition générale

Lance les 3 examens dans des conditions réelles, avec un .env neuf.
Cherche des clés oubliées dans le code (grep de sk-, gsk_…).
Assure-toi qu'aucun conteneur ne reste (docker ps -a).
Prépare la soutenance : pour chaque paramètre (max_iterations, prompt, troncature, modèle), sache dans quel fichier et à quelle ligne il se trouve.

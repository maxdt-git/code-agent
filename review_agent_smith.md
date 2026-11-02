# Préparation à la correction : agent_smith

Ce document reprend les 17 questions de la feuille de correction. Pour chacune : ce que fait le correcteur, où regarder dans le code, ce qu'il faut montrer ou modifier, ce qu'il faut savoir expliquer, et les pièges.

Les chemins sont relatifs à la racine du dépôt (`~/monGit/agent_smith`). Les numéros de ligne correspondent à l'état du code au 2 novembre 2026.

---

## 0. Avant la correction (à faire la veille)

### 0.1 Commiter les correctifs Podman du 2 novembre

Trois fichiers ont été modifiés pour que tout marche sur les PC de l'école. À la question 11, le correcteur te fera faire `git checkout` pour annuler les modifications de test. **Si ces correctifs ne sont pas commités, ils seront effacés aussi.**

| Fichier | Changement |
|---|---|
| `Makefile` | cible `docker-up` (démarre `podman.socket`) et `podman unshare` devant `exam-swebench` |
| `src/agent_smith/swebench/docker_env.py` | préfixe `docker.io/` sur le nom d'image (Podman refuse les noms courts sans terminal) |
| `src/agent_swebench/__main__.py` | transmet `XDG_RUNTIME_DIR`, `CONTAINER*` et `_CONTAINERS*` au serveur d'outils |

### 0.2 Environnement sur un PC de l'école (Podman sans root)

Le correcteur lance les scripts **directement** (`./exams/exam_swebench.sh ...`), sans passer par `make`. Avant de commencer, tape :

```bash
systemctl --user enable --now podman.socket     # sinon : DockerException, 0/5 partout
```

Pour SWE-bench, propose de lancer `make exam-swebench`. Sinon, mets `podman unshare` devant la commande du correcteur :

```bash
podman unshare ./exams/exam_swebench.sh --student-path . --moulinette-path moulinette --env-file .env
```

Si tu dois l'expliquer : la moulinette copie le patch dans le conteneur avec ton uid (44506311). Ce numéro n'existe pas dans le conteneur d'un Podman sans root, donc `lchown ... invalid argument` et tout échoue. Sous `podman unshare`, ton uid devient 0 et la copie passe. On ne modifie ni la moulinette ni `swebench`.

### 0.3 Quotas

Le quota Groq (200 000 tokens par jour) est **par organisation, pas par clé**. Une nouvelle clé générée pendant la correction ne remet pas le compteur à zéro. **Ne fais aucun run Groq le jour de la correction avant l'examen.** Ordre de grandeur : MBPP ≈ 1 500 tokens par tâche, SWE-bench ≈ 20 000 à 70 000 par tâche.

### 0.4 Commande pour lancer une seule tâche MBPP (utile à la question 11)

```bash
make dump-mbpp                                  # écrit cache/mbpp_task.json
UV_PYTHON_INSTALL_DIR=/goinfre/$USER/agent_smith/uv/python \
UV_PROJECT_ENVIRONMENT=/goinfre/$USER/agent_smith/.venv \
uv run python -m agent_mbpp --task-file cache/mbpp_task.json --output /tmp/sol.json
```

---

## Q1. Clés d'API et offre gratuite

**Ce que fait le correcteur :** il regarde tes tableaux de bord (Groq, Gemini, OpenRouter), vérifie que tu es en offre gratuite, te fait générer de nouvelles clés en direct, puis cherche des clés écrites en dur dans le code.

**Où regarder :**
- `.env.example` : noms des variables. Plusieurs clés par provider sont acceptées, avec `_1`, `_2`, etc.
- `config/llm.json` : les 3 providers, chacun avec son `key_env` (`GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`).
- `src/agent_smith/llm/keys.py:5` (`load_keys`) : lit `PREFIX` ou `PREFIX_<n>` dans l'environnement. `KeyPool` fait tourner les clés en cas de rate limit.
- `load_dotenv()` : `src/agent_mbpp/__main__.py:102` et `src/agent_swebench/__main__.py:148`.

**Résultat des greps du correcteur :** `grep "sk-"` ne trouve rien. `grep "api_key\s*="` trouve seulement `client.py:150` et `backend.py:98`, qui passent la clé lue dans l'environnement. `.env` est dans `.gitignore`.

**À expliquer :**
- Modèle par défaut : `qwen/qwen3.8-27b` sur Groq. C'est le meilleur sur MBPP (19/20, environ 1 400 tokens par tâche) et il répond en environ 0,5 s.
- Pour SWE-bench, c'est aussi Qwen, parce qu'il consomme le moins de tokens d'entrée (environ 2 fois moins que `gemini-3.5-flash-lite`). Gemini est le plan B quand le quota Groq est épuisé.
- Le défaut reste Groq Qwen pour les deux agents. On change avec `--model-name` / `--provider-url`, ou `make exam-swebench MODEL=... PROVIDER=...`.

**Piège :** le correcteur met la nouvelle clé sous le nom `GROQ_API_KEY` (sans suffixe). C'est accepté (`keys.py`, la partie `if not rest`).

---

## Q2. Lancer les deux examens en arrière-plan

**Ce que fait le correcteur :** il lance `exam_mbpp.sh` (≈ 5 min) et `exam_swebench.sh` (≈ 45 min) dans deux terminaux.

**À vérifier :** pas d'erreur immédiate, `.env` chargé, l'image Docker se télécharge.

**Pièges (voir 0.2) :**
- `podman.socket` doit tourner.
- SWE-bench doit tourner sous `podman unshare` sur un PC de l'école.
- Les erreurs possibles et leur cause :

| Erreur | Cause |
|---|---|
| `DockerException ... FileNotFoundError` | socket Podman absent |
| `lchown /tmp/patch.diff: invalid argument` | lancé sans `podman unshare` |
| `short-name resolution enforced` | ancien code, sans le préfixe `docker.io/` |
| `HTTP 429 ... tokens per day` | quota Groq épuisé |

---

## Q3. Commandes obligatoires

| Commande | Point d'entrée |
|---|---|
| `uv run python -m agent_mbpp --help` | `src/agent_mbpp/__main__.py:24` (argparse) |
| `uv run python -m agent_swebench --help` | `src/agent_swebench/__main__.py:76` (a aussi `--no-fallback`) |
| `uv run sandbox [config.json]` | `pyproject.toml` → `agent_smith.sandbox.cli:main`. Config par défaut : `config/sandbox.json` (`cli.py:17`) |
| `uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py"` | `cli.py:140` (`connect`) |
| `uv run sandbox --mcp-server <URL>` | `mcp_bridge.py`, avec `streamable_http_client` (ligne 70) |

`--mcp-stdio` et `--mcp-server` sont mutuellement exclusifs (`cli.py:37`).

**Piège :** un simple `uv run` crée un `.venv` dans le dépôt, alors que le Makefile utilise `/goinfre`. Ça marche quand même, c'est juste plus lent la première fois.

**À expliquer :** les clés viennent uniquement de l'environnement (`.env`, via `python-dotenv`).

---

## Q4. Modèles Pydantic

**Où regarder :** `src/agent_smith/models.py`.

| Classe | Ligne | Remarque |
|---|---|---|
| `StepMetrics` | 8 | les 11 champs demandés, `timestamp` en ISO (`datetime.now().isoformat()`) |
| `SolutionOutput` | 28 | inclut `system_prompt` et `error`, `timestamp` en ISO |
| `SandboxConfig` | 49 | `authorized_imports`, `allowed_directories`, `max_execution_time_seconds`, `max_memory_mb` |
| `MBPPTaskInput` | 61 | `task_id: int` |
| `SWEBenchTaskInput` | 73 | `docker_image`, `eval_script`, `hints_text` |

Sérialisation : `solution.model_dump_json(indent=2)` (`agent_mbpp/__main__.py:150`). Les tâches sont lues avec `model_validate_json`.

**À expliquer :** les modèles suivent strictement le sujet. Pydantic valide les types à la lecture des tâches et à l'écriture de la solution.

---

## Q5. Sécurité du sandbox (tests 1 à 5 de `exam_sandbox.sh`)

Architecture en 3 couches. C'est à savoir raconter :

1. **Processus enfant** : `sandbox.py:28` (`_start`). On utilise `multiprocessing` en mode « spawn ». Si l'enfant plante ou dépasse une limite, on le tue et on le relance.
2. **Analyse du code avant exécution** : `guards.py:258` (`check_tree`). L'arbre syntaxique (`ast`) est inspecté et les noms ou attributs interdits sont refusés.
3. **Exécution avec des builtins filtrés** : `executor.py:109` (`execute`). `exec` tourne avec notre propre dictionnaire `__builtins__`.

| Test | Où c'est géré |
|---|---|
| Imports (1-2) | `guards.py:59` (`make_safe_import`) : liste blanche, `"collections.*"` autorise les sous-modules (`is_allowed`, ligne 41), import relatif refusé. Le module rendu est une **copie filtrée** (`make_safe_module`, ligne 224) : `math.os` ou `collections.sys` sont inaccessibles. `__import__` est remplacé. |
| Fichiers (3) | `guards.py:99` (`make_safe_open`) : `os.path.realpath` résout `..` et les liens symboliques **avant** la vérification. `/tmp/agent_other` n'est pas dans `/tmp/agent` (`base + os.sep`, ligne 93). Un numéro de descripteur de fichier est refusé. |
| Builtins (4) | `guards.py:14` (`FORBIDDEN_BUILTINS`) : eval, exec, compile, open (remplacé par `safe_open`), globals, locals, vars, input, exit… Les attributs dunder (`__class__`, `__subclasses__`…) sont bloqués par `is_forbidden_attr` (ligne 211) et par `safe_getattr`. |
| Réseau (5) | Deux barrières. (1) `socket`, `urllib`, `http` ne sont pas dans la liste blanche. (2) `worker.py:90-107` : `socket.socket` est remplacé par `BlockedSocket` dans tout le processus enfant, donc même un module autorisé ne peut pas ouvrir de connexion. |

Autre sécurité : `worker.py:22` vide `os.environ` dans l'enfant, pour que les clés d'API ne soient pas lisibles depuis le sandbox.

**Démonstration en direct :**

```
uv run sandbox
>>> print("hello world")
>>> final_answer("test")          → [final answer] >>> test
>>> import os                     → ImportError: import of 'os' is not allowed
>>> open('/etc/passwd')           → PermissionError: access to '/etc/passwd' is not allowed
>>> open('../../../etc/passwd')   → PermissionError
```

**À dire :** seulement la bibliothèque standard (`ast`, `multiprocessing`, `resource`, `builtins`), pas de RestrictedPython.

---

## Q6. MCP

**Transports :** `mcp_bridge.py:26`. La cible est soit des `StdioServerParameters` (stdio), soit une URL (HTTP streamable). Le bridge fait tourner la boucle `asyncio` du client MCP dans un thread à part, pour que le reste du code reste synchrone.

**Serveurs d'outils (les nôtres, aucun serveur externe) :**
- `mcp_tools_mbpp.py` : `run_tests(code, test_list)`, avec un timeout de 10 s et une sortie tronquée à 1 000 caractères.
- `mcp_tools_swebench.py` : `read_file`, `edit_file`, `list_files`, `search_code`, `search_function_or_class_definition_in_code`, `find_references`, `run_tests`, `get_patch`, `run_command`. Chaque outil fait un `docker exec` dans le conteneur de la tâche (`shell`, ligne 63).

**`final_answer` n'est pas un outil MCP :** il est injecté directement dans le sandbox (`executor.py:125-132`). Il enregistre la réponse, et la boucle s'arrête après l'étape (`loop.py:106`).

**Découverte dynamique :** `sandbox.py:23-25`. Au démarrage, `bridge.list_tools()` est appelé et chaque outil devient une fonction Python dans l'enfant (`worker.py:34-45`, `make_tool`). L'appel remonte au parent par le pipe, et le parent appelle le serveur MCP (`sandbox.py:148`, `_call_tool`). Les arguments positionnels sont convertis en arguments nommés d'après le schéma de l'outil.

**Manuel généré :** `manual.py:45` (`build_manual`). Les signatures sont construites à partir des schémas JSON de chaque outil (`signature`, ligne 26, et `JSON_TYPES`), avec leur description. Les règles du sandbox viennent de la config. Brancher un autre serveur MCP change le manuel automatiquement.

**Démonstration :**

```
uv run sandbox --mcp-stdio "python exams/sandbox_tests/simple_mcp_server.py"
>>> print(sandbox_manual)          → add, multiply, echo apparaissent
>>> print(add(2, 3))
```

---

## Q7. Limites de ressources et retours au LLM

| Point | Où | Comment |
|---|---|---|
| Timeout | `sandbox.py:54-120` | Le parent attend avec `poll(remaining)`. Au-delà de la limite, il tue l'enfant et en relance un neuf (`_restart`). Le temps passé dans les outils MCP **ne compte pas** (ligne 96). |
| Sortie partielle | `executor.py:58-83`, `worker.py:29` | Chaque `print` est envoyé au parent au fil de l'eau (`("output", text)`). En cas de timeout, ce qui a déjà été affiché est rendu, avec `timed_out=True`. |
| Mémoire | `worker.py:73-87` | `resource.setrlimit(RLIMIT_AS, taille actuelle + max_memory_mb)`, appliqué **après** nos propres imports. Si l'enfant meurt, on obtient un message explicite et il est relancé (`sandbox.py:79-90`). |

Les messages au LLM, qui ne doit jamais avoir à deviner ce qui s'est passé :

| Cas | Où | Message |
|---|---|---|
| Aucun bloc de code | `extract.py:219` | « No code found in your answer… » |
| Bloc non fermé | `extract.py:169` | « Your code was not closed with ```… » |
| Plusieurs blocs | `extract.py:165` | « Found N code blocks: they were all executed… » |
| Format XML, JSON ou ReAct converti | `extract.py:174-211` | « Your xml/JSON tool was converted to python: … » |
| Réponse entière exécutée comme du Python | `extract.py:213` | message dédié |
| Timeout | `loop.py:24`, `sandbox.py:113` | « Execution timed out: the output below is partial. » + « …was killed, sandbox restarted: variables lost » |
| Sortie tronquée (sandbox) | `executor.py:46-56` | « [output truncated: kept first 10000 characters, N more were dropped] » |
| Sortie tronquée (outils SWE) | `mcp_tools_swebench.py:49` | « [output truncated: showing last/first 10000 of N characters] » |
| Rien d'affiché | `loop.py:28` | « nothing was printed, use print() to see values » |

Tout est assemblé dans `format_observation` (`loop.py:10`).

---

## Q8. Résultat MBPP

**Limites du sujet, et ce que fait l'agent** (`src/agent_mbpp/__main__.py:17-21, 44`) :

| Limite | Sujet | Agent |
|---|---|---|
| Itérations | 10 | 8 |
| Tokens d'entrée | 6 000 | 6 000, avec une marge de 90 % |
| Tokens de sortie | 1 500 | 1 500 |
| Temps | 120 s | arrêt à 105 s |

Le budget est vérifié **avant** chaque appel (`loop.py:70-76`) : on estime le coût de la prochaine requête (nombre de caractères / 4) et on s'arrête proprement si elle risque de dépasser. L'objectif est 4/5.

Run du 2 novembre (après la correction de Podman) : 5/5 validés. Exemple, la tâche 92 : 2 itérations, 1 422 tokens d'entrée.

---

## Q9. 3 étoiles MBPP

Il faut 5/5, une moyenne d'itérations inférieure à 5, et des tokens sous 50 % des limites (moins de 3 000 en entrée et 750 en sortie). En pratique : 2 à 3 itérations et environ 1 400 tokens d'entrée par tâche. C'est atteignable si le quota est disponible.

---

## Q10. Métriques dans `solution.json`

**Où c'est rempli :** `loop.py:87-104`.
- Les tokens d'entrée et de sortie viennent de la réponse de l'API (`completion.result.input_tokens/output_tokens`). On ne retombe sur une estimation (caractères / 4) que si le provider ne les renvoie pas.
- `request_time_ms` est mesuré autour de l'appel HTTP réussi (`client.py:141, 156`).
- `retries` = nombre de requêtes − 1 (`client.py:160`). `api_url` et `model_name` viennent de la cible réellement utilisée (`client.py:162-163`). Avec un fallback, le modèle réellement appelé est donc bien celui qui est enregistré.
- Les totaux sont des **sommes des étapes** (`agent_mbpp/__main__.py:141-143`), donc forcément cohérents. `total_requests` = somme de (retries + 1). `total_time_seconds` est mesuré avec `time.monotonic()` depuis le début de `main`.

**Commande :**

```bash
cd moulinette && uv run moulinette_eval display ../evaluations/mbpp/<date>/<id>/solution.json
```

---

## Q11. Les 4 modifications en direct (le point le plus risqué)

Chaque modification fait 1 ou 2 lignes. Relance une tâche MBPP après chacune (commande en 0.4), puis vérifie `/tmp/sol.json`.

### Modification 1 : marqueur dans le prompt système

`src/agent_mbpp/__main__.py:117`

```python
system_prompt = "[CORRECTION MARKER 42] " + SYSTEM_RULES + "\n" + manual
```

Ce que ça prouve : le `system_prompt` enregistré est exactement la variable envoyée au LLM (`run_agent(client, sandbox, system_prompt, …)`, puis le message système dans `loop.py:62`).

### Modification 2 : marqueur dans la sortie du sandbox

`src/agent_smith/sandbox/sandbox.py:64`, dans `execute` :

```python
self._conn.send("print('SANDBOX_MARKER_42')\n" + code)
```

Ce que ça prouve : `sandbox_output` est la vraie sortie de l'enfant, mise en forme par `format_observation`.

Attention : si à une étape le LLM n'a produit aucun code, le sandbox n'est pas appelé et le marqueur est absent de cette étape. C'est normal, l'observation dit alors « No code found ».

### Modification 3 : marqueur au début du code envoyé au sandbox

`src/agent_smith/agent/loop.py:81`, juste après `extraction = extract_code(text)` :

```python
if extraction.code:
    extraction.code = "# CORRECTOR_CHECK\n" + extraction.code
```

Ce que ça prouve : `extraction.code` est à la fois ce qui est exécuté (ligne 83) et ce qui est enregistré dans `sandbox_input` (ligne 102).

### Modification 4 : faux nom de modèle

`src/agent_smith/agent/loop.py:99`

```python
model_name="correction-model-42",
```

Ce que ça prouve : la métadonnée est enregistrée séparément de l'appel. Le vrai modèle est utilisé dans `client.py:151` (`model=target.model`), donc la tâche est toujours résolue.

### Revenir en arrière

```bash
git checkout src/
```

Ça marche **seulement si les correctifs Podman ont été commités avant** (voir 0.1).

---

## Q12. Anti-triche

### Partie A : `./exams/exam_anticheat.sh --student-path .`

Le script donne 3 avertissements sur 6, tous des faux positifs, à expliquer :

| Avertissement | Explication |
|---|---|
| GitHub URLs | Dans `exams/sandbox_tests/test_network_blocked.py`, le test fourni par l'école, qui vérifie justement que `api.github.com` est **bloqué**. |
| PR/Issue in prompts | `agent_swebench/__main__.py:111` : « Fix this issue in the repository ». « issue » désigne l'énoncé du bug fourni par la tâche. Les autres résultats sont dans la moulinette. |
| SWE-bench dataset access | Uniquement dans `moulinette/` (le correcteur de l'école). Notre code n'importe pas `swebench`. |

Les 3 autres vérifications (requêtes HTTP externes, historique git, bibliothèques d'orchestration interdites) passent.

### Partie B : `system_prompt` et `sandbox_input`

- Le prompt (`agent_swebench/__main__.py:36-66`) est générique, sans aucun indice propre à une tâche. Il **interdit** même explicitement de chercher en ligne ou dans l'historique git (ligne 57).
- Le réseau est bloqué dans le sandbox. `run_command` s'exécute dans le conteneur de la tâche, pas sur l'hôte.

### Partie D : expliquer la stratégie

La méthode est en 5 étapes, écrite dans le prompt (lignes 46-52) :
1. **Localiser** : `search_code` et `search_function_or_class_definition_in_code`, puis `read_file`.
2. **Reproduire** le bug avec `run_command("python -c ...")`.
3. **Corriger** avec `edit_file`, avec un changement minimal.
4. **Vérifier** : relancer le snippet, puis `run_tests()` une fois, parce que c'est lent.
5. **Soumettre** : `final_answer(get_patch())`.

Choix pas évidents à savoir justifier :
- **Le patch est toujours relu depuis le conteneur** (`__main__.py:188`), même si le LLM n'a pas appelé `final_answer`. Le travail déjà fait n'est jamais perdu.
- **`run_tests` ne rend que la section entre `>>>>> Start/End Test Output`, sans la trace `set -x`** (`mcp_tools_swebench.py:297`). C'est l'ablation du benchmark.
- **Code extrait de formats variés** (XML, JSON, ReAct) avec une note au LLM. Les modèles ne respectent pas tous le format demandé.
- **`<end_code>` comme séquence d'arrêt** (`loop.py:44`), pour que le modèle n'invente pas lui-même l'Observation.

---

## Q13. `BENCHMARK_REPORT.md`

**Structure** (titres du fichier) : 1. Setup → 2. Results → 3. Provider reliability → 4. Intermediary metrics → 5. Ablation study → 6. Conclusions → Backing data. Les 6 parties demandées sont présentes.

**Données qui justifient les chiffres :** le dossier `benchmark/` contient `<tâche>__<modèle>__run<N>.json`, avec à côté un `.validation.txt` (verdict de la moulinette) et un `.stderr.log`. Les tableaux sont produits par `scripts/bench_report.py`, et les runs par `scripts/bench.sh`.

**Contrôle sur un exemple (partie B) :** ouvre un JSON de `benchmark/`, montre que `sandbox_input` et `sandbox_output` sont remplis, que les tokens correspondent au tableau et que `task_id` est le bon.

Le texte complet à savoir raconter est en **annexe**.

---

## Q14. 3 étoiles benchmark

Critères : 7 modèles ou plus, **ou** 5 tâches ou plus ; 3 providers ou plus ; 3 métriques ou plus ; 2 ablations ou plus ; des conclusions pertinentes.

Ce que tu as :
- 5 modèles et 3 tâches communes, **plus 3 autres tâches avec Qwen**, soit 6 tâches au total.
- 3 providers (Gemini, Groq, OpenRouter).
- 3 métriques intermédiaires.
- 2 ablations (`run_tests` sur SWE-bench, prompt v0→v3 sur MBPP).

Argument à donner : le critère « 5 tâches ou plus » est rempli avec les 6 tâches Qwen.

---

## Q15. Gestion de Docker

**Où regarder :** `src/agent_smith/swebench/docker_env.py`.
- Le pull utilise `docker_image`, avec `docker.io/` ajouté si le registre manque (lignes 15-20).
- Le démarrage lance `docker run -i --rm --name agent_smith_<pid> <image> cat`, puis attend que `docker inspect` réponde `Running=true` (lignes 42-61).
- **Le mécanisme clé :** `cat` lit l'entrée standard, qui est un pipe tenu par le processus Python. Si l'agent meurt pour n'importe quelle raison, **y compris `kill -9`**, le noyau ferme le pipe, `cat` se termine, le conteneur s'arrête, et `--rm` le supprime. Aucun code n'a besoin de s'exécuter.
- En sortie normale : `stop()` (ligne 76) ferme l'entrée standard, puis lance `docker rm -f` par sécurité.
- **SIGTERM** est transformé en `SystemExit` (`agent_swebench/__main__.py:69, 147`). **SIGINT** (Ctrl+C) provoque `KeyboardInterrupt`. Dans les deux cas, le `finally` (lignes 191-199) ferme le sandbox, le bridge et le conteneur, et **écrit toujours** `solution.json`.
- `make clean` supprime les conteneurs `agent_smith_*` restés d'un crash.

**Démonstration avec `kill -9` :** lance une tâche SWE-bench, attends que `docker ps` montre `agent_smith_…`, fais `kill -9 <pid>`, puis `docker ps | grep sweb.eval` ne renvoie plus rien après une ou deux secondes.

---

## Q16. Résultat SWE-bench

**Limites** (`agent_swebench/__main__.py:24-27`) :

| Limite | Sujet | Agent |
|---|---|---|
| Itérations | 30 | 25 |
| Tokens d'entrée | 300 000 | 300 000 |
| Tokens de sortie | 10 000 | 10 000 |
| Temps | 900 s | arrêt à 840 s |

La tâche s'arrête aussi si le budget de tokens est presque atteint (`loop.py:74`). L'objectif est 2/3.

**Dépendances Docker en plus :** aucune. Les outils n'utilisent que `grep`, `git`, `python` et `bash`, déjà présents dans l'image. `CONTAINER_SETUP` (`mcp_tools_swebench.py:22`) se contente d'activer l'environnement conda `testbed` de l'image avant chaque commande. Rien n'est installé.

Run du 2 novembre, une fois les solutions revalidées sous `podman unshare` : django-11066, sympy-13480 et sympy-14711 sont tous `RESOLVED_FULL`. Ça fait 3/3, en 6, 10 et 9 itérations, avec environ 18 000 à 24 000 tokens d'entrée.

---

## Q17. 3 étoiles SWE-bench

Il faut 3/3, une moyenne d'itérations inférieure à 15, et des tokens sous 50 % (moins de 150 000 en entrée et 5 000 en sortie). Le run du 2 novembre remplit ces conditions : moyenne d'environ 8,3 itérations, moins de 25 000 tokens en entrée et moins de 500 en sortie. Le principal risque est le quota Groq (voir 0.3).

---
---

# Annexe : le benchmark expliqué simplement

## L'idée en une phrase

« J'ai fait tourner mon agent SWE-bench avec 5 modèles de 3 providers gratuits sur les 3 mêmes tâches. J'ai mesuré qui réussit, à quel coût et avec quelle fiabilité. J'ai aussi fait une expérience avant/après sur mon agent. »

Le sujet (section 4.7) demande au minimum 5 modèles, 2 providers et 3 tâches. Tu as 5 modèles, 3 providers (Gemini, Groq, OpenRouter) et 3 tâches, plus 3 tâches bonus avec Qwen.

## Comment les chiffres sont produits (ça prouve qu'ils ne sont pas inventés)

- `scripts/bench.sh` lance l'agent avec un seul modèle sur plusieurs tâches. L'option `--no-fallback` empêche l'agent de passer à un autre modèle en cas d'erreur, pour que chaque run mesure un seul modèle.
- Ce même script appelle ensuite la moulinette officielle (`moulinette_eval validate`) et enregistre le verdict dans un fichier `.validation.txt`.
- `scripts/bench_report.py` lit tous les `solution.json` du dossier `benchmark/` et en calcule les tableaux.
- Les fichiers sont nommés `<tâche>__<modèle>__run<N>.json`. Si un correcteur doute d'un chiffre, tu ouvres le JSON correspondant.

## Section 1 : Setup (le « quoi » et le « pourquoi »)

Les 5 modèles et pourquoi ils ont été choisis :

| Modèle | Provider | Raison du choix |
|---|---|---|
| gemini-3.5-flash-lite | Google | accepte les longues requêtes |
| gemini-3.6-flash | Google | le Gemini le plus rapide |
| qwen3.8-27b | Groq | provider très rapide (0,5 s), meilleur modèle sur MBPP |
| gpt-oss-120b | Groq | le plus gros modèle disponible sur Groq |
| north-mini-code | OpenRouter | modèle spécialisé code, rapide |

Les 3 tâches : sympy-13480, xarray-4629 et sympy-14711.

- Ce sont celles que le sujet conseille pour commencer.
- Elles viennent de 2 dépôts différents.
- La difficulté monte : 13480 est une simple faute de frappe, 14711 demande de modifier un opérateur (`__add__`) d'une classe.

## Section 2 : Résultats (qui gagne ?)

Score sur 3 :

- gemini-3.5-flash-lite : 3/3
- qwen3.8-27b : 3/3, et même 6/6 sur toutes les tâches de l'examen (sympy, xarray, django, scikit-learn)
- gemini-3.6-flash : 2/3
- gpt-oss-120b : 1/3
- north-mini-code : 0/3

Pourquoi les échecs, en langage simple :

- **north-mini-code** ne répond jamais dans le format attendu (bloc ```python). Il utilise son propre format, que l'extracteur ne reconnaît pas. Résultat : 0 code exécuté sur 75 étapes.
- **gpt-oss-120b** essaie d'appeler un outil interne à lui (`container.exec`), que Groq refuse (erreur 400). Une autre fois, sa requête dépasse 8 000 tokens, la limite par minute de Groq (erreur 413).
- **gemini-3.6-flash** sur 14711 : il tourne en rond pendant 22 étapes sans modifier le fichier, puis son quota du jour est épuisé (erreur 429).

👉 À retenir : les échecs viennent surtout du format de réponse et des limites des providers, pas de l'intelligence des modèles.

## Section 3 : Fiabilité des providers

Ce qu'il faut retenir :

- **Groq** est très rapide (0,5 s par requête) mais limité : 8 000 tokens par minute et 200 000 tokens par jour, soit environ 5 tâches par jour. D'où les nombreux retries de Qwen (75) : le client attend, puis réessaie.
- **Gemini** est lent (environ 20 s par requête pour flash-lite) mais n'a eu aucun retry ni aucune erreur. En revanche, gemini-3.6-flash n'a droit qu'à 20 requêtes par jour, soit 1 ou 2 tâches.
- **OpenRouter** accepte 50 requêtes gratuites par jour, partagées entre tous ses modèles.
- Les providers changent avec le temps : des modèles ont disparu (erreur 404) et la latence varie d'un jour à l'autre (19,7 s puis 8,5 s).

**Fallback (la démo bonus) :** avant `--no-fallback`, quand Qwen atteignait la limite de Groq, l'agent passait seul à Cohere. Deux tâches ont quand même réussi, parce que l'agent récupère toujours le patch depuis le conteneur à la fin. Le travail déjà fait n'est donc jamais perdu.

## Section 4 : Métriques intermédiaires

Le sujet en demande au moins 2. Tu en as 3 :

1. **À quelle étape l'agent lit pour la première fois le fichier qu'il corrigera** (efficacité d'exploration). Réponse : très vite, entre l'étape 1 et 6, et entre 1 et 3 dans la plupart des cas. Les outils de recherche fonctionnent.
2. **À quelle étape il modifie ce fichier pour la première fois.** Exemple parlant : sur 14711, Gemini lit le fichier à l'étape 6 mais ne le modifie qu'à l'étape 20, parce qu'il relit sans arrêt les mêmes lignes.
3. **Le délai entre « les tests passent » et `final_answer`** (discipline de soumission, l'idéal est 0). En v1, c'est « jamais » partout. C'est ce problème qui a mené à l'ablation.

## Section 5 : Ablation (la partie la plus intéressante à raconter)

**Le problème découvert :** en v1, `run_tests` renvoyait les 10 000 derniers caractères de la sortie. Or le script d'évaluation affiche d'abord les résultats des tests, puis une énorme trace de debug (`set -x`), soit 356 000 caractères au total. Les 10 000 derniers ne contenaient que la trace. Le modèle ne voyait donc jamais si ses tests passaient.

**La correction (v2) :** on ne renvoie que la partie entre les marqueurs `>>>>> Start Test Output` et `>>>>> End Test Output`. On passe à 3 500 caractères, qui se terminent par « 44 passed ».

**Le résultat (même modèle, mêmes tâches) :**

- toujours 3/3 ;
- −33 % de tokens d'entrée (219 k → 146 k) ;
- sur la tâche la plus dure : 5 itérations de moins et −41 % de tokens. Le modèle voit les tests passer et soumet 2 étapes plus tard, au lieu d'épuiser tout son budget.

**Honnêteté à mentionner :** sur 13480, la v2 coûte 3 itérations de plus, parce que le modèle lance maintenant les tests avant de soumettre. De plus, il n'y a qu'un run par configuration, donc une part de hasard est possible.

Il y a aussi une **ablation sur MBPP**. Le prompt passe de v0 à v3 et le score monte de 0/1 à 19/20. Le seul échec (tâche 461) vient d'une solution de référence fausse dans le dataset.

## Section 6 : Conclusions (ce que tu dois savoir répondre)

- **Modèle par défaut pour SWE-bench : qwen3.8-27b**, à cause des tokens d'entrée. Sur les 3 tâches communes, il en consomme 99 846, contre 219 202 pour gemini-3.5-flash-lite en v1 et 146 111 en v2. Sa tâche la plus chère monte à 37 341 tokens, soit 12 % de la limite de 300 000. Gemini, lui, est monté à 155 923 sur sympy-14711 (52 %), au-dessus des 50 % demandés pour les 3 étoiles. Qwen a aussi le meilleur score (6/6), moins d'itérations sur la tâche dure (16 contre 25) et il est 40 fois plus rapide. Son point faible, c'est le provider : le quota Groq de 200 000 tokens par jour ne couvre qu'environ 5 tâches, et la limite de 8 000 tokens par requête a coupé 2 runs.
- **Deuxième choix : gemini-3.5-flash-lite**, les jours où le quota Groq est épuisé. Il fait 3/3 en v1 comme en v2, sans aucune erreur ni retry, mais il consomme plus de tokens et il est lent (8 à 20 s par requête), tout en restant sous les 900 s.
- **Pour MBPP : qwen3.8-27b.** Il fait 19/20 avec environ 1 400 tokens par tâche, alors que la limite est de 6 000.
- **Modèles écartés :** north-mini-code (mauvais format), gpt-oss-120b (outils internes refusés et requêtes trop grosses), gemini-3.6-flash (quota trop faible).
- **Leçon générale :** le principal risque, ce sont les quotas gratuits, pas les modèles. 5 des 6 erreurs de providers sont des quotas ou des limites de taille.

## Questions probables du correcteur et réponses courtes

- **« Pourquoi ces 3 tâches ? »** Ce sont celles conseillées par le sujet, elles couvrent 2 dépôts et une difficulté croissante.
- **« Pourquoi `--no-fallback` ? »** Pour qu'un run mesure un seul modèle. Sinon, on ne sait pas quel modèle a réellement résolu la tâche.
- **« Qu'est-ce qu'une ablation ? »** On change une seule chose (ici la sortie de `run_tests`) en gardant le même modèle et les mêmes tâches, et on compare avant et après.
- **« Comment tu prouves que les chiffres sont réels ? »** Chaque ligne correspond à un `solution.json` du dossier `benchmark/`, validé par la moulinette (fichier `.validation.txt`), et les tableaux sont générés par un script.
- **« C'est quoi un retry ? »** Une requête refusée par le provider (limite de débit, timeout) que le client renvoie après une attente. Le champ `retries` de chaque étape les compte.
- **« Pourquoi Qwen et pas Gemini, qui n'a aucune erreur ? »** Parce qu'il consomme 2 fois moins de tokens d'entrée (99 846 contre 219 202 sur les 3 tâches), et que sa pire tâche reste à 12 % de la limite, contre 52 % pour Gemini. Les erreurs de Qwen viennent des limites de Groq, pas du modèle. Gemini reste le plan B quand le quota Groq est épuisé.

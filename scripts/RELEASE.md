# Livraison locale, sans publication

Python 3.9+ et Git suffisent : il n'y a plus rien à compiler (depuis 2.0.0, le
programme est le dossier `py/`). Aucun CLI Copilot n'est nécessaire pour
construire.

```sh
python3 scripts/package_release.py            # Mac
python .\scripts\package_release.py           # Windows
```

Le script :

1. prend l'instantané des fichiers suivis par Git (jamais la mémoire, l'état,
   les caches, `__pycache__`) ;
2. vérifie que la version de `.github/plugin/plugin.json` est la seule annoncée,
   et qu'elle correspond à l'étiquette quand la chaîne tourne sur une étiquette ;
3. vérifie que `hooks/copilot.json` est celui qu'écrit `outils/genere_hooks.py` ;
4. extrait l'instantané à part et y rejoue toute la suite de tests, avec un
   `HOME`, un `USERPROFILE` et un `COPILOT_HOME` jetables, sans variable de
   plugin héritée ;
5. interroge le programme extrait (`version`) et compare son identité —
   version + empreinte de `py/` — à l'empreinte calculée séparément par le
   script ; le lanceur `sh` est essayé de même hors Windows ;
6. refuse si une source a changé pendant la construction.

La sortie est `release/harnais-<version>.zip` (une seule archive pour Windows et
macOS) avec son empreinte `.zip.sha256`, `release-manifest.json` (version,
empreinte, Python, tests, empreintes des fichiers) et `SHA256SUMS`. ZIP sans
compression, ordre lexical, permissions fixes, date fixée par
`SOURCE_DATE_EPOCH` (défaut 1980-01-01) : à contenu identique, archive identique.

Les fins de ligne sont figées par `.gitattributes` (LF, CRLF pour le `.cmd`) :
sans cela un checkout Windows changerait l'empreinte de `py/` et casserait le
lanceur `sh`.

La chaîne GitHub (`paquet.yml`) emploie le même script sous Windows et ne fait
que conserver l'archive comme artifact. Elle ne publie pas de release.

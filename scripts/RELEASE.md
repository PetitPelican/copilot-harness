# Livraison locale, sans publication

Python 3.11+, Git et Rust sont nécessaires. Aucun CLI Copilot n'est nécessaire
pour construire. Lancer depuis ce checkout, après création de `install.ps1`.
Les tests utilisent un HOME et des dossiers de travail jetables strictement
dans la sortie de livraison, sans lire les plugins installés du poste.
Les dépendances Cargo doivent déjà être disponibles :

```powershell
python .\scripts\package_release.py --target x86_64-pc-windows-gnu
```

Sur Windows avec Visual Studio, `x86_64-pc-windows-msvc` est également admise.
Sur macOS Apple Silicon :

```sh
python3 scripts/package_release.py --target aarch64-apple-darwin
```

Le script teste puis construit avec `--locked --offline`, vérifie les versions
du plugin, de Cargo et du lockfile, et interroge le programme construit.
`--online` autorise explicitement Cargo à télécharger les dépendances manquantes ;
le mode normal n'accède pas au réseau. Pas de fetch, push, publication ou dépôt créé.
Il refuse les autres plateformes et la compilation croisée non vérifiable.
Rappels est construit et vérifié uniquement sur macOS.

La sortie est `release/harnais-0.15.0-windows-x86_64.zip` (ou `darwin-arm64`),
avec une empreinte `.zip.sha256`. `--output` accepte uniquement un sous-dossier
de ce checkout. L'archive contient le plugin directement à la racine,
`install.ps1`, les sources nécessaires à sa reconstruction, les lanceurs,
le seul programme fraîchement construit et son identité. Ni binaires préexistants
d'autres plateformes, ni `.git`, mémoire personnelle, état, caches, verdicts,
corpus privé de contrôles ou atelier utilisateur ne sont copiés. Seuls les quatre
bancs synthétiques `portable-smoke.ps1`, `install-windows.ps1` et
`hook-contract.ps1` et `cto-start.ps1` sont inclus pour vérifier la copie distribuée.
Le dernier lance deux prompts synthétiques via Copilot : il nécessite un accès
Copilot actif et mesure le briefing avec ses deux hooks seuls, pas la conversation
d'accueil complète ni les gardes de fin de tour.
Les fichiers du plugin
et de Rust viennent de l'index Git, dans leur contenu courant ; ajouter à Git
les nouveaux fichiers du plugin avant de construire. Le script de livraison,
son mode d'emploi, ses tests et l'installateur sont inclus même avant leur premier commit.
Depuis une archive extraite sans `.git`, la liste des sources vient du manifeste
de livraison, filtrée par la même liste autorisée ; la reconstruction reste locale.

Sous Windows GNU : CRT et bibliothèques MinGW statiques, timestamp PE neutralisé.
Sous MSVC : CRT statique et `/Brepro`. Les imports PE sont analysés ; toute DLL
hors système Windows fait échouer la livraison. Le programme est ensuite exécuté
avec un PATH limité aux dossiers système, sans les DLL du compilateur.
La cible Windows suppose Windows 10/11 x86_64 (UCRT et DLL système présents).

`release-manifest.json` garde les versions d'outillage, flags, imports DLL,
identité et empreintes des fichiers. L'identité est l'empreinte du contenu des
sources effectives, y compris les changements non commités, pas une affirmation
que HEAD a été construit. `SHA256SUMS` couvre les fichiers et le manifeste
(pas lui-même).

ZIP sans compression : ordre lexical, permissions fixes, aucune heure ou chemin
personnel injecté dans les métadonnées. `SOURCE_DATE_EPOCH` fixe la date des entrées
(défaut : 1980-01-01 UTC). À contenu et outillage identiques, l'assemblage est
identique ; les versions Rust/Swift/SDK restent des entrées de compilation,
et la reproductibilité bit-à-bit entre toolchains différentes n'est pas promise.
Toute source modifiée pendant la construction fait refuser l'archive.

La chaîne GitHub emploie le même script sur chaque plateforme native et ne fait
que conserver les archives comme artifacts. Elle ne publie pas de release.

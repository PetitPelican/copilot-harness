# -*- coding: utf-8 -*-
"""ÉCRIT `hooks/copilot.json` — on ne l'édite jamais à la main.

Chaque hook Copilot porte DEUX commandes, une par shell (`bash`, `powershell`),
et chacune doit retrouver le paquet, trouver Python, puis le dire à voix haute
quand l'un des deux manque. Sept hooks × deux shells, à la main, divergent :
une correction faite dans l'un oublie les treize autres. Ici, un gabarit par
shell, et la table des hooks.

    python3 outils/genere_hooks.py          # réécrit le fichier
    python3 outils/genere_hooks.py --verifie  # code 1 s'il diffère (contrôles)

LE BASH passe par `bin/harnais`, qui porte la recherche de Python.
LE POWERSHELL la porte EN LIGNE, à dessein :
  · appeler `harnais.cmd` coûterait un cmd.exe de plus à chaque hook, et cmd
    lit mal un chemin à parenthèses ;
  · un script `.ps1` dépend de la stratégie d'exécution de la machine
    (Restricted par défaut sur un poste Windows) : un hook bloqué par elle ne
    part pas, et ne le dit pas. Une commande en ligne n'y est pas soumise.
Tout reste en ASCII : PowerShell 5.1 relit ce texte dans la page de code du
poste, et un accent y devient autre chose.
"""
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
FICHIER = os.path.join(ICI, "..", "hooks", "copilot.json")
REPARE = "Remettre le paquet en etat : copilot plugin update harnais@atelier-copilot"

# (événement, filtre d'outil, sous-commande, code si rien ne part, délai, ce qui est perdu)
HOOKS = [
    ("SessionStart", None, "briefing", 1, 15,
     "aucun briefing d'entree n'est servi ce tour."),
    ("userPromptTransformed", None, "briefing", 1, 15,
     "aucun briefing d'entree n'est servi ce tour."),
    ("PreToolUse", "Bash", "mind-guard", 2, 20,
     "le garde de commit ne peut pas s'executer, je REFUSE la commande plutot que de la laisser passer."),
    ("PreToolUse", "Edit|Write", "perimetre", 2, 20,
     "la garde de perimetre ne peut pas s'executer, je REFUSE l'ecriture plutot que de la laisser passer."),
    ("PreToolUse", "Bash", "production", 2, 20,
     "le garde de la Production ne peut pas s'executer, je REFUSE la commande plutot que de la laisser passer."),
    ("PreToolUse", "Edit|Write|Bash", "consignes", 2, 20,
     "le verrou des consignes ne peut pas s'executer, je REFUSE l'outil plutot que de le laisser ecrire un fichier de consignes."),
    ("PreToolUse", "Bash|Read|Grep", "coffre", 2, 20,
     "le garde du coffre ne peut pas s'executer, je REFUSE l'outil plutot que de le laisser afficher un secret."),
    # `apres-bash` : le journal, la lecture des faits ET le temoin du coffre, en un seul
    # processus ; `apres-lecture` : la lecture des faits ET le temoin, apres un Read ou un Grep.
    # Le nom de l'outil de sous-agents : `Task` (ramene de `task` par `hote`) ; `task` en filet,
    # au cas ou l'hote filtre sur le nom brut (pas mesure).
    ("PreToolUse", "Task|task", "sous-agent", 2, 10,
     "la garde des sous-agents ne peut pas s'executer, je REFUSE le lancement plutot que de le laisser passer."),
    ("PostToolUse", "Bash", "apres-bash", 1, 20,
     "ce commit n'entre pas au journal, cette lecture n'est pas comptee dans brain/poids.json, "
     "et une cle passee en clair ne serait pas signalee."),
    ("PostToolUse", "Read|Grep", "apres-lecture", 1, 10,
     "cette lecture n'est pas comptee dans brain/poids.json, et une cle passee en clair ne serait pas signalee."),
    ("Stop", None, "attente", 1, 40,
     "la fin de tour n'est pas gardee : rien ne remonte a @user."),
]

BASH = ('r=""; for c in "${COPILOT_PLUGIN_ROOT:-}" "${PLUGIN_ROOT:-}" '
        '"${COPILOT_HOME:-${HOME:-$USERPROFILE}/.copilot}/installed-plugins/atelier-copilot/harnais"; '
        'do if [ -n "$c" ] && [ -f "$c/bin/harnais" ]; then r="$c"; break; fi; done; '
        'if [ -n "$r" ]; then COPILOT_PLUGIN_ROOT="$r"; export COPILOT_PLUGIN_ROOT; '
        'exec sh "$r/bin/harnais" @SOUS@; fi; '
        'echo "harnais : le paquet est introuvable - @PERTE@ @REPARE@" >&2; exit @CODE@')

POWERSHELL = (
    "$r=@($env:COPILOT_PLUGIN_ROOT,$env:PLUGIN_ROOT)|Where-Object{$_ -and (Test-Path -LiteralPath (Join-Path $_ 'py\\main.py'))}|Select-Object -First 1;"
    "$h=if($env:COPILOT_HOME){$env:COPILOT_HOME}else{Join-Path $env:USERPROFILE '.copilot'};"
    "if(-not $r){$r=Join-Path $h 'installed-plugins\\atelier-copilot\\harnais'};"
    "$env:COPILOT_PLUGIN_ROOT=$r;$m=Join-Path $r 'py\\main.py';"
    "$d=if($env:COPILOT_PLUGIN_DATA){$env:COPILOT_PLUGIN_DATA}elseif($env:PLUGIN_DATA){$env:PLUGIN_DATA}else{Join-Path $h 'plugin-data\\atelier-copilot\\harnais'};"
    "$p=@();"
    "if($env:HARNAIS_PYTHON){if(Test-Path -LiteralPath $env:HARNAIS_PYTHON){$p=@($env:HARNAIS_PYTHON)}}"
    "else{$c=Get-Command py -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1;"
    "if($c){$p=@($c.Source,'-3')}"
    "else{$c=Get-Command python,python3 -CommandType Application -ErrorAction SilentlyContinue|Where-Object{$_.Source -notlike '*\\WindowsApps\\*'}|Select-Object -First 1;"
    "if($c){$p=@($c.Source)}}};"
    "if((Test-Path -LiteralPath $m) -and $p.Count){$a=@($p|Select-Object -Skip 1)+@('-S','-E','-X',\"pycache_prefix=$d\\pycache\",$m,'@SOUS@');"
    "$x=$p[0];& $x @a;exit $LASTEXITCODE};"
    "$w=if(Test-Path -LiteralPath $m){\"aucun Python 3.9 ou plus n'est installe (winget install Python.Python.3.13, ou python.org en cochant Add to PATH ; le faux python du Microsoft Store ne compte pas)\"}"
    "else{\"le programme du paquet manque dans $r\\py - @REPARE@\"};"
    "[Console]::Error.WriteLine(\"harnais : $w - @PERTE@\");exit @CODE@")


def remplis(gabarit, sous, code, perte):
    return (gabarit.replace("@SOUS@", sous).replace("@CODE@", str(code))
            .replace("@PERTE@", perte).replace("@REPARE@", REPARE))


def contenu():
    hooks = {}
    for evt, filtre, sous, code, delai, perte in HOOKS:
        h = {"type": "command"}
        if filtre:
            h["matcher"] = filtre
        h["bash"] = remplis(BASH, sous, code, perte)
        h["powershell"] = remplis(POWERSHELL, sous, code, perte)
        h["timeoutSec"] = delai
        hooks.setdefault(evt, []).append(h)
    texte = json.dumps({"version": 1, "hooks": hooks}, indent=2, ensure_ascii=True) + "\n"
    assert texte.isascii()
    return texte


def main(argv):
    t = contenu()
    if "--verifie" in argv:
        try:
            with open(FICHIER, encoding="utf-8") as f:
                actuel = f.read()
        except OSError:
            actuel = ""
        if actuel != t:
            sys.stderr.write("hooks/copilot.json differe de son generateur : "
                             "python3 outils/genere_hooks.py\n")
            return 1
        return 0
    with open(FICHIER, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

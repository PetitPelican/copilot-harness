# -*- coding: utf-8 -*-
"""UNE ÉQUIPE EN MINIATURE, dans la forme « un dossier par agent » (14/10/2026).

    X/                      dépôt de la MÉMOIRE (ignore agents/*/code*/)
      fact/base.md          avec un `cap:`
      shared/
      agents/OPS/           state.md · todo.md · AGENTS.md
        code/               checkout PRINCIPAL du dépôt du code
      agents/PO/            state.md · todo.md · AGENTS.md
        code/               worktree du même dépôt, branche `po`

Partagé par les essais de chaque module : une seule construction, la même
partout — sinon chaque fichier de tests épingle sa propre idée de la forme.
COPILOT : le fichier de consignes d'un agent est `AGENTS.md` (Claude : `CLAUDE.md`).
"""
import os
import subprocess

# Daté du JOUR : un `maj:` figé fait mordre la garde « état pas à jour » avant
# celle qu'un essai éprouve, deux jours plus tard (mesuré le 16/10/2026).
ETAT = "---\nmaj: %s\nsante: vert\njalon: banc\n---\n" % __import__("datetime").date.today().isoformat()
BASE = "---\ncap: un banc\n---\n# Base\n"


def _git(d, *a):
    subprocess.run(["git", "-c", "commit.gpgsign=false"] + list(a), cwd=d, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   env=dict(os.environ, GIT_AUTHOR_NAME="banc", GIT_AUTHOR_EMAIL="banc@x",
                            GIT_COMMITTER_NAME="banc", GIT_COMMITTER_EMAIL="banc@x"))


def _ecris(p, texte):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as h:
        h.write(texte)


def construis(x, agents=("OPS", "PO"), code=True):
    """Construit l'équipe dans le dossier `x` (existant, vide). Rend `x`."""
    j = os.path.join
    _git(x, "init", "-q", "-b", "main")
    _ecris(j(x, ".gitignore"), "agents/*/code*/\n")
    _ecris(j(x, "fact", "base.md"), BASE)
    os.makedirs(j(x, "shared"), exist_ok=True)
    for a in agents:
        _ecris(j(x, "agents", a, "state.md"), ETAT)
        _ecris(j(x, "agents", a, "todo.md"), "# Ce qui attend\n")
        _ecris(j(x, "agents", a, "AGENTS.md"), "# %s\n" % a)
    _git(x, "add", "-A")
    _git(x, "commit", "-q", "-m", "memoire")
    if code:
        principal = j(x, "agents", agents[0], "code")
        os.makedirs(principal)
        _git(principal, "init", "-q", "-b", "main")
        _ecris(j(principal, "apps", "app.ts"), "export {}\n")
        _git(principal, "add", "-A")
        _git(principal, "commit", "-q", "-m", "code")
        for a in agents[1:]:
            _git(principal, "worktree", "add", "-q", "-b", a.lower(), j(x, "agents", a, "code"))
    return x

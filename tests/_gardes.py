# -*- coding: utf-8 -*-
"""Aides communes aux tests des gardes portées de Claude (production, coffre,
sous-agents, consignes) : une équipe jetable, les charges au format Copilot, le
lanceur `py/main.py` lancé comme un hook le lance."""
import contextlib
import io
import json
import os
import subprocess
import sys

from _isole import Isole, RACINE_DEPOT, git, ecris, lis  # noqa: F401

MAIN = os.path.join(RACINE_DEPOT, "py", "main.py")


def muet(f, *a):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return f(*a)


def sortie(f, *a):
    """(valeur rendue, sortie standard, sortie d'erreur)."""
    o, e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        r = f(*a)
    return r, o.getvalue(), e.getvalue()


def charge_camel(outil, args, cwd, **plus):
    """La charge telle que Copilot l'envoie en camelCase : `toolName`, `toolArgs`."""
    c = {"sessionId": "s-essai", "cwd": cwd, "toolName": outil, "toolArgs": args}
    c.update(plus)
    return c


def charge_pascal(outil, args, cwd, **plus):
    """La charge PascalCase : `tool_name`, `tool_input`."""
    c = {"session_id": "s-essai", "cwd": cwd, "tool_name": outil, "tool_input": args}
    c.update(plus)
    return c


def lance(sous, entree, env=None, args=(), cwd=None):
    """`python main.py <sous> [args]` avec `entree` sur l'entrée standard."""
    if not isinstance(entree, (bytes, str)):
        entree = json.dumps(entree)
    if isinstance(entree, str):
        entree = entree.encode("utf-8")
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, MAIN, sous] + list(args), input=entree, cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e, timeout=60)


def refus(o):
    """La décision de refus d'un hook (racine de l'objet), ou None si muet."""
    t = o.stdout.decode("utf-8")
    if not t.strip():
        return None
    return json.loads(t)


class Poste(Isole):
    """Un poste jetable avec une équipe : `self.x` (dépôt, branche main, un commit)."""

    def equipe(self, noms="OPS,PO", entete_regles=None):
        x = os.path.realpath(self.dossier("equipe"))
        git(x, "init", "-q", "-b", "main")
        r = muet(__import__("adopte").main, [x, "--equipe", noms, "--go"])
        assert r == 0, "adopte a échoué"
        if entete_regles:
            # Une équipe naît « un dossier par agent » (`fact/` à la racine), et ses
            # règles portent déjà un en-tête : on le REMPLACE, on n'en empile pas un second.
            f = self.regles(x)
            t = lis(f)
            if t.startswith("---"):
                fin = t.find("\n---", 3)
                t = t[fin + 4:].lstrip("\n") if fin >= 0 else t
            ecris(f, "---\n%s\n---\n\n" % entete_regles + t)
        git(x, "add", "-A")
        git(x, "commit", "-qm", "equipe")
        return x

    def regles(self, x):
        f = os.path.join(x, "fact", "rules.md")
        return f if os.path.isfile(f) else os.path.join(x, "brain", "fact", "rules.md")

    def agent_dir(self, x, nom):
        return os.path.join(x, "agents", nom)

    def journal_session(self, sid, *noms):
        """Le journal de session de Copilot, avec un agent choisi dans le menu."""
        p = os.path.join(os.environ["COPILOT_HOME"], "session-state", sid, "events.jsonl")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        lignes = [{"type": "subagent.selected", "data": {"agentName": n}} for n in noms]
        ecris(p, "".join(json.dumps(v) + "\n" for v in lignes))
        return p

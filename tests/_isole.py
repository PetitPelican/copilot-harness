# -*- coding: utf-8 -*-
"""Socle commun des tests portés de Rust : un poste jetable et des aides.

Chaque test tourne avec un HOME / USERPROFILE / COPILOT_HOME / COPILOT_PLUGIN_DATA
jetables, COPILOT_PLUGIN_ROOT sur ce dépôt, et sans COPILOT_PROJECT_DIR /
HARNAIS_JUGE / HARNAIS_PROFIL. Le cache de `memoire.git` est vidé.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

RACINE_DEPOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE_DEPOT, "py"))

import memoire  # noqa: E402


def _env_git():
    e = dict(os.environ)
    e.update({"GIT_CONFIG_NOSYSTEM": "1",
              "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return e


def git(d, *a):
    """git avec une identité jetable ; échoue le test si git échoue. Rend la sortie."""
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false"] + list(a), cwd=str(d), env=_env_git(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0, "git %r : %s" % (a, r.stderr.decode("utf-8", "replace"))
    return r.stdout.decode("utf-8", "replace")


def ecris(p, t):
    """Écrit `t` dans `p`, en créant les dossiers."""
    p = str(p)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def lis(p):
    with open(str(p), encoding="utf-8", newline="") as f:
        return f.read()


class Isole(unittest.TestCase):
    """Base des tests : environnement jetable, `memoire._VUS` vidé."""

    def setUp(self):
        memoire._VUS.clear()
        self.poste = tempfile.mkdtemp(prefix="poste-")
        self.addCleanup(shutil.rmtree, self.poste, True)
        env = {
            "HOME": self.poste, "USERPROFILE": self.poste,
            "COPILOT_HOME": os.path.join(self.poste, ".copilot"),
            "COPILOT_PLUGIN_DATA": os.path.join(self.poste, "plugin-data"),
            "COPILOT_PLUGIN_ROOT": RACINE_DEPOT,
        }
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        for k in ("COPILOT_PROJECT_DIR", "HARNAIS_JUGE", "HARNAIS_PROFIL"):
            os.environ.pop(k, None)

    def dossier(self, nom="d"):
        """Un dossier jetable, vide."""
        d = tempfile.mkdtemp(prefix="essai-%s-" % nom)
        self.addCleanup(shutil.rmtree, d, True)
        return d

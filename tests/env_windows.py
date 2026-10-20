# -*- coding: utf-8 -*-
"""Ce qu'un environnement RÉDUIT doit garder sous Windows. Sans `SYSTEMROOT`, un
Python lancé par un essai meurt avant la première ligne (« _Py_HashRandomization_Init:
failed to get random numbers ») — mesuré par la CI Windows le 16/10/2026."""
import os

GARDES = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC", "USERPROFILE",
          "PROGRAMDATA", "LOCALAPPDATA", "APPDATA")


def essentiel():
    if os.name != "nt":
        return {}
    return {k: os.environ[k] for k in GARDES if k in os.environ}

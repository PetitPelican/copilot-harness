# -*- coding: utf-8 -*-
"""LES PORTES DU PAQUET : les hooks, le lanceur, et ce qu'ils disent quand rien ne part."""
import json
import os
import subprocess
import sys
import unittest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(RACINE, "outils"))

import genere_hooks  # noqa: E402


# Les hooks qui REFUSENT quand le paquet ou Python manque : un garde absent ne laisse pas passer.
GARDES_FERMEES = ("mind-guard", "perimetre", "production", "coffre", "sous-agent",
                   "consignes")


def hooks():
    with open(os.path.join(RACINE, "hooks", "copilot.json"), encoding="utf-8") as f:
        return json.load(f)["hooks"]


class Essais(unittest.TestCase):

    def test_le_fichier_des_hooks_est_celui_du_generateur(self):
        self.assertEqual(genere_hooks.main(["--verifie"]), 0,
                         "hooks/copilot.json a été retouché à la main")

    def test_chaque_hook_appelle_sa_sous_commande_dans_les_deux_shells(self):
        # (événement, filtre, sous-commande), dans l'ordre du fichier : plusieurs gardes
        # partagent un filtre, et l'ordre est celui où l'hôte les lance.
        attendu = [("SessionStart", None, "briefing"), ("userPromptTransformed", None, "briefing"),
                   ("PreToolUse", "Bash", "mind-guard"), ("PreToolUse", "Edit|Write", "perimetre"),
                   ("PreToolUse", "Bash", "production"), ("PreToolUse", "Edit|Write|Bash", "consignes"),
                   ("PreToolUse", "Bash|Read|Grep", "coffre"),
                   ("PreToolUse", "Task|task", "sous-agent"),
                   ("PostToolUse", "Bash", "apres-bash"), ("PostToolUse", "Read|Grep", "apres-lecture"),
                   ("Stop", None, "attente")]
        vu = []
        for evt, liste in hooks().items():
            for h in liste:
                sous = None
                for e, m, s_ in attendu:
                    if (e, m) == (evt, h.get("matcher")) and 'exec sh "$r/bin/harnais" %s;' % s_ in h["bash"]:
                        sous = s_
                self.assertIsNotNone(sous, "hook inattendu : %s %s" % (evt, h.get("matcher")))
                vu.append((evt, h.get("matcher"), sous))
                self.assertIn('exec sh "$r/bin/harnais" %s;' % sous, h["bash"])
                self.assertIn(",$m,'%s');" % sous, h["powershell"])
                self.assertTrue(h["powershell"].isascii())
                # Un garde qui ne part pas REFUSE ; les autres le disent sans bloquer.
                code = 2 if sous in GARDES_FERMEES else 1
                self.assertTrue(h["bash"].endswith("exit %d" % code), h["bash"][-40:])
                self.assertTrue(h["powershell"].endswith("exit %d" % code))
        self.assertEqual(sorted(vu, key=repr), sorted(attendu, key=repr), "un hook manque ou est en trop")
        # TÉMOIN : le faux Python du Store est écarté, `py` ne l'est pas.
        ps = hooks()["Stop"][0]["powershell"]
        self.assertIn("-notlike '*\\WindowsApps\\*'", ps)
        self.assertIn("Get-Command py -CommandType Application -ErrorAction SilentlyContinue|Select-Object", ps)

    @unittest.skipIf(os.name == "nt", "le lanceur sh se lance sous macOS ; Windows a son .cmd")
    def test_sans_python_le_lanceur_le_dit_et_les_gardes_refusent(self):
        env = dict(os.environ, HARNAIS_PYTHON="/n/existe/pas")
        for sous, code in (("perimetre", 2), ("mind-guard", 2), ("production", 2),
                           ("coffre", 2), ("sous-agent", 2), ("consignes", 2),
                           ("briefing", 1), ("attente", 1)):
            p = subprocess.run(["sh", os.path.join(RACINE, "bin", "harnais"), sous],
                               input=b"{}", capture_output=True, env=env)
            self.assertEqual(p.returncode, code, sous)
            self.assertIn("Python", p.stderr.decode("utf-8"))
        # TÉMOIN : avec un Python, le même lanceur répond.
        env["HARNAIS_PYTHON"] = sys.executable
        p = subprocess.run(["sh", os.path.join(RACINE, "bin", "harnais"), "version"],
                           capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertRegex(p.stdout.decode(), r"^\S+ [0-9a-f]{12}\n$")

    def test_le_lanceur_windows_est_en_ascii_et_en_crlf(self):
        with open(os.path.join(RACINE, "bin", "harnais.cmd"), "rb") as f:
            b = f.read()
        self.assertTrue(b.isascii())
        self.assertEqual(b.count(b"\n"), b.count(b"\r\n"), "cmd lit mal les sauts de ligne nus")
        self.assertIn(b'findstr /v /i "WindowsApps"', b)


if __name__ == "__main__":
    unittest.main()

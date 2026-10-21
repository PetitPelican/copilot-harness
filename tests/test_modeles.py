# -*- coding: utf-8 -*-
"""LES MODÈLES DE L'ATELIER COPILOT (21/10/2026) — l'agent principal sur Sol, tout
délégué sur Luna, raisonnement élevé ; et les listes de distribution des
contrôles Windows, qui doivent suivre celle de l'installeur."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(RACINE, "py"))
import copilot  # noqa: E402
import experts  # noqa: E402
import relecture  # noqa: E402


class Modeles(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        os.environ.pop("HARNAIS_MODELE_JUGE", None)

    def test_un_profil_genere_porte_sol_en_raisonnement_eleve(self):
        """Le profil que l'app lit pour l'agent principal. Le témoin : l'en-tête
        reste un en-tête (fermé), et le nom de l'agent y est toujours."""
        p = os.path.join(self.d, "p")
        os.makedirs(p)
        r = subprocess.run([sys.executable, os.path.join(RACINE, "py", "main.py"), "adopte", p,
                            "--equipe", "OPS,PO", "--modeles", "ops,po", "--go"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stderr)
        for n in ("ops", "po"):
            with open(os.path.join(p, ".github", "agents", n + ".agent.md"), encoding="utf-8") as h:
                t = h.read()
            entete = t.split("---\n")[1]
            self.assertIn("name: %s\n" % n, entete)
            self.assertIn("model: gpt-6.1-sol\n", entete)
            self.assertIn("reasoning-effort: high\n", entete)

    def _commande(self, appel):
        vu = {}

        def faux_run(c, **k):
            vu["c"] = c
            return subprocess.CompletedProcess(c, 1, b"", b"")
        with mock.patch.object(copilot, "executable", return_value="copilot"), \
                mock.patch("subprocess.run", side_effect=faux_run):
            appel()
        return vu["c"]

    def test_les_juges_prennent_luna_en_raisonnement_eleve(self):
        for appel in (lambda: relecture.juge("invite"), lambda: experts.juge("invite")):
            c = self._commande(appel)
            i = c.index("--model")
            self.assertEqual(c[i + 1], "gpt-6-luna")
            self.assertEqual(c[c.index("--reasoning-effort") + 1], "high")

    def test_harnais_modele_juge_force_un_autre_modele(self):
        """Le témoin : forcé, le modèle change, et aucun effort n'est imposé (tous
        les modèles ne l'acceptent pas)."""
        os.environ["HARNAIS_MODELE_JUGE"] = "autre-modele"
        self.addCleanup(os.environ.pop, "HARNAIS_MODELE_JUGE", None)
        for appel in (lambda: relecture.juge("invite"), lambda: experts.juge("invite")):
            c = self._commande(appel)
            self.assertEqual(c[c.index("--model") + 1], "autre-modele")
            self.assertNotIn("--reasoning-effort", c)


def _listes(texte):
    """Les listes PowerShell qui copient une distribution (elles commencent par
    `'.github\\plugin', 'bin'`)."""
    return [set(re.findall(r"'([^']+)'", m))
            for m in re.findall(r"@\(('\.github\\plugin', 'bin'[^)]*)\)", texte)]


class Distribution(unittest.TestCase):
    def test_les_controles_copient_ce_que_l_installeur_exige(self):
        """21/10/2026 : `cto-start.ps1` copiait la liste de la version Rust, sans
        `py\\`, et l'installeur refusait (« Distribution missing py\\main.py »)."""
        with open(os.path.join(RACINE, "install.ps1"), encoding="utf-8") as h:
            reference = _listes(h.read())
        self.assertEqual(len(reference), 1)
        reference = reference[0]
        self.assertIn("py", reference)
        vus = 0
        d = os.path.join(RACINE, "controles")
        for n in sorted(os.listdir(d)):
            if not n.endswith(".ps1"):
                continue
            with open(os.path.join(d, n), encoding="utf-8") as h:
                for l in _listes(h.read()):
                    vus += 1
                    self.assertEqual(l, reference, n)
        self.assertGreaterEqual(vus, 3)       # cto-start, install-windows, atelier-deplace


if __name__ == "__main__":
    unittest.main()

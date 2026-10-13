# -*- coding: utf-8 -*-
"""`harnais/src/menage.rs` n'a AUCUN `#[test]` (0 test Rust) : il est jugé par
`controles/menage.sh` et par comparaison à l'oracle. Les 3 essais ci-dessous sont
des AJOUTS DU PORTAGE, sans équivalent Rust — à retirer si le compte doit égaler 0."""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))
import menage  # noqa: E402


def lance(args):
    sortie = io.StringIO()
    with contextlib.redirect_stdout(sortie):
        rc = menage.main(args)
    return rc, sortie.getvalue()


class Essais(unittest.TestCase):
    def dossier(self):
        d = os.path.realpath(tempfile.mkdtemp(prefix="menage-"))
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_dry_run_garde_et_apply_supprime_un_cache_ignore(self):
        d = self.dossier()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, stdout=subprocess.PIPE)
        with open(os.path.join(d, ".gitignore"), "w") as h:
            h.write("node_modules/\n")
        os.makedirs(os.path.join(d, "node_modules"))
        with open(os.path.join(d, "node_modules/gros"), "wb") as h:
            h.write(b"\0" * (2 * 1048576))
        rc, sortie = lance(["--projet", d])
        self.assertEqual(rc, 0)
        self.assertIn("node_modules", sortie)
        self.assertTrue(os.path.isdir(os.path.join(d, "node_modules")), "le dry-run a supprimé")
        lance(["--projet", d, "--apply"])      # témoin négatif du précédent
        self.assertFalse(os.path.exists(os.path.join(d, "node_modules")))

    def test_la_plus_ancienne_date_se_trie_comme_du_texte(self):
        d = self.dossier()
        os.makedirs(os.path.join(d, ".fact"))
        os.makedirs(os.path.join(d, "docs"))
        with open(os.path.join(d, "docs/long.md"), "w") as h:
            h.write("2026-03-04\n12/05/2026\n" + "x\n" * 600)
        _, sortie = lance(["--projet", d])
        self.assertIn("la plus ancienne entrée datée : 12/05/2026", sortie)

    def test_lignes_comme_str_lines_de_rust(self):
        self.assertEqual(menage.lignes("a\r\nb\n"), ["a", "b"])
        self.assertEqual(menage.lignes("a b\n"), ["a b"])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""`harnais/src/migration.rs` n'a AUCUN `#[test]` (0 test Rust) : il est jugé par
comparaison à l'oracle et par `controles/`. Les 3 essais ci-dessous sont des
AJOUTS DU PORTAGE, sans équivalent Rust — à retirer si le compte doit égaler 0."""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))
import migration  # noqa: E402


def lance(args):
    sortie = io.StringIO()
    with contextlib.redirect_stdout(sortie):
        rc = migration.main(args)
    return rc, sortie.getvalue()


def git(d, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t"] + list(a), cwd=d,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


class Essais(unittest.TestCase):
    def projet(self):
        d = os.path.realpath(tempfile.mkdtemp(prefix="migre-"))
        self.addCleanup(shutil.rmtree, d, True)
        git(d, "init", "-q", "-b", "main")
        for n in ["base.md", "architecture.md", "stack.md", "rules.md"]:
            os.makedirs(os.path.join(d, ".fact"), exist_ok=True)
            with open(os.path.join(d, ".fact", n), "w") as h:
                h.write("---\ncap: x\n---\n")
        os.makedirs(os.path.join(d, ".mind"))
        with open(os.path.join(d, ".mind/state.md"), "w") as h:
            h.write("s")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "c")
        return d

    def test_le_blanc_n_ecrit_rien_et_apply_deplace(self):
        d = self.projet()
        rc, _ = lance([d])
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(os.path.join(d, "brain")), "le blanc a écrit")
        rc, _ = lance([d, "--apply"])      # témoin négatif : sans lui, un outil muet passerait
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(os.path.join(d, "brain/fact/base.md")))
        self.assertFalse(os.path.exists(os.path.join(d, ".fact")))

    def test_workflow_n_est_pas_un_fait_de_trop(self):
        """Claude 0.17.0 — `workflow.md`, commun à tous depuis le 12/10/2026, faisait
        refuser un projet comme « un fichier de trop ». Témoin : un vrai fichier de
        trop refuse."""
        d = self.projet()
        with open(os.path.join(d, ".fact/workflow.md"), "w") as h:
            h.write("w")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "w")
        rc, sortie = lance([d])
        self.assertEqual(rc, 0, sortie)
        with open(os.path.join(d, ".fact/questions.md"), "w") as h:
            h.write("q")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "q")
        rc, sortie = lance([d])
        self.assertEqual(rc, 2)
        self.assertIn("questions.md", sortie)

    def test_un_echec_de_git_dit_pourquoi(self):
        """Un `git` qui échoue sans rien sur la sortie standard rend sa raison."""
        rc, sortie = migration.git(tempfile.gettempdir(), ["checkout", "-q", "branche-qui-n-existe-pas"])
        self.assertNotEqual(rc, 0)
        self.assertNotEqual(sortie, "", "l'échec ne dit pas pourquoi")

    def test_refuse_si_brain_existe(self):
        d = self.projet()
        os.makedirs(os.path.join(d, "brain"))
        rc, sortie = lance([d, "--apply"])
        self.assertEqual(rc, 1)    # la forme est ambiguë : « rien à faire », rien déplacé
        self.assertTrue(os.path.isdir(os.path.join(d, ".fact")))

    def test_lignes_comme_str_lines_de_rust(self):
        self.assertEqual(migration.lignes("a\r\nb\n\nc"), ["a", "b", "", "c"])
        self.assertEqual(migration.lignes("a\nb\n"), ["a", "b"])
        self.assertEqual(migration.lignes(""), [])
        # `splitlines` de Python couperait ici : pas Rust.
        self.assertEqual(migration.lignes("a b\x0bc\n"), ["a b\x0bc"])


class HorsDepot(unittest.TestCase):
    def test_sans_depot_la_migration_refuse_en_code_2_et_le_dit(self):
        """Dossier hors de tout dépôt git : « aucun dépôt au-dessus de … », code 2, rien d'écrit
        (Rust 0.12.8 : code 2, même texte)."""
        d = os.path.realpath(tempfile.mkdtemp(prefix="migre-horsdepot-"))
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, ".fact"))
        for avec in ([d], [d, "--apply"]):
            rc, sortie = lance(avec)
            self.assertEqual(rc, 2, avec)
            self.assertIn("aucun dépôt au-dessus de %s" % d, sortie)
        self.assertFalse(os.path.exists(os.path.join(d, "brain")), "rien ne s'écrit hors dépôt")


if __name__ == "__main__":
    unittest.main()

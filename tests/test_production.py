# -*- coding: utf-8 -*-
"""Le garde de la Production (portée de Claude 0.19) : seul l'agent nommé pousse, et
seulement muni d'un laissez-passer daté. Chaque refus a son témoin muet.

Écarts voulus avec le harnais Claude : la charge est celle de Copilot (camelCase
`toolName`/`toolArgs`, ou `tool_name`/`tool_input`), un refus sort par `hote.refus`
(`permissionDecision` à la racine), le shell peut être PowerShell, et le shell d'un
agent lancé à la racine d'une copie retrouve l'agent par le journal de session.
"""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import agent  # noqa: E402
import hote  # noqa: E402
import production  # noqa: E402
from _gardes import (Poste, charge_camel, charge_pascal, ecris, git, lance, lis, muet,  # noqa: E402
                     refus, sortie)

REGLES = "production: main, production\nproduction-agent: OPS\nproduction-duree: 15"


class Base(Poste):
    def setUp(self):
        super().setUp()
        agent._SESSION[0] = None
        self.addCleanup(lambda: agent._SESSION.__setitem__(0, None))

    def juge(self, agent_dir, cmd, cwd=None, shell="Bash"):
        """Le garde, sur une charge normalisée comme `hote.traduis` la rend."""
        outil = {"Bash": "bash", "PowerShell": "powershell"}[shell]
        c = hote.traduis(charge_camel(outil, {"command": cmd}, cwd or agent_dir))
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": agent_dir}):
            return production.juge(c)

    def passe(self, agent_dir, motif="oui de l'humain", *args):
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": agent_dir}):
            return muet(production.laissez_passer, list(args) + [motif])


class Naissance(Base):
    def test_une_equipe_typee_nait_fermee(self):
        # Le tronc commun (0.19) écrit l'en-tête à la naissance : PO ne pousse pas sur main
        # sans que personne l'ait réglé à la main.
        x = os.path.realpath(self.dossier("typee"))
        self.assertEqual(muet(__import__("adopte").main,
                              [x, "--equipe", "OPS,PO", "--modeles", "ops,po", "--go"]), 0)
        e = production._entete(self.regles(x))
        self.assertEqual(e.get("production-agent"), "OPS")
        self.assertIsNotNone(self.juge(self.agent_dir(x, "PO"), "git push origin main"))
        self.assertIsNone(self.juge(self.agent_dir(x, "PO"), "git push origin po"))


class Equipe(Base):
    def setUp(self):
        super().setUp()
        self.x = self.equipe("OPS,PO", REGLES)
        self.ops = self.agent_dir(self.x, "OPS")
        self.po = self.agent_dir(self.x, "PO")

    def test_le_reglage_se_lit_dans_l_entete_des_regles(self):
        e = production._entete(self.regles(self.x))
        self.assertEqual(e["production-agent"], "OPS")
        self.assertIn("main", e["production"])
        r = production.reglage(self.po)
        self.assertEqual(r[1], {"main", "production"})
        self.assertEqual((r[2], r[3]), ("OPS", 15))

    def test_po_ne_pousse_jamais_sur_main_meme_muni(self):
        for cmd in ("git push origin main", "git push origin HEAD:main", "git push origin +main",
                    "git push origin refs/heads/main", "git push --all", "git push origin 'refs/heads/*'",
                    "env X=1 git push origin main", "echo ok && git push origin main",
                    "cd code && git push origin main", "git -C code push origin main",
                    "git push origin production", "gh pr merge 12 --merge"):
            m = self.juge(self.po, cmd)
            self.assertIsNotNone(m, cmd)
            self.assertIn("OPS", m, cmd)
        self.assertEqual(self.passe(self.po), 1, "PO ne s'accorde pas de laissez-passer")
        self.assertIsNotNone(self.juge(self.po, "git push origin main"))
        # TÉMOIN : sa branche de travail passe.
        self.assertIsNone(self.juge(self.po, "git push origin po"))
        self.assertIsNone(self.juge(self.po, "git -C code push origin dev"))
        self.assertIsNone(self.juge(self.po, "git status"))
        self.assertIsNone(self.juge(self.po, "gh pr list"))

    def test_un_push_nu_depuis_main_est_vu(self):
        # La copie de PO est un second arbre de travail, sur sa branche `po`.
        copie = os.path.join(os.path.realpath(self.dossier("copie")), "po")
        git(self.x, "worktree", "add", "-q", copie, "-b", "po")
        self.addCleanup(lambda: git(self.x, "worktree", "prune"))
        self.assertIsNotNone(self.juge(self.po, "git push", cwd=self.x))
        # TÉMOIN : depuis la copie, sur la branche `po`.
        self.assertIsNone(self.juge(self.po, "git push", cwd=copie))

    def test_ops_pousse_avec_un_laissez_passer_et_seulement_avec(self):
        m = self.juge(self.ops, "git push origin main")
        self.assertIsNotNone(m)
        self.assertIn("laissez-passer", m)
        self.assertEqual(self.passe(self.ops, "l'humain : « oui, mets en ligne »"), 0)
        self.assertIsNone(self.juge(self.ops, "git push origin main"))
        projet = production.reglage(self.ops)[0]
        _, log = production._fichiers(projet)
        j = lis(log)
        self.assertIn("déposé", j)
        self.assertIn("usage", j)
        # TÉMOIN : périmé, il ne sert plus.
        f, _ = production._fichiers(projet)
        vieux = time.time() - 16 * 60
        os.utime(f, (vieux, vieux))
        self.assertIsNotNone(self.juge(self.ops, "git push origin main"))

    def test_le_laissez_passer_de_ops_ne_desserre_pas_la_garde_de_po(self):
        self.passe(self.ops)
        self.assertIsNone(self.juge(self.ops, "git push origin main"))
        self.assertIsNotNone(self.juge(self.po, "git push origin main"))

    def test_le_nom_de_l_agent_se_compare_sans_la_casse(self):
        # Le profil de l'app est en minuscules (`ops`) ; le dossier, comme il est écrit.
        f = self.regles(self.x)
        ecris(f, lis(f).replace("production-agent: OPS", "production-agent: ops"))
        self.assertEqual(self.passe(self.ops), 0)
        self.assertIsNone(self.juge(self.ops, "git push origin main"))

    def test_l_agent_choisi_dans_le_menu_est_celui_qui_parle(self):
        """L'app lance tout à la racine de la copie : l'agent vient du journal de
        session, et le hook (`hote.prepare`) s'y place."""
        self.journal_session("s-menu", "po")
        env = {"COPILOT_PROJECT_DIR": ""}
        c = charge_camel("bash", {"command": "git push origin main"}, self.x, sessionId="s-menu")
        o = lance("production", c, env)
        self.assertEqual(o.returncode, 0, o.stderr)
        d = refus(o)
        self.assertEqual(d["permissionDecision"], "deny")
        self.assertIn("OPS", d["permissionDecisionReason"])     # PO choisi : réservé à OPS
        # TÉMOIN : OPS choisi dans le menu, laissez-passer posé depuis sa session.
        self.journal_session("s-ops", "ops")
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": self.x}):
            self.assertEqual(muet(production.laissez_passer, ["--session", "s-ops", "oui de l'humain"]), 0)
        c = charge_camel("bash", {"command": "git push origin main"}, self.x, sessionId="s-ops")
        o = lance("production", c, env)
        self.assertEqual((o.returncode, o.stdout), (0, b""), o.stderr)

    def test_le_shell_sans_agent_identifie_n_obtient_rien(self):
        """FERMÉ sur l'identité : depuis la racine, sans journal, personne n'est OPS."""
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": self.x}):
            r, _, err = sortie(production.laissez_passer, ["oui de l'humain"])
        self.assertEqual(r, 1)
        self.assertIn("--session", err)
        self.assertIsNotNone(self.juge(self.x, "git push origin main"))
        # TÉMOIN : un `--session` qui désigne PO ne change rien non plus.
        self.journal_session("s-po", "po")
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": self.x}):
            self.assertEqual(muet(production.laissez_passer, ["--session", "s-po", "oui"]), 1)

    def test_le_hook_rend_un_refus_lisible_par_copilot(self):
        c = charge_camel("bash", {"command": "git push origin main"}, self.po)
        o = lance("production", c, {"COPILOT_PROJECT_DIR": self.po})
        self.assertEqual(o.returncode, 0, o.stderr)
        d = refus(o)
        self.assertEqual(d["permissionDecision"], "deny")        # à la racine, pas sous hookSpecificOutput
        self.assertNotIn("hookSpecificOutput", d)
        self.assertTrue(o.stdout.decode("ascii"))                # ASCII pur
        # Même chose en PascalCase.
        c = charge_pascal("Bash", {"command": "git push origin main"}, self.po)
        self.assertEqual(refus(lance("production", c, {"COPILOT_PROJECT_DIR": self.po}))["permissionDecision"],
                         "deny")

    def test_temoins_muets_par_le_lanceur(self):
        for c in (charge_camel("bash", {"command": "git push origin po"}, self.po),
                  charge_camel("bash", {"command": "git status"}, self.po),
                  charge_camel("view", {"path": "git push origin main"}, self.po),
                  charge_camel("edit", {"path": "x", "old_str": "git push origin main"}, self.po),
                  "{pas du json git push merge api"):
            o = lance("production", c, {"COPILOT_PROJECT_DIR": self.po})
            self.assertEqual((o.returncode, o.stdout), (0, b""), (c, o.stderr))


class PowerShell(Base):
    def setUp(self):
        super().setUp()
        self.x = self.equipe("OPS,PO", REGLES)
        self.po = self.agent_dir(self.x, "PO")

    def test_les_formes_powershell_sont_vues(self):
        for cmd in ("git push origin main",
                    "Set-Location code; git push origin main",
                    "sl code; git push origin main",
                    "Push-Location code\ngit push origin main",
                    "git push origin `\n  main",
                    "& 'C:\\Program Files\\Git\\cmd\\git.exe' push origin main",
                    "& git push origin HEAD:refs/heads/main",
                    "gh pr merge 3 --squash",
                    "Invoke-RestMethod -Method Put -Uri https://api.github.com/repos/o/r/merges "
                    "-Headers $h -Body $b",
                    "irm -Method POST https://api.github.com/repos/o/r/git/refs/heads/main",
                    "Invoke-WebRequest -Uri https://api.github.com/repos/o/r/git/refs/heads/main "
                    "-Method Patch -Body '{}'",
                    "$ErrorActionPreference='Stop'; git status; git push origin main"):
            m = self.juge(self.po, cmd, shell="PowerShell")
            self.assertIsNotNone(m, cmd)
            self.assertIn("OPS", m, cmd)

    def test_temoins_powershell_muets(self):
        for cmd in ("git push origin po",
                    "Set-Location code; git push origin dev",
                    "Write-Host 'git push origin main'",
                    "Write-Output \"gh pr merge 3\"",
                    "Invoke-RestMethod -Uri https://api.github.com/repos/o/r/merges",    # une lecture
                    "Invoke-RestMethod -Uri https://api.github.com/repos/o/r/pulls -Method Get",
                    "git log --oneline; git status"):
            self.assertIsNone(self.juge(self.po, cmd, shell="PowerShell"), cmd)

    def test_les_barres_inverses_d_un_chemin_windows_survivent(self):
        """shlex (posix) mangerait `C:\\work\\copie` : sous PowerShell la barre est un séparateur."""
        ps = production._jetons("Set-Location C:\\work\\copie; git push", True)
        self.assertEqual(ps[:2], ["Set-Location", "C:\\work\\copie"])
        # TÉMOIN : sous bash la barre reste un échappement.
        self.assertEqual(production._jetons("echo a\\ b", False), ["echo", "a b"])

    def test_la_charge_powershell_telle_que_copilot_l_envoie(self):
        c = charge_camel("powershell", {"command": "git push origin main"}, self.po)
        o = lance("production", c, {"COPILOT_PROJECT_DIR": self.po})
        self.assertEqual(refus(o)["permissionDecision"], "deny", o.stderr)
        c = charge_camel("powershell", {"command": "git push origin po"}, self.po)
        o = lance("production", c, {"COPILOT_PROJECT_DIR": self.po})
        self.assertEqual((o.returncode, o.stdout), (0, b""), o.stderr)


class SansReglage(Base):
    def test_rien_n_est_ferme_sans_reglage(self):
        """TÉMOIN de tout le reste : un projet sans réglage ne ferme rien."""
        x = self.equipe("OPS,PO")
        self.assertIsNone(self.juge(self.agent_dir(x, "PO"), "git push origin main"))

    def test_un_entete_sans_production_ne_ferme_rien(self):
        x = self.equipe("OPS,PO", "production-agent: OPS")
        self.assertIsNone(self.juge(self.agent_dir(x, "PO"), "git push origin main"))
        self.assertIsNone(self.juge(self.agent_dir(x, "PO"), "gh pr merge 1", shell="PowerShell"))

    def test_une_entree_illisible_ne_bloque_pas(self):
        self.assertIsNone(production.juge("pas un objet"))
        self.assertIsNone(production.juge({"tool_name": "Bash", "tool_input": {"command": 3}}))
        self.assertIsNone(production.juge({"tool_name": "Read", "tool_input": {"command": "git push origin main"}}))


class Seul(Base):
    def test_un_projet_seul_se_ferme_par_ses_regles(self):
        p = os.path.realpath(self.dossier("mono"))
        git(p, "init", "-q", "-b", "main")
        muet(__import__("adopte").main, [p, "--go"])
        self.assertIsNone(self.juge(p, "git push origin main"), "pas de réglage : ouvert")
        f = os.path.join(p, "brain", "fact", "rules.md")
        t = lis(f)
        ecris(f, "---\nproduction: main\n---\n" + t)
        self.assertIsNotNone(self.juge(p, "git push origin main"))
        self.assertEqual(self.passe(p), 0)
        self.assertIsNone(self.juge(p, "git push origin main"))
        # Un entête écrit par PowerShell 5.1 : BOM et fins de ligne CRLF.
        with open(f, "wb") as h:
            h.write("\ufeff---\r\nproduction: main\r\n---\r\n".encode("utf-8") + t.encode("utf-8"))
        self.assertEqual(production._entete(f).get("production"), "main")


if __name__ == "__main__":
    unittest.main()

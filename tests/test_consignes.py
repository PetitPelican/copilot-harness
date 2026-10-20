# -*- coding: utf-8 -*-
"""Le verrou des consignes (portée de Claude) : seul le CTO écrit un fichier de consignes
(AGENTS.md, CLAUDE.md, copilot-instructions.md) ; tout le monde lit. Chaque refus a son
témoin qui passe.

Écarts voulus avec le harnais Claude : les fichiers sont ceux que Copilot lit, le seul
gardien est le CTO (pas d'agent Harness dans un atelier Copilot), l'agent est celui que le
harnais résout (menu, dossier, copie de travail), la charge et le refus sont ceux de
Copilot, et PowerShell a ses formes.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import agent  # noqa: E402
import consignes  # noqa: E402
import hote  # noqa: E402
from _gardes import (Isole, Poste, charge_camel, charge_pascal, git, lance, muet,  # noqa: E402
                     refus)


def bash(c):
    return hote.traduis(charge_camel("bash", {"command": c}, "/p"))


def pwsh(c):
    return hote.traduis(charge_camel("powershell", {"command": c}, "/p"))


def edit(p, outil="edit"):
    """Une écriture, telle que Copilot l'envoie : `edit` / `create` avec `path`."""
    return hote.traduis(charge_camel(outil, {"path": p, "old_str": "a", "new_str": "b"}, "/p"))


def patch(fichier, verbe="Update"):
    corps = "*** Begin Patch\n*** %s File: %s\n@@\n-a\n+b\n*** End Patch\n" % (verbe, fichier)
    return hote.traduis(charge_camel("apply_patch", corps, "/p"))


class Base(Isole):
    def setUp(self):
        super().setUp()
        agent._SESSION[0] = None
        self.addCleanup(lambda: agent._SESSION.__setitem__(0, None))

    def en(self, nom):
        """L'agent est lancé depuis un dossier de ce nom."""
        d = os.path.join(os.path.realpath(self.dossier("agent")), nom)
        os.makedirs(d)
        p = mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": d})
        p.start()
        self.addCleanup(p.stop)
        return d


class Verrou(Base):

    def test_un_agent_ne_modifie_pas_ses_consignes(self):
        self.en("Projet PO")
        for d in (edit("/x/Projet/agents/Projet PO/AGENTS.md"), edit("/x/AGENTS.md", "create"),
                  edit("/x/CLAUDE.md"), edit("/x/claude.md"), edit("/x/.github/copilot-instructions.md"),
                  edit("C:\\x\\Projet\\agents\\PO\\AGENTS.md"), patch("agents/PO/AGENTS.md"),
                  patch("AGENTS.md", "Add"), patch(".github/copilot-instructions.md", "Delete"),
                  hote.traduis(charge_pascal("Write", {"file_path": "/x/AGENTS.md"}, "/p")),
                  bash("echo x >> AGENTS.md"), bash("sed -i '' 's/a/b/' ../../AGENTS.md"),
                  bash("git -C code rm AGENTS.md"), bash("rm -f code/AGENTS.md"),
                  bash("cat > \"/x/agents/Projet QA/AGENTS.md\" <<'EOF'\nx\nEOF"),
                  bash("python3 -c \"open('AGENTS.md','w').write('x')\""),
                  bash("mv AGENTS.md AGENTS.md.vieux"),
                  bash("cp /tmp/neuf .github/copilot-instructions.md"),
                  bash("echo x > CLAUDE.md")):
            self.assertIsNotNone(consignes.juge(d), d)

    def test_temoin_lire_passe(self):
        """TÉMOIN : un verrou qui refuserait tout passerait l'essai précédent."""
        self.en("Projet PO")
        for d in (bash("cat AGENTS.md"), bash("grep -n memoire ../../AGENTS.md"),
                  bash("head -20 AGENTS.md | wc -l"), bash("git log --oneline -- AGENTS.md"),
                  bash("diff a/AGENTS.md b/AGENTS.md"), edit("/x/agents/Projet PO/todo.md"),
                  edit("/x/AGENTS.md.notes"), edit("/x/MON-AGENTS.md"), edit("/x/agents.md.txt"),
                  patch("brain/mind/PO/todo.md"), edit("/x/.github/agents/ops.agent.md"),
                  hote.traduis(charge_pascal("Read", {"file_path": "/x/AGENTS.md"}, "/p")),
                  hote.traduis(charge_camel("view", {"path": "/x/AGENTS.md"}, "/p")),
                  bash("echo x >> todo.md"), bash("harnais adopte --go")):
            self.assertIsNone(consignes.juge(d), d)

    def test_temoin_nommer_n_est_pas_ecrire(self):
        """QA, 14/10 (0.18.2) : une ligne de todo qui CITE le fichier de consignes était
        refusée. Seule la cible d'une écriture compte."""
        self.en("Projet QA")
        for d in (bash("cat >> todo.md <<'EOF'\n- [ ] le AGENTS.md du projet cite memoire/\nEOF"),
                  bash('echo "voir AGENTS.md" >> todo.md'), bash("cp AGENTS.md /tmp/copie"),
                  bash("git -C code log -- AGENTS.md > /tmp/hist"),
                  bash("python3 - <<'EOF'\nprint(open('AGENTS.md').read())\nEOF"),
                  bash("grep -c x AGENTS.md && echo ok >> todo.md"),
                  bash('git commit -m "ajoute copilot-instructions.md au perimetre"'),
                  # Un chemin en minuscules n'est pas un mode d'ouverture (`open('agents.md')`).
                  bash("python3 -c \"print(open('agents.md').read())\""),
                  bash("python3 - <<'EOF'\nprint(open('claude.md', encoding='utf-8').read())\nEOF")):
            self.assertIsNone(consignes.juge(d), d)

    def test_un_script_qui_ecrit_reste_refuse(self):
        self.en("Projet QA")
        for d in (bash("python3 - <<'EOF'\nopen('agents/QA/AGENTS.md', 'a').write('x')\nEOF"),
                  bash("python3 -c \"open('agents.md', 'w').write('x')\""),
                  bash("cp /tmp/neuf ../../AGENTS.md"), bash("tee -a AGENTS.md < x"),
                  bash("ln -sf /tmp/x AGENTS.md"), bash('echo x > "/a b/AGENTS.md"')):
            self.assertIsNotNone(consignes.juge(d), d)

    def test_le_cto_ecrit_sans_egard_a_la_casse(self):
        for nom in ("CTO", "cto"):        # `atelier-monte` crée le dossier `cto`
            self.en(nom)
            self.assertIsNone(consignes.juge(edit("/x/Atelier/AGENTS.md")), nom)
            self.assertIsNone(consignes.juge(patch("AGENTS.md")), nom)
            self.assertIsNone(consignes.juge(bash("echo x >> /x/AGENTS.md")), nom)
            self.assertIsNone(consignes.juge(pwsh("Set-Content AGENTS.md 'x'")), nom)

    def test_il_n_y_a_pas_d_agent_harness_dans_un_atelier_copilot(self):
        self.assertEqual(consignes.GARDIENS, ("CTO",))
        self.en("Harness")
        self.assertIsNotNone(consignes.juge(edit("/x/AGENTS.md")))

    def test_un_nom_proche_ne_passe_pas(self):
        for nom in ("CTO-bis", "cto2", "Mon CTO"):
            self.en(nom)
            self.assertIsNotNone(consignes.juge(edit("/x/AGENTS.md")), nom)

    def test_un_appelant_non_identifie_n_est_pas_un_gardien(self):
        """Fermé sur l'identité : un projet à plusieurs agents, aucun choisi ni par défaut."""
        agent._SESSION[0] = agent.Session("/x", "/x", ["OPS", "PO"], agent.Lecture())
        self.assertEqual(consignes.qui(), [])
        self.assertIsNotNone(consignes.juge(edit("/x/AGENTS.md")))
        # TÉMOIN : un CTO choisi dans le menu d'un tel projet écrit.
        agent._SESSION[0] = agent.Session("/x", "/x", ["CTO", "PO"], agent.Lecture())
        agent._SESSION[0].actif = "CTO"
        self.assertIsNone(consignes.juge(edit("/x/AGENTS.md")))


class PowerShell(Base):
    def test_les_formes_powershell_sont_vues(self):
        self.en("Expert")
        for c in ("Set-Content AGENTS.md 'x'", "Set-Content -Path .\\AGENTS.md -Value 'x'",
                  "Add-Content -Path AGENTS.md -Value 'une ligne'", "'x' | Out-File AGENTS.md",
                  "'x' | Out-File -FilePath .github\\copilot-instructions.md -Append",
                  "sc CLAUDE.md x", "ac AGENTS.md x", "Remove-Item AGENTS.md", "ri -Force AGENTS.md",
                  "del .github\\copilot-instructions.md", "Rename-Item AGENTS.md vieux.md",
                  "Rename-Item -Path vieux.md -NewName AGENTS.md", "Move-Item AGENTS.md x\\",
                  "Move-Item x.md -Destination AGENTS.md", "Copy-Item neuf.md AGENTS.md",
                  "Copy-Item -Path neuf.md -Destination CLAUDE.md", "cpi neuf .github\\copilot-instructions.md",
                  "New-Item AGENTS.md -ItemType File", "Get-Content neuf | Set-Content AGENTS.md",
                  "(Get-Content AGENTS.md) -replace 'a','b' | Set-Content AGENTS.md",
                  "Set-Content -Path (Join-Path $dir 'AGENTS.md') -Value x",
                  "Write-Output x > AGENTS.md", "Write-Output x >> CLAUDE.md",
                  "[IO.File]::WriteAllText('AGENTS.md', 'x')",
                  "[System.IO.File]::AppendAllText(\"C:\\x\\AGENTS.md\", 'x')",
                  "[IO.File]::Delete('.github\\copilot-instructions.md')",
                  "git rm AGENTS.md", "git checkout -- AGENTS.md",
                  "python -c \"open('AGENTS.md','w').write('x')\"",
                  "pwsh -Command \"Set-Content AGENTS.md x\"",
                  "$x = 1; Set-Content AGENTS.md $x", "& 'C:\\Windows\\System32\\cmd.exe' /c echo x > AGENTS.md"):
            self.assertIsNotNone(consignes.juge(pwsh(c)), c)

    def test_temoins_powershell_muets(self):
        """Lire, citer, copier DEPUIS : aucun n'écrit un fichier de consignes."""
        self.en("Expert")
        for c in ("Get-Content AGENTS.md", "gc .github\\copilot-instructions.md | Measure-Object",
                  "Select-String -Path AGENTS.md -Pattern memoire", "type CLAUDE.md",
                  "Copy-Item AGENTS.md $env:TEMP\\copie", "Copy-Item AGENTS.md -Destination x.md",
                  "Add-Content -Path todo.md -Value 'voir AGENTS.md'",
                  "Add-Content todo.md -Value AGENTS.md", "Set-Content todo.md 'le CLAUDE.md du projet'",
                  "'voir copilot-instructions.md' | Out-File todo.md", "Write-Host 'Set-Content AGENTS.md x'",
                  "git log --oneline -- AGENTS.md", "git diff AGENTS.md", "Test-Path AGENTS.md",
                  "[IO.File]::ReadAllText('AGENTS.md')", "[IO.File]::WriteAllText('todo.md', 'AGENTS.md')",
                  "Set-Content todo.md @'\nvoir -> AGENTS.md\net > CLAUDE.md\n'@",
                  "Get-ChildItem -Recurse -Filter AGENTS.md", "harnais adopte --go"):
            self.assertIsNone(consignes.juge(pwsh(c)), c)

    def test_les_deux_shells_lisent_la_meme_ligne_autrement(self):
        # `\` échappe sous bash, sépare sous PowerShell : la cible `.github\copilot-instructions.md`
        # n'est un fichier de consignes que lue en PowerShell.
        self.en("Expert")
        self.assertIsNotNone(consignes.juge(pwsh("Set-Content .github\\copilot-instructions.md x")))
        self.assertTrue(consignes.ecrit_un_fichier_de_consignes("echo x > .github\\copilot-instructions.md"))

    def test_le_nom_d_outil_powershell_traverse_hote_et_le_garde(self):
        self.en("Expert")
        c = hote.traduis(charge_camel("powershell", {"command": "Set-Content AGENTS.md x"}, "/p"))
        self.assertTrue(hote.est_powershell(c))
        self.assertIsNotNone(consignes.juge(c))
        c = hote.traduis(charge_pascal("PowerShell", {"command": "Set-Content AGENTS.md x"}, "/p"))
        self.assertIsNotNone(consignes.juge(c))


class Identite(Poste):
    """Qui est le CTO : le dossier de travail, la copie de travail, l'agent choisi dans le menu."""

    def setUp(self):
        super().setUp()
        agent._SESSION[0] = None
        self.addCleanup(lambda: agent._SESSION.__setitem__(0, None))

    def test_a_la_racine_d_une_copie_le_nom_du_depot_principal_compte(self):
        """L'app lance le CTO dans une copie de travail dont le nom n'est pas `cto`."""
        cto = os.path.join(os.path.realpath(self.dossier("poste")), "cto")
        os.makedirs(cto)
        git(cto, "init", "-q", "-b", "main")
        git(cto, "commit", "-q", "--allow-empty", "-m", "premier")
        copie = os.path.join(os.path.realpath(self.dossier("copies")), "tache-42")
        git(cto, "worktree", "add", "-q", copie, "-b", "tache-42")
        self.addCleanup(lambda: git(cto, "worktree", "prune"))
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": copie}):
            self.assertTrue(consignes.est_gardien())
            self.assertIsNone(consignes.juge(edit("/x/AGENTS.md")))
        # TÉMOIN : un sous-dossier de ce dépôt n'est pas le CTO (`agents/PO` d'un projet `cto`).
        sous = os.path.join(cto, "agents", "PO")
        os.makedirs(sous)
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": sous}):
            self.assertFalse(consignes.est_gardien())
            self.assertIsNotNone(consignes.juge(edit("/x/AGENTS.md")))
        # TÉMOIN : la copie d'un autre dépôt.
        autre = os.path.join(os.path.realpath(self.dossier("poste2")), "produit")
        os.makedirs(autre)
        git(autre, "init", "-q", "-b", "main")
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": autre}):
            self.assertFalse(consignes.est_gardien())

    def test_dans_une_equipe_l_agent_du_menu_parle(self):
        x = self.equipe("OPS,PO")
        self.journal_session("s-po", "po")
        c = charge_camel("create", {"path": os.path.join(x, "AGENTS.md")}, x, sessionId="s-po")
        o = lance("consignes", c, {"COPILOT_PROJECT_DIR": ""})
        self.assertEqual(refus(o)["permissionDecision"], "deny", o.stderr)
        # TÉMOIN : dans un projet à plusieurs agents, même un dossier racine qui s'appellerait
        # `cto` ne fait pas du PO un gardien.
        self.assertFalse(consignes.est_gardien(os.path.join(x, "agents", "PO")))

    def test_la_racine_d_une_equipe_sans_agent_choisi_n_est_pas_un_gardien(self):
        x = self.equipe("OPS,PO")
        self.assertFalse(consignes.est_gardien(x))


class ParLeLanceur(Isole):
    """Le hook tel qu'il part : charge camelCase de Copilot sur l'entrée standard."""

    def dossier_agent(self, nom):
        d = os.path.join(os.path.realpath(self.dossier("lanceur")), nom)
        os.makedirs(d)
        return d

    def test_le_refus_sort_en_decision_copilot(self):
        d = self.dossier_agent("Expert")
        for outil, args in (("create", {"path": "/x/AGENTS.md"}), ("edit", {"path": "/x/CLAUDE.md"}),
                            ("bash", {"command": "echo x >> AGENTS.md"}),
                            ("powershell", {"command": "Set-Content AGENTS.md x"}),
                            ("apply_patch", "*** Begin Patch\n*** Add File: AGENTS.md\n+x\n*** End Patch\n")):
            o = lance("consignes", charge_camel(outil, args, d), {"COPILOT_PROJECT_DIR": d})
            self.assertEqual(o.returncode, 0, o.stderr)
            r = refus(o)
            self.assertEqual(r["permissionDecision"], "deny", outil)       # à la racine
            self.assertNotIn("hookSpecificOutput", r)
            self.assertIn("CTO", r["permissionDecisionReason"])
            self.assertTrue(o.stdout.decode("ascii"))

    def test_temoins_muets(self):
        d = self.dossier_agent("Expert")
        for outil, args in (("edit", {"path": "/x/todo.md"}), ("view", {"path": "/x/AGENTS.md"}),
                            ("bash", {"command": "cat AGENTS.md"}),
                            ("powershell", {"command": "Get-Content AGENTS.md"}),
                            ("bash", {"command": "echo 'voir AGENTS.md' >> todo.md"})):
            o = lance("consignes", charge_camel(outil, args, d), {"COPILOT_PROJECT_DIR": d})
            self.assertEqual((o.returncode, o.stdout), (0, b""), (outil, o.stderr))
        # Le CTO, lui, écrit.
        cto = self.dossier_agent("CTO")
        o = lance("consignes", charge_camel("create", {"path": "/x/AGENTS.md"}, cto),
                  {"COPILOT_PROJECT_DIR": cto})
        self.assertEqual((o.returncode, o.stdout), (0, b""), o.stderr)
        # Et une charge illisible ne bloque pas.
        o = lance("consignes", "{pas du json AGENTS.md", {"COPILOT_PROJECT_DIR": d})
        self.assertEqual((o.returncode, o.stdout), (0, b""))

    def test_le_juge_muet_fait_taire_le_hook(self):
        d = self.dossier_agent("Expert")
        o = lance("consignes", charge_camel("create", {"path": "/x/AGENTS.md"}, d),
                  {"COPILOT_PROJECT_DIR": d, "HARNAIS_JUGE": "1"})
        self.assertEqual((o.returncode, o.stdout), (0, b""))


if __name__ == "__main__":
    unittest.main()

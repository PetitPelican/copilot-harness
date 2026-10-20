# -*- coding: utf-8 -*-
"""Essais de `harnais demenage` — une équipe `brain/` passe à « un dossier par agent ».

Le banc reproduit une équipe d'avant, fabriquée : le code en copie principale, la
mémoire `brain/` (soit son propre dépôt — cas A —, soit commitée DANS le dépôt du code,
ce que fait Copilot — cas B), un dossier `agents/<nom>/` par agent avec son rôle et son
périmètre, une copie de travail par agent hors du projet, une copie posée DANS le
principal, une copie de Production à garder, un `.env.local` ignoré, des droits en
chemins relatifs ET absolus.

Chaque cas est joué deux fois (A et B) : l'outil doit rendre la même équipe.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _isole import Isole, git, ecris, lis  # noqa: E402
import banc_equipe  # noqa: E402
import demenage  # noqa: E402
import equipe  # noqa: E402
import memoire  # noqa: E402
import niveau  # noqa: E402

ETAT = "---\nmaj: 2026-10-14\nsante: vert\njalon: x\n---\n"


def sain(c):
    return subprocess.run(["git", "status"], cwd=c, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).returncode == 0


class Banc(Isole):
    autonome = False

    def setUp(self):
        super(Banc, self).setUp()
        self.racine = os.path.realpath(self.dossier("demenage"))
        j = os.path.join
        P = self.P = j(self.racine, "Projet")
        wt = self.wt = j(self.racine, ".worktrees")
        os.makedirs(P)
        git(P, "init", "-q", "-b", "main")
        ecris(j(P, ".gitignore"), ("brain/\n" if self.autonome else "") + ".env*\n")
        ecris(j(P, "apps", "app.ts"), "export {}\n")
        ecris(j(P, "docs", "decisions.md"), "# Décisions\n")
        ecris(j(P, "AGENTS.md"), "# Consignes communes\n")
        for n in ("OPS", "PO"):
            autre = "OPS" if n == "PO" else "PO"
            ecris(j(P, "agents", n, "AGENTS.md"), "# rôle %s\n" % n)
            ecris(j(P, "agents", n, ".github", "copilot", "perimetre.json"), json.dumps({"deny": [
                "agents/%s" % autre, "brain/mind/%s" % autre, "assets/%s" % autre, "brain/poids.json",
                "brain/workspace", "package.json", "apps/web", ".github/agents",
                j(P, "brain", "mind", autre), "memoire-old"]}, indent=2) + "\n")
        ecris(j(P, "agents", "PO", ".mcp.json"), '{"servers": {}}\n')
        ecris(j(P, "agents", "PO", ".github", "copilot", "settings.json"), "{}\n")
        if not self.autonome:
            self.brain(j(P, "brain"))
        git(P, "add", "-A")
        git(P, "commit", "-qm", "code")
        ecris(j(P, ".env.local"), "CLE=1\n")
        if self.autonome:
            self.brain(j(P, "brain"))
            B = j(P, "brain")
            git(B, "init", "-q", "-b", "main")
            git(B, "add", "-A")
            git(B, "commit", "-qm", "memoire")
        git(P, "worktree", "add", "-q", "-b", "po", j(wt, "po"))
        git(P, "worktree", "add", "-q", "--detach", j(wt, "promotion"))
        git(P, "worktree", "add", "-q", "-b", "isole", j(P, ".copies", "agent-1"))
        git(P, "worktree", "add", "-q", "-b", "sauvage", j(wt, "sauvage"))
        ecris(j(wt, "po", ".env.local"), "CLE=2\n")
        self.agents = ("OPS", "PO", "QA")

    def brain(self, B):
        j = os.path.join
        ecris(j(B, "fact", "base.md"), "---\ncap: banc\n---\n")
        ecris(j(B, "fact", "roles.md"), "# Rôles\n")
        for n in ("OPS", "PO", "QA"):
            ecris(j(B, "mind", n, "state.md"), ETAT)
            ecris(j(B, "mind", n, "todo.md"), "# todo %s\n" % n)
        ecris(j(B, "workspace", "2026-10-OPS.md"), "carnet\n")
        ecris(j(B, "poids.json"), "{}\n")

    def lance(self, *a):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = demenage.main([self.P] + list(a))
        return code, out.getvalue()

    def complet(self, *extra):
        return self.lance("--copie", "PO=%s" % os.path.join(self.wt, "po"),
                          "--en-plus", "OPS:promotion=%s" % os.path.join(self.wt, "promotion"), *extra)

    def empreintes(self):
        """Tout ce qui existe sur le disque, code et copies compris : un blanc ne doit rien changer."""
        v = {}
        for r in (self.P, self.wt):
            for d, dirs, fs in os.walk(r):
                for f in fs:
                    p = os.path.join(d, f)
                    if os.sep + ".git" + os.sep in p or f == ".git":
                        continue
                    with open(p, "rb") as h:
                        v[p] = h.read()
        v["__noms__"] = sorted(os.listdir(self.racine))
        return v


class Cas(object):
    """Les essais, communs aux deux cas."""

    def test_a_blanc_rien_ne_bouge(self):
        avant = self.empreintes()
        code, out = self.complet()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.empreintes(), avant, "le blanc a écrit")
        self.assertTrue(os.path.isdir(os.path.join(self.P, "brain")))
        self.assertFalse(os.path.exists(self.P + ".code-demenage"))
        self.assertFalse(os.path.exists(self.P + ".demenage.json"))
        self.assertIn("sauvage", out, "la copie sans agent est nommée")
        self.assertIn("À ENREGISTRER DANS LE CODE", out)
        self.assertIn("écarté, sans objet chez Copilot", out, "les conversations/inscriptions de Claude : écartées, avec la raison")
        self.assertIn("copie neuve agents/QA/code", out)

    def test_sans_agents_arretes_rien_n_est_ecrit(self):
        avant = self.empreintes()
        code, out = self.complet("--apply")
        self.assertEqual(code, 1)
        self.assertIn("--agents-arretes", out)
        self.assertEqual(self.empreintes(), avant)

    def test_le_demenagement(self):
        j = os.path.join
        P = self.P
        n_avant = len(demenage.copies(P))
        mem_avant = int(git(os.path.join(P, "brain"), "rev-list", "--count", "HEAD").strip()) if self.autonome else None
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        # La mémoire EST le projet.
        self.assertFalse(os.path.exists(j(P, "brain")))
        self.assertEqual(lis(j(P, "fact", "base.md")), "---\ncap: banc\n---\n")
        self.assertEqual(lis(j(P, "agents", "PO", "todo.md")), "# todo PO\n")
        self.assertEqual(lis(j(P, "agents", "QA", "state.md")), ETAT)
        self.assertEqual(lis(j(P, "shared", "2026-10-OPS.md")), "carnet\n")
        self.assertEqual(lis(j(P, "poids.json")), "{}\n")
        self.assertEqual(lis(j(P, "docs", "decisions.md")), "# Décisions\n")
        self.assertEqual(lis(j(P, "AGENTS.md")), "# Consignes communes\n")
        self.assertEqual(lis(j(P, "agents", "PO", "AGENTS.md")), "# rôle PO\n")
        self.assertIn("QA", lis(j(P, "agents", "QA", "AGENTS.md")), "un rôle posé pour qui n'en avait pas")
        self.assertEqual(git(P, "status", "--porcelain").strip(), "", "la mémoire est enregistrée, et ignore le code")
        self.assertFalse(os.path.exists(P + ".code-demenage"))
        self.assertFalse(os.path.exists(P + ".demenage.json"))
        # Le code, chaque copie chez son agent, fichiers ignorés compris.
        ops, po, qa = j(P, "agents", "OPS", "code"), j(P, "agents", "PO", "code"), j(P, "agents", "QA", "code")
        self.assertEqual(lis(j(ops, ".env.local")), "CLE=1\n")
        self.assertEqual(lis(j(po, ".env.local")), "CLE=2\n")
        self.assertEqual(git(po, "rev-parse", "--abbrev-ref", "HEAD").strip(), "po")
        self.assertEqual(git(qa, "rev-parse", "--abbrev-ref", "HEAD").strip(), "qa", "une copie neuve, comme à la naissance")
        liste = demenage.copies(ops)
        chemins = [c for c, _ in liste]
        self.assertEqual(len(liste), n_avant + 1)
        for c in (ops, po, qa, j(P, "agents", "OPS", "code-promotion"),
                  j(ops, ".copies", "agent-1"), j(self.wt, "sauvage")):
            self.assertIn(os.path.realpath(c), chemins)
            self.assertTrue(sain(c), c)
        # Les droits : un exemplaire, traduit, chaque règle garde son sens.
        d = json.loads(lis(j(P, "agents", "PO", ".github", "copilot", "perimetre.json")))["deny"]
        self.assertIn("agents/OPS", d)
        self.assertIn("shared", d, "brain/workspace -> shared")
        self.assertIn("poids.json", d)
        self.assertIn("assets/OPS", d)
        self.assertIn("agents/PO/code/package.json", d, "un droit sur le code vise SA copie du code")
        self.assertIn("agents/PO/code/apps/web", d)
        self.assertIn(".github/agents", d, "le contrôle du harnais ne change pas d'adresse")
        self.assertIn("agents/PO/code/memoire-old", d, "un chemin voisin est du code, pas de la mémoire")
        self.assertEqual(d.count("agents/OPS"), 1, "l'absolu d'avant et le relatif de la naissance ne font qu'un")
        self.assertNotIn(j(P, "agents", "OPS"), d, "sous le projet, la garde de Copilot écrit en relatif")
        self.assertNotIn("agents/PO", d, "PO ne doit pas se fermer son propre dossier")
        self.assertNotIn("brain", json.dumps(d))
        # Le périmètre de la naissance a complété : les autres dossiers d'agent sont fermés.
        self.assertIn("agents/QA", d)
        # Le harnais y lit une équipe.
        memoire._VUS.clear()
        r = memoire.resous(j(P, "agents", "PO"))
        self.assertEqual((r.forme, r.nom_agent), (memoire.Forme.Equipe, "PO"))
        # L'historique : A garde celui de la mémoire (+1), B garde le tout dans le code.
        if self.autonome:
            self.assertEqual(int(git(P, "rev-list", "--count", "HEAD").strip()), mem_avant + 1)
        else:
            self.assertTrue(os.path.isfile(j(ops, "brain", "fact", "base.md")),
                            "l'ancienne mémoire reste dans le code, intacte")
            self.assertIn("code", git(ops, "log", "--format=%s", "-1"))
        # Rien de sensible n'est enregistré dans la mémoire.
        suivis = git(P, "ls-files").split("\n")
        self.assertFalse([f for f in suivis if ".env" in f or ".mcp.json" in f], suivis)
        self.assertFalse(os.path.exists(j(P, "agents", "PO", ".mcp.json")), "les accès des connexions ne montent pas")
        self.assertTrue(os.path.isfile(j(po, "agents", "PO", ".mcp.json")), "…et restent dans le code")
        self.assertFalse(os.path.exists(j(P, "agents", "PO", ".github", "copilot", "settings.json")),
                         "le paquet se déclare UNE fois, à la racine Git")

    def test_ce_que_produit_la_naissance(self):
        """L'outil de passage produit CE QUE LA NAISSANCE produit : mêmes fichiers d'équipe,
        même périmètre pour qui n'avait rien, même déclaration du paquet."""
        j = os.path.join
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        with contextlib.redirect_stdout(io.StringIO()):
            niveau.main([self.P, "--apply"])
        d = os.path.realpath(self.dossier("naissance"))
        x = j(d, "Neuve")
        equipe._TYPES.clear()
        self.addCleanup(equipe._TYPES.clear)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(equipe.naissance(x, ["OPS", "PO", "QA"], None, True), 0)

        def suivis(r):
            return set(git(r, "ls-files").split("\n")) - {""}
        naissance, passage = suivis(x), suivis(self.P)
        structure = [f for f in naissance if f.startswith(("agents/", ".github/", "fact/")) or f in (".gitignore", "AGENTS.md")]
        manquants = sorted(set(structure) - passage)
        self.assertEqual(manquants, [], "la naissance produit ceci, le passage non")
        # QA n'avait aucun périmètre : il reçoit exactement celui de la naissance.
        self.assertEqual(lis(j(self.P, "agents", "QA", ".github", "copilot", "perimetre.json")),
                         lis(j(x, "agents", "QA", ".github", "copilot", "perimetre.json")))
        if self.autonome:
            lignes = lis(j(self.P, ".gitignore")).split("\n")
            self.assertTrue(all(l in lignes for l in equipe.GITIGNORE_EQUIPE.split("\n") if l and l[0] != "#"))
        else:
            self.assertEqual(lis(j(self.P, ".gitignore")), lis(j(x, ".gitignore")))
        self.assertEqual(lis(j(self.P, ".github", "agents", "qa.agent.md")),
                         lis(j(x, ".github", "agents", "qa.agent.md")).replace("Neuve", "Projet"))
        s = json.loads(lis(j(self.P, ".github", "copilot", "settings.json")))
        self.assertTrue(s["enabledPlugins"]["harnais@atelier-copilot"])

    def test_docs_differents_bloquent(self):
        ecris(os.path.join(self.wt, "po", "docs", "decisions.md"), "autre\n")
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 1)
        self.assertIn("`docs/` diffère", out)
        self.assertTrue(os.path.isdir(os.path.join(self.P, "brain")), "TÉMOIN : rien n'a bougé")

    def test_un_secret_qui_monterait_bloque(self):
        j = os.path.join
        # un fichier .env dans docs/
        ecris(j(self.P, "docs", ".env.prod"), "A=1\n")
        ecris(j(self.wt, "po", "docs", ".env.prod"), "A=1\n")
        code, out = self.complet()
        self.assertEqual(code, 1)
        self.assertIn(".env.prod", out)
        self.assertNotIn("A=1", out, "jamais la valeur")
        for f in (j(self.P, "docs", ".env.prod"), j(self.wt, "po", "docs", ".env.prod")):
            os.remove(f)
        # operations.md
        ecris(j(self.P, "docs", "operations.md"), "privé\n")
        ecris(j(self.wt, "po", "docs", "operations.md"), "privé\n")
        code, out = self.complet()
        self.assertEqual(code, 1)
        self.assertIn("operations.md", out)
        os.remove(j(self.P, "docs", "operations.md"))
        os.remove(j(self.wt, "po", "docs", "operations.md"))
        # une clé privée
        for r in (self.P, j(self.wt, "po")):
            ecris(j(r, "docs", "cle.txt"), "-----BEGIN RSA PRIVATE KEY-----\n")
        code, out = self.complet()
        self.assertIn("cle.txt", out)
        for r in (self.P, j(self.wt, "po")):
            os.remove(j(r, "docs", "cle.txt"))
        # une clé de forme connue (Stripe), assemblée ici pour qu'elle n'existe pas en clair dans le dépôt
        jeton = "sk_" + "live_" + "abcdefghijklmnop1234"
        for r in (self.P, j(self.wt, "po")):
            ecris(j(r, "docs", "notes.md"), "la clé : %s\n" % jeton)
        code, out = self.complet()
        self.assertEqual(code, 1)
        self.assertIn("notes.md", out)
        self.assertNotIn(jeton, out, "jamais la valeur")

    def test_un_env_dans_assets_bloque(self):
        j = os.path.join
        ecris(j(self.P, "assets", ".env"), "A=1\n")
        code, out = self.lance()
        self.assertEqual(code, 1)
        self.assertIn(".env", out)
        self.assertNotIn("A=1", out)

    def test_un_env_dans_un_dossier_d_agent_reste_dans_le_code_et_ne_monte_pas(self):
        j = os.path.join
        # PO se lançait dans SA copie : c'est son dossier à elle qui monte.
        ecris(j(self.wt, "po", "agents", "PO", ".env.local"), "A=1\n")
        ecris(j(self.wt, "po", "agents", "PO", "notes.md"), "une note\n")
        code, out = self.complet()
        self.assertEqual(code, 0, out)
        self.assertIn("reste dans le code, ne monte pas", out)
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(j(self.P, "agents", "PO", ".env.local")))
        self.assertTrue(os.path.isfile(j(self.P, "agents", "PO", "code", "agents", "PO", ".env.local")),
                        "…il est resté dans le code, à l'octet")
        self.assertEqual(lis(j(self.P, "agents", "PO", "notes.md")), "une note\n", "le reste du dossier d'agent monte")

    def test_un_secret_de_forme_connue_dans_un_dossier_d_agent_bloque(self):
        jeton = "sk_" + "live_" + "abcdefghijklmnop1234"
        ecris(os.path.join(self.P, "agents", "PO", "notes.md"), "la clé : %s\n" % jeton)
        code, out = self.lance()
        self.assertEqual(code, 1, out)
        self.assertIn("notes.md", out)
        self.assertNotIn(jeton, out)

    def test_un_secret_dans_brain_bloque(self):
        """A : la mémoire a un changement non enregistré. B : `brain/` est copié vers un dépôt
        neuf qui part sur GitHub — la clé, ou le `.env`, l'en empêche."""
        ecris(os.path.join(self.P, "brain", "fact", "stack.md"), "la clé : %s\n" % ("sk_" + "live_" + "abcdefghijklmnop1234"))
        ecris(os.path.join(self.P, "brain", "fact", ".env.local"), "A=1\n")
        code, out = self.lance()
        self.assertEqual(code, 1, out)
        if not self.autonome:
            self.assertIn("stack.md", out)
            self.assertIn(".env.local", out)

    def test_l_espace_des_livrables_d_avant_passe_d_abord_a_assets(self):
        ecris(os.path.join(self.P, "outputs", "OPS", "plan.sql"), "select 1;\n")
        code, out = self.complet()
        self.assertEqual(code, 1)
        self.assertIn("mise-a-niveau", out)
        self.assertIn("outputs", out)

    def test_un_temoin_rouge_ramene_tout(self):
        """Le retour arrière : un inventaire qui change en route doit tout ramener."""
        vrai = demenage.inventaire

        def faux(r):
            v, k = vrai(r)
            if r.endswith(os.path.join("agents", "PO", "code")):
                v = dict(v, fantome=(1, 1))
            return v, k
        avant = sorted(c for c, _ in demenage.copies(self.P))
        brut = self.empreintes()
        with mock.patch.object(demenage, "inventaire", faux):
            code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 1, out)
        self.assertIn("ÉCHEC du déplacement du code", out)
        self.assertIn("retour arrière fait", out)
        self.assertEqual(sorted(c for c, _ in demenage.copies(self.P)), avant)
        for c in avant:
            self.assertTrue(sain(c), c)
        self.assertFalse(os.path.exists(self.P + ".code-demenage"))
        self.assertEqual(self.empreintes(), brut, "TÉMOIN : tout est revenu à l'octet")
        self.assertFalse(os.path.exists(os.path.join(self.P, "agents", "OPS", "code")))
        self.assertFalse(os.path.exists(os.path.join(self.P, "agents", "QA")))
        self.assertEqual(git(self.P, "branch", "--list", "qa").strip(), "", "la branche créée en route est retirée")
        if self.autonome:
            self.assertTrue(os.path.isdir(os.path.join(self.P, "brain", ".git")))
            self.assertFalse(os.path.exists(os.path.join(self.P, "brain", "agents")))
        # …et l'essai suivant n'est pas bloqué par un reste.
        code, out = self.complet()
        self.assertEqual(code, 0, out)

    def test_un_etat_git_qui_change_ramene_tout(self):
        """Le travail non enregistré fait partie de ce qu'on ne perd pas : si l'état git
        d'une copie n'est plus celui d'avant, tout revient."""
        ecris(os.path.join(self.wt, "po", "apps", "app.ts"), "export const modifie = 1\n")
        ecris(os.path.join(self.wt, "po", "apps", "nouveau.ts"), "neuf\n")
        vrai = demenage.etat_git
        compte = {"n": 0}

        def faux(c, sans_brain=False):
            h, b, l = vrai(c, sans_brain)
            compte["n"] += 1
            if c.endswith(os.path.join("agents", "PO", "code")):
                l = l[1:]
            return h, b, l
        with mock.patch.object(demenage, "etat_git", faux):
            code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 1, out)
        self.assertIn("l'état git a changé", out)
        self.assertEqual(lis(os.path.join(self.wt, "po", "apps", "nouveau.ts")), "neuf\n")
        self.assertFalse(os.path.exists(os.path.join(self.P, "agents", "PO", "code")))

    def test_le_travail_non_enregistre_traverse(self):
        ecris(os.path.join(self.wt, "po", "apps", "app.ts"), "export const modifie = 1\n")
        ecris(os.path.join(self.wt, "po", "apps", "nouveau.ts"), "neuf\n")
        avant = demenage.etat_git(os.path.join(self.wt, "po"))[2]
        self.assertEqual(len(avant), 2)
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        po = os.path.join(self.P, "agents", "PO", "code")
        self.assertEqual(demenage.etat_git(po)[2], avant)
        self.assertEqual(lis(os.path.join(po, "apps", "app.ts")), "export const modifie = 1\n")

    def test_une_copie_sans_agent_qui_emprunte_les_dependances(self):
        """Une copie sans agent dont `node_modules` est un LIEN vers celles d'une copie qui
        déménage : le lien pend après le déplacement, ce n'est pas un fichier apparu."""
        if os.name == "nt":
            self.skipTest("pas de lien symbolique sous Windows : le harnais n'en pose jamais")
        j = os.path.join
        git(self.P, "worktree", "add", "-q", "--detach", j(self.wt, "emprunte"))
        os.makedirs(j(self.wt, "po", "apps", "node_modules"))
        os.symlink(j(self.wt, "po", "apps", "node_modules"), j(self.wt, "emprunte", "apps", "node_modules"))
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.islink(j(self.wt, "emprunte", "apps", "node_modules")))

    def test_une_copie_au_git_perdu_est_ignoree(self):
        j = os.path.join
        git(self.P, "worktree", "add", "-q", "--detach", j(self.wt, "jetable"))
        os.remove(j(self.wt, "jetable", ".git"))
        code, out = self.complet()
        self.assertEqual(code, 0, out)
        self.assertIn("jetable", out)
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(j(self.wt, "jetable", "apps", "app.ts")))

    def test_une_branche_prise_ailleurs_bloque_et_une_branche_libre_se_reprend(self):
        j = os.path.join
        git(self.P, "worktree", "add", "-q", "-b", "qa", j(self.wt, "qa-ancien"))
        code, out = self.complet()
        self.assertEqual(code, 1)
        self.assertIn("la branche `qa` de QA est déjà prise", out)
        # Libre : la copie qui la tenait part, la branche reste.
        git(self.P, "worktree", "remove", "--force", j(self.wt, "qa-ancien"))
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        self.assertEqual(git(j(self.P, "agents", "QA", "code"), "rev-parse", "--abbrev-ref", "HEAD").strip(), "qa")

    def test_un_etat_et_un_dossier_d_agent_qui_se_recouvrent_bloquent(self):
        j = os.path.join
        ecris(j(self.P, "agents", "OPS", "state.md"), "double\n")
        code, out = self.complet()
        self.assertEqual(code, 1)
        self.assertIn("state.md", out)

    def test_relancer_apres_coup_dit_deja(self):
        self.complet("--apply", "--agents-arretes")
        memoire._VUS.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = demenage.main([self.P, "--apply", "--agents-arretes"])
        self.assertEqual(code, 0)
        self.assertIn("déjà « un dossier par agent »", out.getvalue())


class CasA(Cas, Banc):
    autonome = True

    def test_a_la_memoire_a_un_changement_en_attente_bloque(self):
        ecris(os.path.join(self.P, "brain", "mind", "PO", "todo.md"), "changé\n")
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 1)
        self.assertIn("changements non enregistrés", out)
        self.assertTrue(os.path.isdir(os.path.join(self.P, "brain", ".git")))


class CasB(Cas, Banc):
    autonome = False

    def test_b_la_memoire_neuve_est_un_depot_a_part_et_l_ancienne_reste(self):
        j = os.path.join
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isdir(j(self.P, ".git")))
        self.assertEqual(int(git(self.P, "rev-list", "--count", "HEAD").strip()), 1, "un dépôt neuf, un enregistrement")
        ops = j(self.P, "agents", "OPS", "code")
        self.assertEqual(git(ops, "rev-parse", "--show-toplevel").strip().replace("\\", "/"),
                         ops.replace("\\", "/"), "le code a son propre dépôt, avec tout son passé")
        self.assertIn("brain", git(ops, "ls-files"), "l'ancienne mémoire reste suivie dans le code")
        memoire._VUS.clear()

    def test_b_un_echec_de_la_memoire_defait_tout(self):
        """Dans le cas B la mémoire neuve n'est que des copies : si l'une n'arrive pas
        identique, le code revient aussi, et rien de la mémoire neuve ne reste."""
        vrai = demenage.empreinte
        brut = self.empreintes()

        def faux(p):
            h = vrai(p)
            return h[::-1] if p.endswith("roles.md") and os.sep + "fact" + os.sep in p and "agents" not in p.split(os.sep)[-3:] \
                and p.startswith(self.P + os.sep + "fact") else h
        with mock.patch.object(demenage, "empreinte", faux):
            code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 1, out)
        self.assertIn("ÉCHEC du rangement de la mémoire", out)
        self.assertIn("retour arrière fait", out)
        self.assertEqual(self.empreintes(), brut, "TÉMOIN : tout est revenu à l'octet")
        self.assertFalse(os.path.exists(os.path.join(self.P, "fact")))
        self.assertEqual(int(git(self.P, "rev-list", "--count", "HEAD").strip()), 1)
        self.assertTrue(os.path.isdir(os.path.join(self.P, "brain")))
        self.assertFalse(os.path.exists(self.P + ".code-demenage"))
        code, out = self.complet()
        self.assertEqual(code, 0, out)

    def test_b_une_modification_de_brain_non_enregistree_est_copiee_et_nommee(self):
        ecris(os.path.join(self.P, "brain", "mind", "PO", "todo.md"), "# todo PO\n- [ ] en cours\n")
        code, out = self.complet()
        self.assertIn("modification(s) non enregistrée(s)", out)
        code, out = self.complet("--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        self.assertIn("en cours", lis(os.path.join(self.P, "agents", "PO", "todo.md")))
        self.assertIn("en cours", lis(os.path.join(self.P, "agents", "OPS", "code", "brain", "mind", "PO", "todo.md")))


class Formes(Isole):
    def depot(self, nom="Proj"):
        d = os.path.join(os.path.realpath(self.dossier("formes")), nom)
        os.makedirs(d)
        git(d, "init", "-q", "-b", "main")
        return d

    def lance(self, *a):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = demenage.main(list(a))
        return code, out.getvalue()

    def compacte(self):
        p = self.depot("Compacte")
        ecris(os.path.join(p, "brain/fact/base.md"), "---\ncap: x\n---\n")
        for a in ("OPS", "QA"):
            ecris(os.path.join(p, "brain/mind", a, "state.md"), ETAT)
            ecris(os.path.join(p, "brain/mind", a, "todo.md"), "- [ ] t\n")
            ecris(os.path.join(p, ".github/agents", "%s.agent.md" % a.lower()),
                  "---\nname: %s\n---\n<!-- harnais:role:start -->\n# %s\n<!-- harnais:role:end -->\n" % (a.lower(), a))
            ecris(os.path.join(p, ".github/copilot/perimetres", "%s.json" % a.lower()), json.dumps({"deny": []}) + "\n")
        git(p, "add", "-A")
        git(p, "commit", "-qm", "c")
        return p

    def test_la_forme_compacte_est_nommee_pas_touchee_meme_avec_apply(self):
        p = self.compacte()
        avant = git(p, "ls-files")
        for args in ([p], [p, "--apply", "--agents-arretes"]):
            code, out = self.lance(*args)
            self.assertEqual(code, 0, out)
            self.assertIn("COMPACTE", out)
            self.assertIn("choix de Copilot", out)
            self.assertIn("harnais adopte --equipe", out)
            self.assertFalse(os.path.exists(os.path.join(p, "agents")))
            self.assertFalse(os.path.exists(p + ".code-demenage"))
        self.assertEqual(git(p, "ls-files"), avant)
        self.assertEqual(git(p, "status", "--porcelain").strip(), "")
        self.assertTrue(os.path.isfile(os.path.join(p, "brain/mind/OPS/state.md")))

    def test_une_equipe_mixte_bloque_sans_rien_deviner(self):
        p = self.compacte()
        ecris(os.path.join(p, "brain/mind/PO/state.md"), ETAT)
        ecris(os.path.join(p, "agents/PO/AGENTS.md"), "# PO\n")
        git(p, "add", "-A")
        git(p, "commit", "-qm", "d")
        code, out = self.lance(p, "--apply", "--agents-arretes")
        self.assertEqual(code, 1, out)
        self.assertIn("MIXTE", out)
        self.assertFalse(os.path.exists(p + ".code-demenage"))

    def test_une_equipe_deja_un_dossier_par_agent(self):
        x = banc_equipe.construis(os.path.realpath(self.dossier("v3")))
        avant = git(x, "ls-files")
        code, out = self.lance(x, "--apply", "--agents-arretes")
        self.assertEqual(code, 0, out)
        self.assertIn("déjà « un dossier par agent »", out)
        self.assertEqual(git(x, "ls-files"), avant)

    def test_une_memoire_d_avant_brain_passe_d_abord_par_mise_a_niveau(self):
        p = self.depot("Ancien")
        ecris(os.path.join(p, ".fact/base.md"), "---\ncap: x\n---\n")
        ecris(os.path.join(p, "agents/OPS/.mind/state.md"), ETAT)
        git(p, "add", "-A")
        git(p, "commit", "-qm", "c")
        code, out = self.lance(p, "--apply", "--agents-arretes")
        self.assertEqual(code, 1, out)
        self.assertIn("mise-a-niveau", out)
        self.assertTrue(os.path.isdir(os.path.join(p, ".fact")))

    def test_sans_usage_il_dit_l_usage(self):
        code, out = self.lance()
        self.assertEqual(code, 2)
        self.assertIn("usage", out)

    def test_un_projet_sans_agent_n_est_pas_une_equipe(self):
        p = self.depot("Seul")
        ecris(os.path.join(p, "brain/fact/base.md"), "---\ncap: x\n---\n")
        ecris(os.path.join(p, "brain/mind/state.md"), ETAT)
        git(p, "add", "-A")
        git(p, "commit", "-qm", "c")
        code, out = self.lance(p)
        self.assertEqual(code, 1, out)
        self.assertIn("aucun agent", out)


class Windows(unittest.TestCase):
    """Les chemins d'un poste Windows, simulés : git rend `C:/Users/u/Projet`, Python
    `C:\\Users\\u\\Projet` ; un droit s'écrit avec l'un ou l'autre séparateur."""

    def nt(self):
        import ntpath
        for cible, nom, valeur in ((niveau.os, "name", "nt"), (niveau.os.path, "join", ntpath.join),
                                   (niveau.os.path, "normpath", ntpath.normpath)):
            p = mock.patch.object(cible, nom, valeur)
            p.start()
            self.addCleanup(p.stop)

    def plan(self):
        pl = demenage.Plan("C:\\Users\\u\\Projet")
        pl.agents = ["OPS", "PO"]
        pl.premier = "OPS"
        pl.copies = [("C:\\Users\\u\\Projet", "main"), ("C:\\Users\\u\\wt\\po", "po")]
        pl.copie = {"OPS": "C:\\Users\\u\\Projet", "PO": "C:\\Users\\u\\wt\\po"}
        pl.badge = {"OPS": "C:\\Users\\u\\Projet", "PO": "C:\\Users\\u\\wt\\po"}
        pl.autonome = True
        return pl

    def test_la_sortie_de_git_worktree_list_est_ecrite_comme_windows_l_ecrit(self):
        self.nt()
        out = ("worktree C:/Users/u/Projet\nHEAD abc\nbranch refs/heads/main\n\n"
               "worktree C:/Users/u/wt/po\r\nHEAD def\r\nbranch refs/heads/po\r\n\n")
        self.assertEqual(demenage.lis_copies(out, norm=memoire.natif),
                         [("C:\\Users\\u\\Projet", "main"), ("C:\\Users\\u\\wt\\po", "po")])

    def test_les_droits_en_chemin_windows_sont_traduits(self):
        self.nt()
        pl = self.plan()
        t = demenage.traduit_entree
        # PO travaille dans sa copie : un absolu sous le checkout principal est du code d'OPS.
        self.assertEqual(t("C:\\Users\\u\\Projet\\brain\\mind\\OPS", "PO", pl)[0],
                         ["C:\\Users\\u\\Projet\\agents\\OPS"])
        # PO travaillait dans sa copie : un droit relatif se lisait depuis CETTE copie.
        self.assertEqual(t("brain\\mind\\OPS", "PO", pl)[0], ["agents\\OPS"])
        self.assertEqual(t("brain/workspace", "PO", pl)[0], ["shared"])
        self.assertEqual(t("package.json", "PO", pl)[0], ["agents/PO/code/package.json"])
        self.assertEqual(t("apps\\web", "PO", pl)[0], ["agents\\PO\\code\\apps\\web"])
        # un absolu sous la copie de PO : la copie suit, le séparateur est gardé
        self.assertEqual(t("C:\\Users\\u\\wt\\po\\brain\\fact", "PO", pl)[0], ["C:\\Users\\u\\Projet\\fact"])
        # la casse ne distingue rien sous Windows
        self.assertEqual(t("BRAIN/Mind/OPS", "PO", pl)[0], ["agents/OPS"])
        # un chemin hors du projet reste tel quel
        self.assertEqual(t("D:\\ailleurs\\x", "PO", pl)[0], ["D:\\ailleurs\\x"])

    @unittest.skipIf(os.name == "nt", "propre aux systèmes où la casse distingue deux dossiers : "
                                      "sous Windows, `BRAIN` et `brain` sont le même dossier")
    def test_les_memes_droits_hors_windows_gardent_la_casse(self):
        pl = demenage.Plan("/Users/u/Projet")
        pl.agents, pl.premier, pl.badge = ["OPS", "PO"], "OPS", {"OPS": "/Users/u/Projet", "PO": "/Users/u/Projet"}
        self.assertEqual(demenage.traduit_entree("BRAIN/mind/OPS", "PO", pl)[0], ["agents/PO/code/BRAIN/mind/OPS"],
                         "un nom qui n'est pas `brain` est du code")
        self.assertEqual(demenage.traduit_entree("brain/mind/OPS", "PO", pl)[0], ["agents/OPS"])
        self.assertEqual(demenage.traduit_entree("/Users/u/Projet/brain/fact", "PO", pl)[0], ["/Users/u/Projet/fact"])


class Traduction(unittest.TestCase):
    def plan(self):
        pl = demenage.Plan("/Users/u/Projet")
        pl.agents, pl.premier = ["OPS", "PO", "QA"], "OPS"
        pl.badge = dict((n, "/Users/u/Projet") for n in pl.agents)
        pl.autonome = True
        return pl

    def test_agents_seul_vise_les_pairs_pas_soi(self):
        pl = self.plan()
        self.assertEqual(demenage.traduit_entree("agents", "PO", pl)[0], ["agents/OPS", "agents/QA"])

    def test_dot_reste_dot_et_l_externe_reste_externe(self):
        pl = self.plan()
        self.assertEqual(demenage.traduit_entree(".", "PO", pl)[0], ["."])
        self.assertEqual(demenage.traduit_entree("/etc/hosts", "PO", pl)[0], ["/etc/hosts"])

    def test_un_dossier_de_brain_hors_methode_est_nomme_en_b(self):
        pl = self.plan()
        pl.autonome = False
        ys, note = demenage.traduit_entree("brain/branding", "PO", pl)
        self.assertIn("non traduit", note)
        pl.autonome = True
        self.assertEqual(demenage.traduit_entree("brain/branding", "PO", pl), (["branding"], None))

    def test_le_json_est_traduit_champ_par_champ(self):
        pl = self.plan()
        t = json.dumps({"deny": ["brain/mind/OPS", "apps"], "allow": ["brain/fact/base.md"], "x": "brain/mind/OPS"})
        neuf, n, _ = demenage.traduit_droits(t, "PO", pl)
        v = json.loads(neuf)
        self.assertEqual((v["deny"], v["allow"], v["x"]), (["agents/OPS", "agents/PO/code/apps"], ["fact/base.md"], "brain/mind/OPS"))
        self.assertEqual(n, 3)


if __name__ == "__main__":
    unittest.main()

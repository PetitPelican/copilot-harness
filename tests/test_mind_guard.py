# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/mind_guard.rs` (5 tests)."""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import env_windows
from _isole import Isole
import mind_guard
from mind_guard import (CHAMPS_REQUIS_FACT, NOMS_MIND, aujourd_hui, autorise, champ, entete,
                        est_du_code, noms_fact, verifie_state)


class Essais(Isole):

    def test_le_plafond_porte_sur_les_noms(self):
        """LE PLAFOND PORTE SUR LES NOMS, et il a deux mots distincts."""
        # Écart voulu : `workflow.md` est un cinquième fichier de faits en Python
        # (commun à tous les agents) ; le Rust n'en admet que quatre + roles.md.
        for n in ["base.md", "architecture.md", "stack.md", "rules.md", "roles.md", "workflow.md"]:
            self.assertIn(n, noms_fact(), "%s devrait être admis" % n)
        # CE QUE LE PLAFOND REFUSE — sinon on épingle une liste qui dit oui à tout.
        for n in ["extra.md", "notes.md", "base.txt", "Base.md"]:
            self.assertNotIn(n, noms_fact(), "%s devrait être refusé" % n)
        self.assertEqual(NOMS_MIND, ["state.md", "todo.md"])
        self.assertNotIn("belief.md", NOMS_MIND)

        # `fact-neuf` VAUT `fact-ok` — la hiérarchie, pas une clé partagée.
        # Sans elle la serrure ne s'ouvrirait jamais : `autorise()` ancre le mot
        # en FIN de commande, deux mots ne peuvent donc pas cohabiter.
        self.assertTrue(autorise("git commit -m x # fact-neuf", "fact-neuf"))
        self.assertFalse(autorise("git commit -m x # fact-ok", "fact-neuf"))
        # ET L'INVERSE RESTE FAUX : `fact-ok` n'autorise pas un 5ᵉ nom.
        self.assertFalse(autorise("git commit -m x # fact-neuf", "mind-neuf"))

    def test_l_echappatoire_se_lit_en_FIN_de_commande(self):
        self.assertTrue(autorise("git commit -m x # mind-ok", "mind-ok"))
        self.assertTrue(autorise("git commit -m x #fact-ok  ", "fact-ok"))
        self.assertTrue(autorise("git commit -m x # fact-ok\n", "fact-ok"))
        # LE DÉFAUT RÉPARÉ : une sous-chaîne n'importe où désarmait le garde.
        self.assertFalse(autorise("git checkout -b essai-fact-ok && git commit -m x", "fact-ok"))
        self.assertFalse(autorise("git commit -m 'répare fact-ok un jour'", "fact-ok"))
        self.assertFalse(autorise("git commit -m x", "mind-ok"))
        # UNE CLÉ, UNE SERRURE : `mind-ok` n'ouvre pas la serrure de `.fact/`.
        self.assertFalse(autorise("git commit -m x # mind-ok", "fact-ok"))

    def test_l_entete_se_lit_comme_le_tableau_de_bord(self):
        e = entete("---\nmaj: 2026-09-09\ncap: aller là   # un commentaire\n---\n\ntexte")
        self.assertEqual(champ(e, "maj"), "2026-09-09")
        self.assertEqual(champ(e, "cap"), "aller là")
        # TÉMOINS NÉGATIFS : pas d'en-tête, en-tête non fermé, texte nu.
        self.assertEqual(entete("texte sans en-tête"), [])
        self.assertEqual(entete("---\nmaj: x\n"), [])
        self.assertEqual(entete(""), [])

    def test_le_state_est_juge_sur_sa_structure_puis_sa_fraicheur(self):
        ok = "---\nmaj: %s\nsante: verte\njalon: x\n---\n" % aujourd_hui()
        self.assertEqual(verifie_state(ok, CHAMPS_REQUIS_FACT), [])
        # structure : sans en-tête, le projet DISPARAÎT du tableau de bord
        m = verifie_state("rien", CHAMPS_REQUIS_FACT)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0][0], "structure")
        # structure : champ manquant
        m = verifie_state("---\nmaj: %s\n---\n" % aujourd_hui(), CHAMPS_REQUIS_FACT)
        self.assertTrue(any(k == "structure" and "`sante:`" in v for k, v in m))
        # structure : date qui n'est pas une date
        m = verifie_state("---\nmaj: hier\nsante: v\njalon: x\n---\n", CHAMPS_REQUIS_FACT)
        self.assertTrue(any(k == "structure" and "« hier »" in v for k, v in m))
        # fraîcheur : date valide mais pas celle du jour
        m = verifie_state("---\nmaj: 2020-01-01\nsante: v\njalon: x\n---\n", CHAMPS_REQUIS_FACT)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0][0], "fraicheur")

    def test_le_harnais_de_l_agent_n_est_pas_du_code_projet(self):
        self.assertTrue(est_du_code("src/a.ts", "", ""))
        self.assertTrue(est_du_code("truc.py", "", ""))
        self.assertTrue(est_du_code("agents/ios/src/a.ts", "agents/ios/", ""))
        # LES DEUX JEUX DE PRÉFIXES, et c'est le défaut que ça répare :
        self.assertFalse(est_du_code("agents/ios/.github/copilot/garde.py", "agents/ios/", ""))
        self.assertFalse(est_du_code(".fact/base.md", "", ""))
        self.assertFalse(est_du_code("docs/decisions.md", "", ""))
        self.assertFalse(est_du_code(".logs/2026-09-09.md", "", ""))
        self.assertFalse(est_du_code("site/index.html", "", ""), "rendu généré")
        self.assertTrue(est_du_code("site/_content/a.py", "", ""), "mais son contenu, si")
        self.assertFalse(est_du_code("LISEZMOI.md", "", ""))
        # Ce que produit un agent n'est pas du code projet, quel que soit son format…
        # Écart voulu : le dossier des livrables est `assets/` (agent.BANC) ; `outputs/`
        # et `brain/workbench/` restent reconnus comme anciens noms (assertions du Rust).
        self.assertFalse(est_du_code("assets/OPS/requete.sql", "", ""))
        self.assertFalse(est_du_code("assets/PO/analyse.ipynb", "", ""))
        self.assertFalse(est_du_code("outputs/OPS/requete.sql", "", ""), "ancien nom, toujours lu")
        self.assertFalse(est_du_code("outputs/PO/analyse.ipynb", "", ""), "ancien nom, toujours lu")
        # …mais le même fichier hors du banc, si.
        self.assertTrue(est_du_code("src/requete.sql", "", ""))
        self.assertFalse(est_du_code("brain/workbench/OPS/requete.sql", "", ""),
                         "l'ancien établi reste lu")
        self.assertTrue(est_du_code("brain/requete.sql", "", ""),
                        "le reste de brain/ n'est pas exempté")


class Equipe(Isole):
    """v3 · « un dossier par agent » : l'agent se tient dans `agents/<nom>/`, qui est
    le dépôt de la MÉMOIRE, et enregistre son code dans `code/`. Porté de Claude
    0.19 ; le hook est lancé comme Copilot le lance (`main.py mind-guard`, charge
    normalisée par `hote`, refus à la racine de l'objet)."""

    RACINE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def setUp(self):
        Isole.setUp(self)
        import banc_equipe
        self.x = banc_equipe.construis(os.path.realpath(self.dossier("equipe")))
        self.po = os.path.join(self.x, "agents", "PO")
        self.code = os.path.join(self.po, "code")

    def juge(self, commande, cwd=None):
        env = dict(env_windows.essentiel(), **{k: os.environ[k] for k in (
            "HOME", "USERPROFILE", "COPILOT_HOME", "COPILOT_PLUGIN_DATA", "COPILOT_PLUGIN_ROOT")})
        env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
        env["LANG"] = "C.UTF-8"
        env["COPILOT_PROJECT_DIR"] = self.po
        entree = json.dumps({"toolName": "bash", "toolArgs": {"command": commande}})
        r = subprocess.run([sys.executable, os.path.join(self.RACINE, "py", "main.py"), "mind-guard"],
                           cwd=cwd or self.po, env=env, input=entree.encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        sortie = r.stdout.decode("utf-8", "replace").strip()
        if not sortie:
            return None
        v = json.loads(sortie)
        self.assertEqual(v["permissionDecision"], "deny")
        return v["permissionDecisionReason"]

    def indexe_du_code(self, mtime_etat):
        with open(os.path.join(self.code, "apps", "app.ts"), "a", encoding="utf-8") as h:
            h.write("// x\n")
        subprocess.run(["git", "add", "apps/app.ts"], cwd=self.code, check=True)
        etat = os.path.join(self.po, "state.md")
        os.utime(etat, (mtime_etat, mtime_etat))

    def test_un_commit_tape_dans_le_dossier_de_l_agent_vise_la_memoire(self):
        with open(os.path.join(self.po, "todo.md"), "a", encoding="utf-8") as h:
            h.write("- [ ] x\n")
        subprocess.run(["git", "add", "todo.md"], cwd=self.po, check=True)
        m = self.juge("git commit -m x")
        self.assertIsNotNone(m)
        self.assertIn("MÉMOIRE", m)
        self.assertIn("git -C code commit", m)
        # TÉMOIN : l'échappatoire ouvre la serrure.
        self.assertIsNone(self.juge("git commit -m x # memoire-ok"))

    def test_git_dash_C_code_juge_le_code_contre_l_etat_de_l_agent(self):
        self.indexe_du_code(1000000000)          # état très ancien
        for cmd in ("git -C code commit -m x", "cd code && git commit -m x"):
            m = self.juge(cmd)
            self.assertIsNotNone(m, cmd)
            self.assertIn("du code projet est indexé", m)
            self.assertIn("Mets `state.md` à jour", m)
            self.assertNotIn("memoire/", m)
        # TÉMOIN : un état plus récent que le code laisse passer.
        os.utime(os.path.join(self.po, "state.md"), None)
        self.assertIsNone(self.juge("git -C code commit -m x"))

    def test_les_faits_s_ecrivent_dans_la_memoire_avec_fact_ok(self):
        with open(os.path.join(self.x, "fact", "base.md"), "a", encoding="utf-8") as h:
            h.write("ajout\n")
        subprocess.run(["git", "add", "fact/base.md"], cwd=self.x, check=True)
        self.assertIsNone(self.juge("git commit -m x # fact-ok"))
        # TÉMOIN : `memoire-ok` ouvre la mémoire, PAS les faits.
        m = self.juge("git commit -m x # memoire-ok")
        self.assertIsNotNone(m)
        self.assertIn("fact", m)

    def test_le_role_de_l_agent_n_est_pas_un_intrus(self):
        """COPILOT : le rôle est `AGENTS.md` ; `CLAUDE.md` d'une équipe mixte aussi."""
        for nom in ("AGENTS.md", "CLAUDE.md"):
            with open(os.path.join(self.po, nom), "a", encoding="utf-8") as h:
                h.write("ajout\n")
            subprocess.run(["git", "add", nom], cwd=self.po, check=True)
            self.assertIsNone(self.juge("git commit -m x # memoire-ok"), nom)
        # TÉMOIN : un troisième nom dans l'esprit reste refusé.
        with open(os.path.join(self.po, "notes.md"), "w", encoding="utf-8") as h:
            h.write("x\n")
        subprocess.run(["git", "add", "notes.md"], cwd=self.po, check=True)
        m = self.juge("git commit -m x # memoire-ok")
        self.assertIsNotNone(m)
        self.assertIn("notes.md", m)

    def test_une_copie_du_code_ne_nait_que_dans_le_dossier_de_l_agent(self):
        dehors = ("git -C code worktree add ../../../ailleurs",
                  "git -C code worktree add -b essai " + os.path.join(self.dossier("sauvage"), "copie"),
                  "cd code && git worktree add ../../OPS/code-x")
        for cmd in dehors:
            m = self.juge(cmd)
            self.assertIsNotNone(m, cmd)
            self.assertIn("code-<sujet>", m)
        # TÉMOINS : dans son dossier, ou sur la demande du commanditaire.
        for cmd in ("git -C code worktree add ../code-essai",
                    "git -C code worktree add -b essai ../code-essai",
                    "git -C code worktree add %s # copie-ok" % self.dossier("voulu"),
                    "git -C code worktree list"):
            self.assertIsNone(self.juge(cmd), cmd)

    def test_juge_copie_ne_vaut_qu_en_equipe_dans_un_dossier_d_agent(self):
        """Hors équipe, ou à la racine de l'équipe (personne n'y est chez lui), la
        garde se tait : elle ne fabrique pas de refus là où elle n'a pas de repère."""
        cmd = "git worktree add " + os.path.join(self.dossier("ailleurs"), "copie")
        self.assertIsNotNone(mind_guard.juge_copie(cmd, self.po))
        self.assertIsNone(mind_guard.juge_copie(cmd, self.x), "racine de l'équipe")
        self.assertIsNone(mind_guard.juge_copie(cmd, self.dossier("hors-equipe")), "hors équipe")

    def test_chemin_de_copie(self):
        f = mind_guard.chemin_de_copie
        self.assertEqual(f("git worktree add ../x"), "../x")
        self.assertEqual(f("git -C code worktree add -b essai ../x main"), "../x")
        self.assertEqual(f("git worktree add --detach ../x"), "../x")
        self.assertEqual(f('git worktree add "../a b"'), "../a b")
        self.assertIsNone(f("git worktree list"))
        self.assertIsNone(f("git worktree add"))

    def test_la_tache_du_commit_est_jugee_par_taches_quand_il_est_la(self):
        """Claude 0.19.2 : dans la copie du code d'une équipe, `taches.juge_commit` peut
        refuser un commit. COPILOT : ce module est porté à part ; sans lui, la garde est
        muette. TÉMOINS dans les deux sens, et pas dans la mémoire."""
        import types
        from unittest import mock
        entree = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git -C code commit -m x"}})
        ici = os.getcwd()
        os.chdir(self.po)
        self.addCleanup(os.chdir, ici)
        faux = types.ModuleType("taches")
        faux.juge_commit = lambda cmd, courant: "TACHE-REQUISE"
        with mock.patch.dict(sys.modules, {"taches": faux}):
            self.assertEqual(mind_guard.juge(entree, self.po), "TACHE-REQUISE")
            # Dans la mémoire (pas de `-C code`), la tâche n'est pas demandée.
            memoire_ = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x # memoire-ok"}})
            self.assertNotEqual(mind_guard.juge(memoire_, self.po), "TACHE-REQUISE")
        with mock.patch.dict(sys.modules, {"taches": None}):        # import impossible
            self.assertNotEqual(mind_guard.juge(entree, self.po), "TACHE-REQUISE")
        sans_fonction = types.ModuleType("taches")
        with mock.patch.dict(sys.modules, {"taches": sans_fonction}):
            self.assertNotEqual(mind_guard.juge(entree, self.po), "TACHE-REQUISE")

    def test_le_dossier_du_commit(self):
        d = mind_guard.dossier_du_commit
        self.assertEqual(d("git -C code commit -m x", self.po), self.code)
        self.assertEqual(d("cd code && git commit", self.po), self.code)
        self.assertEqual(d('git -C "code" commit', self.po), self.code)
        self.assertEqual(d("git commit -m x", self.po), self.po)
        self.assertEqual(d("git -C inexistant commit", self.po), self.po)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/agent.rs` (8 tests)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import memoire
from agent import (Choix, Lecture, Source, chemin_journal, correspond, lignes_briefing, lis_journal,
                   nom_de_profil, resous)


def _env():
    e = dict(os.environ)
    e.update({"GIT_CONFIG_NOSYSTEM": "1",
              "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return e


def git(d, *a):
    r = subprocess.run(["git", "-c", "commit.gpgsign=false"] + list(a), cwd=d, env=_env(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0, "git %r : %s" % (a, r.stderr.decode("utf-8", "replace"))


def ecris(p, t):
    with open(p, "w", encoding="utf-8") as f:
        f.write(t)


def choisi(nom):
    return {"type": "subagent.selected", "data": {"agentName": nom}}


def retire():
    return {"type": "subagent.deselected", "data": {}}


def journal(d, lignes):
    p = os.path.join(d, "events.jsonl")
    t = "".join(json.dumps(v, separators=(",", ":"), ensure_ascii=False) + "\n" for v in lignes)
    ecris(p, t)
    return p


class Essais(unittest.TestCase):

    def setUp(self):
        # `memoire.git` garde ses réponses par (dossier, arguments) pour la vie du processus.
        memoire._VUS.clear()

    def dossier(self, nom):
        d = tempfile.mkdtemp(prefix="agent-actif-%s-" % nom)
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def projet(self, nom, agents):
        """Un projet `brain/` à trois agents, commité."""
        d = self.dossier(nom)
        git(d, "init", "-q")
        os.makedirs(os.path.join(d, "brain/fact"))
        ecris(os.path.join(d, "brain/fact/base.md"), "---\ncap: essai\n---\n")
        for a in agents:
            os.makedirs(os.path.join(d, "agents", a))
            ecris(os.path.join(d, "agents", a, "AGENTS.md"), "# %s — rôle\n\nRÔLE-%s\n" % (a, a))
            os.makedirs(os.path.join(d, "brain/mind", a))
            ecris(os.path.join(d, "brain/mind", a, "state.md"), "---\nmaj: 2026-01-01\n---\n")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "projet")
        return os.path.realpath(d)

    def test_une_equipe_un_dossier_par_agent_a_ses_agents_dans_le_menu(self):
        """Claude 0.19 : à la racine de l'équipe (la mémoire), chaque `agents/<nom>/`
        qui porte un état est un agent ; le harnais s'y place. TÉMOINS : un dossier
        sans état n'en est pas un, et un projet mono à dossier `agents/` de code reste mono."""
        import agent
        sys.path.insert(0, os.path.dirname(__file__))
        import banc_equipe
        d = os.path.realpath(self.dossier("equipe-menu"))
        x = banc_equipe.construis(d)
        os.makedirs(os.path.join(x, "agents", "outils"))                 # sans état
        self.assertEqual(agent.agents_du_projet(x), ["OPS", "PO"])
        s = resous(x, Lecture())
        self.assertEqual(s.actif, None, "ni QA ni choix : personne n'est placé")
        l = Lecture()
        l.choix = Choix("agent", "po", 1)
        s = resous(x, l)
        self.assertEqual((s.actif, s.source.genre), ("PO", "menu"))
        self.assertEqual(s.place, os.path.join(x, "agents", "PO"))
        # TÉMOIN : un projet mono dont `agents/` est du code.
        m = self.dossier("mono-code")
        git(m, "init", "-q")
        os.makedirs(os.path.join(m, "agents", "bot"))
        ecris(os.path.join(m, "agents", "bot", "state.md"), "x")
        self.assertEqual(agent.agents_du_projet(os.path.realpath(m)), [])

    def test_le_journal_rend_le_dernier_choix_et_ignore_les_sous_agents(self):
        d = self.dossier("journal")
        # Le démarrage tel que l'app l'écrit : deux `selected` identiques.
        p = journal(d, [{"type": "session.start"}, choisi("ops"), choisi("ops"),
                        {"type": "user.message", "data": {"content": "subagent.selected ?"}}])
        l = lis_journal(p)
        self.assertTrue(l.trouve)
        self.assertEqual(l.lignes, 4)
        self.assertEqual(l.choix, Choix("agent", "ops", 2),
                         "le doublon du démarrage ne déplace pas la ligne du choix")

        # « Default agent », puis retour, puis un sous-agent qui ne compte pas.
        p = journal(d, [choisi("ops"), choisi("ops"), retire(),
                        {"type": "session.compaction_complete"},
                        choisi("ops"),
                        {"type": "subagent.started", "agentId": "a1", "data": {"agentName": "task"}},
                        {"type": "subagent.selected", "agentId": "a1", "data": {"agentName": "explore"}}])
        l = lis_journal(p)
        self.assertEqual(l.choix, Choix("agent", "ops", 5))
        self.assertEqual(l.compactions, 1)

        p = journal(d, [choisi("ops"), retire(), retire()])
        self.assertEqual(lis_journal(p).choix, Choix("retire", None, 2))

        # Une ligne illisible ne casse pas la lecture.
        ecris(p, "{pas du json subagent.\n{\"type\":\"subagent.selected\",\"data\":{\"agentName\":\"qa\"}}\n")
        self.assertEqual(lis_journal(p).choix, Choix("agent", "qa", 2))

        absent = lis_journal(os.path.join(d, "absent.jsonl"))
        self.assertFalse(absent.trouve)
        self.assertEqual(absent.choix, Choix("rien"))

    def test_le_chemin_du_journal_ne_se_compose_qu_avec_un_identifiant_sain(self):
        m = "/maison/.copilot"
        self.assertEqual(chemin_journal({"session_id": "7d09-18_41"}, m),
                         os.path.join(m, "session-state", "7d09-18_41", "events.jsonl"))
        self.assertEqual(chemin_journal({"session_id": "x", "transcript_path": "/t/events.jsonl"}, m),
                         "/t/events.jsonl", "la fin de tour donne le chemin")
        self.assertIsNone(chemin_journal({"session_id": "../../etc"}, m))
        self.assertIsNone(chemin_journal({"session_id": ""}, m))
        self.assertIsNone(chemin_journal({}, m))

    def test_le_nom_du_menu_designe_le_dossier(self):
        a = ["OPS", "Projet QA", "QA"]
        self.assertEqual(correspond("ops", a), "OPS")
        self.assertEqual(correspond("projet-qa", a), "Projet QA")
        self.assertEqual(correspond("QA", a), "QA")
        self.assertIsNone(correspond("reviewer", a))
        self.assertEqual(nom_de_profil("Projet QA"), "projet-qa")

    def test_la_regle_menu_dossier_defaut(self):
        d = self.projet("regle", ["OPS", "PO", "QA"])

        def lecture(c):
            return Lecture(chemin=os.path.join(d, "j"), trouve=True, lignes=9, compactions=0, choix=c)

        # 1. Le menu gagne, et le harnais se place dans le dossier de l'agent.
        s = resous(d, lecture(Choix("agent", "ops", 2)))
        self.assertEqual(s.actif, "OPS")
        self.assertEqual(s.source, Source("menu", 2))
        self.assertEqual(s.place, os.path.join(d, "agents", "OPS"))

        # 2. Rien de choisi, session lancée dans un dossier d'agent : lui, sur place.
        s = resous(os.path.join(d, "agents/PO"), lecture(Choix("rien")))
        self.assertEqual((s.actif, s.source, s.place), ("PO", Source("dossier"), None))

        # 3. « Default agent » ou rien, à la racine : QA, et c'est dit.
        s = resous(d, lecture(Choix("retire", None, 80)))
        self.assertEqual((s.actif, s.source), ("QA", Source("defaut", 80)))
        self.assertEqual(s.place, os.path.join(d, "agents", "QA"))
        s = resous(d, Lecture())
        self.assertEqual((s.actif, s.source), ("QA", Source("defaut", None)))

        # Un agent du menu qui n'est pas du projet ne prend PAS le défaut.
        s = resous(d, lecture(Choix("agent", "reviewer", 4)))
        self.assertEqual((s.actif, s.place), (None, None))
        self.assertEqual(s.source.genre, "inconnu")

        # Le menu l'emporte sur le dossier.
        s = resous(os.path.join(d, "agents/PO"), lecture(Choix("agent", "ops", 3)))
        self.assertEqual(s.place, os.path.join(d, "agents", "OPS"))

    def test_sans_qa_ni_choix_aucun_agent_et_mono_reste_mono(self):
        d = self.projet("sans-qa", ["OPS", "PO"])
        s = resous(d, Lecture())
        self.assertEqual((s.actif, s.source, s.place), (None, Source("aucun"), None))
        tete, _ = lignes_briefing(s)
        t = "\n".join(tete)
        self.assertTrue("agent  : AUCUN" in t and "RIEN n'est gardé" in t, t)

        # Un dossier `agents/` de CODE, sans esprit : le projet reste mono.
        d = self.projet("mono", [])
        os.makedirs(os.path.join(d, "agents/QA"))
        s = resous(d, Lecture())
        self.assertEqual(s.agents, [])
        self.assertEqual((s.place, len(lignes_briefing(s)[0])), (None, 0))

    def test_dans_une_copie_de_travail_le_placement_vise_la_copie(self):
        d = self.projet("copie", ["OPS", "QA"])
        w = os.path.join(self.dossier("copie-w"), "session")
        git(d, "worktree", "add", "-q", "-b", "session", w)
        w = os.path.realpath(w)
        s = resous(w, Lecture(choix=Choix("agent", "ops", 2)))
        self.assertEqual(s.place, os.path.join(w, "agents", "OPS"), "jamais le dossier principal")
        tete, fin = lignes_briefing(s)
        self.assertTrue("OPS" in tete[0] and "ligne 2" in tete[0], repr(tete))
        self.assertTrue(any(l == "RÔLE-OPS" for l in fin), "le rôle est MONTRÉ : %r" % (fin,))
        self.assertIn("agents/OPS/AGENTS.md", fin[0], "chemin relatif à la vraie session : %s" % fin[0])
        git(d, "worktree", "remove", "--force", w)

    def test_le_role_est_servi_hors_de_son_dossier_seulement_et_borne(self):
        d = self.projet("role", ["OPS", "QA"])
        # Dans son dossier : Copilot charge le rôle, le briefing ne le double pas.
        s = resous(os.path.join(d, "agents/OPS"), Lecture())
        self.assertEqual(lignes_briefing(s)[1], [])
        # Un rôle trop long est coupé, et c'est dit.
        long = "".join("ligne %d\n" % i for i in range(400))
        ecris(os.path.join(d, "agents/QA/AGENTS.md"), long)
        s = resous(d, Lecture())
        fin = lignes_briefing(s)[1]
        self.assertTrue(any("coupé" in l for l in fin))
        self.assertTrue(len(fin) < 260)

    def test_la_signature_change_avec_l_agent_le_choix_et_la_compaction_pas_avec_la_lecture(self):
        d = self.projet("signature", ["OPS", "QA"])

        def lu(c, n, k):
            return Lecture(chemin=os.path.join(d, "j"), trouve=True, lignes=n, compactions=k, choix=c)

        a = resous(d, lu(Choix("agent", "ops", 2), 10, 0)).signature()
        self.assertEqual(a, resous(d, lu(Choix("agent", "ops", 2), 99, 0)).signature())
        self.assertNotEqual(a, resous(d, lu(Choix("agent", "ops", 95), 99, 0)).signature(),
                            "un retour sur ops après « Default agent » rebriefe")
        self.assertNotEqual(a, resous(d, lu(Choix("agent", "ops", 2), 99, 1)).signature(),
                            "une compaction rebriefe")
        self.assertNotEqual(a, resous(d, lu(Choix("retire", None, 80), 99, 0)).signature())


if __name__ == "__main__":
    unittest.main()

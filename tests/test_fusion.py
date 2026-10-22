# -*- coding: utf-8 -*-
"""FUSIONNER SANS RIEN PERDRE DE LA MÉMOIRE (2.2.0) — deux personnes, un projet.

Un dépôt distant, deux copies (A et B), un projet logé. A et B écrivent chacun
dans le même `todo.md` ; A pousse le premier. Chaque règle se voit MORDRE, et se
taire quand le travail de l'autre est intégré."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
from test_loge import MAIN, _env  # noqa: E402

TODO = "svc/flux_a/brain/mind/OPS/todo.md"


class DeuxCopies(unittest.TestCase):
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "home"))
        self.distant = os.path.join(self.d, "distant.git")
        self.sh(self.d, "git", "init", "-q", "--bare", "-b", "main", self.distant)
        self.a = os.path.join(self.d, "a")
        self.b = os.path.join(self.d, "b")
        self.sh(self.d, "git", "clone", "-q", self.distant, self.a)
        os.makedirs(os.path.join(self.a, "svc", "flux_a"))
        self.ecrit(self.a, "svc/flux_a/a.py", "a = 1\n")
        self.sh(self.a, "git", "add", "-A")
        self.sh(self.a, "git", "commit", "-qm", "init")
        self.sh(self.a, sys.executable, MAIN, "adopte", "--projet", "svc/flux_a", "--equipe", "OPS,PO",
                "--nom", "flux-a", "--go")
        self.ajoute(self.a, TODO, "- [ ] tâche commune !moyen\n")
        self.sh(self.a, "git", "add", "-A")
        self.sh(self.a, "git", "commit", "-qm", "harnais")
        self.sh(self.a, "git", "push", "-q", "-u", "origin", "main")
        self.sh(self.d, "git", "clone", "-q", self.distant, self.b)
        # A avance ; B écrit de son côté sans avoir tiré.
        self.ajoute(self.a, TODO, "- [ ] tâche de A !haut\n")
        self.sh(self.a, "git", "commit", "-qam", "A")
        self.sh(self.a, "git", "push", "-q")
        self.ajoute(self.b, TODO, "- [ ] tâche de B !bas\n")
        self.sh(self.b, "git", "commit", "-qam", "B")

    def sh(self, cwd, *a, ok=True):
        r = subprocess.run(list(a), cwd=cwd, env=_env(self.d), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr.decode())
        return r

    def ecrit(self, ou, p, t):
        with open(os.path.join(ou, *p.split("/")), "w", encoding="utf-8") as h:
            h.write(t)

    def ajoute(self, ou, p, t):
        os.makedirs(os.path.dirname(os.path.join(ou, *p.split("/"))), exist_ok=True)
        with open(os.path.join(ou, *p.split("/")), "a", encoding="utf-8") as h:
            h.write(t)

    def vieux_fetch(self, ou):
        f = os.path.join(ou, ".git", "FETCH_HEAD")
        if not os.path.exists(f):
            open(f, "w").close()
        os.utime(f, (1000000000, 1000000000))

    def garde(self, commande, ou=None):
        ou = ou or self.b
        c = {"tool_name": "bash", "cwd": ou, "tool_input": {"command": commande}}
        r = subprocess.run([sys.executable, MAIN, "production"], cwd=ou, input=json.dumps(c).encode(),
                           env=_env(self.d, COPILOT_PROJECT_DIR=ou), stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        t = r.stdout.decode("utf-8").strip()
        return json.loads(t)["permissionDecisionReason"] if t else None

    def rebase_en_conflit(self):
        self.sh(self.b, "git", "pull", "-q", "--rebase", ok=False)
        self.assertTrue(os.path.exists(os.path.join(self.b, ".git", "REBASE_HEAD")))


class RecupererDabord(DeuxCopies):
    def test_pousser_sans_fetch_recent_est_refuse(self):
        self.vieux_fetch(self.b)
        m = self.garde("git push")
        self.assertIsNotNone(m)
        self.assertIn("git fetch", m)
        # Le témoin : `git pull` récupère de lui-même, il passe.
        self.assertIsNone(self.garde("git pull --rebase"))

    def test_pousser_en_retard_sur_la_branche_suivie_est_refuse(self):
        self.sh(self.b, "git", "fetch", "-q")
        m = self.garde("git push")
        self.assertIsNotNone(m)
        self.assertIn("origin/main", m)
        self.assertIn(TODO, m)
        self.assertIsNotNone(self.garde("git merge feature"))
        # Depuis un autre dossier, par `cd` : la garde suit la copie où git tourne.
        self.assertIsNotNone(self.garde("cd b && git push origin HEAD:refs/for/main", ou=self.d))

    def test_pousser_a_jour_passe(self):
        self.sh(self.a, "git", "fetch", "-q")
        self.assertIsNone(self.garde("git push", ou=self.a))

    def test_fusion_ok_leve_la_regle(self):
        self.vieux_fetch(self.b)
        self.assertIsNone(self.garde("git push # fusion-ok"))

    def test_un_depot_sans_memoire_n_est_pas_concerne(self):
        c = os.path.join(self.d, "c")
        self.sh(self.d, "git", "clone", "-q", self.distant, c)
        shutil.rmtree(os.path.join(c, "svc"))
        shutil.rmtree(os.path.join(c, ".github"))
        self.vieux_fetch(c)
        self.assertIsNone(self.garde("git push", ou=c))


class RienPerdu(DeuxCopies):
    def test_une_resolution_qui_perd_les_lignes_de_l_autre_est_refusee(self):
        self.rebase_en_conflit()
        # Pendant un rebase, « theirs » est le commit de B : celui de A disparaît.
        self.sh(self.b, "git", "checkout", "-q", "--theirs", TODO)
        self.sh(self.b, "git", "add", TODO)
        m = self.garde("git rebase --continue")
        self.assertIsNotNone(m)
        self.assertIn("tâche de A", m)
        self.assertNotIn("tâche de B", m)

    def test_des_marqueurs_de_conflit_indexes_sont_refuses(self):
        self.rebase_en_conflit()
        self.sh(self.b, "git", "add", TODO)
        m = self.garde("git rebase --continue")
        self.assertIsNotNone(m)
        self.assertIn("marqueurs", m)

    def test_une_resolution_qui_garde_les_deux_cotes_passe(self):
        self.rebase_en_conflit()
        with open(os.path.join(self.b, *TODO.split("/")), encoding="utf-8") as h:
            t = [x for x in h.read().splitlines(True)
                 if not x.startswith(("<<<<<<<", "=======", ">>>>>>>"))]
        self.ecrit(self.b, TODO, "".join(t))
        self.sh(self.b, "git", "add", TODO)
        self.assertIsNone(self.garde("git rebase --continue"))
        # Une tâche cochée d'un côté remplace l'ancienne : pas de perte.
        self.sh(self.b, "git", "-c", "core.editor=true", "rebase", "--continue")

    def test_une_fusion_par_merge_est_jugee_aussi(self):
        self.sh(self.b, "git", "fetch", "-q")
        self.sh(self.b, "git", "merge", "-q", "origin/main", ok=False)
        self.assertTrue(os.path.exists(os.path.join(self.b, ".git", "MERGE_HEAD")))
        self.sh(self.b, "git", "checkout", "-q", "--ours", TODO)
        self.sh(self.b, "git", "add", TODO)
        m = self.garde("git commit -m fusion")
        self.assertIsNotNone(m)
        self.assertIn("tâche de A", m)
        self.assertIsNone(self.garde("git commit -m fusion # fusion-ok"))

    def test_une_tache_avancee_d_un_cote_n_exige_pas_l_ancienne(self):
        # A coche la tâche commune ; B ajoute la sienne ; la résolution garde la
        # version cochée et la tâche de B : rien n'est perdu.
        with open(os.path.join(self.a, *TODO.split("/")), encoding="utf-8") as h:
            t = h.read()
        self.ecrit(self.a, TODO, t.replace("- [ ] tâche commune !moyen", "- [x] tâche commune !moyen"))
        self.sh(self.a, "git", "commit", "-qam", "A coche")
        self.sh(self.a, "git", "push", "-q")
        self.rebase_en_conflit()
        a_lignes = self.sh(self.b, "git", "show", "origin/main:" + TODO).stdout.decode()
        self.ecrit(self.b, TODO, a_lignes + "- [ ] tâche de B !bas\n")
        self.sh(self.b, "git", "add", TODO)
        self.assertIsNone(self.garde("git rebase --continue"))

    def test_hors_operation_un_commit_n_est_pas_juge(self):
        self.assertIsNone(self.garde("git commit -m rien"))


class Briefing(DeuxCopies):
    def test_le_briefing_dit_que_la_branche_suivie_a_avance(self):
        self.sh(self.b, "git", "fetch", "-q")
        sys.path.insert(0, os.path.join(os.path.dirname(ICI), "py"))
        r = subprocess.run([sys.executable, "-c", "import fusion,sys;print(fusion.ligne_briefing(sys.argv[1]))",
                            os.path.join(self.b, "svc", "flux_a", "brain", "mind", "OPS")],
                           cwd=os.path.join(os.path.dirname(ICI), "py"), env=_env(self.d, PYTHONIOENCODING="utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        t = r.stdout.decode("utf-8")
        self.assertIn("origin/main", t, r.stderr.decode())
        self.assertIn("1 fichier(s) de la mémoire", t)
        r = subprocess.run([sys.executable, "-c", "import fusion,sys;print(fusion.ligne_briefing(sys.argv[1]))",
                            os.path.join(self.a, "svc", "flux_a", "brain", "mind", "OPS")],
                           cwd=os.path.join(os.path.dirname(ICI), "py"), env=_env(self.d, PYTHONIOENCODING="utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Le témoin : A a tout intégré — aucun retard à signaler.
        self.assertNotIn("commit(s) que tu n'as pas", r.stdout.decode("utf-8"))


class Arrivees(DeuxCopies):
    """Le briefing dit ce que les autres ont apporté — une fois, au bon moment."""

    def briefing(self, session="s", evenement="SessionStart"):
        j = os.path.join(self.d, "journal.jsonl")
        with open(j, "w") as h:
            h.write(json.dumps({"type": "subagent.selected", "data": {"agentName": "flux-a-ops"}}) + "\n")
        c = {"hook_event_name": evenement, "session_id": session, "transcript_path": j, "cwd": self.b}
        r = subprocess.run([sys.executable, MAIN, "briefing"], cwd=self.b, input=json.dumps(c).encode(),
                           env=_env(self.d, COPILOT_PROJECT_DIR=self.b, PYTHONIOENCODING="utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        t = r.stdout.decode("utf-8").strip()
        return json.loads(t)["additionalContext"] if t else ""

    def setUp(self):
        super().setUp()
        # B n'est pas l'auteur de A : chaque copie a son identité.
        self.sh(self.b, "git", "config", "user.email", "b@b")
        self.sh(self.b, "git", "reset", "-q", "--hard", "HEAD~1")    # B n'a rien écrit…
        self.sh(self.b, "git", "pull", "-q", "--rebase")              # … et a tout intégré
        self.premier = self.briefing("s0")                             # le curseur est posé

    def pousse_de_a(self, chemin, ligne, message):
        self.sh(self.a, "git", "pull", "-q", "--rebase")
        self.ajoute(self.a, chemin, ligne)
        self.sh(self.a, "git", "add", "-A")
        self.sh(self.a, "git", "commit", "-q", "--author", "Autre <autre@x>", "-m", message)
        self.sh(self.a, "git", "push", "-q")

    def test_un_pull_qui_apporte_la_memoire_est_dit_une_fois(self):
        self.assertNotIn("arrivé :", self.premier, "le premier passage n'annonce pas l'historique")
        self.pousse_de_a(TODO, "- [ ] encore A !haut\n", "A1")
        self.pousse_de_a("svc/flux_a/.logs/2026-10-22.md", "- A a travaillé\n", "A2")
        self.sh(self.b, "git", "pull", "-q", "--rebase")
        t = self.briefing("s1", "UserPromptSubmit")
        self.assertIn("arrivé : 2 commit(s) de Autre", t)
        self.assertIn("brain/mind/OPS/todo.md", t)
        self.assertIn(".logs/2026-10-22.md", t)
        self.assertNotIn("svc/flux_a/brain", t.split("arrivé :")[1].split("\n")[0])
        # Une fois : au message suivant, rien n'a changé — pas de second briefing.
        self.assertEqual(self.briefing("s1", "UserPromptSubmit"), "")
        # Et une nouvelle session ne la redit pas : elle a été lue.
        self.assertNotIn("arrivé :", self.briefing("s2"))

    def test_seuls_les_journaux_suffisent_a_relancer_le_briefing(self):
        self.briefing("s1", "UserPromptSubmit")
        self.pousse_de_a("svc/flux_a/.logs/2026-10-22.md", "- A a travaillé\n", "A")
        self.sh(self.b, "git", "pull", "-q", "--rebase")
        self.assertIn("arrivé : 1 commit(s) de Autre", self.briefing("s1", "UserPromptSubmit"))

    def test_le_code_seul_ou_mes_propres_commits_ne_sont_pas_annonces(self):
        # Témoin 1 : A ne touche que le code.
        self.pousse_de_a("svc/flux_a/a.py", "b = 2\n", "code")
        # Témoin 2 : B écrit dans la mémoire, sous son nom.
        self.ajoute(self.b, "svc/flux_a/brain/mind/PO/todo.md", "- [ ] tâche de B !bas\n")
        self.sh(self.b, "git", "commit", "-q", "--author", "Moi <b@b>", "-am", "B")
        self.sh(self.b, "git", "pull", "-q", "--rebase")
        self.assertNotIn("arrivé :", self.briefing("s1"))


if __name__ == "__main__":
    unittest.main()

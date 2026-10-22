# -*- coding: utf-8 -*-
"""UN PROJET LOGÉ DANS UN DÉPÔT DE CODE (2.2.0) — `adopte --projet`.

Un dépôt héberge plusieurs projets, chacun dans son dossier, chacun avec sa
mémoire à côté de son code. La session s'ouvre à la racine ; le profil choisi
dans le menu désigne le projet. Chaque test fait MORDRE ce qu'il prouve, et
garde un témoin qui doit passer."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
MAIN = os.path.join(RACINE, "py", "main.py")


def _env(d, **plus):
    e = dict(os.environ)
    for k in ("COPILOT_PROJECT_DIR", "HARNAIS_JUGE", "COPILOT_PLUGIN_ROOT", "PLUGIN_ROOT"):
        e.pop(k, None)
    e.update({"COPILOT_HOME": os.path.join(d, "home"), "COPILOT_PLUGIN_DATA": os.path.join(d, "data"),
              "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
              "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1"})
    e.update(plus)
    return e


class Banc(unittest.TestCase):
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "home"))
        self.depot = os.path.join(self.d, "depot")
        for p in ("svc/flux_a", "svc/flux_b"):
            os.makedirs(os.path.join(self.depot, *p.split("/")))
        with open(os.path.join(self.depot, "svc", "flux_a", "a.py"), "w") as h:
            h.write("a = 1\n")
        with open(os.path.join(self.depot, "svc", "flux_b", "b.py"), "w") as h:
            h.write("b = 1\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def git(self, *a, ok=True):
        r = subprocess.run(["git", "-C", self.depot] + list(a), env=_env(self.d),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr.decode())
        return r.stdout.decode()

    def harnais(self, *a, stdin=None, cwd=None, **env):
        r = subprocess.run([sys.executable, MAIN] + list(a), cwd=cwd or self.depot,
                           env=_env(self.d, **env), input=(stdin or "").encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")

    def adopte(self, dossier, roles, court, *plus):
        rc, out, err = self.harnais("adopte", "--projet", dossier, "--equipe", roles, "--nom", court,
                                    "--go", *plus)
        self.assertEqual(rc, 0, out + err)
        return out

    def journal(self, nom):
        j = os.path.join(self.d, nom + ".jsonl")
        with open(j, "w") as h:
            h.write(json.dumps({"type": "subagent.selected", "data": {"agentName": nom}}) + "\n")
        return j

    def hook(self, sous, charge):
        return self.harnais(sous, stdin=json.dumps(charge), COPILOT_PROJECT_DIR=self.depot)

    def lis(self, *p):
        with open(os.path.join(self.depot, *p), encoding="utf-8") as h:
            return h.read()


class Adoption(Banc):
    def test_la_memoire_vit_dans_le_dossier_du_projet_et_les_profils_a_la_racine(self):
        self.adopte("svc/flux_a", "OPS,PO,QA", "flux-a")
        for p in ("svc/flux_a/brain/fact/base.md", "svc/flux_a/brain/fact/roles.md",
                  "svc/flux_a/brain/mind/OPS/state.md", "svc/flux_a/brain/mind/QA/todo.md",
                  "svc/flux_a/docs/decisions.md", ".github/agents/flux-a-ops.agent.md",
                  ".github/copilot/perimetres/flux-a-qa.json"):
            self.assertTrue(os.path.isfile(os.path.join(self.depot, *p.split("/"))), p)
        # Le témoin : rien à la racine, et le paquet n'y est PAS déclaré — le
        # chemin d'un poste serait faux sur celui d'à côté.
        self.assertFalse(os.path.exists(os.path.join(self.depot, "brain")))
        self.assertFalse(os.path.exists(os.path.join(self.depot, ".github", "copilot", "settings.json")))
        p = self.lis(".github", "agents", "flux-a-ops.agent.md")
        self.assertIn('<!-- harnais:projet dossier="svc/flux_a" esprit="OPS" -->', p)
        self.assertIn("name: flux-a-ops\n", p.split("---\n")[1])
        self.assertIn("merge=union", self.lis("svc", "flux_a", ".gitattributes"))

    def test_rien_ne_s_ecrase_et_un_second_passage_ne_pose_rien(self):
        self.adopte("svc/flux_a", "OPS,PO", "flux-a")
        with open(os.path.join(self.depot, "svc", "flux_a", "brain", "mind", "OPS", "todo.md"), "a") as h:
            h.write("- [ ] à moi\n")
        out = self.adopte("svc/flux_a", "OPS,PO", "flux-a")
        self.assertIn("déjà au harnais", out)
        self.assertIn("- [ ] à moi", self.lis("svc", "flux_a", "brain", "mind", "OPS", "todo.md"))

    def test_un_profil_d_un_autre_projet_n_est_pas_repris(self):
        self.adopte("svc/flux_a", "OPS", "flux")
        rc, out, err = self.harnais("adopte", "--projet", "svc/flux_b", "--equipe", "OPS", "--nom", "flux")
        self.assertNotEqual(rc, 0)
        self.assertIn("désigne déjà svc/flux_a", err)

    def test_la_racine_et_un_dossier_absent_sont_refuses(self):
        for d in (".", "svc/absent", ".."):
            rc, _, err = self.harnais("adopte", "--projet", d, "--equipe", "OPS")
            self.assertNotEqual(rc, 0, d)


class Resolution(Banc):
    def setUp(self):
        super().setUp()
        self.adopte("svc/flux_a", "OPS,PO,QA", "flux-a")
        self.adopte("svc/flux_b", "OPS,QA", "flux-b")

    def test_l_agent_choisi_dans_le_menu_se_place_dans_l_esprit_de_son_projet(self):
        rc, out, _ = self.harnais("agent", "--racine", self.depot, "--journal", self.journal("flux-b-ops"))
        self.assertEqual(rc, 0)
        self.assertIn("actif   : flux-b-ops", out)
        self.assertIn(os.path.join("svc", "flux_b", "brain", "mind", "OPS"), out)
        # Le témoin : l'autre projet a son OPS, et ce n'est pas lui.
        rc, out, _ = self.harnais("agent", "--racine", self.depot, "--journal", self.journal("flux-a-ops"))
        self.assertIn(os.path.join("svc", "flux_a", "brain", "mind", "OPS"), out)

    def test_la_resolution_rend_les_chemins_du_projet(self):
        rc, out, _ = self.harnais("resolution", os.path.join(self.depot, "svc", "flux_a", "brain", "mind", "PO"))
        r = json.loads(out)
        self.assertEqual(r["forme"], "brain")
        self.assertEqual(r["prefixe_fact"], "svc/flux_a/brain/fact/")
        self.assertEqual(r["prefixe_mind"], "svc/flux_a/brain/mind/PO/")
        self.assertEqual(r["nom_agent"], "PO")
        # Le témoin : à la racine, aucune mémoire — on ne mêle pas les projets.
        rc, out, _ = self.harnais("resolution", self.depot)
        self.assertEqual(json.loads(out)["forme"], "sans-memoire")

    def test_le_perimetre_borne_l_agent_a_son_projet(self):
        j = self.journal("flux-a-ops")

        def ecrit(p):
            rc, out, _ = self.hook("perimetre", {"tool_name": "edit", "transcript_path": j, "cwd": self.depot,
                                                 "tool_input": {"path": os.path.join(self.depot, *p.split("/"))}})
            return "deny" in out
        self.assertTrue(ecrit("svc/flux_b/b.py"), "le code d'un autre projet")
        self.assertTrue(ecrit("svc/flux_b/brain/mind/OPS/todo.md"), "la mémoire d'un autre projet")
        self.assertTrue(ecrit("svc/flux_a/brain/mind/PO/todo.md"), "l'esprit d'un pair")
        self.assertTrue(ecrit("svc/flux_a/brain/fact/base.md"), "les faits : un seul écrivain")
        self.assertTrue(ecrit("README.md"), "la racine du dépôt")
        # Les témoins : son code, son esprit, ses livrables.
        self.assertFalse(ecrit("svc/flux_a/a.py"))
        self.assertFalse(ecrit("svc/flux_a/brain/mind/OPS/todo.md"))
        self.assertFalse(ecrit("svc/flux_a/assets/OPS/plan.md"))

    def test_le_briefing_nomme_le_projet_et_ses_faits(self):
        rc, out, _ = self.hook("briefing", {"hook_event_name": "SessionStart", "session_id": "s",
                                            "transcript_path": self.journal("flux-a-qa"), "cwd": self.depot})
        t = json.loads(out)["additionalContext"]
        self.assertIn("Briefing d'entrée · flux_a · QA", t)
        self.assertIn("svc/flux_a/brain/fact/base.md", t)
        self.assertIn("svc/flux_a/docs/decisions.md", t)
        self.assertNotIn("svc/flux_b", t)

    def test_la_garde_de_commit_suit_l_etat_de_l_agent_du_projet(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "harnais")
        j = self.journal("flux-a-ops")
        with open(os.path.join(self.depot, "svc", "flux_a", "a.py"), "a") as h:
            h.write("a = 2\n")
        self.git("add", "svc/flux_a/a.py")
        c = {"tool_name": "bash", "tool_input": {"command": "git commit -m x"}, "transcript_path": j,
             "cwd": self.depot}
        rc, out, _ = self.hook("mind-guard", c)
        self.assertIn("svc/flux_a/brain/mind/OPS/state.md", out)
        # Le témoin : l'état mis à jour, le commit passe.
        f = os.path.join(self.depot, "svc", "flux_a", "brain", "mind", "OPS", "state.md")
        with open(f, encoding="utf-8") as h:
            t = h.read()
        with open(f, "w", encoding="utf-8") as h:
            h.write(t.replace("jalon:", "jalon: essai —", 1))
        self.git("add", "svc/flux_a/brain/mind/OPS/state.md")
        rc, out, _ = self.hook("mind-guard", c)
        self.assertEqual(out.strip(), "")

    def test_les_faits_d_un_autre_projet_sont_verrouilles_aussi(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "harnais")
        with open(os.path.join(self.depot, "svc", "flux_b", "brain", "fact", "base.md"), "a") as h:
            h.write("\nautre\n")
        self.git("add", "-A")
        c = {"tool_name": "bash", "tool_input": {"command": "git commit -m x"},
             "transcript_path": self.journal("flux-a-ops"), "cwd": self.depot}
        rc, out, _ = self.hook("mind-guard", c)
        self.assertIn("svc/flux_b/brain/fact/base.md", out)
        c["tool_input"]["command"] = "git commit -m x # fact-ok"
        rc, out, _ = self.hook("mind-guard", c)
        self.assertNotIn("svc/flux_b/brain/fact", out)

    def test_le_journal_s_ecrit_dans_le_dossier_du_projet(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "harnais")
        rc, out, err = self.hook("apres-bash", {"tool_name": "bash", "cwd": self.depot,
                                                "tool_input": {"command": "git commit -m harnais"},
                                                "transcript_path": self.journal("flux-b-qa")})
        self.assertEqual(rc, 0, err)
        logs = os.path.join(self.depot, "svc", "flux_b", ".logs")
        self.assertTrue(os.path.isdir(logs), err)
        self.assertTrue(all(f.endswith("-QA.md") for f in os.listdir(logs)), os.listdir(logs))
        self.assertFalse(os.path.exists(os.path.join(self.depot, ".logs")))

    def test_la_vue_d_equipe_rend_une_ligne_par_projet(self):
        rc, out, err = self.harnais("equipe-vue", "--racine", self.d, "--projet", "depot")
        self.assertEqual(rc, 0, err)
        self.assertIn("── depot / svc/flux_a", out)
        self.assertIn("── depot / svc/flux_b", out)
        # Le témoin : la racine sans mémoire n'a pas sa ligne.
        self.assertNotIn("── depot  ", out)


class Migration(Banc):
    def setUp(self):
        super().setUp()
        rc, out, err = self.harnais("adopte", ".", "--equipe", "OPS,PO,QA", "--compact", "--go")
        self.assertEqual(rc, 0, out + err)
        os.makedirs(os.path.join(self.depot, "assets", "OPS"))
        with open(os.path.join(self.depot, "assets", "OPS", "plan.md"), "w") as h:
            h.write("plan\n")
        with open(os.path.join(self.depot, "brain", "mind", "OPS", "todo.md"), "a") as h:
            h.write("- [ ] le travail d'avant\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "brain racine")

    def test_la_memoire_de_racine_descend_avec_son_historique(self):
        rc, out, _ = self.harnais("adopte", "--projet", "svc/flux_a", "--equipe", "OPS,PO,QA",
                                  "--nom", "flux-a", "--depuis-racine")
        self.assertIn("DESCEND DE LA RACINE", out)
        self.assertTrue(os.path.isdir(os.path.join(self.depot, "brain")), "à blanc : rien ne bouge")
        self.adopte("svc/flux_a", "OPS,PO,QA", "flux-a", "--depuis-racine")
        self.assertFalse(os.path.exists(os.path.join(self.depot, "brain")))
        self.assertIn("le travail d'avant", self.lis("svc", "flux_a", "brain", "mind", "OPS", "todo.md"))
        self.assertEqual(self.lis("svc", "flux_a", "assets", "OPS", "plan.md"), "plan\n")
        st = self.git("status", "--porcelain")
        self.assertIn("R  brain/mind/OPS/todo.md -> svc/flux_a/brain/mind/OPS/todo.md", st)
        self.assertFalse(os.path.exists(os.path.join(self.depot, ".github", "agents", "ops.agent.md")))
        g = json.loads(self.lis(".github", "copilot", "perimetres", "flux-a-ops.json"))
        self.assertIn("svc/flux_a/brain/mind/PO", g["deny"])
        self.assertEqual(g["allow"], ["svc/flux_a"])
        q = json.loads(self.lis(".github", "copilot", "perimetres", "flux-a-qa.json"))
        self.assertIn("svc/flux_a/brain/mind/QA", q["allow"])
        self.assertIn('dossier="svc/flux_a" esprit="QA"', self.lis(".github", "agents", "flux-a-qa.agent.md"))
        rc, out, _ = self.harnais("agent", "--racine", self.depot, "--journal", self.journal("flux-a-ops"))
        self.assertIn("actif   : flux-a-ops", out)

    def test_une_memoire_deja_dans_le_projet_n_est_pas_ecrasee(self):
        os.makedirs(os.path.join(self.depot, "svc", "flux_a", "brain", "fact"))
        rc, _, err = self.harnais("adopte", "--projet", "svc/flux_a", "--equipe", "OPS",
                                  "--nom", "flux-a", "--depuis-racine", "--go")
        self.assertNotEqual(rc, 0)
        self.assertIn("existe déjà", err)
        self.assertTrue(os.path.isdir(os.path.join(self.depot, "brain", "mind", "OPS")))


if __name__ == "__main__":
    unittest.main()

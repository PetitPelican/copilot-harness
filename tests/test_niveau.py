# -*- coding: utf-8 -*-
"""`harnais mise-a-niveau` — sur des projets FABRIQUÉS, jamais sur un vrai.

Le contrat : ne rien perdre des données actuelles, changer seulement
l'architecture. D'où le premier essai : chaque fichier de la mémoire se retrouve,
à l'octet, à sa nouvelle adresse — et l'historique du dépôt de mémoire avec lui.
Les droits d'un agent (`perimetre.json`) suivent, l'espace des livrables passe à
`assets/` s'il n'y en a pas déjà un, la forme compacte est nommée sans être touchée.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _isole import Isole, git, ecris, lis  # noqa: E402
import banc_equipe  # noqa: E402
import memoire  # noqa: E402
import niveau  # noqa: E402
from memoire import Forme  # noqa: E402

ETAT = "---\nmaj: 2026-10-14\nsante: vert\njalon: j\n---\n"


def lance(args):
    s = io.StringIO()
    with contextlib.redirect_stdout(s):
        rc = niveau.main(args)
    return rc, s.getvalue()


def inventaire(r):
    d = {}
    for b, ds, fs in os.walk(r):
        ds[:] = [x for x in ds if x != ".git"]
        for f in fs:
            p = os.path.join(b, f)
            with open(p, "rb") as h:
                d[os.path.relpath(p, r).replace(os.sep, "/")] = hashlib.sha256(h.read()).hexdigest()
    return d


def droits(p, agent):
    return json.loads(lis(os.path.join(p, "agents", agent, ".github", "copilot", "perimetre.json")))


class Base(Isole):
    def setUp(self):
        super(Base, self).setUp()
        self.maison = os.path.realpath(self.dossier("niveau"))

    def depot(self, nom="Proj"):
        p = os.path.join(self.maison, nom)
        os.makedirs(p)
        git(p, "init", "-q", "-b", "main")
        return p

    def deportee(self, distant=True, en_trop=False):
        """Une équipe en forme déportée : `memoire/` est un dépôt à part, ignoré par
        celui du code ; les droits visent l'ancien chemin (relatifs ET absolus)."""
        p = self.depot()
        ecris(os.path.join(p, ".gitignore"), "node_modules/\nmemoire/\n")
        ecris(os.path.join(p, "AGENTS.md"), "# Proj\n\nLes faits : `memoire/.fact/`.\n")
        for a in ("OPS", "QA"):
            autre = "QA" if a == "OPS" else "OPS"
            ecris(os.path.join(p, "agents", a, "AGENTS.md"), "# %s\n" % a)
            ecris(os.path.join(p, "agents", a, ".github", "copilot", "perimetre.json"), json.dumps({
                "deny": ["memoire/agents/%s" % autre,
                         os.path.join(p, "memoire", "agents", autre),
                         "memoire-old", "apps/web"],
                "allow": ["memoire/agents/%s/.mind" % a],
            }, indent=2) + "\n")
        git(p, "add", "-A")
        git(p, "commit", "-qm", "code")
        m = os.path.join(p, "memoire")
        for f in ("base.md", "stack.md", "architecture.md", "rules.md", "roles.md", "workflow.md"):
            ecris(os.path.join(m, ".fact", f), "---\ncap: le cap\n---\n\n# %s\n" % f if f == "base.md" else "# %s\n\nvrai\n" % f)
        if en_trop:
            ecris(os.path.join(m, ".fact", "questions.md"), "# en trop\n")
        for a in ("OPS", "QA", "ANCIEN"):
            ecris(os.path.join(m, "agents", a, ".mind", "state.md"), ETAT)
            ecris(os.path.join(m, "agents", a, ".mind", "todo.md"), "- [ ] tâche de %s\n" % a)
        ecris(os.path.join(m, "agents", "OPS", "preuves", "capture.txt"), "preuve\n")
        ecris(os.path.join(m, "equipe", "2026-10-OPS.md"), "une entrée du carnet\n")
        ecris(os.path.join(m, "branding", "logo.svg"), "<svg/>\n")
        git(m, "init", "-q", "-b", "main")
        git(m, "add", "-A")
        git(m, "commit", "-qm", "mémoire")
        if distant:
            d = os.path.join(self.maison, "distant.git")
            git(self.maison, "init", "-q", "--bare", d)
            git(m, "remote", "add", "origin", d)
        return p

    def brain_equipe(self, nom="Equipe", agents=("OPS", "QA")):
        """Une équipe « dossier d'avant » : `brain/mind/<nom>` + `agents/<nom>/`."""
        p = self.depot(nom)
        ecris(os.path.join(p, "brain", "fact", "base.md"), "---\ncap: x\n---\n")
        for a in agents:
            ecris(os.path.join(p, "brain", "mind", a, "state.md"), ETAT)
            ecris(os.path.join(p, "brain", "mind", a, "todo.md"), "- [ ] t\n")
            ecris(os.path.join(p, "agents", a, "AGENTS.md"), "# %s\n" % a)
            ecris(os.path.join(p, "agents", a, ".github", "copilot", "perimetre.json"), json.dumps({
                "deny": ["agents/%s" % x for x in agents if x != a]
                        + ["brain/mind/%s" % x for x in agents if x != a] + ["outputs/%s" % x for x in agents if x != a],
                "allow": ["outputs/%s" % a]}, indent=2) + "\n")
        return p

    def valide(self, p, message="c"):
        git(p, "add", "-A")
        git(p, "commit", "-qm", message)


class Deportee(Base):
    def test_rien_ne_se_perd_et_l_historique_suit(self):
        p = self.deportee()
        m = os.path.join(p, "memoire")
        avant = inventaire(m)
        n_avant = int(git(m, "rev-list", "--count", "HEAD").strip())
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 0, out)
        b = os.path.join(p, "brain")
        apres = inventaire(b)

        def adresse(x):
            x = re.sub(r"^\.fact/", "fact/", x)
            x = re.sub(r"^agents/([^/]+)/\.mind/", r"mind/\1/", x)
            return re.sub(r"^equipe/", "workspace/", x)
        for x, h in avant.items():
            self.assertEqual(apres.get(adresse(x)), h, "perdu ou changé : %s" % x)
        self.assertEqual(len(apres), len(avant), "un fichier en plus ou en moins")
        self.assertFalse(os.path.exists(m), "l'ancien dossier existe encore")
        self.assertEqual(int(git(b, "rev-list", "--count", "HEAD").strip()), n_avant + 1,
                         "l'historique n'a pas suivi, ou le déplacement n'est pas enregistré")
        self.assertEqual(git(b, "status", "--porcelain").strip(), "", "déplacement laissé en attente")
        self.assertEqual(memoire.resous(os.path.join(p, "agents", "QA")).forme, Forme.Brain)

    def test_les_droits_suivent_la_memoire(self):
        p = self.deportee()
        lance([p, "--apply", "--agents-arretes"])
        d = droits(p, "OPS")
        # QA n'a que son état : la règle d'OPS sur QA vise brain/mind/QA. OPS garde des
        # preuves à côté : la règle de QA sur OPS vise ses DEUX nouvelles adresses.
        self.assertIn("brain/mind/QA", d["deny"])
        self.assertIn(os.path.join(p, "brain", "mind", "QA"), d["deny"], "l'absolu reste absolu")
        self.assertNotIn("brain/agents/QA", d["deny"], "une adresse qui n'existera pas")
        q = droits(p, "QA")
        self.assertIn("brain/mind/OPS", q["deny"])
        self.assertIn("brain/agents/OPS", q["deny"])
        self.assertEqual(d["allow"], ["brain/mind/OPS"], "un allow sur .mind suit aussi")
        self.assertIn("memoire-old", d["deny"], "un chemin voisin a été mordu")
        self.assertIn("apps/web", d["deny"], "un droit sur le code n'a pas à bouger")
        self.assertNotIn("memoire/", json.dumps(d))
        f = os.path.join(p, "agents", "OPS", ".github", "copilot")
        self.assertTrue(any(n.startswith("perimetre.json.avant-mise-a-niveau-") for n in os.listdir(f)),
                        "aucune copie d'avant")
        self.assertEqual(lis(os.path.join(p, ".gitignore")), "node_modules/\nbrain/\n")

    def test_le_paquet_est_declare_une_fois_a_la_racine_git(self):
        p = self.deportee()
        lance([p, "--apply", "--agents-arretes"])
        v = json.loads(lis(os.path.join(p, ".github", "copilot", "settings.json")))
        self.assertTrue(v["enabledPlugins"]["harnais@atelier-copilot"])
        self.assertFalse(os.path.exists(os.path.join(p, "agents", "OPS", ".github", "copilot", "settings.json")))

    def test_le_blanc_n_ecrit_rien_et_le_contenu_est_nomme(self):
        p = self.deportee()
        avant = inventaire(p)
        rc, out = lance([p])
        self.assertEqual(rc, 0, out)
        self.assertEqual(inventaire(p), avant, "le blanc a écrit")
        self.assertFalse(os.path.exists(os.path.join(p, "brain")))
        self.assertIn("brain/branding", out)
        self.assertIn("brain/agents/OPS/ garde preuves", out)
        self.assertIn("brain/mind/ANCIEN/ n'a ni dossier", out)
        self.assertIn("AGENTS.md:3", out)

    def test_sans_le_drapeau_d_arret_rien_ne_bouge(self):
        p = self.deportee()
        rc, out = lance([p, "--apply"])
        self.assertEqual(rc, 2)
        self.assertTrue(os.path.isdir(os.path.join(p, "memoire")))
        self.assertFalse(os.path.exists(os.path.join(p, "brain")))

    def test_un_fait_en_trop_bloque_et_son_absence_debloque(self):
        p = self.deportee(en_trop=True)
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 2)
        self.assertIn("questions.md", out)
        self.assertTrue(os.path.isdir(os.path.join(p, "memoire")), "a bougé malgré le refus")

    def test_sans_depot_distant_rien_ne_bouge(self):
        p = self.deportee(distant=False)
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 2)
        self.assertIn("AUCUN dépôt distant", out)
        self.assertTrue(os.path.isdir(os.path.join(p, "memoire")))

    def test_une_modification_en_attente_bloque(self):
        p = self.deportee()
        ecris(os.path.join(p, "memoire", "agents", "QA", ".mind", "todo.md"), "- [ ] changé\n")
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 2)
        self.assertIn("non enregistrée", out)

    def test_relancer_apres_coup_ne_change_rien(self):
        p = self.deportee()
        lance([p, "--apply", "--agents-arretes"])
        memoire._VUS.clear()
        avant = inventaire(p)
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 0, out)
        self.assertIn("Déjà à niveau", out)
        self.assertEqual(inventaire(p), avant)


class EnPlace(Base):
    def test_mono_en_place_passe_en_brain_et_recoit_ses_faits(self):
        p = self.depot("Mono")
        ecris(os.path.join(p, ".fact", "base.md"), "---\ncap: x\n---\n")
        ecris(os.path.join(p, ".mind", "state.md"), ETAT)
        ecris(os.path.join(p, ".mind", "todo.md"), "- [ ] t\n")
        ecris(os.path.join(p, "src", "a.ts"), "x\n")
        self.valide(p)
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 0, out)
        for f in ("fact/base.md", "fact/stack.md", "fact/rules.md", "fact/architecture.md",
                  "fact/workflow.md", "mind/state.md", "mind/todo.md"):
            self.assertTrue(os.path.isfile(os.path.join(p, "brain", f)), f)
        self.assertEqual(lis(os.path.join(p, "brain/fact/base.md")), "---\ncap: x\n---\n")
        self.assertFalse(os.path.exists(os.path.join(p, ".fact")))
        self.assertIn("brain/fact", git(p, "show", "--stat", "HEAD"), "le déplacement n'est pas enregistré")
        self.assertIn("atelier-copilot", lis(os.path.join(p, ".github/copilot/settings.json")))


class DejaBrain(Base):
    def test_un_projet_brain_ne_recoit_que_ce_qui_manque(self):
        p = self.depot("Neuf")
        ecris(os.path.join(p, "brain/fact/base.md"), "---\ncap: x\n---\n")
        ecris(os.path.join(p, "brain/mind/state.md"), "s\n")
        rc, out = lance([p, "--apply"])          # rien ne bouge : pas besoin d'arrêter
        self.assertEqual(rc, 0, out)
        self.assertEqual(lis(os.path.join(p, "brain/mind/state.md")), "s\n", "écrasé")
        self.assertTrue(os.path.isfile(os.path.join(p, "brain/fact/rules.md")))
        memoire._VUS.clear()
        rc, out = lance([p])
        self.assertIn("Déjà à niveau", out)

    def test_a_cheval_bloque(self):
        p = self.depot("Cheval")
        ecris(os.path.join(p, "brain/fact/base.md"), "x\n")
        ecris(os.path.join(p, ".fact/base.md"), "x\n")
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 2)
        self.assertIn("Trancher à la main", out)


class Reecriture(unittest.TestCase):
    def test_une_borne_avant_de_mordre(self):
        corr = [("/a/memoire", "/a/brain")]
        self.assertEqual(niveau.reecrit_entree("/a/memoire/x", "/a", corr), (["/a/brain/x"], True))
        self.assertEqual(niveau.reecrit_entree("/a/memoire-old", "/a", corr), (["/a/memoire-old"], False))
        self.assertEqual(niveau.reecrit_entree("memoire", "/a", corr), (["brain"], True))
        self.assertEqual(niveau.reecrit_entree("memoire-old/x", "/a", corr), (["memoire-old/x"], False))

    def test_un_dossier_qui_se_separe_donne_ses_deux_adresses(self):
        corr = [("/a/memoire", "/a/brain")]
        multi = {"/a/memoire/agents/OPS": ["/a/brain/mind/OPS", "/a/brain/agents/OPS"]}
        self.assertEqual(niveau.reecrit_entree("memoire/agents/OPS", "/a", corr, multi),
                         (["brain/mind/OPS", "brain/agents/OPS"], True))
        # Un droit PLUS PROFOND n'est pas dédoublé : il n'a qu'une adresse d'arrivée.
        self.assertEqual(niveau.reecrit_entree("memoire/agents/OPS/preuves", "/a", corr, multi),
                         (["brain/agents/OPS/preuves"], True))

    def test_le_json_hors_deny_et_allow_n_est_pas_touche(self):
        t = json.dumps({"deny": ["memoire/x"], "note": "memoire/x", "allow": []})
        neuf, n = niveau.reecrit_droits(t, "/a", [("/a/memoire", "/a/brain")])
        v = json.loads(neuf)
        self.assertEqual((n, v["deny"], v["note"]), (1, ["brain/x"], "memoire/x"))
        self.assertEqual(niveau.reecrit_droits(t, "/a", [("/zz", "/yy")]), (t, 0))


class Windows(unittest.TestCase):
    """Les chemins d'un poste Windows, simulés (`os.name` = nt) : un droit s'écrit
    `C:\\Users\\u\\Proj\\memoire\\…` ou `C:/Users/u/Proj/memoire/…`, la casse ne distingue
    pas deux dossiers, et chaque entrée garde son séparateur."""

    def nt(self):
        import ntpath
        p = mock.patch.object(niveau.os, "name", "nt")
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(niveau.os.path, "join", ntpath.join)
        q.start()
        self.addCleanup(q.stop)

    def test_un_droit_en_chemin_windows_suit(self):
        self.nt()
        racine = "C:\\Users\\u\\Proj"
        corr = [(racine + "\\memoire", racine + "\\brain")]
        self.assertEqual(niveau.reecrit_entree("C:\\Users\\u\\Proj\\memoire\\agents\\QA", racine, corr),
                         (["C:\\Users\\u\\Proj\\brain\\agents\\QA"], True))
        self.assertEqual(niveau.reecrit_entree("C:/Users/u/Proj/memoire/agents/QA", racine, corr),
                         (["C:/Users/u/Proj/brain/agents/QA"], True))
        # la casse ne distingue rien sous Windows, le voisin reste intact
        self.assertEqual(niveau.reecrit_entree("c:\\users\\U\\proj\\MEMOIRE\\x", racine, corr),
                         (["C:\\Users\\u\\Proj\\brain\\x"], True))
        self.assertEqual(niveau.reecrit_entree("C:\\Users\\u\\Proj\\memoire-old\\x", racine, corr)[1], False)

    def test_un_droit_relatif_reste_relatif_et_garde_ses_barres(self):
        self.nt()
        racine = "C:\\Users\\u\\Proj"
        corr = [(racine + "\\memoire", racine + "\\brain")]
        self.assertEqual(niveau.reecrit_entree("memoire/agents/QA", racine, corr), (["brain/agents/QA"], True))
        self.assertEqual(niveau.reecrit_entree("memoire\\agents\\QA", racine, corr), (["brain\\agents\\QA"], True))

    def test_la_racine_sans_lecteur_est_laissee_telle_quelle(self):
        self.nt()
        self.assertEqual(niveau.reecrit_entree("\\x\\memoire", "C:\\Users\\u\\Proj",
                                               [("C:\\Users\\u\\Proj\\memoire", "C:\\Users\\u\\Proj\\brain")]),
                         (["\\x\\memoire"], False))

    def test_la_casse_compte_hors_windows(self):
        self.assertEqual(niveau.reecrit_entree("/A/MEMOIRE/x", "/a", [("/a/memoire", "/a/brain")])[1], False)


class Livrables(Base):
    """Décision du 20/10/2026 : `outputs/` (1.2 à 1.3) et `brain/workbench/` (0.19 à 1.1)
    passent à `assets/` — seulement s'il n'y a pas déjà un `assets/`."""

    def projet_brain(self, nom="Liv"):
        p = self.depot(nom)
        ecris(os.path.join(p, "brain/fact/base.md"), "---\ncap: x\n---\n")
        ecris(os.path.join(p, "brain/mind/state.md"), ETAT)
        ecris(os.path.join(p, "brain/mind/todo.md"), "- [ ] t\n")
        return p

    def test_outputs_seul_est_renomme_et_son_historique_suit(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 1;\n")
        ecris(os.path.join(p, "outputs", "OPS", "note.md"), "un plan\n")
        self.valide(p)
        avant = inventaire(os.path.join(p, "outputs"))
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(p, "outputs")))
        self.assertEqual(inventaire(os.path.join(p, "assets")), avant, "un livrable perdu ou changé")
        en_attente = [l for l in git(p, "status", "--porcelain").split("\n") if l and not l.startswith("??")]
        self.assertEqual(en_attente, [], "renommage laissé en attente")
        self.assertIn("{outputs => assets}/OPS/plan.sql", git(p, "show", "--stat", "--format=", "HEAD"))
        self.assertIn("rename", git(p, "show", "--summary", "--format=", "HEAD"),
                      "git a vu un renommage : l'historique suit")

    def test_outputs_seul_les_droits_suivent(self):
        p = self.brain_equipe()
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 1;\n")
        self.valide(p)
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 0, out)
        q = droits(p, "QA")
        self.assertIn("assets/OPS", q["deny"])
        self.assertNotIn("outputs/OPS", q["deny"])
        self.assertEqual(droits(p, "OPS")["allow"], ["assets/OPS"])

    def test_outputs_a_cote_d_un_assets_est_nomme_et_rien_ne_bouge(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 1;\n")
        ecris(os.path.join(p, "assets", "logo.svg"), "<svg/>\n")
        self.valide(p)
        outputs = inventaire(os.path.join(p, "outputs"))
        assets = inventaire(os.path.join(p, "assets"))
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertTrue(os.path.isdir(os.path.join(p, "outputs")), "renommé malgré le conflit")
        self.assertEqual(inventaire(os.path.join(p, "outputs")), outputs)
        self.assertEqual(inventaire(os.path.join(p, "assets")), assets, "rien n'a été fusionné dans assets/")
        self.assertIn("CONFLIT", out)
        self.assertIn("`outputs/`", out)
        self.assertEqual(rc, 0)

    def test_le_conflit_en_blanc_rien_ne_bouge_et_rien_n_est_ecrit(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 1;\n")
        ecris(os.path.join(p, "assets", "logo.svg"), "<svg/>\n")
        self.valide(p)
        # `Déjà à niveau` est faux ici : des faits manquent, ils seront posés — mais PAS l'espace
        # des livrables.
        rc, out = lance([p])
        self.assertIn("CONFLIT", out)
        self.assertNotIn("LES LIVRABLES PASSENT", out)

    def test_le_blanc_n_ecrit_rien(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 1;\n")
        self.valide(p)
        avant = inventaire(p)
        statut = git(p, "status", "--porcelain")
        rc, out = lance([p])
        self.assertEqual(rc, 0, out)
        self.assertIn("LES LIVRABLES PASSENT À assets/", out)
        self.assertEqual(inventaire(p), avant, "le blanc a écrit")
        self.assertEqual(git(p, "status", "--porcelain"), statut)
        self.assertTrue(os.path.isdir(os.path.join(p, "outputs")))
        self.assertFalse(os.path.exists(os.path.join(p, "assets")))

    def test_sans_le_drapeau_d_arret_le_renommage_est_refuse(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 1;\n")
        self.valide(p)
        rc, out = lance([p, "--apply"])
        self.assertEqual(rc, 2)
        self.assertTrue(os.path.isdir(os.path.join(p, "outputs")))
        self.assertFalse(os.path.exists(os.path.join(p, "assets")))

    def test_un_livrable_non_enregistre_bloque(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 1;\n")
        self.valide(p)
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 2;\n")
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 2)
        self.assertIn("non enregistrée", out)
        self.assertTrue(os.path.isdir(os.path.join(p, "outputs")))

    def test_brain_workbench_seul_est_renomme(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "brain", "workbench", "OPS", "analyse.md"), "une analyse\n")
        self.valide(p)
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(p, "brain", "workbench")))
        self.assertEqual(lis(os.path.join(p, "assets", "OPS", "analyse.md")), "une analyse\n")
        self.assertNotIn("brain/workbench : hors méthode", out, "il part, ce n'est plus du contenu à ranger")

    def test_brain_workbench_a_cote_d_un_assets_est_nomme(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "brain", "workbench", "OPS", "analyse.md"), "une analyse\n")
        ecris(os.path.join(p, "assets", "logo.svg"), "<svg/>\n")
        self.valide(p)
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertTrue(os.path.isdir(os.path.join(p, "brain", "workbench")))
        self.assertFalse(os.path.exists(os.path.join(p, "assets", "OPS")))
        self.assertIn("CONFLIT", out)
        self.assertIn("brain/workbench", out)

    def test_outputs_et_workbench_sans_assets_se_disputent_le_nom(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 1;\n")
        ecris(os.path.join(p, "brain", "workbench", "OPS", "analyse.md"), "une analyse\n")
        self.valide(p)
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertIn("CONFLIT", out)
        self.assertTrue(os.path.isdir(os.path.join(p, "outputs")))
        self.assertTrue(os.path.isdir(os.path.join(p, "brain", "workbench")))
        self.assertFalse(os.path.exists(os.path.join(p, "assets")))

    def test_un_agents_md_qui_cite_outputs_est_nomme(self):
        p = self.projet_brain()
        ecris(os.path.join(p, "AGENTS.md"), "# Proj\n\nLes livrables : `outputs/OPS/`.\n")
        ecris(os.path.join(p, "outputs", "OPS", "plan.sql"), "select 1;\n")
        self.valide(p)
        rc, out = lance([p])
        self.assertIn("AGENTS.md:3 cite l'ancien espace des livrables", out)

    def test_une_equipe_un_dossier_par_agent_renomme_aussi(self):
        d = self.dossier("v3")
        x = banc_equipe.construis(os.path.realpath(d))
        ecris(os.path.join(x, "outputs", "OPS", "plan.sql"), "select 1;\n")
        git(x, "add", "-A")
        git(x, "commit", "-qm", "livrable")
        rc, out = lance([x, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 0, out)
        self.assertEqual(lis(os.path.join(x, "assets", "OPS", "plan.sql")), "select 1;\n")
        self.assertFalse(os.path.exists(os.path.join(x, "outputs")))
        self.assertFalse(os.path.exists(os.path.join(x, "brain")))


class FormesDEquipe(Base):
    def test_la_forme_compacte_est_nommee_et_pas_touchee(self):
        p = self.depot("Compacte")
        ecris(os.path.join(p, "brain/fact/base.md"), "---\ncap: x\n---\n")
        for a in ("OPS", "QA"):
            ecris(os.path.join(p, "brain/mind", a, "state.md"), ETAT)
            ecris(os.path.join(p, "brain/mind", a, "todo.md"), "- [ ] t\n")
            ecris(os.path.join(p, ".github/agents", "%s.agent.md" % a.lower()),
                  "---\nname: %s\n---\n<!-- harnais:role:start -->\n# %s\n<!-- harnais:role:end -->\n" % (a.lower(), a))
            ecris(os.path.join(p, ".github/copilot/perimetres", "%s.json" % a.lower()),
                  json.dumps({"deny": ["brain/mind/%s" % ("QA" if a == "OPS" else "OPS")]}) + "\n")
        self.valide(p)
        rc, out = lance([p, "--apply", "--agents-arretes"])
        self.assertEqual(rc, 0, out)
        self.assertIn("COMPACTE", out)
        self.assertIn("choix de Copilot", out)
        self.assertIn("harnais adopte --equipe", out, "la ligne qui dit comment passer à un dossier par agent")
        # TÉMOIN : ni dossier d'agent, ni déplacement, ni profil réécrit
        self.assertFalse(os.path.exists(os.path.join(p, "agents")))
        self.assertTrue(os.path.isfile(os.path.join(p, "brain/mind/OPS/state.md")))
        self.assertIn("harnais:role:start", lis(os.path.join(p, ".github/agents/ops.agent.md")))
        self.assertEqual(json.loads(lis(os.path.join(p, ".github/copilot/perimetres/ops.json"))),
                         {"deny": ["brain/mind/QA"]})

    def test_un_dossier_d_avant_est_nomme_avec_son_geste(self):
        p = self.brain_equipe()
        self.valide(p)
        rc, out = lance([p])
        self.assertIn("dossier d'avant", out)
        self.assertIn("harnais demenage", out)

    def test_une_equipe_mixte_n_est_pas_devinee(self):
        p = self.brain_equipe()
        ecris(os.path.join(p, "brain/mind/PO/state.md"), ETAT)
        ecris(os.path.join(p, "brain/mind/PO/todo.md"), "t\n")
        ecris(os.path.join(p, ".github/agents/po.agent.md"),
              "---\nname: po\n---\n<!-- harnais:role:start -->\n# PO\n<!-- harnais:role:end -->\n")
        self.valide(p)
        rc, out = lance([p])
        self.assertIn("MIXTE", out)


class Atelier(Base):
    def test_le_diagnostic_dit_quoi_faire_et_n_ecrit_rien(self):
        atelier = os.path.join(self.maison, "Atelier")
        os.makedirs(atelier)
        gros = self.deportee()
        os.rename(gros, os.path.join(atelier, "Alpha"))
        seul = os.path.join(atelier, "Beta")
        os.makedirs(seul)
        git(seul, "init", "-q", "-b", "main")
        ecris(os.path.join(seul, "src", "a.ts"), "x\n")
        self.valide(seul)
        comp = os.path.join(atelier, "Gamma")
        os.makedirs(comp)
        git(comp, "init", "-q", "-b", "main")
        ecris(os.path.join(comp, "brain/fact/base.md"), "---\ncap: x\n---\n")
        ecris(os.path.join(comp, "brain/mind/OPS/state.md"), ETAT)
        ecris(os.path.join(comp, ".github/agents/ops.agent.md"),
              "---\nname: ops\n---\n<!-- harnais:role:start -->\n# OPS\n<!-- harnais:role:end -->\n")
        self.valide(comp)
        avant = inventaire(atelier)
        rc, out = lance(["--atelier", "--racine", atelier])
        self.assertEqual(rc, 0, out)
        self.assertEqual(inventaire(atelier), avant, "le diagnostic a écrit")
        ligne = {n: next(l for l in out.split("\n") if l.strip().startswith(n)) for n in ("Alpha", "Beta", "Gamma")}
        self.assertIn("mise-a-niveau --apply --agents-arretes", ligne["Alpha"])
        self.assertIn("adopte", ligne["Beta"])
        self.assertIn("compacte", ligne["Gamma"])
        self.assertIn("nommée, pas touchée", ligne["Gamma"])


class UnDossierParAgent(Isole):
    """Sur une équipe déjà « un dossier par agent », la mise à niveau COMPLÈTE au bon
    endroit et ne recrée jamais `brain/`."""

    def test_completer_sans_recreer_brain(self):
        d = os.path.realpath(self.dossier("niveau-v3"))
        x = banc_equipe.construis(d)
        os.remove(os.path.join(x, "agents", "PO", "todo.md"))
        code, out = lance([x, "--apply"])
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(os.path.join(x, "brain")))
        self.assertTrue(os.path.isfile(os.path.join(x, "fact", "rules.md")))
        self.assertTrue(os.path.isfile(os.path.join(x, "agents", "PO", "todo.md")))
        self.assertIn("cap: un banc", lis(os.path.join(x, "fact", "base.md")),
                      "TÉMOIN : un fait existant n'est jamais écrasé")

    def test_un_profil_absent_est_nomme(self):
        d = os.path.realpath(self.dossier("niveau-v3p"))
        x = banc_equipe.construis(d)
        code, out = lance([x])
        self.assertIn("profil du menu d'agent absent", out)
        self.assertIn("equipe --profils", out)


class Cablage(Base):
    """Les deux sous-commandes sont branchées dans `main` et dites dans l'aide."""

    def test_les_sous_commandes_sont_dans_la_table_et_dans_l_aide(self):
        import main
        self.assertEqual(main.TABLE["mise-a-niveau"][:2], ("niveau", "main"))
        self.assertEqual(main.TABLE["demenage"][:2], ("demenage", "main"))
        self.assertIn("mise-a-niveau", main.AIDE)
        self.assertIn("demenage", main.AIDE)

    def test_par_le_point_d_entree(self):
        import main
        p = self.depot("Neuf")
        ecris(os.path.join(p, "brain/fact/base.md"), "---\ncap: x\n---\n")
        s = io.StringIO()
        with contextlib.redirect_stdout(s):
            rc = main.main(["mise-a-niveau", p])
        self.assertEqual(rc, 0, s.getvalue())
        self.assertIn("MISE À NIVEAU", s.getvalue())
        s = io.StringIO()
        with contextlib.redirect_stdout(s):
            rc = main.main(["demenage"])
        self.assertEqual(rc, 2)
        self.assertIn("usage", s.getvalue())

    def test_le_tronc_commun_n_ecarte_plus_niveau_ni_demenage(self):
        d = json.loads(lis(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outils", "tronc-commun.json")))
        self.assertNotIn("niveau", d["ecartes"])
        self.assertNotIn("demenage", d["ecartes"])
        self.assertIn("taches", d["ecartes"], "le reste du fichier n'est pas touché")
        self.assertIn("versions", d["ecartes"])


if __name__ == "__main__":
    unittest.main()

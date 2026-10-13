# -*- coding: utf-8 -*-
"""Les essais de `synchro` — un test par `#[test]` du Rust (`harnais/src/synchro.rs`) : sept."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import synchro  # noqa: E402
from synchro import Accroc, court, enregistre, renvoi, synchronise  # noqa: E402

RECUP, ENVOI = synchro.DELAI_RECUPERATION, synchro.DELAI_ENVOI


def g(d, a):
    o = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t"] + list(a), cwd=d,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert o.returncode == 0, "git %r : %s" % (a, o.stderr.decode("utf-8", "replace"))


def ecrire(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def lire(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


class Essais(unittest.TestCase):

    def bac(self, nom):
        d = os.path.join(tempfile.gettempdir(), "harnais-synchro-%s-%d" % (nom, os.getpid()))
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        self.addCleanup(shutil.rmtree, d, True)
        return os.path.realpath(d)

    def deux_postes(self, nom):
        """Un distant nu et deux copies, comme deux personnes."""
        d = self.bac(nom)
        nu = os.path.join(d, "distant.git")
        g(d, ["init", "-q", "--bare", "-b", "main", nu])
        a = os.path.join(d, "a")
        g(d, ["clone", "-q", nu, "a"])
        os.makedirs(os.path.join(a, "fact"))
        ecrire(os.path.join(a, "fact/base.md"), "un\ndeux\ntrois\n")
        ecrire(os.path.join(a, "commun.md"), "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\n")
        g(a, ["checkout", "-q", "-b", "main"])
        g(a, ["add", "-A"])
        g(a, ["commit", "-qm", "init"])
        g(a, ["push", "-q", "-u", "origin", "main"])
        b = os.path.join(d, "b")
        g(d, ["clone", "-q", nu, "b"])
        for c in (a, b):
            g(c, ["config", "user.name", "t"])
            g(c, ["config", "user.email", "t@t"])
        return (a, b, nu)

    def test_ce_qu_ecrit_a_est_lu_par_b(self):
        (a, b, _) = self.deux_postes("lu")
        ecrire(os.path.join(a, "note-a.md"), "de A\n")
        enregistre(a, "A", "fact/")
        ba = synchronise(a, True, RECUP, ENVOI)
        self.assertEqual((ba.envoyes, ba.accroc), (1, None), repr(ba))
        bb = synchronise(b, True, RECUP, ENVOI)
        self.assertEqual((bb.recus, bb.accroc), (1, None), repr(bb))
        self.assertEqual(lire(os.path.join(b, "note-a.md")), "de A\n")

    def test_deux_seances_sur_des_fichiers_differents_fusionnent(self):
        (a, b, _) = self.deux_postes("fusion")
        ecrire(os.path.join(a, "a.md"), "A\n")
        ecrire(os.path.join(b, "b.md"), "B\n")
        enregistre(a, "A", "fact/")
        enregistre(b, "B", "fact/")
        self.assertIsNone(synchronise(a, True, RECUP, ENVOI).accroc)
        bb = synchronise(b, True, RECUP, ENVOI)
        self.assertEqual((bb.recus, bb.envoyes, bb.accroc), (1, 2, None), repr(bb))
        self.assertEqual(synchronise(a, True, RECUP, ENVOI).recus, 2)
        self.assertTrue(os.path.exists(os.path.join(a, "b.md"))
                        and os.path.exists(os.path.join(b, "a.md")))

    def test_le_meme_passage_s_arrete_sans_perte_et_n_envoie_rien(self):
        (a, b, nu) = self.deux_postes("conflit")
        ecrire(os.path.join(a, "commun.md"), "l1\nl2\nl3\nl4 de A\nl5\nl6\nl7\nl8\n")
        ecrire(os.path.join(b, "commun.md"), "l1\nl2\nl3\nl4 de B\nl5\nl6\nl7\nl8\n")
        enregistre(a, "A", "fact/")
        enregistre(b, "B", "fact/")
        self.assertIsNone(synchronise(a, True, RECUP, ENVOI).accroc)
        distant_avant = court(nu, ["rev-parse", "main"])
        tete_b = court(b, ["rev-parse", "HEAD"])
        bb = synchronise(b, True, RECUP, ENVOI)
        self.assertEqual(bb.accroc, Accroc.Conflit(["commun.md"]), repr(bb))
        self.assertEqual(bb.en_retard, 1)
        # Rien de perdu, rien de forcé, rien de laissé à moitié.
        self.assertEqual(court(b, ["rev-parse", "HEAD"]), tete_b)
        self.assertIn("l4 de B", lire(os.path.join(b, "commun.md")))
        self.assertEqual(court(nu, ["rev-parse", "main"]), distant_avant)
        self.assertEqual(court(b, ["status", "--porcelain"]), "")
        self.assertIn("commun.md", renvoi(b, bb)[1])

    def test_deux_passages_differents_du_meme_fichier_fusionnent(self):
        (a, b, _) = self.deux_postes("passages")
        ecrire(os.path.join(a, "commun.md"), "l1 de A\nl2\nl3\nl4\nl5\nl6\nl7\nl8\n")
        ecrire(os.path.join(b, "commun.md"), "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8 de B\n")
        enregistre(a, "A", "fact/")
        enregistre(b, "B", "fact/")
        synchronise(a, True, RECUP, ENVOI)
        self.assertIsNone(synchronise(b, True, RECUP, ENVOI).accroc)
        t = lire(os.path.join(b, "commun.md"))
        self.assertTrue("l1 de A" in t and "l8 de B" in t)

    def test_les_faits_ne_s_enregistrent_jamais_seuls(self):
        (a, _, _) = self.deux_postes("faits")
        ecrire(os.path.join(a, "fact/base.md"), "réécrit\n")
        ecrire(os.path.join(a, "n.md"), "x\n")
        self.assertEqual(enregistre(a, "A", "fact/"), ["fact/base.md"])
        self.assertEqual(court(a, ["status", "--porcelain"]), "M fact/base.md")
        # Le témoin : sans préfixe de faits, tout part — c'est bien le préfixe qui retient.
        (c, _, _) = self.deux_postes("faits-temoin")
        ecrire(os.path.join(c, "fact/base.md"), "réécrit\n")
        enregistre(c, "C", "")
        self.assertEqual(court(c, ["status", "--porcelain"]), "")

    def test_hors_ligne_rien_ne_bloque_et_le_retard_se_dit(self):
        (a, _, nu) = self.deux_postes("horsligne")
        ailleurs = os.path.splitext(nu)[0] + ".parti"
        os.rename(nu, ailleurs)
        ecrire(os.path.join(a, "n.md"), "x\n")
        enregistre(a, "A", "fact/")
        ba = synchronise(a, True, RECUP, ENVOI)
        self.assertTrue(ba.accroc is not None and ba.accroc.genre == "HorsLigne", repr(ba))
        self.assertEqual(ba.en_retard, 1)
        self.assertIsNone(renvoi(a, ba), "hors ligne ne doit pas bloquer")
        self.assertIn("pas encore envoyé", synchro.ligne(a, ba))
        os.rename(ailleurs, nu)
        ba = synchronise(a, True, RECUP, ENVOI)
        self.assertEqual((ba.envoyes, ba.accroc), (1, None))

    def test_sans_branche_suivie_on_le_dit(self):
        d = self.bac("sanssuivi")
        g(d, ["init", "-q"])
        ecrire(os.path.join(d, "x"), "x")
        g(d, ["add", "-A"])
        g(d, ["commit", "-qm", "x"])
        self.assertEqual(synchronise(d, True, RECUP, ENVOI).accroc, Accroc.SansSuivi)


class DepotEntier(unittest.TestCase):
    """`HARNAIS_SYNCHRO=git-depot` (13/10/2026) : le dépôt ENTIER de l'agent se
    synchronise — consignes, réglages, savoir-faire, mémoire —, un poste par
    personne. Les fichiers sensibles ne partent jamais."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"HARNAIS_SYNCHRO": "git-depot"})
        self.env.start()
        self.addCleanup(self.env.stop)
        d = os.path.realpath(tempfile.mkdtemp(prefix="harnais-depot-"))
        self.addCleanup(shutil.rmtree, d, True)
        nu = os.path.join(d, "distant.git")
        g(d, ["init", "-q", "--bare", "-b", "main", nu])
        a = os.path.join(d, "a")
        g(d, ["clone", "-q", nu, "a"])
        for r in ("brain/fact", "brain/mind/Maxime", "brain/mind/Damien",
                  "agents/Legal Maxime/.claude", "agents/Legal Damien/.claude"):
            os.makedirs(os.path.join(a, r))
        ecrire(os.path.join(a, "brain/fact/base.md"), "# Base\n\n## Nature\nx\n")
        for n in ("Maxime", "Damien"):
            ecrire(os.path.join(a, "brain/mind/%s/state.md" % n),
                   "---\nmaj: 2026-10-13\nsante: verte\njalon: j\n---\n")
            ecrire(os.path.join(a, "brain/mind/%s/todo.md" % n), "# t\n")
            ecrire(os.path.join(a, "agents/Legal %s/CLAUDE.md" % n), "un\ndeux\ntrois\n")
            ecrire(os.path.join(a, "agents/Legal %s/.claude/settings.json" % n), "{}\n")
        ecrire(os.path.join(a, ".gitignore"), "*.pdf\nbrain/local/\n")
        g(a, ["checkout", "-q", "-b", "main"])
        g(a, ["add", "-A"])
        g(a, ["commit", "-qm", "init"])
        g(a, ["push", "-q", "-u", "origin", "main"])
        b = os.path.join(d, "b")
        g(d, ["clone", "-q", nu, "b"])
        for c in (a, b):
            g(c, ["config", "user.name", "t"])
            g(c, ["config", "user.email", "t@t"])
        self.a, self.b, self.nu = a, b, nu

    def res(self, poste, agent):
        import memoire
        return memoire.resous(os.path.join(poste, "agents", agent))

    def tour(self, poste, agent):
        """Fin de tour d'un expert : enregistrer tout (registre local exclu), puis synchroniser."""
        d = synchro.depot(self.res(poste, agent))
        self.assertEqual(d, os.path.realpath(poste), "le dépôt synchronisé est le dépôt entier")
        enregistre(d, agent, "", exclus=("brain/local/",))
        return synchronise(d, True, RECUP, ENVOI)

    def au_distant(self):
        o = subprocess.run(["git", "--git-dir", self.nu, "ls-tree", "-r", "--name-only", "main"],
                           stdout=subprocess.PIPE)
        return o.stdout.decode("utf-8").splitlines()

    def test_une_consigne_un_reglage_et_un_fait_changes_chez_l_un_arrivent_chez_l_autre(self):
        ecrire(os.path.join(self.a, "agents/Legal Maxime/CLAUDE.md"), "un\nDEUX\ntrois\n")
        ecrire(os.path.join(self.a, "agents/Legal Maxime/.claude/settings.json"), '{"env": {}}\n')
        ecrire(os.path.join(self.a, "brain/fact/societe.md"), "# Société\n- capital 1 000 € (dit, 13/10/2026)\n")
        ba = self.tour(self.a, "Legal Maxime")
        self.assertEqual((ba.envoyes, ba.accroc), (1, None), repr(ba))
        bb = self.tour(self.b, "Legal Damien")
        self.assertEqual((bb.recus, bb.accroc), (1, None), repr(bb))
        self.assertEqual(lire(os.path.join(self.b, "agents/Legal Maxime/CLAUDE.md")), "un\nDEUX\ntrois\n")
        self.assertIn("capital", lire(os.path.join(self.b, "brain/fact/societe.md")))

    def test_les_fichiers_sensibles_ne_partent_jamais(self):
        """Ignorés par git (pièce PDF, registre local) ou non (un `.env`, les réglages
        propres au poste, la trace du briefing) : aucun n'atteint le distant."""
        os.makedirs(os.path.join(self.a, "brain/local"))
        ecrire(os.path.join(self.a, "brain/local/registre.md"), "né le 1er janvier\n")
        ecrire(os.path.join(self.a, "piece.pdf"), "%PDF\n")
        ecrire(os.path.join(self.a, ".env"), "CLE=secret\n")
        ecrire(os.path.join(self.a, "agents/Legal Maxime/.env.local"), "CLE=secret\n")
        ecrire(os.path.join(self.a, "agents/Legal Maxime/.claude/settings.local.json"), "{}\n")
        ecrire(os.path.join(self.a, "agents/Legal Maxime/.claude/.briefing.json"), "{}\n")
        ecrire(os.path.join(self.a, "agents/Legal Maxime/.claude/.briefing.lock"), "1\n")
        ecrire(os.path.join(self.a, "brain/fact/societe.md"), "x\n")
        ba = self.tour(self.a, "Legal Maxime")
        self.assertEqual((ba.envoyes, ba.accroc), (1, None), repr(ba))
        distant = self.au_distant()
        self.assertIn("brain/fact/societe.md", distant, "témoin : l'envoi a bien eu lieu")
        for f in ("brain/local/registre.md", "piece.pdf", ".env", "agents/Legal Maxime/.env.local",
                  "agents/Legal Maxime/.claude/settings.local.json",
                  "agents/Legal Maxime/.claude/.briefing.json",
                  "agents/Legal Maxime/.claude/.briefing.lock"):
            self.assertNotIn(f, distant, "%s est parti" % f)

    def test_l_ouverture_dit_en_clair_que_le_depot_est_partage(self):
        l = synchro.demarrage(self.res(self.a, "Legal Maxime"), "Legal Maxime")
        self.assertIn("dépôt partagé : ce dépôt est synchronisé avec l'autre poste", l)
        self.assertIn("sans relecture", l)
        with mock.patch.dict(os.environ, {"HARNAIS_SYNCHRO": ""}):
            self.assertIsNone(synchro.demarrage(self.res(self.a, "Legal Maxime"), "Legal Maxime"),
                              "témoin négatif : sans synchro, rien n'est dit")

    def test_un_secret_deja_suivi_arrete_tout_envoi(self):
        ecrire(os.path.join(self.a, ".env"), "CLE=secret\n")
        g(self.a, ["add", "-f", ".env"])
        g(self.a, ["commit", "-qm", "erreur"])
        ba = self.tour(self.a, "Legal Maxime")
        self.assertEqual(ba.accroc.genre, "Sensible", repr(ba))
        self.assertEqual(ba.envoyes, 0)
        self.assertNotIn(".env", self.au_distant())
        cle, msg = renvoi(self.a, ba)
        self.assertIn("ARRÊTÉE", msg)

    def test_le_meme_passage_d_une_consigne_modifie_des_deux_cotes_s_arrete(self):
        ecrire(os.path.join(self.a, "agents/Legal Maxime/CLAUDE.md"), "un\nA\ntrois\n")
        ecrire(os.path.join(self.b, "agents/Legal Maxime/CLAUDE.md"), "un\nB\ntrois\n")
        self.assertIsNone(self.tour(self.a, "Legal Maxime").accroc)
        bb = self.tour(self.b, "Legal Damien")
        self.assertEqual(bb.accroc, Accroc.Conflit(["agents/Legal Maxime/CLAUDE.md"]), repr(bb))
        self.assertEqual(lire(os.path.join(self.b, "agents/Legal Maxime/CLAUDE.md")), "un\nB\ntrois\n",
                         "rien n'est écrasé chez B")
        self.assertEqual(bb.envoyes, 0)

    def test_en_mode_git_le_depot_de_l_agent_n_est_jamais_rendu(self):
        """Témoin négatif : sans `-depot`, une mémoire sans dépôt propre ne se synchronise pas."""
        with mock.patch.dict(os.environ, {"HARNAIS_SYNCHRO": "git"}):
            self.assertIsNone(synchro.depot(self.res(self.a, "Legal Maxime")))
        with mock.patch.dict(os.environ, {"HARNAIS_SYNCHRO": ""}):
            self.assertFalse(synchro.active())


class CasLimites(unittest.TestCase):
    """Textes et noms que la mutation d'un octet a laissés vivants ; chaque attendu a été relevé
    sur le Rust 0.12.8 (état écrit par `harnais attente` avec `HARNAIS_SYNCHRO=git`)."""

    def test_chaque_accroc_a_sa_phrase(self):
        self.assertEqual(synchro.phrase(Accroc.HorsLigne("réseau coupé")), "distant injoignable (réseau coupé)")
        self.assertEqual(synchro.phrase(Accroc.SansSuivi),
                         "le dépôt de mémoire n'a pas de branche suivie sur un distant")
        self.assertEqual(synchro.phrase(Accroc.Conflit(["mind/todo.md"])),
                         "le même passage a été modifié des deux côtés dans : mind/todo.md")
        self.assertEqual(synchro.phrase(Accroc.Conflit(["a.md", "b.md"])),
                         "le même passage a été modifié des deux côtés dans : a.md, b.md")
        self.assertEqual(synchro.phrase(Accroc.Bloque("un fichier local serait écrasé")),
                         "intégration refusée par git (un fichier local serait écrasé)")
        self.assertEqual(synchro.phrase(Accroc.Refuse("le distant a bougé")),
                         "envoi refusé, le distant a bougé (le distant a bougé) — réessayé au prochain tour")

    def test_une_erreur_git_se_resume_a_sa_premiere_ligne_parlante_de_160_signes(self):
        long = "fatal: " + "x" * 300
        self.assertEqual(synchro.premiere(long), long[:160])
        self.assertEqual(len(synchro.premiere(long)), 160)
        self.assertEqual(synchro.premiere("x" * 160), "x" * 160, "160 signes tiennent entiers")
        self.assertEqual(len(synchro.premiere("é" * 200)), 160)
        self.assertEqual(synchro.premiere("hint: patience\n\n  fatal: la vraie\nsuite"), "fatal: la vraie")
        self.assertEqual(synchro.premiere(""), "erreur sans message")
        self.assertEqual(synchro.premiere("hint: seulement un conseil"), "erreur sans message")

    def test_le_fichier_d_etat_porte_seize_signes_du_condense_du_depot(self):
        """`synchro-<16 signes>.json` : même nom que le Rust pour le même dépôt."""
        import hashlib
        import re
        depot = ("/private/tmp/claude-501/-Users-BigMax-Agentic-Harness/d154396e-1d8a-410b-8278-"
                 "6bb3672ea1a6/scratchpad/syncfixe/p/brain")
        with mock.patch.dict(os.environ, {"COPILOT_PLUGIN_DATA": "/donnees"}):
            f = synchro.fichier_etat(depot)
        self.assertEqual(f, os.path.join("/donnees", "attente", "synchro-657a64a06e81b7cc.json"))
        nom = os.path.basename(f)
        self.assertRegex(nom, r"\Asynchro-[0-9a-f]{16}\.json\Z")
        self.assertEqual(nom, "synchro-%s.json" % hashlib.sha1(depot.encode("utf-8")).hexdigest()[:16])
        with mock.patch.dict(os.environ, {"COPILOT_PLUGIN_DATA": "/donnees"}):
            self.assertNotEqual(synchro.fichier_etat("/autre/depot"), f)


if __name__ == "__main__":
    unittest.main()

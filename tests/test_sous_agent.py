# -*- coding: utf-8 -*-
"""La garde des sous-agents (portée de Claude 0.19.3) : un sous-agent qui regarde du visuel
ou reçoit un lot de plus de 30 éléments ne part pas sans l'accord de l'humain. Chaque refus
a son témoin muet.

Écarts voulus avec le harnais Claude : l'outil est `task` (Copilot) et non `Agent` /
`Workflow` ; ses champs ne sont pas documentés dans le dépôt, donc TOUS les champs texte
des arguments sont lus (PAS MESURÉ contre un `task` réel) ; le laissez-passer vaut pour la
copie de travail (racine git), pas pour un agent ; un refus sort par `hote.refus`.
"""
import json
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import hote  # noqa: E402
import sous_agent  # noqa: E402
from _gardes import Isole, charge_camel, charge_pascal, git, lance, muet, refus  # noqa: E402

# Une consigne synthétique de la forme du 18/10/2026 : produire des textes alternatifs
# en REGARDANT chaque image.
CONSIGNE_IMAGES = (
    "Tu rédiges des textes alternatifs (attribut alt, pour lecteurs d'écran) en français pour "
    "des diapositives de présentation.\n\n"
    "Méthode : pour chaque diapositive, convertis-la en PNG de 1000 px dans ton dossier de "
    "travail, puis regarde l'image avec l'outil Read et décris-la.")
# Un audit ordinaire, en lecture seule, qui PARLE d'images sans les regarder.
AUDIT = (
    "Tu fais un AUDIT D'ACCESSIBILITÉ EN LECTURE SEULE du site. N'ouvre jamais "
    "docs/operations.md. Lis d'abord docs/regles.md.\n"
    "5. Images : alt manquant ou non pertinent (alt = nom de fichier), images décoratives ; "
    "iframes sans title.\n"
    "- Images : formats servis, images surdimensionnées, poids des 10 plus lourdes ressources.\n"
    "- public/images fait ~400 Mo et ~1000 fichiers : combien sont réellement référencées ?\n"
    "- Liens : 404 = vidéo retirée ?")



class Base(Isole):
    def setUp(self):
        super().setUp()
        self.depot = os.path.realpath(self.dossier("depot"))
        git(self.depot, "init", "-q", "-b", "main")
        self.agent = os.path.join(self.depot, "agents", "PO")
        os.makedirs(self.agent)
        env = mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": self.agent})
        env.start()
        self.addCleanup(env.stop)

    def juge(self, prompt, description="tâche", **plus):
        ti = {"description": description, "prompt": prompt, "agent_type": "general-purpose"}
        ti.update(plus)
        return sous_agent.juge(hote.traduis(charge_camel("task", ti, self.agent)))

    def passe(self, motif="l'humain : « oui, 3 lots de 30 »"):
        return muet(sous_agent.laissez_passer, [motif])


class Visuel(Base):
    def test_la_consigne_du_18_10_est_refusee(self):
        r = self.juge(CONSIGNE_IMAGES)
        self.assertIsNotNone(r)
        self.assertIn("visuel", r)
        self.assertIn("laissez-passer-lot", r)
        self.assertIn("lot de 30", r)

    def test_regarder_l_image_mord_seul(self):
        # Sans la phrase des textes alternatifs, le verbe qui voit suffit.
        self.assertIsNotNone(self.juge("Pour chaque fichier, regarde l'image avec l'outil Read."))

    def test_l_audit_ordinaire_passe(self):
        self.assertIsNone(self.juge(AUDIT, description="Audit accessibilité"))

    def test_formes_qui_mordent(self):
        for p in ("Lis le contrat (PDF) et résume-le.",
                  "Ouvre docs/guide.pdf puis dis ce qu'il prévoit.",
                  "Look at each screenshot and describe the layout.",
                  "Décris les captures d'écran du dossier.",
                  "Fais un OCR des factures.",
                  "Write alt text for every picture on the page.",
                  "Ne lis pas le code, regarde les captures d'écran."):
            with self.subTest(p=p):
                self.assertIsNotNone(self.juge(p))

    def test_formes_qui_passent(self):
        for p in ("Ne lis aucune image : le code seul.",
                  "Lis le code qui génère les miniatures des images.",
                  "Do not open any screenshot; read src/ only.",
                  "Observations sur la capture d'écran réelle : la carte est trop large.",
                  'Le SVG a viewBox="0 0 120 60" ; porte-le dans l\'app.',
                  "Audite les gardes du dépôt et rends un rapport."):
            with self.subTest(p=p):
                self.assertIsNone(self.juge(p))

    def test_la_description_seule_suffit(self):
        self.assertIsNotNone(self.juge("Suis la méthode du fichier joint.",
                                       description="Décrire visuels lot 1"))

    def test_un_champ_inconnu_est_lu_aussi(self):
        """Les champs de `task` ne sont pas documentés ici : un champ texte inattendu,
        même imbriqué, est jugé comme la consigne."""
        ti = {"instructions": "Regarde chaque capture d'écran et note les défauts"}
        self.assertIsNotNone(sous_agent.juge(hote.traduis(charge_camel("task", ti, self.agent))))
        ti = {"prompt": "Audite le dépôt", "contexte": {"fichiers": ["a.py"],
                                                          "consigne": "Décris les images du dossier"}}
        self.assertIsNotNone(sous_agent.juge(hote.traduis(charge_camel("task", ti, self.agent))))
        # TÉMOIN : les mêmes champs, sans visuel, passent.
        ti = {"instructions": "Audite le dépôt", "contexte": {"fichiers": ["a.py"], "consigne": "Lis src/"}}
        self.assertIsNone(sous_agent.juge(hote.traduis(charge_camel("task", ti, self.agent))))

    def test_des_arguments_en_texte_json_sont_decodes(self):
        c = hote.traduis(charge_camel("task", json.dumps({"prompt": "Décris les images du dossier"}),
                                      self.agent))
        self.assertIsNotNone(sous_agent.juge(c))

    def test_les_deux_formes_de_charge_nomment_le_meme_outil(self):
        p = {"description": "d", "prompt": "Regarde l'image du dossier."}
        self.assertIsNotNone(sous_agent.juge(hote.traduis(charge_camel("task", p, self.agent))))
        self.assertIsNotNone(sous_agent.juge(hote.traduis(charge_pascal("Task", p, self.agent))))
        self.assertEqual(hote.outil_pascal("task"), "Task")

    def test_un_autre_outil_n_est_pas_juge(self):
        for outil, args in (("bash", {"command": "regarde l'image"}),
                            ("view", {"path": "regarde l'image.png"}),
                            ("edit", {"path": "x", "new_str": "Décris les images"}),
                            ("web_fetch", {"prompt": "regarde l'image"})):
            with self.subTest(outil=outil):
                self.assertIsNone(sous_agent.juge(hote.traduis(charge_camel(outil, args, self.agent))))
        # Ni un lancement sans consigne.
        self.assertIsNone(sous_agent.juge(hote.traduis(charge_camel("task", {}, self.agent))))
        self.assertIsNone(sous_agent.juge("pas un objet"))


class Lot(Base):
    def test_un_gros_lot_d_images_est_refuse_meme_muni(self):
        self.passe()
        r = self.juge("Décris les 2 273 images du dossier.")
        self.assertIsNotNone(r)
        self.assertIn("2273 médias", r)

    def test_un_lot_de_texte_passe(self):
        # CTO, 20/10 : le verrou est réservé aux médias ; un lot de texte n'a jamais
        # dépassé 6,7 M en un mois, et le coupe-circuit le couvre.
        for p in ("tests/ (38 fichiers, 7371 l.) : classe chaque fichier.",
                  "78 migration files were added. Read each file.",
                  "Il y a des centaines de pages à résumer."):
            with self.subTest(p=p):
                self.assertIsNone(self.juge(p))

    def test_une_masse_sans_chiffre(self):
        self.passe()
        self.assertIsNotNone(self.juge("Il y a des centaines de captures à trier."))
        self.assertIsNotNone(self.juge("Thousands of screenshots are in the folder."))

    def test_trente_passe_avec_le_laissez_passer(self):
        self.assertIsNotNone(self.juge("Décris ces 30 images."))
        self.passe()
        self.assertIsNone(self.juge("Décris ces 30 images."))
        self.assertIsNotNone(self.juge("Décris ces 31 images."))


class LaissezPasser(Base):
    def test_il_ouvre_le_visuel_et_journalise(self):
        self.assertIsNotNone(self.juge(CONSIGNE_IMAGES))
        self.assertEqual(self.passe(), 0)
        self.assertIsNone(self.juge(CONSIGNE_IMAGES))
        _, log = sous_agent._fichiers(sous_agent._agent(self.agent))
        with open(log, encoding="utf-8") as h:
            lignes = h.read().splitlines()
        self.assertTrue(lignes[0].split("\t")[1] == "déposé")
        self.assertTrue(lignes[-1].split("\t")[1] == "usage")
        self.assertIn("3 lots de 30", lignes[-1])

    def test_il_expire(self):
        self.passe()
        f, _ = sous_agent._fichiers(sous_agent._agent(self.agent))
        vieux = time.time() - (sous_agent.DUREE * 60 + 5)
        os.utime(f, (vieux, vieux))
        self.assertIsNotNone(self.juge(CONSIGNE_IMAGES))

    def test_il_vaut_pour_la_copie_ou_il_est_pose_pas_pour_une_autre(self):
        """L'app lance toutes les conversations à la racine d'une copie : le shell d'un
        agent ne sait pas qui parle, la clé est donc le dépôt — que le hook (dans
        `agents/PO`) et le shell (à la racine) retrouvent tous deux."""
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": self.depot}):
            self.assertEqual(muet(sous_agent.laissez_passer, ["oui de l'humain"]), 0)
        self.assertIsNone(self.juge(CONSIGNE_IMAGES), "posé depuis la racine, vu depuis agents/PO")
        # TÉMOIN : une autre copie, un autre dépôt, ne profite pas du laissez-passer.
        autre = os.path.realpath(self.dossier("autre"))
        git(autre, "init", "-q", "-b", "main")
        with mock.patch.dict(os.environ, {"COPILOT_PROJECT_DIR": autre}):
            self.assertIsNotNone(sous_agent.juge(hote.traduis(charge_camel(
                "task", {"prompt": CONSIGNE_IMAGES}, autre))))

    def test_sans_motif_il_refuse(self):
        self.assertEqual(muet(sous_agent.laissez_passer, []), 2)
        self.assertIsNotNone(self.juge(CONSIGNE_IMAGES))


class Lanceur(Base):
    def test_le_refus_sort_en_decision_du_hook(self):
        o = lance("sous-agent", charge_camel("task", {"description": "Décrire visuels", "prompt": CONSIGNE_IMAGES},
                                              self.agent), {"COPILOT_PROJECT_DIR": self.agent})
        self.assertEqual(o.returncode, 0)
        d = refus(o)
        self.assertEqual(d["permissionDecision"], "deny")        # à la racine
        self.assertNotIn("hookSpecificOutput", d)
        self.assertIn("l'humain", d["permissionDecisionReason"])
        self.assertTrue(o.stdout.decode("ascii"))                # ASCII pur

    def test_muet_sur_l_audit_et_sur_l_illisible(self):
        for entree in (charge_camel("task", {"prompt": AUDIT}, self.agent),
                       charge_camel("bash", {"command": CONSIGNE_IMAGES}, self.agent),
                       "{pas du json"):
            o = lance("sous-agent", entree, {"COPILOT_PROJECT_DIR": self.agent})
            self.assertEqual((o.returncode, o.stdout), (0, b""))

    def test_le_juge_muet_fait_taire_le_hook(self):
        o = lance("sous-agent", charge_camel("task", {"prompt": CONSIGNE_IMAGES}, self.agent),
                  {"COPILOT_PROJECT_DIR": self.agent, "HARNAIS_JUGE": "1"})
        self.assertEqual((o.returncode, o.stdout), (0, b""))

    def test_le_laissez_passer_par_le_lanceur(self):
        o = lance("laissez-passer-lot", "", {"COPILOT_PROJECT_DIR": self.agent}, ["oui de l'humain"])
        self.assertEqual(o.returncode, 0, o.stderr)
        self.assertIsNone(self.juge(CONSIGNE_IMAGES))
        # Depuis la racine de la copie, comme le shell d'un agent de l'app.
        o = lance("sous-agent", charge_camel("task", {"prompt": CONSIGNE_IMAGES}, self.depot),
                  {"COPILOT_PROJECT_DIR": self.depot})
        self.assertEqual((o.returncode, o.stdout), (0, b""), o.stderr)


if __name__ == "__main__":
    unittest.main()

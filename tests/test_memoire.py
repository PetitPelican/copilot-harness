# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/memoire.rs` (19 tests)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole, ecris, git
import memoire
from memoire import (BRAIN, NOM, Forme, base, base_projet, lot, pour_agent, pour_projet,
                     racine_depot, resous)


def mk(*parts):
    os.makedirs(os.path.join(*parts), exist_ok=True)


def j(*parts):
    return os.path.join(*parts)


class Essais(Isole):

    def bac(self, n):
        """`bac` du Rust : un dossier neuf, canonicalisé (sur macOS /var -> /private/var)."""
        d = tempfile.mkdtemp(prefix="harnais-memoire-%s-" % n)
        self.addCleanup(shutil.rmtree, d, True)
        return os.path.realpath(d)

    def depot(self, n):
        d = self.bac(n)
        subprocess.run(["git", "init", "-q"], cwd=d, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return d

    def test_copilot_resout_la_memoire_du_worktree_jamais_celle_du_principal(self):
        d = self.depot("worktree-isole")
        mk(d, "brain/fact")
        mk(d, "brain/mind")
        ecris(j(d, "brain/fact/base.md"), "principal")
        git(d, "add", ".")
        git(d, "commit", "-qm", "initial")
        w = j(d, "copie")
        git(d, "worktree", "add", "-q", "-b", "copie", w)
        ecris(j(w, "brain/fact/base.md"), "copie")
        r = resous(w)
        self.assertEqual(r.racine, os.path.realpath(w))
        self.assertEqual(r.fact, j(os.path.realpath(w), "brain", "fact"))
        with open(j(r.fact, "base.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "copie")
        shutil.rmtree(j(w, "brain"))
        self.assertEqual(resous(w).forme, Forme.SansMemoire, "pas de repli sur le principal")
        git(d, "worktree", "remove", "--force", w)

    def test_le_prefixe_de_l_esprit_suit_la_forme(self):
        """LE PRÉFIXE DE L'ESPRIT SUIT LA FORME, dans les trois formes : c'est leur
        DIVERGENCE qui est le sujet, pas l'une d'elles."""
        d = self.bac("pfx-mind")
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # v1 · en place
        mk(d, ".fact")
        mk(d, ".mind")
        self.assertEqual(resous(d).prefixe_mind, ".mind/")

        # v2 · LE CERVEAU, ET L'ANCIEN A DISPARU. Les laisser cohabiter rend
        # `Ambigue` — c'est le but de cette forme, et la migration retire
        # l'ancien dans le même geste.
        shutil.rmtree(j(d, ".fact"))
        shutil.rmtree(j(d, ".mind"))
        mk(d, "brain/fact")
        mk(d, "brain/mind")
        r = resous(d)
        self.assertEqual(r.prefixe_mind, "brain/mind/")
        self.assertEqual(r.prefixe_fact, "brain/fact/")

        # v2 · le cerveau, à plusieurs — l'esprit porte le nom de l'agent
        a = j(d, "agents/ios")
        mk(a, ".github/copilot")
        mk(d, "brain/mind/ios")
        r = resous(a)
        self.assertEqual(r.prefixe_mind, "brain/mind/ios/")
        # ET LE COMMUN RESTE COMMUN : les faits ne prennent pas le nom.
        self.assertEqual(r.prefixe_fact, "brain/fact/")

    def test_hors_depot_tout_rend_none(self):
        d = self.bac("hors")
        # TÉMOIN NÉGATIF : sans dépôt, aucune résolution ne doit inventer un chemin.
        self.assertIsNone(racine_depot(d))
        self.assertIsNone(base(d))
        self.assertEqual(pour_agent(d), (None, None))
        self.assertEqual(lot(d), "")

    def test_un_projet_sans_dossier_memoire_ne_bouge_pas(self):
        d = self.bac("enplace")
        mk(d, ".fact")
        # Pas de `memoire/` : la réponse est « résous comme avant », pas une erreur.
        self.assertIsNone(base_projet(d))
        self.assertEqual(pour_projet(d), (None, None))

    def test_un_projet_deporte_rend_ses_deux_maisons(self):
        d = self.bac("deporte")
        for s in [".fact", ".mind", "agents/Projet PO/.mind", "agents/QA/.mind"]:
            mk(d, NOM, s)
        fact, etats = pour_projet(d)
        self.assertEqual(fact, j(d, NOM, ".fact"))
        e = etats
        # Deux agents, classés — et le `.mind` racine EST ignoré quand des
        # agents existent : c'est la règle de la version Python.
        self.assertEqual(len(e), 2)
        self.assertEqual(e[0][0], "Projet PO")
        self.assertEqual(e[1][0], "QA")

    def test_mono_agent_retombe_sur_le_mind_racine(self):
        d = self.bac("mono")
        mk(d, NOM, ".mind")
        _, etats = pour_projet(d)
        e = etats
        self.assertEqual(len(e), 1)
        self.assertIsNone(e[0][0], "aucun nom : c'est le projet lui-même")

    # ── `resous()` : la forme est une VALEUR ──────────────────────────────
    # Chaque cas porte son contraire. Un contrôle qui ne rend jamais `Ambigue`
    # ne prouve pas qu'il sait la reconnaître.

    def test_resous_hors_depot_ne_devine_rien(self):
        r = resous(self.bac("r-hors"))
        self.assertEqual(r.forme, Forme.HorsDepot)
        self.assertIsNone(r.racine)
        self.assertIsNone(r.fact)
        # TÉMOIN : hors dépôt, `mind` aussi reste vide — sinon on inventerait
        # un chemin dans un dossier qui n'appartient à personne.
        self.assertIsNone(r.mind)
        self.assertFalse(Forme.a_des_faits(r.forme))

    def test_un_depot_sans_memoire_ne_se_dit_plus_hors_depot(self):
        # Ce cas se nommait « hors-depot » alors que la ligne suivante du
        # diagnostic donnait la racine du dépôt.
        d = self.depot("r-sansmem")
        r = resous(d)
        self.assertEqual(r.forme, Forme.SansMemoire)
        self.assertEqual(Forme.mot(r.forme), "sans-memoire")
        self.assertIsNotNone(r.racine)
        self.assertIsNone(r.base_des_prefixes())
        # TÉMOIN : le même dossier avec des faits change de forme, et sa base
        # des préfixes est l'arbre — pas `None` pour tout le monde.
        mk(d, ".fact")
        r = resous(d)
        self.assertEqual(r.forme, Forme.EnPlace)
        self.assertEqual(r.base_des_prefixes(), r.arbre)
        self.assertIsNotNone(r.base_des_prefixes())

    def test_resous_en_place_rend_des_chemins_et_un_prefixe(self):
        d = self.depot("r-enplace")
        mk(d, ".fact")
        r = resous(d)
        self.assertEqual(r.forme, Forme.EnPlace)
        self.assertEqual(r.fact, j(d, ".fact"))
        self.assertEqual(r.mind, j(d, ".mind"))
        # Le préfixe est ce que `git diff --cached` rend, barre finale comprise.
        self.assertEqual(r.prefixe_fact, ".fact/")
        self.assertTrue(Forme.a_des_faits(r.forme))

    def test_resous_en_place_depuis_un_agent_porte_le_lot(self):
        d = self.depot("r-agent")
        mk(d, ".fact")
        a = j(d, "agents", "QA")
        mk(a)
        r = resous(a)
        self.assertEqual(r.forme, Forme.EnPlace)
        self.assertEqual(r.lot, "agents/QA")
        # Les faits sont au PROJET, l'état est à l'AGENT — c'est toute la règle.
        self.assertEqual(r.fact, j(d, ".fact"))
        # Le lot reste en `/` (préfixe git), comme le Rust : comparer la forme normale.
        self.assertEqual(os.path.normpath(r.mind), j(d, "agents", "QA", ".mind"))
        self.assertEqual(r.prefixe_fact, ".fact/")

    def test_resous_deportee_vise_le_depot_de_memoire(self):
        d = self.depot("r-deporte")
        mk(d, NOM, ".fact")
        r = resous(d)
        self.assertEqual(r.forme, Forme.Deportee)
        self.assertEqual(r.fact, j(d, NOM, ".fact"))
        # DÉPORTÉE : le préfixe est NU. Les chemins que la garde compare
        # viennent du dépôt de mémoire, où le lot n'existe pas.
        self.assertEqual(r.prefixe_fact, ".fact/")
        self.assertEqual(r.prefixe_projet, "")
        self.assertTrue(Forme.a_des_faits(r.forme))

    def test_dans_la_v1_le_deporte_gagne_et_ce_n_est_pas_une_ambiguite(self):
        d = self.depot("r-v1-deux")
        mk(d, ".fact")
        mk(d, NOM, ".fact")
        r = resous(d)
        # LE DÉPORT NE SUPPRIME PAS L'ANCIEN DOSSIER : les deux cohabitent
        # légitimement, et la règle « le déporté gagne » est établie. Élargir
        # l'ambiguïté à ce cas ferait cesser des briefings de trouver leurs
        # faits. Un garde trop large casse ce qu'il devait protéger.
        self.assertEqual(r.forme, Forme.Deportee)
        self.assertEqual(r.fact, j(d, NOM, ".fact"))

    def test_resous_sans_faits_ne_pretend_pas_en_avoir(self):
        d = self.depot("r-avant")
        # Ni `.fact/` ni `memoire/` : la forme d'AVANT la migration.
        r = resous(d)
        self.assertIsNone(r.fact)
        # TÉMOIN : c'est ici que se jouait le piège du `cap:`. Un projet sans
        # faits ne doit pas être annoncé comme en ayant, sinon la garde de
        # commit lui réclame le mauvais contrat d'en-tête.
        self.assertFalse(Forme.a_des_faits(r.forme))
        # Mais le chemin de l'état est rendu quand même : l'appelant doit
        # pouvoir dire « cherché ici, absent », jamais rester muet.
        self.assertEqual(r.mind, j(d, ".mind"))

    # ── v2 · le cerveau ──────────────────────────────────────────────────

    def test_resous_v2_mono_un_seul_esprit(self):
        d = self.depot("r-brain-mono")
        for s in ["fact", "mind"]:
            mk(d, BRAIN, s)
        r = resous(d)
        self.assertEqual(r.forme, Forme.Brain)
        self.assertEqual(r.fact, j(d, BRAIN, "fact"))
        # MONO : pas de niveau `<nom>`. Il n'y a qu'un esprit, le nommer serait
        # inventer une équipe qui n'existe pas.
        self.assertEqual(r.mind, j(d, BRAIN, "mind"))
        # Pas de carnet non plus : personne à qui écrire, et un dossier vide
        # se lirait comme un carnet muet.
        self.assertIsNone(r.workspace)
        self.assertFalse(r.brain_autonome)
        self.assertTrue(Forme.a_des_faits(r.forme))

    def test_le_carnet_nait_la_ou_on_le_cherche(self):
        """Le témoin porte les deux sens : chaque forme rend SON emplacement, et
        aucune ne rend celui d'une autre."""
        d = self.depot("r-ws")
        # en place : le carnet est à la racine du dépôt de code
        mk(d, ".fact")
        self.assertEqual(resous(d).workspace_prevu(), j(d, "equipe"))

        # cerveau : le carnet est DANS le cerveau, pas à côté
        b = self.depot("r-ws-brain")
        mk(b, BRAIN, "fact")
        vu = resous(b).workspace_prevu()
        self.assertTrue(vu.endswith(os.path.join("brain", "workspace")), "cerveau : rendu %r" % vu)
        self.assertFalse(vu.endswith("equipe"), "cerveau : rend l'emplacement d'en-place")

        # AMBIGUË : deux arbres, aucun choix. Créer ici, c'est créer un carnet
        # que l'autre arbre ne verra jamais.
        a = self.depot("r-ws-ambigu")
        mk(a, BRAIN, "fact")
        mk(a, ".fact")
        self.assertEqual(resous(a).forme, Forme.Ambigue)
        self.assertIsNone(resous(a).workspace_prevu())

    def test_la_racine_et_l_arbre_s_ecrivent_pareil(self):
        """UNE SEULE ORTHOGRAPHE PAR DOSSIER, dans toute la résolution. (Le défaut
        ne se voit que sous Windows ; sur macOS ce test passe dans les deux sens.)"""
        d = self.depot("r-orthographe")
        mk(d, ".fact")
        r = resous(d)
        self.assertEqual(r.racine, r.arbre, "deux orthographes du même dossier")
        # Et le carnet se compose sur cette orthographe-là, pas sur une autre.
        self.assertEqual(r.workspace_prevu(), j(d, "equipe"))

    def test_resous_v2_multi_un_esprit_par_agent(self):
        d = self.depot("r-brain-multi")
        for s in ["fact", "mind/Projet QA", "workspace"]:
            mk(d, BRAIN, s)
        mk(d, "agents", "Projet QA")
        r = resous(j(d, "agents", "Projet QA"))
        self.assertEqual(r.forme, Forme.Brain)
        self.assertEqual(r.lot, "agents/Projet QA")
        # `agents/` n'existe PAS dans le cerveau : il ne désigne que le dossier
        # de lancement, dans le code. Le cerveau range par NOM.
        self.assertEqual(r.nom_agent, "Projet QA")
        self.assertEqual(r.mind, j(d, BRAIN, "mind", "Projet QA"))
        self.assertEqual(r.fact, j(d, BRAIN, "fact"))
        self.assertEqual(r.workspace, j(d, BRAIN, "workspace"))

    def test_resous_refuse_de_choisir_entre_les_trois_arbres(self):
        # TROIS combinaisons, et aucune ne doit rendre un arbre. C'est l'état
        # qu'une migration interrompue laisse : servir l'un des deux servirait
        # l'état d'hier, sans un mot.
        # L'ANCIEN CONTRE LE NEUF, et seulement ça. `.fact` + `memoire` est
        # une cohabitation de v1, pas une migration à moitié faite.
        for a, b in [(".fact", BRAIN), (NOM, BRAIN)]:
            d = self.depot("r-3arbres-%s-%s" % (a.lstrip("."), b))
            mk(d, a)
            mk(d, b)
            r = resous(d)
            self.assertEqual(r.forme, Forme.Ambigue, "%s + %s devait être ambigu" % (a, b))
            # ET RIEN N'EST RENDU. Un chemin rendu serait lu.
            self.assertIsNone(r.fact)
            self.assertIsNone(r.mind)

    def test_resous_v2_sait_si_le_cerveau_a_son_depot(self):
        d = self.depot("r-brain-autonome")
        mk(d, BRAIN, "fact")
        self.assertFalse(resous(d).brain_autonome)
        # Ce qui reste de « déportée » une fois que ce n'est plus une forme :
        # une propriété, qui ne décide que d'une chose — où l'on commite.
        subprocess.run(["git", "init", "-q"], cwd=j(d, BRAIN),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertTrue(resous(d).brain_autonome)


class Equipe(Isole):
    """v3 · « UN DOSSIER PAR AGENT » (décision du 14/10/2026), porté de Claude 0.19."""

    def setUp(self):
        Isole.setUp(self)
        import banc_equipe
        self.x = banc_equipe.construis(os.path.realpath(self.dossier("equipe")))

    def j(self, *p):
        return os.path.join(self.x, *p)

    def test_depuis_le_dossier_de_l_agent(self):
        r = resous(self.j("agents", "PO"))
        self.assertEqual(r.forme, Forme.Equipe)
        self.assertEqual(r.projet, self.x)
        self.assertEqual(r.fact, self.j("fact"))
        self.assertEqual(r.mind, self.j("agents", "PO"))
        self.assertEqual(r.workspace, self.j("shared"))
        self.assertEqual((r.lot, r.prefixe_lot, r.nom_agent), ("agents/PO", "agents/PO/", "PO"))
        self.assertEqual((r.prefixe_fact, r.prefixe_mind), ("fact/", "agents/PO/"))
        self.assertTrue(r.brain_autonome)
        self.assertEqual(r.base_des_prefixes(), self.x)
        self.assertEqual(r.workspace_prevu(), self.j("shared"))
        # git tourne DANS la mémoire : c'est à l'appelant de le voir.
        self.assertEqual(r.racine, self.x)

    def test_depuis_le_fond_de_sa_copie_du_code(self):
        """Démarrer n'importe où sous `agents/<nom>/` rend l'équipe — aucun outil ne
        peut alors recréer un `brain/` dans le code. Et git y parle du CODE.
        COPILOT : `racine` est l'arbre courant (la copie de l'agent), jamais le
        checkout principal — l'app isole chaque copie avec sa propre mémoire."""
        for a in ("OPS", "PO"):
            r = resous(self.j("agents", a, "code", "apps"))
            self.assertEqual((r.forme, r.mind, r.nom_agent), (Forme.Equipe, self.j("agents", a), a))
            self.assertNotEqual(r.racine, self.x, "git devait parler du dépôt du code")
        self.assertEqual(resous(self.j("agents", "PO", "code")).racine, self.j("agents", "PO", "code"))

    def test_git_dans_le_code_position_dans_l_agent(self):
        r = memoire.resous_depuis(self.j("agents", "PO", "code"), self.j("agents", "PO"))
        self.assertEqual((r.forme, r.nom_agent), (Forme.Equipe, "PO"))
        self.assertEqual(r.arbre, self.j("agents", "PO", "code"))

    def test_depuis_la_racine_de_l_equipe(self):
        r = resous(self.x)
        self.assertEqual((r.forme, r.nom_agent, r.lot), (Forme.Equipe, "", ""))
        self.assertEqual(r.mind, self.j("agents"))

    def test_temoins_negatifs(self):
        """Sans `fact/`, ou avec un `brain/` à côté, ce n'est PAS une équipe : un
        projet `brain/` multi a aussi des `agents/<nom>/`."""
        shutil.rmtree(self.j("fact"))
        self.assertNotEqual(resous(self.j("agents", "PO")).forme, Forme.Equipe)
        mk(self.x, "fact")
        mk(self.x, BRAIN, "fact")
        self.assertNotEqual(resous(self.j("agents", "PO")).forme, Forme.Equipe)
        self.assertEqual(memoire.forme_mot(Forme.Equipe), "equipe")
        self.assertTrue(memoire.a_des_faits(Forme.Equipe))

    def test_porteur_equipe_sans_git_ni_dossier_frere(self):
        """Un dossier `agents/<nom>/` sous une racine sans dépôt propre n'est pas une
        équipe ; et la remontée finit à la racine du lecteur sans boucler."""
        # Les objets de git sont en lecture seule sous Windows : `rmtree` seul y échoue.
        shutil.rmtree(self.j(".git"), onerror=lambda f, p, _: (os.chmod(p, 0o700), f(p)))
        self.assertIsNone(memoire.porteur_equipe(self.j("agents", "PO")))
        self.assertIsNone(memoire.porteur_equipe(os.path.abspath(os.sep)))

    def test_dossier_du_commit(self):
        """`git -C <dir>` et `cd <dir> &&` désignent où git tourne ; un dossier qui
        n'existe pas rend le dossier courant (git échouera de lui-même)."""
        c = self.j("agents", "PO")
        f = memoire.dossier_du_commit
        self.assertEqual(f("git -C code commit -m x", c), os.path.normpath(self.j("agents", "PO", "code")))
        self.assertEqual(f('git -C "code" commit', c), os.path.normpath(self.j("agents", "PO", "code")))
        self.assertEqual(f("cd code && git commit -m x", c), os.path.normpath(self.j("agents", "PO", "code")))
        # témoins : rien à suivre, ou dossier absent
        self.assertEqual(f("git commit -m x", c), c)
        self.assertEqual(f("git -C nexiste-pas commit", c), c)

    def test_natif_ne_touche_pas_un_chemin_deja_natif(self):
        self.assertIsNone(memoire.natif(None))
        self.assertEqual(memoire.natif(""), "")
        d = os.path.join(self.x, "fact")
        self.assertEqual(memoire.natif(d), d)
        if os.name == "nt":
            self.assertEqual(memoire.natif("C:/a/b"), "C:\\a\\b")

    def test_natif_ecrit_un_chemin_de_git_comme_windows_l_ecrit(self):
        """Sous Windows git rend `C:/Users/u`, Python `C:\\Users\\u` : le même dossier doit
        s'écrire pareil (mesuré par la CI Windows de Claude, 16/10/2026). Simulé ici :
        TÉMOIN, hors Windows le chemin n'est pas touché."""
        import ntpath
        from unittest import mock
        with mock.patch.object(memoire.os, "name", "nt"), mock.patch.object(memoire.os.path, "normpath", ntpath.normpath):
            self.assertEqual(memoire.natif("C:/Users/u"), "C:\\Users\\u")
            self.assertEqual(memoire.natif(None), None)
        if os.name != "nt":
            self.assertEqual(memoire.natif("C:/Users/u"), "C:/Users/u")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/attente.rs` (36 tests Rust).

26 portés ici, 10 écartés : ils ne testent QUE l'écriture ou la lecture des Rappels
macOS, absents du Python (écart voulu n° 3). Liste des écartés, avec la fonction
Rust qu'ils éprouvent :

  essais_rappels_natifs
    - un_osascript_intercale_ferme_le_chemin_natif ........ premier_dans_path / natif_permis
    - le_vrai_osascript_ouvre_le_chemin_natif_et_son_absence_le_ferme ... idem
  essais_titres_sur_une_ligne
    - un_morceau_de_titre_n_est_pas_une_demande_de_user .... recolle (lecture des Rappels)
    - la_lecture_complete_recolle_le_titre_reel ............ analyse_lecture (idem)
  essais
    - une_fin_de_tour_qui_ne_peut_pas_ecrire_nomme_la_liste_le_compte_et_la_cause
                                                           note_rappels_muets
    - l_encadrement_ne_peut_pas_etre_referme_par_son_contenu  encadre (texte venu des Rappels)
    - la_reponse_se_lit_dans_le_titre ...................... base_reponse (« Ta réponse : »)
  essais_rappels_croises
    - un_doublon_ouvert_se_voit_et_une_coche_ne_compte_pas . analyse_lecture
    - question_a_choix_reconnue_et_pas_le_reste ............ question_a_choix (cochage Rappels)
    - un_verrou_tenu_refuse_un_perime_se_reprend ........... prends_verrou des Rappels
                                                           (pas celui de briefing, porté
                                                           par test_briefing)
"""
import json
import os
import re
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import RACINE_DEPOT, Isole, ecris, git
import attente
import briefing
from attente import (GARDES_ACTIVES, PIED_RENVOI, TITRE_CIBLES, active, blocs_bruts, chantiers,
                     cibles_a_rappeler, consigne, dernier_message, enveloppe_note, entete,
                     fini_re, fnmatch, insere_cible, lis, libelle, libelle_carnet, ligne_cible,
                     lien_notion, lisible, ou_ecrire, posee, repart_sur_un_renvoi,
                     repere_cible, reponse_re, sha16, sort_de_la_machine, specs_constat,
                     texte_cible, titre_et_corps, tour_carnet, zone_touchee)

PY = os.path.join(RACINE_DEPOT, "py")


def ev(t, contenu):
    return {"type": t, "data": {"content": contenu}}


class Essais(Isole):

    # ── essais_titres_sur_une_ligne ──────────────────────────────────────

    def test_un_titre_coupe_en_debut_de_ligne_tient_sur_une_ligne(self):
        # LE DÉFAUT, REPRODUIT : un saut de ligne seul passait `lisible`.
        self.assertIn("\n", lisible("Je publie ?\noui / non"))
        t, c = titre_et_corps("**Je publie ?\noui / non**\n      oui → on publie")
        self.assertEqual(t, "Je publie ? oui / non")
        self.assertIn("oui → on publie", c)
        # Le cas qui marchait déjà — suite indentée — ne bouge pas.
        self.assertEqual(titre_et_corps("**Je publie ?\n      oui / non**")[0],
                         "Je publie ? oui / non")

    # ── essais_poser ─────────────────────────────────────────────────────

    def test_une_question_posee_meme_reformulee_ne_relance_pas(self):
        titre = ("On refait avant octobre les quatre graphiques que le directeur sportif "
                 "refuse ? 1 / 2 / 3")
        dit = ("**On refait avant octobre les quatre graphiques que le directeur sportif "
               "refuse ?**\n1. Oui…")
        self.assertTrue(posee(dit, titre))
        reformule = ("Question : le directeur sportif refuse quatre graphiques — on les refait "
                     "avant octobre ?")
        self.assertTrue(posee(reformule, titre))
        # LE TÉMOIN : un message qui parle d'autre chose ne la pose pas.
        self.assertFalse(posee("J'ai livré l'écran 3 et corrigé la facturation.", titre))

    def journal_de_session(self, nom, lignes):
        d = self.dossier("journal")
        f = os.path.join(d, "harnais-%s-%d.jsonl" % (nom, os.getpid()))
        ecris(f, "\n".join(json.dumps(v, ensure_ascii=False) for v in lignes))
        return f

    def test_le_dernier_message_est_celui_du_tour(self):
        f = self.journal_de_session("poser", [
            ev("user.message", "une demande"),
            ev("assistant.message", "vieux"),
            ev("user.message", "une autre demande"),
            ev("assistant.message", "A"),
            {"type": "tool.execution_complete", "data": {}},
            ev("assistant.message", "B"),
        ])
        data = {"transcript_path": f}
        self.assertEqual(dernier_message(data), "A\nB")
        self.assertFalse(repart_sur_un_renvoi(data), "un message humain n'est pas un renvoi")
        self.assertEqual(dernier_message({}), "")

    def test_un_renvoi_de_fin_de_tour_n_efface_pas_ce_qui_a_ete_pose(self):
        """LE CAS : la question posée, puis un renvoi de fin de tour, puis une
        ligne. Le tour porte encore la question — la relancer, c'était lui faire
        tout recopier."""
        renvoi = "attente : ...%s" % PIED_RENVOI
        lignes = [
            ev("user.message", "une demande"),
            ev("assistant.message", "Je fais faire une version 11 d'Android ? 1 / 2"),
            ev("user.message", renvoi),
            ev("assistant.message", "Ligne corrigée."),
        ]
        f = self.journal_de_session("renvoi", lignes)
        data = {"transcript_path": f}
        tour = dernier_message(data)
        self.assertTrue(posee(tour, "Je fais faire une version 11 d'Android : 1 non / 2 oui ?"),
                        tour)
        self.assertTrue(repart_sur_un_renvoi(data),
                        "le dernier message de l'utilisateur est un renvoi")
        # TÉMOIN : un vrai message humain ouvre bien un nouveau tour.
        l2 = list(lignes)
        l2.insert(3, ev("user.message", "autre chose"))
        f2 = self.journal_de_session("renvoi2", l2)
        data2 = {"transcript_path": f2}
        self.assertNotIn("version 11", dernier_message(data2))
        self.assertFalse(repart_sur_un_renvoi(data2))

    def test_un_lien_notion_porte_l_identifiant_de_la_page(self):
        self.assertTrue(lien_notion(
            "↳ https://www.notion.so/projet/Ecran-3-0123456789abcdef0123456789abcdef"))
        self.assertTrue(lien_notion("↳ notion.so/0123456789abcdef0123456789abcdef"))
        # TÉMOINS : le nom seul, un domaine sans page, une page d'ailleurs.
        self.assertFalse(lien_notion("↳ voir la ligne dans Notion"))
        self.assertFalse(lien_notion("↳ https://www.notion.so/"))
        self.assertFalse(lien_notion("↳ https://example.com/0123456789abcdef0123456789abcdef"))

    def test_une_question_a_tirets_est_bien_formee(self):
        """Une question recopiée d'un todo : bien formée, avec des tirets."""
        corps = ("  - 1 → rien ne part : tu installes Android 10.\n"
                 "  - 2 → tu m'écris ce qui manque.\n"
                 "  - fini quand → ton Android montre les cartes d'avant.")
        self.assertTrue(fini_re().search(corps))
        sans_fini = fini_re().sub("", corps)
        self.assertGreaterEqual(len(list(reponse_re().finditer(sans_fini))), 2)
        # TÉMOIN : sans ligne de fin, ni avec ni sans tiret, rien n'est reconnu.
        self.assertFalse(fini_re().search("  - 1 → a\n  - 2 → b\n  - quand c'est fini, dis-le"))
        self.assertFalse(fini_re().search("  - enfin, fini quand tu veux"))

    # ── essais_repere_carnet ─────────────────────────────────────────────

    def commit(self, d, f, t):
        ecris(os.path.join(d, f), t)
        git(d, "add", "-A")
        git(d, "commit", "-qm", f)

    def banc(self, nom):
        b = self.dossier("repere-%s" % nom)
        d = os.path.join(b, "agent")
        os.makedirs(d)
        git(d, "init", "-q", "-b", "dev")
        self.commit(d, "partage/a.txt", "0")
        self.commit(d, "propre/x.txt", "0")
        repere = os.path.join(b, "agent.tete")
        # PREMIER PASSAGE : il pose le repère sans rien juger.
        self.assertEqual(zone_touchee(d, repere, ["partage/*"]), [])
        self.assertEqual(lis(repere).strip(), git(d, "rev-parse", "HEAD").strip())
        return b, d, ["partage/*"]

    def test_un_commit_propre_dans_la_zone_sans_entree_mord(self):
        # LE TÉMOIN NÉGATIF : sans lui, une garde qui ne mord plus jamais
        # passerait tous les essais qui suivent.
        b, d, z = self.banc("mord")
        self.commit(d, "partage/a.txt", "1")
        self.assertEqual(tour_carnet(d, os.path.join(b, "agent.tete"), z, False),
                         ["partage/a.txt"])
        self.commit(d, "propre/x.txt", "1")
        self.assertEqual(tour_carnet(d, os.path.join(b, "agent.tete"), z, False), [], "hors zone")

    def test_un_tour_verse_avance_le_repere(self):
        b, d, z = self.banc("verse")
        vieux = os.path.join(b, "vieux.tete")
        shutil.copy(os.path.join(b, "agent.tete"), vieux)
        self.commit(d, "partage/a.txt", "1")
        self.assertEqual(tour_carnet(d, os.path.join(b, "agent.tete"), z, True), [])
        # LE CAS COURANT : le tour suivant, sans rien commiter, ne ressort rien.
        self.assertEqual(tour_carnet(d, os.path.join(b, "agent.tete"), z, False), [])
        # ET LE DÉFAUT EST BIEN REPRODUIT : un repère resté en arrière, comme
        # avant la correction, ressortait le commit déjà versé.
        self.assertEqual(zone_touchee(d, vieux, z), ["partage/a.txt"])

    def test_le_travail_d_un_pair_arrive_par_fusion_ne_compte_pas(self):
        b, d, z = self.banc("pair")
        p = os.path.join(b, "pair")
        git(d, "worktree", "add", "-q", "-b", "pair", p)
        self.commit(p, "partage/b.txt", "du pair")
        # en avance rapide : le journal dit `merge`, pas `commit`
        git(d, "merge", "-q", "pair")
        self.assertEqual(tour_carnet(d, os.path.join(b, "agent.tete"), z, False), [],
                         "avance rapide")
        # par un vrai commit de fusion, mêlé à un commit propre dans la zone
        self.commit(p, "partage/c.txt", "du pair")
        self.commit(d, "partage/moi.txt", "à moi")
        git(d, "merge", "-q", "--no-edit", "pair")
        self.assertEqual(tour_carnet(d, os.path.join(b, "agent.tete"), z, False),
                         ["partage/moi.txt"])

    # ── essais_signature ─────────────────────────────────────────────────

    def test_chaque_garde_se_dit_en_clair_et_signe_son_message(self):
        # Le Rust balaie sa propre source à la recherche de `Some("B…")`. Ici : les
        # codes passés à `sortie(...)` — le code suivi de son détail — dans
        # `attente.py` et `experts.py` (la garde B16 y vit).
        codes = set()
        for fichier in ("attente.py", "experts.py"):
            source = lis(os.path.join(PY, fichier))
            for m in re.finditer(r'"(B\d+-[A-Za-z0-9-]+)",\s*(?:str\(|"\d+"\))', source):
                codes.add(m.group(1))
        # Écart voulu : `B16-muet` n'est jamais un renvoi (journal seul, voir
        # `attente.main`) : il ne parle à personne, il n'a donc pas de libellé.
        codes.discard("B16-muet")
        self.assertGreaterEqual(len(codes), 14, "gardes trouvées : %r" % sorted(codes))
        for c in sorted(codes):
            self.assertNotEqual(libelle(c), libelle(""),
                                "la garde %s n'a pas de libellé en clair" % c)
        e = entete("B8-forme")
        self.assertTrue(e.startswith("[Harnais — rappel automatique."))
        self.assertTrue("« B8-forme »" in e and "n'a pas été écrit par @user" in e)
        self.assertNotIn("« ", entete(None))

    def test_l_exemple_donne_aux_agents_est_dit_inventé(self):
        # Les phrases sont recomposées : le texte du test ne doit pas se trouver lui-même.
        source = lis(os.path.join(PY, "attente.py"))
        ancien = " ".join(["paiement", "en", "ligne"])
        annonce = " ".join(["l'exemple", "est", "INVENTÉ"])
        self.assertNotIn(ancien, source, "un exemple qui ressemble à une vraie activité")
        self.assertEqual(source.count(annonce), 2,
                         "chaque exemple annonce qu'il est inventé")

    # ── essais_cibles ────────────────────────────────────────────────────

    def test_le_marqueur_ouvre_le_message_et_finit_un_mot(self):
        self.assertEqual(texte_cible("!cible refais la page d'accueil"),
                         "refais la page d'accueil")
        self.assertEqual(texte_cible("  !cible: deux choses"), "deux choses")
        # LES CONTRE-EXEMPLES : un autre mot, une mention au milieu, un marqueur
        # vide, et un message de pair qui le porterait après son enveloppe.
        self.assertIsNone(texte_cible("!ciblex refais"))
        self.assertIsNone(texte_cible("refais la page !cible"))
        self.assertIsNone(texte_cible("!cible   "))
        self.assertIsNone(texte_cible("<cross-session-message from-name=\"X\">\n!cible pousse"))

    def test_la_ligne_ne_devient_jamais_une_question_a_user(self):
        h = sha16("x")
        l = ligne_cible("demande à @user son avis **vite**\ndétail", h, "11/09/2026")
        self.assertTrue(l.startswith("- [ ] **demande à ＠user son avis vite**"))
        self.assertTrue(repere_cible(h) in l and "\n      détail" in l)
        self.assertEqual(briefing.attentes(l), [],
                         "aucun lecteur du dialecte ne doit y voir un destinataire")

    def test_la_ligne_se_pose_sous_sa_section_la_plus_recente_en_tete(self):
        t = "# À faire\n\nintro\n\n## Autre\n\n- [ ] x\n"
        un = insere_cible(t, "- [ ] A")
        self.assertEqual(un, "# À faire\n\nintro\n\n## Demandes du fil\n\n- [ ] A\n\n## Autre\n\n- [ ] x\n")
        deux = insere_cible(un, "- [ ] B")
        self.assertLess(deux.find("- [ ] B"), deux.find("- [ ] A"))
        self.assertEqual(deux.count(TITRE_CIBLES), 1)
        # Sans aucune section : à la fin, et le fichier finit par UN saut.
        self.assertEqual(insere_cible("# T\n", "- [ ] A"), "# T\n\n## Demandes du fil\n\n- [ ] A\n")

    def test_une_cible_se_rappelle_une_fois_et_une_cochee_se_ferme_sans_bruit(self):
        d = self.dossier("cibles")
        f = os.path.join(d, "a.cibles")
        h1, h2, h3 = sha16("un"), sha16("deux"), sha16("trois")
        ecris(f, "%s\t2026-09-11\touverte\tun\n%s\t2026-09-11\touverte\tdeux\n"
                 "%s\t2026-09-11\touverte\ttrois\n" % (h1, h2, h3))
        todo = "- [ ] **un** · %s\n- [x] **deux** · %s\n" % (repere_cible(h1), repere_cible(h2))
        r = cibles_a_rappeler(f, todo)
        self.assertEqual(len(r), 2, "l'ouverte et la disparue, pas la cochée : %r" % (r,))
        self.assertTrue(any(e == "ouverte" and c == "un" for _, e, c in r))
        self.assertTrue(any(e == "disparue" and c == "trois" for _, e, c in r))
        # UNE SEULE FOIS : le même todo, rejoué, ne rappelle plus rien.
        self.assertEqual(cibles_a_rappeler(f, todo), [])

    # ── essais ───────────────────────────────────────────────────────────

    def test_une_note_sans_blocage_part_dans_l_enveloppe_que_le_terminal_lit(self):
        """LE TÉMOIN DE LA SONDE. On fige ici la forme qu'une sonde a validée :
        sans la clé, le terminal n'affiche rien du tout."""
        self.assertEqual(enveloppe_note("bonjour"), '{"systemMessage":"bonjour"}')
        v = json.loads(enveloppe_note('a"b'))
        self.assertEqual(v["systemMessage"], 'a"b')
        # Témoin négatif : le texte nu, celui qu'on écrivait avant, ne porte
        # aucune clé — mesuré invisible à code de sortie 0.
        with self.assertRaises(ValueError):
            json.loads("bonjour")

    def test_seules_cinq_gardes_renvoient_l_agent_au_travail(self):
        # Écart voulu (5) : Python ajoute B15 (synchronisation) et B16 (faits d'un
        # expert) aux cinq gardes du Rust ; elles aussi renvoient l'agent au travail.
        for q in ["B1-code-sans-todo", "B5-carnet", "B6-faits", "B13-poser", "B14-notion",
                  "B15-synchro", "B16-faits", "B16-local"]:
            self.assertTrue(active(q), "%s doit rester armée" % q)
            self.assertNotEqual(libelle(q), libelle(""), "%s a sa phrase en clair" % q)
        for q in ["B2-reponse", "B3-tranche", "B4-demande", "B4-cible", "B7-constat-sans-rejeu",
                  "B8-forme", "B9-tombe", "B10-rechutes", "B11-acharnement", "B12-contredit"]:
            self.assertFalse(active(q), "%s ne doit plus renvoyer l'agent" % q)
        # « Seules » : la liste complète, ni plus ni moins.
        self.assertEqual(set(GARDES_ACTIVES),
                         {"B1-code-sans-todo", "B5-carnet", "B6-faits", "B13-poser",
                          "B14-notion", "B15-synchro", "B16-faits", "B16-local"})

    def test_le_dialecte_rend_les_memes_taches_que_le_parseur_python(self):
        t = ("## Chantiers\n"
             "- [ ] !haut @user **Une question ? 1 / 2**\n"
             "- [x] @user tranché\n"
             "- [>] @dehors en cours\n"
             "- [ ] sans destinataire\n"
             "- [ ] deploy vers root@serveur\n")
        c = chantiers(t)
        self.assertEqual(len(c), 5)
        self.assertEqual(c[0].prio, "haut")
        self.assertEqual(c[0].qui, "user")
        self.assertEqual(c[0].titre, "Une question ? 1 / 2", "gras et marqueurs retirés")
        self.assertEqual(c[1].etat, "fait")
        self.assertEqual(c[2].etat, "encours")
        self.assertIsNone(c[3].qui)
        # `root@serveur` : le `@` n'ouvre pas un mot, donc pas un destinataire.
        self.assertIsNone(c[4].qui)
        self.assertIn("root@serveur", c[4].titre, "et le mot ne disparaît pas")

    def test_on_ne_rend_MUET_que_ce_dont_on_est_sur_qu_il_est_local(self):
        # Ce qui sort, ou ce dont on ne sait rien : la règle ne mord pas.
        self.assertTrue(sort_de_la_machine("curl -s https://x"))
        self.assertTrue(sort_de_la_machine("gh api /repos/x"))
        self.assertTrue(sort_de_la_machine("./mon-script.sh"), "inconnu ⇒ on ne tranche pas")
        self.assertTrue(sort_de_la_machine("tailscale status"))
        # Ce dont on est SÛR qu'il est local.
        self.assertFalse(sort_de_la_machine("grep -c x fichier"))
        self.assertFalse(sort_de_la_machine("  (ls -l | wc -l)"))
        self.assertFalse(sort_de_la_machine("/usr/bin/stat -f %m x"))
        # LE DÉFAUT RÉPARÉ : une première version de cette règle rendait MUETS
        # des constats justes, dont un `curl` entre guillemets simples.
        self.assertTrue(sort_de_la_machine("bash -c 'curl -s https://x'"))

    def test_les_specs_de_constat_distinguent_l_absence_du_defaut(self):
        t = ("- [ ] ?constat **X manque**\n      ↻ service :: curl -s https://x :: ^200$\n\n"
             "- [ ] ?constat **Y manque**\n      pas de rejeu\n\n"
             "- [ ] une tâche ordinaire\n")
        s = specs_constat(t)
        self.assertEqual(len(s), 3)
        a = s[0]
        self.assertEqual(a.source, "service")
        self.assertEqual(a.motif, "^200$")
        self.assertFalse(a.sans)
        self.assertTrue(s[1].sans, "marqué mais sans moyen de rouvrir")
        self.assertIsNone(s[2], "sans `?constat` : rien à rejouer")

    def test_le_titre_se_separe_de_son_explication(self):
        t, c = titre_et_corps("**Une question ? oui / non**\noui → ceci\nnon → cela")
        self.assertEqual(t, "Une question ? oui / non")
        self.assertTrue(c.startswith("oui → ceci"))
        # Sans gras : on retombe sur la première phrase, jamais sur huit lignes.
        t, _ = titre_et_corps("Ceci est une phrase assez longue. Et voici la suite.")
        self.assertEqual(t, "Ceci est une phrase assez longue")

    def test_la_mecanique_ne_part_jamais_vers_le_telephone(self):
        # ATTENTION : en Rust, une continuation `\` mange l'indentation de la ligne
        # suivante — et l'indentation EST ce qui fait une ligne de continuation du
        # dialecte. Le texte Rust du test (« …oui → ceci\n\ ↻ service… ») donne donc
        # une ligne `↻` SANS indentation, c'est-à-dire le cas même que le commentaire
        # d'origine dit avoir corrigé. On éprouve ici les DEUX : la ligne `↻`
        # indentée (l'intention) puis telle que le littéral Rust la produit.
        indente = ("- [ ] !haut @user ?constat **Une question ?**\n      oui → ceci\n"
                   "      ↻ service :: curl -s https://x :: ^200$\n      non → cela\n")
        litteral_rust = ("- [ ] !haut @user ?constat **Une question ?**\n      oui → ceci\n"
                         "↻ service :: curl -s https://x :: ^200$\n      non → cela\n")
        for t in (indente, litteral_rust):
            b = blocs_bruts(t)[0]
            self.assertNotIn("↻", b, "la ligne de rejeu porte une commande shell")
            self.assertTrue("!haut" not in b and "@user" not in b and "?constat" not in b)
            self.assertTrue("oui → ceci" in b and "non → cela" in b, "rendu : %r" % (b,))
            self.assertEqual(len(attente.lignes(b)), 3, "trois lignes, pas un pavé : %r" % (b,))

    def test_le_libelle_de_carnet_est_lisible_par_un_pair(self):
        b = "- [x] ~~!haut @user **Réparer l'inscription**~~\n      ↗ Projet PO : c'est réparé."
        self.assertEqual(libelle_carnet(b), "Réparer l'inscription")
        # Un libellé barré qui se ferme à la ligne suivante se recolle.
        b = "- [x] ~~Un titre qui court\n      sur deux lignes~~\n      ↗ Projet PO : voilà."
        self.assertEqual(libelle_carnet(b), "Un titre qui court sur deux lignes")

    def test_fnmatch_traverse_les_barres_comme_en_python(self):
        self.assertTrue(fnmatch("src/api/x.ts", "src/*"))
        self.assertTrue(fnmatch("src/api/x.ts", "*.ts"))
        self.assertTrue(fnmatch("a.py", "?.py"))
        self.assertFalse(fnmatch("src/api/x.ts", "lib/*"))
        self.assertFalse(fnmatch("x.rs", "*.ts"))

    def test_un_gabarit_de_consigne_ne_se_joue_pas(self):
        d = self.dossier("consigne-gabarit")
        ecris(os.path.join(d, "base.md"),
              "# Base\n\n## Consigne\n\nTenir la cible du projet.\n\n"
              "    ↻ service :: <commande qui rend le nombre> :: <motif si la cible est tenue>\n")
        phrase, specs = consigne(d)
        self.assertIsNotNone(phrase)
        # LE CŒUR DU CAS : la ligne d'exemple a la forme exacte d'une
        # vérification. Retenue, elle échoue à chaque tour et se lit comme un
        # écart qui ne bouge pas — un acharnement sur une mesure inexistante.
        self.assertEqual(specs, [], "un gabarit a été retenu comme instrument")

        # TÉMOIN CONTRAIRE : une VRAIE ligne, elle, doit être retenue —
        # sinon on aurait éteint le dispositif au lieu de le corriger.
        ecris(os.path.join(d, "base.md"),
              "# Base\n\n## Consigne\n\nTenir la cible du projet.\n\n"
              "    ↻ service :: curl -s https://exemple/etat :: ^ok$\n")
        _, specs = consigne(d)
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].cmd, "curl -s https://exemple/etat")

    def test_le_garde_nomme_le_fichier_qui_existe_dans_les_trois_formes(self):
        """LE GARDE NOMME LE FICHIER QUI EXISTE, dans les trois formes de mémoire.
        Le témoin porte les DEUX sens : le chemin juste est rendu pour chaque
        forme, ET aucune forme ne rend le chemin d'une autre."""
        r = "/d/projet"
        cas = [
            ("brain", r + "/brain/mind/todo.md", "brain/mind/todo.md"),
            ("en-place", r + "/.mind/todo.md", ".mind/todo.md"),
            ("déportée", r + "/memoire/.mind/todo.md", "memoire/.mind/todo.md"),
        ]
        for forme, todo, attendu in cas:
            rendu = ou_ecrire(r, todo)
            self.assertEqual(rendu, attendu, "forme %s : chemin mal nommé" % forme)
            # Le témoin négatif : ce que cette forme ne doit JAMAIS dire.
            for autre, _, chemin_autre in cas:
                if autre != forme:
                    self.assertNotEqual(rendu, chemin_autre,
                                        "forme %s : nomme le chemin de la forme %s" % (forme, autre))

        # Mémoire hors du dépôt : aucun chemin relatif ne serait ouvrable, on
        # rend donc l'absolu plutôt qu'un chemin joli et faux.
        dehors = "/ailleurs/memoire/.mind/todo.md"
        self.assertEqual(ou_ecrire(r, dehors), "/ailleurs/memoire/.mind/todo.md")


class Windows(Isole):
    """Ce que la CI Windows de Claude a mesuré le 16/10/2026, simulé ici."""

    def test_une_verification_qui_finit_ses_lignes_en_crlf_tient(self):
        spec = attente.Spec("machine", "echo a.b", r"^a\.b$", False)
        with mock.patch.object(attente, "bash_limite", return_value=(0, "a.b\r\n")):
            self.assertEqual(attente.rejouer(spec, 10)[0], attente.TIENT)
        # TÉMOIN : un autre contenu tombe, CRLF ou pas.
        with mock.patch.object(attente, "bash_limite", return_value=(0, "autre\r\n")):
            self.assertEqual(attente.rejouer(spec, 10)[0], attente.TOMBE)

    def test_le_bash_de_git_et_pas_celui_de_wsl(self):
        faux = os.path.join(self.dossier("bash"), "bash.exe")
        ecris(faux, "")
        with mock.patch.object(attente.os, "name", "nt"), mock.patch.dict(os.environ, {"HARNAIS_BASH": faux}):
            self.assertEqual(attente._bash(), faux)
        wsl = os.path.join(self.dossier("Windows"), "System32", "bash.exe")
        ecris(wsl, "")      # il EXISTE : seul son nom l'écarte
        with mock.patch.object(attente.os, "name", "nt"), \
                mock.patch.dict(os.environ, {"HARNAIS_BASH": "", "ProgramFiles": "/n/existe/pas",
                                             "ProgramFiles(x86)": "/n/existe/pas", "LOCALAPPDATA": "/n/existe/pas"}), \
                mock.patch("shutil.which", return_value=wsl):
            self.assertEqual(attente._bash(), "bash", "le lanceur WSL de System32 est écarté")
        # TÉMOIN : hors Windows, `bash` tel quel.
        with mock.patch.object(attente.os, "name", "posix"):
            self.assertEqual(attente._bash(), "bash")


class Equipe(Isole):
    """Claude 0.18 — l'agent se tient dans `agents/<nom>/` (la mémoire, qui ignore
    `code/`) : la fin de tour doit regarder SA copie du code. Lancé comme Copilot
    lance le hook `Stop` : `main.py attente`, renvoi en `decision: block`."""

    def setUp(self):
        Isole.setUp(self)
        import banc_equipe
        self.x = banc_equipe.construis(os.path.realpath(self.dossier("attente-v3")))
        self.po = os.path.join(self.x, "agents", "PO")

    def fin_de_tour(self, depart=None, session="s"):
        import env_windows
        import subprocess
        e = dict(env_windows.essentiel(), **{k: os.environ[k] for k in (
            "HOME", "USERPROFILE", "COPILOT_HOME", "COPILOT_PLUGIN_DATA", "COPILOT_PLUGIN_ROOT")})
        e.update(PATH=os.environ.get("PATH", "/usr/bin:/bin"), LANG="C.UTF-8",
                 COPILOT_PROJECT_DIR=depart or self.po, HARNAIS_RELECTURE_SIMULEE="aucun")
        main = os.path.join(RACINE_DEPOT, "py", "main.py")
        r = subprocess.run([sys.executable, main, "attente"], cwd=depart or self.po,
                           input=json.dumps({"sessionId": session}).encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        sortie = r.stdout.decode("utf-8", "replace").strip()
        if not sortie:
            return None
        v = json.loads(sortie)
        self.assertEqual(v["decision"], "block")
        return v["reason"]

    def test_du_code_ecrit_sans_todo_mord_dans_la_copie_de_l_agent(self):
        with open(os.path.join(self.po, "code", "apps", "neuf.ts"), "w") as h:
            h.write("export const a = 1\n")
        os.utime(os.path.join(self.po, "todo.md"), (1e9, 1e9))
        m = self.fin_de_tour()
        self.assertIsNotNone(m)
        self.assertIn("neuf.ts", m)
        self.assertIn("`todo.md`", m, "nommé depuis le dossier de l'agent")
        # Depuis le fond de sa copie du code, c'est le même agent, le même verdict.
        m2 = self.fin_de_tour(os.path.join(self.po, "code", "apps"), "autre-session")
        self.assertIsNotNone(m2)
        self.assertIn("neuf.ts", m2)
        # TÉMOIN : le todo à jour, le tour finit.
        os.utime(os.path.join(self.po, "todo.md"), None)
        self.assertIsNone(self.fin_de_tour(session="troisieme"))

    def test_la_garde_ecrit_le_registre_que_le_briefing_lit(self):
        """Une question posée UNE fois à la garde est « déjà posée » pour le briefing du
        même agent : les deux lisent et écrivent le MÊME registre. TÉMOIN : avant que la
        garde ait vu la question, le briefing demande de la poser."""
        todo = os.path.join(self.po, "todo.md")
        ecris(todo, "# À faire\n\n- [ ] !haut @user **Je garde la page des prix ? 1 oui / 2 non**\n"
                    "      1 → je garde.\n      2 → je retire.\n      fini quand → c'est tranché.\n")
        os.environ["COPILOT_PROJECT_DIR"] = self.po
        os.environ["ATTENTE_DESTINATAIRES"] = "user"
        self.addCleanup(os.environ.pop, "ATTENTE_DESTINATAIRES", None)
        self.addCleanup(os.environ.pop, "COPILOT_PROJECT_DIR", None)
        avant = briefing.ligne_posees(lis(todo), self.po)
        self.assertIn("pose-la UNE fois", avant)
        self.fin_de_tour()       # première rencontre : la garde inscrit, sans bloquer
        apres = briefing.ligne_posees(lis(todo), self.po)
        self.assertIn("Ne les repose PAS", apres)

    def test_racine_de_et_nom_agent_en_equipe(self):
        racine, r0 = attente.racine_de(self.po)
        self.assertEqual(os.path.realpath(racine), os.path.realpath(os.path.join(self.po, "code")))
        self.assertEqual(r0.nom_agent, "PO")
        # TÉMOIN : hors équipe, la racine reste l'arbre courant.
        d = self.dossier("mono")
        git(d, "init", "-q")
        racine, _ = attente.racine_de(d)
        self.assertEqual(os.path.realpath(racine), os.path.realpath(d))
        # L'agent se nomme d'où qu'il démarre sous son dossier.
        os.environ["COPILOT_PROJECT_DIR"] = os.path.join(self.po, "code", "apps")
        self.assertEqual(attente.nom_agent(racine), "PO")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/adopte.rs` (12 tests).

Écarts voulus avec le Rust : `outputs/` devient `assets/` (`agent.BANC`), et le fait
commun `workflow.md` (la seule addition du port) est posé et compté.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import adopte
import agent
import briefing
import copilot
import memoire
import socle

RACINE_PAQUET = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _env():
    e = dict(os.environ)
    e.update({"GIT_CONFIG_NOSYSTEM": "1",
              "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return e


def ecris(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def lis(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def ecrit_decision(c, d, f):
    """`copilot::decision` d'une écriture de `f` (relatif à `d`) pour l'agent lancé dans `c`."""
    return copilot.decision({"tool_name": "Write", "tool_input": {"file_path": os.path.join(d, f)}}, c)


class Essais(unittest.TestCase):

    def setUp(self):
        # `memoire.git` garde ses réponses par (dossier, arguments) pour la vie du processus.
        memoire._VUS.clear()
        p = mock.patch.dict(os.environ, {"COPILOT_PLUGIN_ROOT": RACINE_PAQUET})
        p.start()
        self.addCleanup(p.stop)
        # Aucune variable de l'agent qui lance les tests ne doit décider du dossier de lancement.
        q = mock.patch.dict(os.environ)
        q.start()
        self.addCleanup(q.stop)
        os.environ.pop("COPILOT_PROJECT_DIR", None)

    def bac(self, nom):
        d = tempfile.mkdtemp(prefix="adopte-%s-" % nom)
        self.addCleanup(shutil.rmtree, d, True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, env=_env(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return d

    def temp(self, prefixe):
        d = tempfile.mkdtemp(prefix=prefixe)
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def main(self, args):
        """`adopte.main` avec ses deux flux captés ; rend le code de sortie."""
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return adopte.main(args)

    def test_adoption_compacte_additive_sans_dossier_agents(self):
        d = self.bac("compact")
        args = [d, "--equipe", "OPS,PO,QA", "--compact"]
        self.assertEqual(self.main(args), 0)
        self.assertFalse(os.path.exists(os.path.join(d, "brain")))
        args = args + ["--go"]
        self.assertEqual(self.main(args), 0)
        self.assertFalse(os.path.exists(os.path.join(d, "agents")))
        for n in ("OPS", "PO", "QA"):
            esprit = os.path.join(d, "brain/mind", n)
            self.assertTrue(os.path.isfile(os.path.join(esprit, "state.md")))
            self.assertTrue(os.path.isfile(os.path.join(esprit, "todo.md")))
            self.assertTrue(os.path.isfile(agent.profil(d, n)))
            self.assertTrue(os.path.isfile(agent.perimetre_compact(d, n)))
        qa = os.path.join(d, "brain/mind/QA")
        self.assertNotIn(".", copilot.lis_deny(qa))
        # Les cinq faits du Rust, plus `workflow.md` (l'addition du port) : 8 entrées
        # avec la mémoire et le dossier de livrables de QA.
        allow = copilot.lis_allow(qa)
        self.assertEqual(len(allow), 8)
        self.assertIn("brain/fact/workflow.md", allow)
        # OPS et PO : une liste de refus seule. Un périmètre les sépare de leurs pairs,
        # il ne borne pas ce qu'ils savent faire.
        for n in ("OPS", "PO"):
            c = os.path.join(d, "brain/mind", n)
            self.assertIsNone(copilot.lis_allow(c), "%s n'a pas de liste autorisée" % n)

            def ecrit(f):
                return ecrit_decision(c, d, f)
            self.assertIsNone(ecrit("%s/%s/a.md" % (agent.BANC, n)))
            self.assertIsNone(ecrit(".github/workflows/ci.yml"), "la CI appartient au projet")
            self.assertIsNone(ecrit(".github/mcp.json"), "la config MCP aussi")
            self.assertIsNone(ecrit("src/code.py"))
            pair = "PO" if n == "OPS" else "OPS"
            self.assertIsNotNone(ecrit("brain/mind/%s/todo.md" % pair), "le territoire d'un pair est refusé")
            self.assertIsNotNone(ecrit("%s/%s/a.md" % (agent.BANC, pair)))
            self.assertIsNotNone(ecrit("brain/fact/base.md"), "les faits n'ont qu'un écrivain")
            self.assertIsNotNone(ecrit(".github/agents/%s.agent.md" % n.lower()),
                                 "le rôle n'est pas modifiable par l'agent")
        ecris(agent.profil(d, "OPS"), "personnalisé")
        self.assertEqual(self.main(args), 0)
        self.assertEqual(lis(agent.profil(d, "OPS")), "personnalisé")

    def test_le_code_externe_est_reference_sans_y_ecrire(self):
        """UN CODE QUI VIT AILLEURS : son adresse entre dans les faits, rien n'entre
        dans son dossier, et un chemin inexistant est refusé."""
        d = self.bac("code-externe")
        code = self.temp("adopte-code-")
        os.makedirs(os.path.join(code, "src"))
        ecris(os.path.join(code, "src/main.py"), "print(1)\n")
        self.assertEqual(self.main([d, "--code", code, "--go"]), 0)
        archi = lis(os.path.join(d, "brain/fact/architecture.md"))
        self.assertIn("## Le code : `%s`" % code, archi)
        e = briefing.etablissements(archi)
        self.assertTrue(any(x[0].startswith("Le code") and x[1] == "dit" for x in e),
                        "ligne d'établissement lisible")
        dans_le_code = []
        for dp, _, fn in os.walk(code):
            dans_le_code.extend(os.path.join(dp, f) for f in fn)
        self.assertEqual(sorted(dans_le_code), [os.path.join(code, "src", "main.py")],
                         "rien n'est écrit dans le code")
        # TÉMOIN : un dossier de code inexistant est refusé, rien n'est posé.
        d2 = self.bac("code-absent")
        self.assertEqual(self.main([d2, "--code", os.path.join(code, "nulle-part"), "--go"]), 1)
        self.assertFalse(os.path.exists(os.path.join(d2, "brain")))

    def test_la_methode_du_projet_nomme_user_d_apres_l_atelier(self):
        """LA MÉTHODE COPIÉE NOMME `@user` QUAND L'ATELIER LE CONNAÎT, et ne laisse
        jamais le gabarit brut sinon."""
        atelier = self.temp("adopte-atelier-")
        projet = os.path.join(atelier, "Mon projet")
        os.makedirs(projet)
        ecris(os.path.join(atelier, "AGENTS.md"),
              adopte._methode_brute().replace("[UTILISATEUR]", "Alice Martin"))
        m = adopte.methode(projet)
        self.assertIn("`@user` désigne Alice Martin, l'humain qui commande l'atelier", m)
        self.assertNotIn("[UTILISATEUR]", m)
        # TÉMOIN : sans atelier qui le nomme, la phrase reste générale.
        os.remove(os.path.join(atelier, "AGENTS.md"))
        m = adopte.methode(projet)
        self.assertIn("`@user` désigne l'humain qui commande l'atelier", m)
        self.assertTrue("[UTILISATEUR]" not in m and "Alice" not in m)

    def test_le_blanc_n_ecrit_rien(self):
        """LE BLANC N'ÉCRIT RIEN — et c'est le contrat, pas un détail. Un passage à
        blanc qui pose un fichier rend le geste irréversible avant d'avoir été
        décidé."""
        d = self.bac("blanc")
        self.assertEqual(self.main([d]), 0)
        self.assertFalse(os.path.exists(os.path.join(d, "brain/fact/base.md")), "le blanc a écrit")
        self.assertFalse(os.path.exists(copilot.settings(d)), "le blanc a écrit les réglages")

    def test_go_pose_le_cerveau_et_branche_le_paquet(self):
        """ET `--go` ÉCRIT VRAIMENT. Le témoin négatif du précédent : sans lui,
        une commande qui n'écrit JAMAIS passerait le premier essai."""
        d = self.bac("go")
        self.assertEqual(self.main([d, "--go"]), 0)
        for f in ("brain/fact/base.md", "brain/fact/workflow.md", "brain/fact/architecture.md",
                  "brain/fact/stack.md", "brain/fact/rules.md", "brain/mind/state.md", "brain/mind/todo.md"):
            self.assertTrue(os.path.exists(os.path.join(d, f)), "%s manque" % f)
        t = lis(copilot.settings(d))
        self.assertIn(copilot.PAQUET, t, "le paquet n'est pas activé")
        self.assertIn('"directory"', t, "la marketplace locale manque")
        j = json.loads(t)
        self.assertEqual(j["extraKnownMarketplaces"]["atelier-copilot"]["source"]["path"], copilot.paquet())
        self.assertFalse(os.path.exists(os.path.join(d, ".claude/settings.json")))

    def test_relancer_ne_change_rien(self):
        """DEUX PASSAGES RENDENT LE MÊME ARBRE. Un outil d'installation qu'on
        n'ose pas relancer n'est pas un outil, c'est un pari."""
        d = self.bac("idem")
        self.main([d, "--go"])
        ecris(os.path.join(d, "brain/fact/base.md"), "MON TEXTE À MOI\n")
        self.main([d, "--go"])
        self.assertEqual(lis(os.path.join(d, "brain/fact/base.md")), "MON TEXTE À MOI\n",
                         "le second passage a écrasé un fichier du projet")

    def test_complete_une_memoire_partielle_sans_ecraser(self):
        d = self.bac("partiel")
        os.makedirs(os.path.join(d, "brain/fact"))
        os.makedirs(os.path.join(d, "brain/mind"))
        for f in ("brain/fact/base.md", "brain/mind/state.md", "brain/mind/todo.md"):
            ecris(os.path.join(d, f), "personnel\n")
        self.assertEqual(self.main([d]), 0)
        self.assertFalse(os.path.exists(os.path.join(d, "brain/fact/stack.md")))
        self.assertEqual(self.main([d, "--go"]), 0)
        for f in socle.FAITS_MONO:
            self.assertTrue(os.path.isfile(os.path.join(d, "brain/fact", f)))
        self.assertTrue(os.path.isfile(os.path.join(d, "brain/fact/workflow.md")))
        self.assertEqual(lis(os.path.join(d, "brain/mind/state.md")), "personnel\n")
        self.assertEqual(self.main([d, "--go"]), 0)

    def test_ajoute_la_methode_sans_remplacer_les_instructions_du_projet(self):
        d = self.bac("instructions")
        f = os.path.join(d, ".github/copilot-instructions.md")
        os.makedirs(os.path.dirname(f))
        ecris(f, "# Instructions personnelles\r\nGarder ce texte.\r\n")
        self.assertEqual(self.main([d]), 0)
        self.assertNotIn(adopte.MARQUEUR_METHODE, lis(f))
        self.assertEqual(self.main([d, "--go"]), 0)
        texte = lis(f)
        self.assertTrue(texte.startswith("# Instructions personnelles\r\nGarder ce texte.\r\n"))
        self.assertIn("# Atelier agentique", texte)
        self.assertEqual(self.main([d, "--go"]), 0)
        self.assertEqual(lis(f), texte)

    def test_la_methode_d_hier_est_remplacee_et_le_reste_garde(self):
        """UN DÉPÔT ADOPTÉ HIER REÇOIT LA MÉTHODE D'AUJOURD'HUI (2.2.2) — seul le
        bloc entre les marques change."""
        d = self.bac("rafraichit")
        f = os.path.join(d, ".github/copilot-instructions.md")
        os.makedirs(os.path.dirname(f))
        vieux = ("# À moi\n\n%s\nANCIENNE MÉTHODE\n%s\n\n# Après, à moi aussi\n"
                 % (adopte.MARQUEUR_METHODE, adopte.FIN_METHODE))
        ecris(f, vieux)
        self.assertEqual(self.main([d]), 0)
        self.assertEqual(lis(f), vieux, "à blanc, rien ne change")
        self.assertEqual(self.main([d, "--go"]), 0)
        texte = lis(f)
        self.assertNotIn("ANCIENNE MÉTHODE", texte)
        self.assertIn("## Les gardes, et quoi faire d'un refus", texte)
        self.assertTrue(texte.startswith("# À moi\n\n") and texte.endswith("\n\n# Après, à moi aussi\n"))
        self.assertEqual(texte.count(adopte.MARQUEUR_METHODE), 1)
        self.assertEqual(self.main([d, "--go"]), 0)
        self.assertEqual(lis(f), texte, "un second passage ne change rien")
        # TÉMOIN : un bloc sans sa fin ne se devine pas — rien n'est touché.
        casse = "%s\nANCIENNE MÉTHODE\n" % adopte.MARQUEUR_METHODE
        ecris(f, casse)
        self.assertEqual(self.main([d, "--go"]), 0)
        self.assertEqual(lis(f), casse)

    def test_la_methode_tient_dans_la_cible(self):
        """POSTE + MÉTHODE + PROFIL : 200 À 300 LIGNES AU TOTAL (Maxime, 23/10). La
        méthode seule reste vers 120 lignes, sans récit daté ni historique."""
        m = adopte._methode_brute()
        n = len(m.splitlines())
        self.assertLessEqual(n, 140, "la méthode a regrossi : %d lignes" % n)
        for date in ("(0.1", "(2.", "Mesuré le"):
            self.assertNotIn(date, m, "ni récit daté, ni historique de versions")
        self.assertNotIn("agents/<nom>/AGENTS.md", m, "l'architecture « un dossier par agent » sort")
        for titre in ("## La mémoire", "## Le format est un contrat", "## Les gardes",
                      "## À plusieurs", "## Déléguer", "## Les frontières", "## Les réflexes"):
            self.assertIn(titre, m)
        self.assertIn("gpt-6.1-sol", m)
        self.assertIn("gpt-6-luna", m)

    def test_une_erreur_de_pose_ne_reussit_pas(self):
        d = self.bac("echec")
        ecris(os.path.join(d, "brain"), "obstacle")
        self.assertEqual(self.main([d, "--go"]), 1)
        self.assertFalse(os.path.exists(copilot.settings(d)))

    def test_les_reglages_existants_survivent(self):
        """LES RÉGLAGES SE FUSIONNENT. Un projet qui a déjà ses permissions doit les
        garder — les écraser couperait ses droits sans le dire."""
        d = self.bac("fusion")
        os.makedirs(os.path.join(d, ".github/copilot"))
        ecris(copilot.settings(d), '{"permissions":{"deny":["Bash(rm*)"]}}')
        self.main([d, "--go"])
        t = lis(copilot.settings(d))
        self.assertIn("Bash(rm*)", t, "les permissions du projet ont été perdues")
        self.assertIn(copilot.PAQUET, t, "le paquet n'a pas été ajouté")

    def test_le_chemin_contenant_un_nom_d_agent_reste_le_projet_cible(self):
        d = self.bac("Agent-A")
        self.assertEqual(self.main([d, "--equipe", "A,B", "--go"]), 0)
        self.assertTrue(os.path.isfile(copilot.settings(d)))
        self.assertTrue(os.path.isfile(os.path.join(d, "agents/A/.github/copilot/perimetre.json")))
        self.assertFalse(os.path.exists(copilot.settings(os.path.join(d, "agents/A"))))

    def test_en_equipe_chacun_a_le_sien(self):
        """UNE ÉQUIPE NAÎT « UN DOSSIER PAR AGENT » (Claude 0.19, 16/10/2026) : chacun son
        état, son rôle, ses droits et SA copie du code ; la racine est le dépôt de la
        mémoire. TÉMOIN : l'ancienne forme (`brain/mind/<nom>/`) n'est plus posée.
        COPILOT : la déclaration du paquet est UNE, à la racine Git (le dossier d'un
        agent n'en porte pas : Copilot l'ignorerait) ; le périmètre est un
        `perimetre.json` par agent, le menu d'agent un profil par agent."""
        d = self.bac("equipe")
        self.assertEqual(self.main([d, "--equipe", "PO,QA", "--go"]), 0)
        for a in ("PO", "QA"):
            for f in ("state.md", "todo.md", "AGENTS.md", ".github/copilot/perimetre.json"):
                self.assertTrue(os.path.isfile(os.path.join(d, "agents", a, f)), "%s sans %s" % (a, f))
            self.assertTrue(os.path.exists(os.path.join(d, "agents", a, "code", ".git")), "%s sans code" % a)
            self.assertFalse(os.path.exists(copilot.settings(os.path.join(d, "agents", a))))
            self.assertTrue(os.path.isfile(agent.profil(d, a)), "%s absent du menu d'agent" % a)
        # Chacun est fermé au dossier de l'autre : la ligne `deny` est posée des deux côtés.
        self.assertEqual(copilot.lis_deny(os.path.join(d, "agents", "PO")), ["agents/QA"])
        self.assertIn("agents/PO", copilot.lis_deny(os.path.join(d, "agents", "QA")))
        for f in ("AGENTS.md", ".gitignore", "fact/base.md", "fact/roles.md", "docs/decisions.md",
                  "shared/LISEZMOI.md", "assets/LISEZMOI.md", ".github/copilot/settings.json"):
            self.assertTrue(os.path.isfile(os.path.join(d, f)), "%s manque" % f)
        self.assertIn(copilot.PAQUET, lis(copilot.settings(d)), "réglage unique à la racine")
        self.assertFalse(os.path.exists(os.path.join(d, "brain")), "l'ancienne forme est revenue")
        # La copie de QA est une copie git du dépôt de PO, sur sa propre branche.
        o = subprocess.run(["git", "worktree", "list"], cwd=os.path.join(d, "agents/PO/code"),
                           stdout=subprocess.PIPE).stdout.decode()
        # `realpath` : le dossier temporaire de Windows peut s'écrire en forme courte
        # (`RUNNER~1`), git l'écrit en forme longue (CI Windows, 20/10/2026).
        self.assertIn(os.path.join(os.path.realpath(d), "agents", "QA", "code").replace("\\", "/").lower(),
                      o.replace("\\", "/").lower(), "git écrit `C:/…` sous Windows")
        # Le résolveur y voit une équipe, depuis le fond de la copie du code.
        r = memoire.resous(os.path.join(d, "agents", "QA", "code"))
        self.assertEqual((r.forme, r.projet), (memoire.Forme.Equipe, os.path.realpath(d)))
        # QA garde son périmètre documentaire : la liste autorisée pointe l'équipe, jamais `brain/`.
        allow = copilot.lis_allow(os.path.join(d, "agents", "QA"))
        self.assertIn("fact/base.md", allow)
        self.assertIn("agents/QA", allow)
        self.assertFalse(any(a.startswith("brain/") or a.startswith(".fact") for a in allow), allow)
        self.assertIsNone(copilot.lis_allow(os.path.join(d, "agents", "PO")), "PO : une liste de refus seule")

    def test_la_garde_d_ecriture_ferme_le_dossier_des_pairs_en_equipe(self):
        """Le périmètre posé par la naissance MORD : PO écrit chez lui, pas chez QA ;
        QA n'écrit ni dans le code de son dossier ni dans les faits qu'il n'a pas reçus.
        Témoin dans les deux sens."""
        d = os.path.realpath(self.bac("garde-eq"))
        self.main([d, "--equipe", "PO,QA", "--go"])
        po, qa = os.path.join(d, "agents", "PO"), os.path.join(d, "agents", "QA")
        self.assertIsNone(ecrit_decision(po, d, "agents/PO/todo.md"))
        self.assertIsNone(ecrit_decision(po, d, "agents/PO/code/src/a.py"))
        self.assertIsNotNone(ecrit_decision(po, d, "agents/QA/todo.md"))
        self.assertIsNotNone(ecrit_decision(qa, d, "agents/PO/todo.md"))
        self.assertIsNone(ecrit_decision(qa, d, "agents/QA/todo.md"))
        self.assertIsNone(ecrit_decision(qa, d, "docs/audit/2026/PLAN.md"))
        self.assertIsNone(ecrit_decision(qa, d, "fact/base.md"))
        self.assertIsNotNone(ecrit_decision(qa, d, "agents/QA/code/src/a.py"), "QA ne répare pas le code")
        self.assertIsNotNone(ecrit_decision(qa, d, "src/a.py"), "hors de son périmètre autorisé")

    def test_une_equipe_ne_nait_pas_sur_un_code(self):
        """Un dossier qui porte déjà quelque chose est refusé, rien n'est écrit.
        TÉMOIN : le même geste dans un dossier vide pose l'équipe (test précédent)."""
        d = self.bac("surcode")
        with open(os.path.join(d, "app.ts"), "w", encoding="utf-8") as h:
            h.write("x\n")
        self.assertEqual(self.main([d, "--equipe", "A,B", "--go"]), 1)
        self.assertEqual(sorted(os.listdir(d)), [".git", "app.ts"])

    def test_a_blanc_l_equipe_n_ecrit_rien(self):
        d = self.bac("eqblanc")
        self.assertEqual(self.main([d, "--equipe", "A,B"]), 0)
        self.assertEqual(os.listdir(d), [".git"])

    def test_une_equipe_neuve_clone_le_code_donne_et_type_ses_roles(self):
        """`--code` est ici la SOURCE clonée chez le premier agent ; `--modeles` type les
        rôles (OPS ferme la Production d'office). TÉMOIN : un modèle inconnu refuse."""
        src = self.bac("source")
        ecris(os.path.join(src, "app.py"), "print(1)\n")
        subprocess.run(["git", "add", "-A"], cwd=src, env=_env(), check=True)
        subprocess.run(["git", "commit", "-qm", "c"], cwd=src, env=_env(), check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        d = os.path.join(self.temp("neuve-"), "equipe")
        self.assertEqual(self.main([d, "--equipe", "OPS,QA", "--modeles", "ops,qa", "--code", src, "--go"]), 0)
        self.assertTrue(os.path.isfile(os.path.join(d, "agents/OPS/code/app.py")), "le code est cloné")
        self.assertTrue(os.path.isfile(os.path.join(d, "agents/QA/code/app.py")), "et partagé en copie git")
        self.assertIn("production-agent: OPS", lis(os.path.join(d, "fact/rules.md")))
        self.assertIn("guichet des questions", lis(os.path.join(d, "agents/QA/AGENTS.md")))
        self.assertIn("seul agent qui y écrit", lis(os.path.join(d, "agents/OPS/AGENTS.md")))
        self.assertIn("guichet unique des questions", lis(os.path.join(d, "AGENTS.md")))
        for t in (lis(os.path.join(d, "agents/QA/AGENTS.md")), lis(os.path.join(d, "AGENTS.md"))):
            self.assertNotRegex(t, r"\{[A-Z]+\}", "aucun champ laissé à remplir par la machine")
        # TÉMOIN : sans modèle, pas de Production fermée.
        e = os.path.join(self.temp("neuve2-"), "equipe")
        self.assertEqual(self.main([e, "--equipe", "A,B", "--go"]), 0)
        self.assertNotIn("production", lis(os.path.join(e, "fact/rules.md")).lower().split("# règles")[0])
        # Un modèle inconnu, ou mal aligné : refus, rien d'écrit.
        f = os.path.join(self.temp("neuve3-"), "equipe")
        self.assertEqual(self.main([f, "--equipe", "A,B", "--modeles", "chef,po"]), 2)
        self.assertEqual(self.main([f, "--equipe", "A,B", "--modeles", "ops"]), 2)
        self.assertFalse(os.path.exists(f))

    def test_deux_noms_au_meme_profil_refusent_la_naissance(self):
        d = self.bac("collision")
        self.assertEqual(self.main([d, "--equipe", "Q A,Q-A", "--go"]), 1)
        self.assertEqual(os.listdir(d), [".git"], "rien n'a été écrit")

    def test_en_mono_le_projet_recoit_son_agents_md_et_ses_decisions(self):
        d = self.bac("etage3")
        self.main([d, "--go"])
        self.assertIn("À REMPLIR", lis(os.path.join(d, "AGENTS.md")))
        self.assertTrue(os.path.isfile(os.path.join(d, "docs", "decisions.md")))
        ecris(os.path.join(d, "AGENTS.md"), "LE MIEN\n")
        self.main([d, "--go"])
        self.assertEqual(lis(os.path.join(d, "AGENTS.md")), "LE MIEN\n", "un AGENTS.md existant a été écrasé")

    def test_les_quatre_faits_sont_poses_a_remplir(self):
        """Claude 0.17.0 — la vue d'équipe disait « adopte le pose » pour stack, architecture
        et rules ; le compte qu'elle lit doit être plein après adoption (déjà vrai ici :
        le test garde la promesse)."""
        d = self.bac("quatre")
        self.main([d, "--go"])
        for f in ("stack.md", "architecture.md", "rules.md"):
            p = os.path.join(d, "brain/fact", f)
            self.assertTrue(os.path.isfile(p), "%s manque" % f)
            self.assertTrue(briefing.a_renseigner(p), "%s n'est pas lu « À RENSEIGNER »" % f)
        self.assertIn("sante: vert\n", adopte.state_md("2026-01-01"))

    def test_une_equipe_demenagee_ne_s_adopte_pas(self):
        """Claude 0.18.0 : sur la forme « un dossier par agent », adopte ne pose rien — un
        `brain/` posé là recréerait la dispersion."""
        sys.path.insert(0, os.path.dirname(__file__))
        import banc_equipe
        x = banc_equipe.construis(os.path.realpath(self.temp("adopte-v3-")))
        self.assertEqual(self.main([x, "--go"]), 0)
        self.assertFalse(os.path.exists(os.path.join(x, "brain")))
        self.assertEqual(self.main([x, "--equipe", "Z", "--go"]), 0, "un agent de plus passe par equipe_v3")
        self.assertTrue(os.path.isfile(os.path.join(x, "agents", "Z", "state.md")))


if __name__ == "__main__":
    unittest.main()

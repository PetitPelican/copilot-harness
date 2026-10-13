# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/vue.rs` (7 tests), puis quelques essais de plus
sur ce que la lecture Copilot a changé (l'inscription, les avertissements)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import agent
import briefing
import copilot
import memoire
import socle
import vue

RACINE_PAQUET = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
MIND_ATTENDU = vue.MIND_ATTENDU
FAITS_TOUS = socle.FAITS_MONO + [socle.FAITS_EQUIPE]
DECLARE = '{"enabledPlugins":{"harnais@atelier-copilot":true},"permissions":{"deny":["Bash(x*)"]}}'


def git(d, *a):
    r = subprocess.run(["git", "-c", "user.email=e@e", "-c", "user.name=e", "-c", "commit.gpgsign=false"]
                       + list(a), cwd=d, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r


def ecris(d, f, t):
    p = os.path.join(d, f)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as h:
        h.write(t)


def branche(d, t):
    """Pose les réglages Copilot du dépôt qui porte `d` — paquet et `deny`
    donnés en JSON —, et le fichier de périmètre de `d` qui en découle."""
    try:
        depot = copilot.racine_git(d)
    except copilot.Refus:
        depot = d
    reglages = copilot.settings(depot)
    v = json.loads(t)
    perm = v.get("permissions")
    deny = perm.get("deny") if isinstance(perm, dict) else None
    n = len(deny) if isinstance(deny, list) else 0
    perimetre = os.path.join(d, ".github", "copilot", "perimetre.json")
    if os.path.exists(perimetre):
        os.remove(perimetre)
    if n > 0:
        os.makedirs(os.path.dirname(perimetre), exist_ok=True)
        with open(perimetre, "w", encoding="utf-8") as h:
            h.write(json.dumps({"deny": [os.path.join(d, "agents", "voisin")]}))
    os.makedirs(os.path.dirname(reglages), exist_ok=True)
    with open(reglages, "w", encoding="utf-8") as h:
        h.write(t)


def courante():
    """La version de ce programme, sans son suffixe de construction locale."""
    a, b, c = vue.numeros(vue.version_annoncee())
    return "%d.%d.%d" % (a, b, c)


def trace(d, v):
    """`""` : une trace d'avant la 0.10.0, sans version."""
    ver = ', "version": "%s"' % v if v else ""
    f = briefing.etat_du_briefing(d)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w", encoding="utf-8") as h:
        h.write('{"derniere": %s, "evenement": "SessionStart"%s}' % (vue.maintenant_s(), ver))


def inscrit(ds, v):
    return vue.Chemins([(d, v) for d in ds])


def explique(d, h, ins):
    """Ce qu'un « ok » manqué a vu : sans lui, la CI Windows ne dit que le verdict."""
    return "%r · lancements %r · inscrits %r · copies %r" % (
        vue.verdict(h), [(l.nom, l.declare, l.inscrit, l.inscrite, l.trace) for l in h.lancements],
        [(c, vue._cle(vue.canon(c))) for c, _ in getattr(ins, "entrees", [])],
        [(c, vue._cle(vue.canon(c))) for c in vue.copies(d)])


def juge(d, ins):
    return vue.verdict(vue.harnais(d, ins))


def commandes_mortes(texte):
    """Ce qui fait qu'un conseil ne cite rien de mort. Une commande se cite
    entre accents graves : « le harnais refuse » est de la prose."""
    with open(os.path.join(RACINE_PAQUET, "py", "main.py"), encoding="utf-8") as f:
        main = f.read()
    skills = os.path.join(RACINE_PAQUET, "skills")
    mortes = []
    for c in re.finditer(r"`harnais ([a-z][a-z-]*)", texte):
        if '"%s":' % c.group(1) not in main:
            mortes.append("harnais %s" % c.group(1))
    for c in re.finditer(r"(?:^|[\s`(])/([a-z][a-z0-9-]*)", texte):
        if not os.path.isfile(os.path.join(skills, c.group(1), "SKILL.md")):
            mortes.append("/%s" % c.group(1))
    for c in re.finditer(r"`copilot plugin ([a-z]+)", texte):
        if c.group(1) not in ("install", "update", "uninstall", "list", "marketplace"):
            mortes.append("copilot plugin %s" % c.group(1))
    return mortes


class Essais(unittest.TestCase):

    def setUp(self):
        # `memoire.git` garde ses réponses par (dossier, arguments) pour la vie du processus.
        memoire._VUS.clear()
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="vue-env-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.maison = os.path.join(self.tmp, "maison")
        os.makedirs(os.path.join(self.maison, ".copilot"))
        p = mock.patch.dict(os.environ, {
            "HOME": self.maison, "USERPROFILE": self.maison,
            "COPILOT_HOME": os.path.join(self.maison, ".copilot"),
            "COPILOT_PLUGIN_ROOT": RACINE_PAQUET,
            "COPILOT_PLUGIN_DATA": os.path.join(self.tmp, "donnees"),
        })
        p.start()
        self.addCleanup(p.stop)
        for k in ("PLUGIN_ROOT", "PLUGIN_DATA", "COPILOT_PROJECT_DIR"):
            os.environ.pop(k, None)

    def dossier(self, nom, avec_git):
        d = os.path.join(self.tmp, "vue-%s" % nom)
        shutil.rmtree(d, True)
        os.makedirs(d)
        if avec_git:
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        return os.path.realpath(d)

    def brain_mono(self, nom):
        """Un projet `brain/` à un agent, complet, déclaré, avec ses `deny`."""
        d = self.dossier(nom, True)
        for f in socle.FAITS_MONO:
            ecris(d, "brain/fact/%s" % f, "x\n")
        for f in MIND_ATTENDU:
            ecris(d, "brain/mind/%s" % f, "x\n")
        branche(d, DECLARE)
        return d

    # ── les 7 essais du Rust ─────────────────────────────────────────────────

    def test_servi_seulement_si_declare_inscrit_et_trace_et_chaque_manque_seul_le_fait_tomber(self):
        """Chaque condition, retirée SEULE, fait tomber le « servi » — sinon un
        verdict qui dit toujours « ok » passerait les mêmes essais."""
        d = self.brain_mono("servi")
        v = courante()
        trace(d, v)
        ins = inscrit([d], v)
        self.assertEqual(juge(d, ins)[0], "ok")
        self.assertEqual(juge(d, vue.Chemins([]))[0], "non-inscrit")
        self.assertEqual(juge(d, vue.Illisibles())[0], "non-mesure", "illisible n'est pas « inscrit »")
        self.assertEqual(juge(d, vue.Toutes(v))[0], "ok", "une inscription globale vaut pour tous")
        os.remove(briefing.etat_du_briefing(d))
        self.assertEqual(juge(d, ins)[0], "jamais-servi")
        trace(d, v)
        branche(d, '{"permissions":{"deny":["Bash(x*)"]}}')
        self.assertEqual(juge(d, ins)[0], "non-branche")
        branche(d, '{"enabledPlugins":{"harnais@atelier-copilot":true}}')
        self.assertEqual(juge(d, ins)[0], "sans-deny")
        branche(d, DECLARE)
        ecris(d, "brain/fact/journal.md", "x\n")
        self.assertEqual(juge(d, ins)[0], "surplus")
        os.remove(os.path.join(d, "brain/fact/journal.md"))
        os.remove(os.path.join(d, "brain/mind/todo.md"))
        v2, c = juge(d, ins)
        self.assertEqual(v2, "incomplet")
        self.assertTrue("brain/mind/todo.md" in c and "harnais adopte --go" in c, c)
        os.remove(os.path.join(d, "brain/mind/state.md"))
        self.assertEqual(juge(d, ins)[0], "sans-agent")

    def test_le_retard_se_juge_contre_la_version_inscrite(self):
        """La référence est ce qui est INSCRIT : c'est ce que l'agent chargera."""
        d = self.brain_mono("retard")
        v = courante()
        trace(d, "0.0.1")
        self.assertEqual(juge(d, inscrit([d], v))[0], "en-retard")
        trace(d, "")
        x, c = juge(d, inscrit([d], v))
        self.assertEqual(x, "en-retard")
        self.assertIn("avant la 0.10.0", c)
        trace(d, v)
        self.assertEqual(juge(d, inscrit([d], v))[0], "ok")
        # Une trace PLUS RÉCENTE que l'inscrite n'est pas un retard.
        trace(d, "999.0.0")
        self.assertEqual(juge(d, inscrit([d], v))[0], "ok")
        trace(d, "0.0.1")
        x, c = juge(d, inscrit([d], "0.0.1"))
        self.assertEqual(x, "inscription-vieille", c)
        self.assertIn("marketplace locale", c)

    def test_toutes_les_formes_de_memoire_sont_vues(self):
        d = self.dossier("neuf", True)
        self.assertEqual(juge(d, vue.Chemins([]))[0], "neuf")
        ecris(d, ".memory/business.md", "x\n")
        x, c = juge(d, vue.Chemins([]))
        self.assertEqual(x, "ancien")
        self.assertIn("business.md", c)

        d = self.dossier("mind-seul", True)
        ecris(d, ".mind/state.md", "x\n")
        self.assertEqual(juge(d, vue.Chemins([]))[0], "ancien")

        d = self.dossier("sans-git", False)
        for f in socle.FAITS_MONO:
            ecris(d, "brain/fact/%s" % f, "x\n")
        self.assertEqual(juge(d, vue.Chemins([]))[0], "sans-git")

        d = self.dossier("v1", True)
        for f in socle.FAITS_MONO:
            ecris(d, ".fact/%s" % f, "x\n")
        for f in MIND_ATTENDU:
            ecris(d, ".mind/%s" % f, "x\n")
        branche(d, DECLARE)
        trace(d, courante())
        ins = inscrit([d], courante())
        self.assertEqual(juge(d, ins)[0], "v1")
        os.makedirs(os.path.join(d, "brain"))
        x, c = juge(d, ins)
        self.assertEqual(x, "ambigu")
        self.assertIn("harnais brain-migre", c)

    def test_a_plusieurs_chaque_agent_est_lu_depuis_son_dossier(self):
        """À plusieurs, l'état de chaque agent vit dans `brain/mind/<nom>/`, et ses
        réglages dans `agents/<nom>/` — ceux de la racine sont inertes."""
        d = self.dossier("equipe", True)
        for f in FAITS_TOUS:
            ecris(d, "brain/fact/%s" % f, "x\n")
        v = courante()
        ags = []
        for a in ("Alpha", "Beta"):
            for f in MIND_ATTENDU:
                ecris(d, "brain/mind/%s/%s" % (a, f), "x\n")
            ag = os.path.join(d, "agents", a)
            ecris(ag, "CLAUDE.md", "x\n")
            branche(ag, DECLARE)
            trace(ag, v)
            ags.append(ag)
        ins = inscrit([ags[0], ags[1]], v)
        h = vue.harnais(d, ins)
        self.assertEqual(vue.verdict(h)[0], "ok", explique(d, h, ins))
        self.assertTrue("faits 5/5" in vue.jauge(h) and "état 4/4" in vue.jauge(h), vue.jauge(h))
        x, c = juge(d, inscrit([ags[0]], v))
        self.assertEqual(x, "non-inscrit")
        self.assertTrue(c.startswith("Beta : "), "l'agent en défaut est nommé : %s" % c)
        os.remove(os.path.join(d, "brain/mind/Beta/todo.md"))
        x, c = juge(d, ins)
        self.assertEqual(x, "incomplet")
        self.assertIn("brain/mind/Beta/todo.md", c)

    def test_equipe_compacte_est_vue_sans_ancien_dossier(self):
        d = self.dossier("compact", True)
        for f in FAITS_TOUS:
            ecris(d, "brain/fact/%s" % f, "x\n")
        v = courante()
        contextes = []
        branche(d, DECLARE)
        for n in ("OPS", "QA"):
            for f in MIND_ATTENDU:
                ecris(d, "brain/mind/%s/%s" % (n, f), "x\n")
            ecris(d, ".github/agents/%s.agent.md" % agent.nom_de_profil(n), "---\nname: essai\n---\nrôle\n")
            ecris(d, ".github/copilot/perimetres/%s.json" % agent.nom_de_profil(n), '{"allow":[],"deny":["."]}')
            contexte = agent.contexte(d, n)
            trace(contexte, v)
            contextes.append(contexte)
        ins = inscrit([contextes[0], contextes[1]], v)
        h = vue.harnais(d, ins)
        self.assertEqual(len(h.lancements), 2)
        self.assertIn("état 4/4", vue.jauge(h))
        self.assertEqual(vue.verdict(h)[0], "ok", explique(d, h, ins))
        self.assertFalse(os.path.exists(os.path.join(d, "agents")))
        os.remove(agent.perimetre_compact(d, "QA"))
        self.assertEqual(juge(d, ins)[0], "sans-deny")

    def test_une_trace_dans_une_copie_de_travail_compte(self):
        """Un agent qui se lance depuis une copie de travail n'a, dans l'arbre
        principal, qu'une trace ancienne — ou aucune."""
        d = self.brain_mono("copie")
        c = d + "-copie"
        shutil.rmtree(c, True)
        self.addCleanup(shutil.rmtree, c, True)
        self.assertEqual(git(d, "commit", "-q", "--allow-empty", "-m", "x").returncode, 0)
        pour_git = c.lstrip("\\?") if c.startswith("\\\\?\\") else c
        ajout = git(d, "worktree", "add", "-q", pour_git)
        self.assertEqual(ajout.returncode, 0, ajout.stderr.decode("utf-8", "replace"))
        c = os.path.realpath(c)
        v = courante()
        ins = inscrit([c], v)
        self.assertEqual(juge(d, ins)[0], "jamais-servi", "témoin : sans la trace de la copie")
        trace(c, v)
        self.assertEqual(juge(d, ins)[0], "ok")

    def test_aucun_conseil_ne_renvoie_a_une_commande_qui_n_existe_pas(self):
        """Le défaut d'origine : deux conseils renvoyaient à des compétences
        supprimées. Tous les verdicts sont produits, et chacun est relu."""
        # témoins : la vérification mord sur les deux morts d'origine
        u, y = "/agentic-" + "upgrade", "/agentic-" + "sync"
        self.assertEqual(commandes_mortes("lancer `%s` puis %s" % (u, y)), [u, y])
        # Composée à l'exécution : écrite en clair, le contrôle de la
        # documentation la prendrait pour une vraie citation.
        self.assertEqual(commandes_mortes("`harnais %s`" % "inexistant"), ["harnais inexistant"])
        self.assertEqual(commandes_mortes("`harnais adopte --go` puis `/agentic-adopte`, dans brain/mind/"), [])
        self.assertEqual(commandes_mortes("le harnais refuse de choisir"), [])
        self.assertEqual(commandes_mortes("`copilot plugin upgrade x`"), ["copilot plugin upgrade"])

        vus = {}

        def note(d, ins):
            v, c = juge(d, ins)
            vus[v] = c
        v = courante()
        d = self.brain_mono("tous")
        ins = inscrit([d], v)
        note(d, vue.Chemins([]))
        note(d, vue.Illisibles())
        note(d, ins)
        trace(d, v)
        note(d, ins)
        trace(d, "0.0.1")
        note(d, ins)
        note(d, inscrit([d], "0.0.1"))
        trace(d, v)
        branche(d, "{}")
        note(d, ins)
        branche(d, '{"enabledPlugins":{"harnais@atelier-copilot":true}}')
        note(d, ins)
        branche(d, DECLARE)
        ecris(d, "brain/fact/journal.md", "x\n")
        note(d, ins)
        os.remove(os.path.join(d, "brain/fact/journal.md"))
        os.remove(os.path.join(d, "brain/mind/todo.md"))
        note(d, ins)
        os.remove(os.path.join(d, "brain/mind/state.md"))
        note(d, ins)
        d = self.dossier("tous-v1", True)
        note(d, ins)
        ecris(d, ".mind/state.md", "x\n")
        note(d, ins)
        ecris(d, ".memory/business.md", "x\n")
        note(d, ins)
        for f in socle.FAITS_MONO:
            ecris(d, ".fact/%s" % f, "x\n")
        shutil.rmtree(os.path.join(d, ".memory"))
        ecris(d, ".mind/todo.md", "x\n")
        branche(d, DECLARE)
        trace(d, v)
        note(d, inscrit([d], v))
        branche(d, "{}")
        note(d, inscrit([d], v))
        os.makedirs(os.path.join(d, "brain"))
        note(d, ins)
        d = self.dossier("tous-sans-git", False)
        note(d, ins)

        # Chaque verdict que le tableau sait afficher a été produit ici : un
        # verdict ajouté sans essai fait échouer celui-ci.
        tous = ["ok", "v1", "en-retard", "neuf", "ancien", "ambigu", "incomplet", "sans-agent",
                "non-branche", "non-inscrit", "non-mesure", "jamais-servi", "sans-git", "surplus",
                "sans-deny", "inscription-vieille"]
        for t in tous:
            self.assertIn(t, vus, "verdict jamais produit par l'essai : %s" % t)
            self.assertNotEqual(vue.symbole(t), "?   ", "%s sans symbole" % t)
        self.assertEqual(len(vus), len(tous), "verdicts produits : %s" % sorted(vus))
        for (v, c) in vus.items():
            self.assertEqual(commandes_mortes(c), [], "%s cite une commande morte : %s" % (v, c))

    # ── ce que la lecture Copilot a changé (hors du bloc d'essais du Rust) ──

    def reglages_globaux(self, texte):
        ecris(os.environ["COPILOT_HOME"], "settings.json", texte)

    def marche(self, chemin):
        return {"atelier-copilot": {"source": {"source": "directory", "path": chemin}}}

    def test_inscription_lue_dans_les_reglages_de_copilot(self):
        """`inscriptions()` : absent → rien d'inscrit ; illisible → non mesuré ;
        paquet activé mais marketplace non résolue → rien ; résolue → pour tous."""
        self.assertEqual(vue.inscriptions().entrees, [])
        self.reglages_globaux("{pas du json")
        self.assertIsInstance(vue.inscriptions(), vue.Illisibles)
        on = {"enabledPlugins": {"harnais@atelier-copilot": True}}
        self.reglages_globaux(json.dumps(dict(on, extraKnownMarketplaces=self.marche("/nexiste/pas"))))
        self.assertEqual(vue.inscriptions().entrees, [])
        self.reglages_globaux(json.dumps(dict(on, extraKnownMarketplaces=self.marche(RACINE_PAQUET))))
        ins = vue.inscriptions()
        self.assertIsInstance(ins, vue.Toutes)
        self.assertIsNone(ins.version)
        off = {"enabledPlugins": {"harnais@atelier-copilot": False},
               "extraKnownMarketplaces": self.marche(RACINE_PAQUET)}
        self.reglages_globaux(json.dumps(off))
        self.assertEqual(vue.inscriptions().entrees, [])
        # Le paquet installé par Copilot suffit à résoudre.
        self.reglages_globaux(json.dumps(on))
        self.assertEqual(vue.inscriptions().entrees, [])
        os.makedirs(os.path.join(os.environ["COPILOT_HOME"], "installed-plugins", "atelier-copilot", "harnais"))
        self.assertIsInstance(vue.inscriptions(), vue.Toutes)

    def test_marketplace_locale_du_projet_vaut_inscription(self):
        d = self.brain_mono("local")
        trace(d, courante())
        self.assertEqual(juge(d, vue.Chemins([])), (
            "non-inscrit", "Paquet déclaré mais marketplace locale non résolue : vérifier le chemin dans "
            ".github/copilot/settings.json."))
        reglages = json.loads(DECLARE)
        reglages["extraKnownMarketplaces"] = self.marche(RACINE_PAQUET)
        branche(d, json.dumps(reglages))
        self.assertEqual(juge(d, vue.Chemins([]))[0], "ok")
        reglages["extraKnownMarketplaces"] = self.marche("/nexiste/pas")
        branche(d, json.dumps(reglages))
        self.assertEqual(juge(d, vue.Chemins([]))[0], "non-inscrit")
        # Les réglages globaux résolus valent aussi pour un projet déclaré.
        self.reglages_globaux(json.dumps({"extraKnownMarketplaces": self.marche(RACINE_PAQUET)}))
        self.assertEqual(juge(d, vue.Chemins([]))[0], "ok")

    def test_la_trace_est_lue_ou_le_briefing_l_ecrit(self):
        """La trace d'entrée n'est plus dans le projet : le projet reste net."""
        d = self.brain_mono("trace")
        ecris(d, ".claude/.briefing.json", '{"derniere": %s, "version": "%s"}' % (vue.maintenant_s(), courante()))
        self.assertEqual(juge(d, inscrit([d], courante()))[0], "jamais-servi")
        trace(d, courante())
        self.assertEqual(juge(d, inscrit([d], courante()))[0], "ok")
        self.assertFalse(os.path.exists(os.path.join(d, ".claude", ".briefing.json.tmp")))

    def test_avertissements_ancien_paquet_et_reglages_inertes(self):
        d = self.dossier("avert", True)
        ecris(d, ".claude/settings.json", '{"enabledPlugins":{"harnais@atelier":true}}')
        self.assertTrue(copilot.ancien_paquet(d))
        ecris(d, ".claude/settings.json", '{"enabledPlugins":{"harnais@atelier-copilot":true}}')
        self.assertFalse(copilot.ancien_paquet(d))
        # Terminal et page disent la même chose.
        racine = os.path.join(self.tmp, "atelier")
        p = os.path.join(racine, "proj")
        os.makedirs(os.path.join(p, "agents"))
        subprocess.run(["git", "init", "-q"], cwd=p, check=True)
        for f in FAITS_TOUS:
            ecris(p, "brain/fact/%s" % f, "x\n")
        for a in ("OPS", "PO"):
            for f in MIND_ATTENDU:
                ecris(p, "brain/mind/%s/%s" % (a, f), "x\n")
            ecris(p, "agents/%s/AGENTS.md" % a, "x\n")
        branche(p, DECLARE)
        ecris(p, "agents/OPS/.github/copilot/settings.json", DECLARE)
        ecris(p, "agents/PO/.claude/settings.json", '{"enabledPlugins":{"harnais@atelier":true}}')
        projets = vue.scanne(racine, "")
        self.assertEqual(len(projets), 1)
        import io
        with mock.patch("sys.stdout", new=io.StringIO()) as sortie:
            vue.terminal(projets, racine)
        texte = sortie.getvalue()
        inerte = os.path.join(p, "agents", "OPS", ".github", "copilot", "settings.json")
        ancien = os.path.join(p, "agents", "PO", ".claude/settings.json")
        self.assertIn("     ATTENTION : %s est inerte hors de la racine Git" % inerte, texte)
        self.assertIn("     ATTENTION : %s déclare encore harnais@atelier (risque de double chargement)" % ancien, texte)
        self.assertEqual(texte.count("ATTENTION"), 2, texte)
        page = vue.page(projets, racine, 0)
        self.assertIn('<div class="conseil">ATTENTION : %s est inerte hors de la racine Git</div>' % inerte, page)
        self.assertIn("AGENTS.md → mémoire", page)
        self.assertEqual(page.count("ATTENTION"), 2)

    def test_la_source_du_paquet_n_est_pas_un_projet(self):
        racine = os.path.join(self.tmp, "atelier2")
        for n in ("copilot-harness", "claude-harnais", "autre"):
            os.makedirs(os.path.join(racine, n))
        self.assertEqual([p.nom for p in vue.scanne(racine, "")], ["autre", "claude-harnais"])
        self.assertEqual([p.nom for p in vue.scanne(racine, "copilot-harness")], ["copilot-harness"])

    def test_un_fait_workflow_est_en_trop_comme_pour_le_rust(self):
        """Le Rust ne connaît pas `workflow.md` : il compte comme un fichier en trop."""
        d = self.brain_mono("workflow")
        trace(d, courante())
        ins = inscrit([d], courante())
        self.assertEqual(juge(d, ins)[0], "ok")
        ecris(d, "brain/fact/workflow.md", "x\n")
        self.assertEqual(juge(d, ins)[0], "surplus")
        self.assertIn("faits 5/4", vue.jauge(vue.harnais(d, ins)))


if __name__ == "__main__":
    unittest.main()

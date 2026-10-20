# -*- coding: utf-8 -*-
"""Le garde du coffre (portée de Claude 0.19.1) : chaque forme qui affiche est refusée, et la
même forme jetée, capturée ou réduite aux noms passe — l'une est le témoin de l'autre.

Écarts voulus avec le harnais Claude : la charge est celle de Copilot (`toolName` /
`toolArgs`, l'outil `view` pour Read), un refus sort par `hote.refus`, et PowerShell
a ses formes (`Get-Content .env`, `type .env`, `$env:CLE`, `Get-ChildItem Env:`).
"""
import base64
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import coffre  # noqa: E402
import hote  # noqa: E402
from _gardes import Isole, charge_camel, charge_pascal, lance, refus, sortie  # noqa: E402

# (refusée, la même qui passe)
PAIRES = [
    # Doppler — mesuré sur 3.77.0 contre un faux coffre
    ("doppler secrets set CLE=x", "doppler secrets set CLE=x --silent"),
    ("doppler secrets set CLE=x", "doppler secrets set CLE=x > /dev/null"),
    ("doppler secrets set CLE=x --json", "doppler secrets set CLE=x --json >/dev/null 2>&1"),
    ("doppler secrets delete CLE --yes", "doppler secrets delete CLE --yes --silent"),
    ("doppler secrets upload .env.local", "doppler secrets upload .env.local --silent"),
    ("doppler secrets", "doppler secrets --only-names"),
    ("doppler secrets -p projet -c prd", "doppler secrets -p projet -c prd --only-names"),
    ("doppler secrets --json | jq .", "doppler secrets --json | jq keys"),
    ("doppler secrets get CLE --plain", "X=$(doppler secrets get CLE --plain)"),
    ("doppler secrets get CLE --plain", 'export X="$(doppler secrets get CLE --plain)"'),
    ("doppler secrets get CLE --silent", "doppler secrets get CLE --plain > .env.local"),
    ("doppler secrets download --no-file", "doppler secrets download --no-file > .env.local"),
    ("doppler secrets substitute gabarit", "doppler secrets substitute gabarit --output f"),
    ("doppler run -- env", "doppler run -- env | grep -oE '^[A-Z_][A-Z0-9_]*='"),
    ("doppler run -- printenv CLE", "doppler run -- printenv CLE > /dev/null"),
    ("doppler run --command env", "doppler run --command 'npm test'"),
    # les formes détournées
    ("cd x && doppler secrets set A=1", "cd x && doppler secrets set A=1 --silent"),
    ("echo ok; doppler secrets", "echo ok; doppler secrets --only-names"),
    ("env DOPPLER_TOKEN=t doppler secrets", "env DOPPLER_TOKEN=t doppler secrets --only-names"),
    ("/opt/homebrew/bin/doppler secrets", "/opt/homebrew/bin/doppler secrets --only-names"),
    ("bash -c 'doppler secrets'", "bash -c 'doppler secrets --only-names'"),
    ("sh -c \"doppler secrets set A=1\"", "sh -c \"doppler secrets set A=1\" > /dev/null"),
    ("doppler secrets set A=1 | tail -1", "doppler secrets set A=1 | wc -l"),
    ("doppler secrets set A=1 > /dev/stdout", "doppler secrets set A=1 > /tmp/x"),
    ("doppler secrets set A=1 2>/dev/null", "doppler secrets set A=1 &>/dev/null"),
    ("doppler \\\n  secrets", "doppler \\\n  secrets --only-names"),
    ("ls\ndoppler secrets", "ls\ndoppler secrets --only-names"),
    # fichiers de secrets
    ("cat .env.local", "grep -oE '^[A-Z_][A-Z0-9_]*=' .env.local"),
    ("cat apps/web/.env.local", "cat apps/web/.env.local | grep -oE '^[A-Z_][A-Z0-9_]*='"),
    ("head -5 .env", "wc -l .env"),
    ("cat .envrc", "grep -c export .envrc"),
    ("grep STRIPE .env.local", "grep -c STRIPE .env.local"),
    ("cat ~/.secrets/coffre-lecture", "ls -la ~/.secrets/"),
    ("cat .mcp.json", "jq '.mcpServers | keys' .mcp.json"),
    ("sed -n 1,5p .env.production", "grep -q STRIPE .env.production"),
    # les autres outils
    ("supabase status", "supabase status -o json | jq keys"),
    # une valeur sur plusieurs lignes traverse `cut` et `sed` : ils ne réduisent pas
    ("cut -d= -f1 .env.local", "grep -c = .env.local"),
    ("cat .env.local | sed 's/=.*//'", "cat .env.local | wc -l"),
    ("npx supabase status", "npx supabase status > /dev/null"),
    ("supabase projects api-keys --project-ref x", "supabase projects api-keys --project-ref x | wc -l"),
    ("gh auth token", "GH_TOKEN=$(gh auth token) gh api user"),
    ("gh auth status --show-token", "gh auth status"),
    ("security find-generic-password -s x -w", "P=$(security find-generic-password -s x -w)"),
    ("security find-generic-password -s x -g", "security find-generic-password -s x -g 2>/dev/null"),
    ("stripe config --list", "stripe config --list | grep -c _key"),
    ("vercel env pull /dev/stdout", "vercel env pull .env.local"),
]

# Ce qui ne doit jamais être refusé : le garde qui refuse tout rendrait le même verdict.
LIBRES = [
    "git status", "ls -la", "cat README.md", "cat .env.example", "grep -rn doppler docs/",
    "echo 'doppler secrets'", "git commit -m 'garde doppler secrets set'",
    "cat <<EOF > doc.md\ndoppler secrets set CLE=x\nEOF", "doppler setup --no-interactive",
    "doppler secrets --only-names --json", "gh pr list", "supabase db push --dry-run",
    "stripe listen", "source .env.local", "cp .env.local /tmp/sauve", "printenv PATH",
    "test -f .env.local && echo present", "doppler run -- npm test",
]


def ps(cmd):
    """Le garde, sur une ligne PowerShell."""
    return coffre.affiche_un_secret(cmd, powershell=True)


# (refusée, la même qui passe) — PowerShell
PAIRES_PS = [
    ("Get-Content .env", "(Get-Content .env).Count"),
    ("Get-Content .env.local", "Get-Content .env.local | Measure-Object"),
    ("gc .env.production", "gc .env.production | Out-Null"),
    ("cat apps\\web\\.env.local", "cat apps\\web\\.env.local | Measure-Object -Line"),
    ("type .env", "$brut = type .env"),
    ("Get-Content -Path .\\.env -Raw", "$brut = Get-Content -Path .\\.env -Raw"),
    ("Get-Content .env", "Get-Content .env > $null"),
    ("Get-Content .env", "Get-Content .env | Out-File copie.txt"),
    ("Get-Content .env", "Get-Content .env | Set-Content $env:TEMP\\x"),
    ("Select-String -Path .env -Pattern KEY", "Select-String -Path .env -Pattern KEY -Quiet"),
    ("sls KEY .env.local", "sls KEY .env.local -Quiet"),
    ("Select-String -Pattern '^[A-Z_][A-Z0-9_]*=' -Path .env",
     "Select-String -OnlyMatching -Pattern '^[A-Z_][A-Z0-9_]*=' -Path .env"),
    ("Get-Content .mcp.json", "(Get-Content .mcp.json | ConvertFrom-Json).mcpServers.PSObject.Properties.Name"),
    ("more .envrc", "(Get-Content .envrc).Length"),
    ("Get-Content C:\\Users\\u\\.secrets\\coffre", "Get-ChildItem C:\\Users\\u\\.secrets"),
    # l'environnement
    ("Write-Host $env:STRIPE_SECRET_KEY", "Write-Host $env:PATH"),
    ("Write-Output \"cle : $env:API_KEY\"", "Write-Output \"chemin : $env:USERPROFILE\""),
    ("echo $env:GITHUB_TOKEN", "$t = $env:GITHUB_TOKEN"),
    ("$env:SUPABASE_SERVICE_KEY", "$env:SUPABASE_SERVICE_KEY = 'x'"),
    ("\"$env:DB_PASSWORD\"", "Test-Path Env:DB_PASSWORD"),
    ("$ENV:API_KEY", "$ENV:API_KEY > $null"),
    ("${env:AUTH_TOKEN}", "$null = ${env:AUTH_TOKEN}"),
    ("Get-ChildItem Env:", "Get-ChildItem Env: | Select-Object -ExpandProperty Name"),
    ("gci env:", "(gci env:).Count"),
    ("dir env:", "dir env: | Out-Null"),
    ("ls Env:*KEY*", "ls Env:PATH"),
    ("Get-Item Env:STRIPE_SECRET_KEY", "Get-Item Env:HOME"),
    ("Get-Content Env:API_KEY", "Get-Content Env:USERNAME"),
    ("[Environment]::GetEnvironmentVariable('GH_TOKEN')", "[Environment]::GetEnvironmentVariable('PATH')"),
    ("[Environment]::GetEnvironmentVariables()", "([Environment]::GetEnvironmentVariables()).Count"),
    # les autres outils, vus de PowerShell
    ("doppler secrets", "doppler secrets --only-names"),
    ("doppler secrets set A=1; Get-Date", "doppler secrets set A=1 --silent; Get-Date"),
    ("& 'C:\\Program Files\\Doppler\\doppler.exe' secrets",
     "& 'C:\\Program Files\\Doppler\\doppler.exe' secrets --only-names"),
    ("gh auth token", "$t = gh auth token"),
    ("Get-Date\nGet-Content .env", "Get-Date\n(Get-Content .env).Count"),
    ("Get-Content `\n  .env", "(Get-Content `\n  .env).Count"),
]

# Ce qu'un PowerShell ordinaire fait, et que le garde qui refuserait tout casserait.
LIBRES_PS = [
    "Get-Content README.md", "Get-Content .env.example", "type docs\\notes.md", "gc package.json",
    "Select-String -Path src\\*.py -Pattern TODO", "Get-ChildItem -Recurse -Filter *.py",
    "Write-Host $env:COMPUTERNAME", "$env:PATH -split ';'", "$env:NODE_ENV = 'test'; npm test",
    "curl.exe -H \"Authorization: Bearer $env:API_TOKEN\" https://example.invalid/x",
    "git status; git log --oneline", "Set-Location code; Get-ChildItem", "Test-Path .env",
    "Copy-Item .env.local $env:TEMP\\sauve", "Write-Host 'Get-Content .env'",
    "Write-Output \"doppler secrets set CLE=x\"", "doppler run -- npm test",
    "$x = 'Get-Content .env'", "Get-ChildItem Env:PATH", "dir C:\\Users", "Get-Content (Get-Item README.md).FullName",
]



class Avant(unittest.TestCase):
    def test_chaque_forme_qui_affiche_est_refusee_et_sa_jumelle_passe(self):
        for mauvaise, bonne in PAIRES:
            with self.subTest(mauvaise=mauvaise):
                self.assertIsNotNone(coffre.affiche_un_secret(mauvaise), mauvaise)
            with self.subTest(bonne=bonne):
                self.assertIsNone(coffre.affiche_un_secret(bonne), bonne)

    def test_le_travail_ordinaire_passe(self):
        for c in LIBRES:
            with self.subTest(c=c):
                self.assertIsNone(coffre.affiche_un_secret(c), c)

    def test_une_ligne_illisible_ne_bloque_pas(self):
        self.assertIsNone(coffre.affiche_un_secret("echo 'non fermé"))
        self.assertIsNone(coffre.affiche_un_secret("echo 'non fermé", powershell=True))

    def test_le_hook_refuse_avec_sa_raison(self):
        _, sort, _ = sortie(coffre.main, json.dumps(hote.traduis(charge_camel(
            "bash", {"command": "doppler secrets set A=1"}, "/p"))))
        d = json.loads(sort)
        self.assertEqual(d["permissionDecision"], "deny")      # à la racine, pas sous hookSpecificOutput
        self.assertNotIn("hookSpecificOutput", d)
        self.assertIn("--silent", d["permissionDecisionReason"])
        self.assertTrue(sort.isascii())
        # TÉMOIN : la même commande avec `--silent` passe, muette.
        _, sort, _ = sortie(coffre.main, json.dumps(hote.traduis(charge_camel(
            "bash", {"command": "doppler secrets set A=1 --silent"}, "/p"))))
        self.assertEqual(sort, "")

    def lire(self, f):
        return coffre.juge(hote.traduis(charge_camel("view", {"path": f}, "/p")))

    def test_ouvrir_un_fichier_de_secrets(self):
        self.assertIsNotNone(self.lire("/p/apps/web/.env.local"))
        self.assertIsNotNone(self.lire("/p/.mcp.json"))
        self.assertIsNotNone(self.lire("C:\\Users\\u\\projet\\.env"))
        self.assertIsNotNone(self.lire(os.path.expanduser("~/.secrets/coffre-lecture")))
        self.assertIsNone(self.lire("/p/.env.example"))
        self.assertIsNone(self.lire("/p/README.md"))
        # La forme PascalCase, `tool_name: Read` et `file_path`.
        self.assertIsNotNone(coffre.juge({"tool_name": "Read", "tool_input": {"file_path": "/p/.env"}}))

    def test_chercher_dans_un_fichier_de_secrets(self):
        g = lambda **ti: coffre.juge({"tool_name": "Grep", "tool_input": ti})
        self.assertIsNotNone(g(pattern="KEY", path=".env.local", output_mode="content"))
        self.assertIsNotNone(g(pattern="KEY", glob=".env*", output_mode="content"))
        self.assertIsNone(g(pattern="KEY", path=".env.local", output_mode="count"))
        self.assertIsNone(g(pattern="KEY", path=".env.local"))
        self.assertIsNone(g(pattern="KEY", glob="*.ts", output_mode="content"))

    def test_un_autre_outil_n_est_pas_juge(self):
        for outil in ("Write", "Edit", "Glob", "Task"):
            self.assertIsNone(coffre.juge({"tool_name": outil, "tool_input": {
                "command": "doppler secrets", "file_path": "/p/.env", "path": "/p/.env",
                "output_mode": "content"}}), outil)


class PowerShell(unittest.TestCase):
    def test_chaque_forme_powershell_est_refusee_et_sa_jumelle_passe(self):
        for mauvaise, bonne in PAIRES_PS:
            with self.subTest(mauvaise=mauvaise):
                self.assertIsNotNone(ps(mauvaise), mauvaise)
            with self.subTest(bonne=bonne):
                self.assertIsNone(ps(bonne), bonne)

    def test_le_travail_ordinaire_powershell_passe(self):
        for c in LIBRES_PS:
            with self.subTest(c=c):
                self.assertIsNone(ps(c), c)

    def test_les_barres_inverses_d_un_chemin_windows_ne_sont_pas_mangees(self):
        # Lue en bash, `\\.env` perd sa barre : `C:Usersx.env` n'est plus un fichier de secrets.
        self.assertIsNone(coffre.affiche_un_secret("cat C:\\Users\\u\\.env"))
        # TÉMOIN : lue en PowerShell, la même ligne est refusée.
        self.assertIsNotNone(coffre.affiche_un_secret("cat C:\\Users\\u\\.env", powershell=True))

    def test_le_nom_d_une_variable_ne_se_juge_que_s_il_se_lit_comme_un_secret(self):
        self.assertIsNotNone(ps("Write-Host $env:MON_JETON_TOKEN"))
        self.assertIsNone(ps("Write-Host $env:MON_DOSSIER"))

    def test_la_charge_powershell_traverse_hote_et_le_garde(self):
        c = hote.traduis(charge_camel("powershell", {"command": "Get-Content .env.local"}, "/p"))
        self.assertTrue(hote.est_powershell(c))
        m = coffre.juge(c)
        self.assertIsNotNone(m)
        self.assertIn("Select-String", m)       # le refus propose la forme PowerShell
        c = hote.traduis(charge_camel("powershell", {"command": "(Get-Content .env.local).Count"}, "/p"))
        self.assertIsNone(coffre.juge(c))
        # La même ligne sous bash n'est pas lue comme PowerShell : `type` y est un builtin.
        c = hote.traduis(charge_camel("bash", {"command": "$env:API_KEY"}, "/p"))
        self.assertIsNone(coffre.juge(c))

    def test_la_forme_pascal_d_un_outil_powershell_est_jugee(self):
        c = hote.traduis(charge_pascal("PowerShell", {"command": "Get-Content .env"}, "/p"))
        self.assertIsNotNone(coffre.juge(c))


class ParLeLanceur(Isole):
    """Le hook tel qu'il part : charge camelCase de Copilot sur l'entrée standard."""

    def test_refus_et_temoins_muets(self):
        for outil, args in (("bash", {"command": "doppler secrets"}),
                            ("powershell", {"command": "Get-Content .env"}),
                            ("view", {"path": "/p/.env.local"}),
                            ("grep", {"pattern": "KEY", "path": "/p/.env", "output_mode": "content"})):
            o = lance("coffre", charge_camel(outil, args, "/p"))
            self.assertEqual(o.returncode, 0, o.stderr)
            d = refus(o)
            self.assertIsNotNone(d, outil)
            self.assertEqual(d["permissionDecision"], "deny", outil)
        for outil, args in (("bash", {"command": "doppler secrets --only-names"}),
                            ("powershell", {"command": "(Get-Content .env).Count"}),
                            ("view", {"path": "/p/README.md"}),
                            ("grep", {"pattern": "KEY", "path": "/p/.env", "output_mode": "count"}),
                            ("edit", {"path": "/p/.env", "old_str": "a", "new_str": "b"})):
            o = lance("coffre", charge_camel(outil, args, "/p"))
            self.assertEqual((o.returncode, o.stdout), (0, b""), (outil, o.stderr))
        o = lance("coffre", "{pas du json doppler secrets")
        self.assertEqual((o.returncode, o.stdout), (0, b""))



def _fausse(prefixe, n=40):
    # Fabriquée à l'exécution : ce fichier ne porte aucune clé que le témoin verrait.
    return prefixe + "A1b2C3d4E5f6G7h8" * (n // 16 + 1)


def _jwt(role):
    b = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
    return "%s.%s.%s" % (b({"alg": "HS256", "typ": "JWT"}), b({"role": role, "iss": "x"}),
                         "s1gnatureS1gnatureS1gnature")

class Lanceur(unittest.TestCase):
    """`~/.secrets/coffre prd secrets` : un script qui relaie à Doppler (QA, 17/10)."""
    def setUp(self):
        self.h = tempfile.mkdtemp(prefix="lanceur-")
        self.addCleanup(shutil.rmtree, self.h, True)
        self.coffre = os.path.join(self.h, "coffre")
        with open(self.coffre, "w") as f:
            f.write('#!/bin/sh\nc="$1"; shift\nexec doppler --config "$c" "$@"\n')
        self.autre = os.path.join(self.h, "autre")
        with open(self.autre, "w") as f:
            f.write('#!/bin/sh\necho "$@"\n')

    def test_le_lanceur_est_juge_comme_doppler(self):
        # Une ligne de Bash porte des `/` : sous Git Bash, `C:\Users\…` nu y serait déjà
        # mangé par le shell lui-même (la CI Windows l'a montré, 17/10/2026).
        c = self.coffre.replace("\\", "/")
        for mauvaise, bonne in [(c + " prd secrets", c + " prd secrets --only-names"),
                                (c + " prd run -- env", c + " prd run -- npm test"),
                                (c + " dev secrets set A=1", c + " dev secrets set A=1 --silent"),
                                ("./coffre prd secrets", "./coffre prd secrets > /dev/null")]:
            with self.subTest(mauvaise=mauvaise):
                self.assertIsNotNone(coffre.affiche_un_secret(mauvaise, self.h))
            with self.subTest(bonne=bonne):
                self.assertIsNone(coffre.affiche_un_secret(bonne, self.h))

    def test_un_script_qui_ne_relaie_pas_a_doppler_passe(self):
        self.assertIsNone(coffre.affiche_un_secret(self.autre.replace("\\", "/") + " prd secrets",
                                                   self.h))
        self.assertIsNone(coffre.affiche_un_secret("/nexiste/pas prd secrets", self.h))


class Apres(Isole):
    """Le témoin : PostToolUse, charge de Copilot (le résultat arrive dans `toolResult`)."""

    def temoin(self, sortie_outil, cmd="cat x", outil="bash", **plus):
        c = charge_camel(outil, {"command": cmd}, "/p",
                         toolResult={"resultType": "success", "textResultForLlm": sortie_outil})
        _, sort, _ = sortie(coffre.temoin, json.dumps(hote.traduis(c)))
        return sort

    def test_une_fausse_cle_affichee_declenche_l_alerte(self):
        cle = _fausse("sbp_")
        o = self.temoin("SUPABASE_ACCESS_TOKEN=" + cle)
        d = json.loads(o)
        self.assertIn("Supabase, jeton personnel", d["systemMessage"])
        self.assertIn("Supabase, jeton personnel", d["additionalContext"])
        self.assertNotIn(cle, o)
        self.assertTrue(o.isascii())
        chemin = os.path.join(os.environ["COPILOT_PLUGIN_DATA"], "coffre", "fuites.log")
        with open(chemin, encoding="utf-8") as f:
            journal = f.read()
        self.assertIn("Supabase, jeton personnel", journal)
        self.assertNotIn(cle, journal)

    def test_chaque_forme_connue(self):
        for p in ("sbp_", "sb_secret_", "sk_live_", "rk_live_", "sk_test_", "rk_test_", "ghp_",
                  "dp.st.", "sk-ant-"):
            with self.subTest(p=p):
                self.assertTrue(self.temoin("x=" + _fausse(p)), p)
        self.assertTrue(self.temoin(_jwt("service_role")))
        self.assertTrue(self.temoin("", cmd="doppler secrets set A=" + _fausse("sk_live_")))

    def test_ce_qui_n_est_pas_une_cle_se_tait(self):
        for s in ("tout va bien", "sbp_court", "le préfixe sk_live_ dans une doc",
                  "pk_live_" + "A1b2C3d4E5f6G7h8" * 2, _jwt("anon")):
            with self.subTest(s=s):
                self.assertEqual(self.temoin(s), "")

    def test_la_cle_vue_par_un_grep_ou_un_view_est_signalee(self):
        for outil, args in (("view", {"path": "/p/notes.txt"}), ("grep", {"pattern": "KEY"})):
            c = charge_camel(outil, args, "/p", toolResult={
                "resultType": "success", "textResultForLlm": "TOKEN=" + _fausse("ghp_")})
            _, sort, _ = sortie(coffre.temoin, json.dumps(hote.traduis(c)))
            self.assertIn("GitHub, jeton", sort, outil)

    def test_par_apres_bash_et_apres_lecture_en_un_seul_processus(self):
        """Le témoin ne coûte pas un processus de plus : il passe par `apres-bash` et `apres-lecture`."""
        cle = _fausse("sb_secret_")
        for sous, outil, args in (("apres-bash", "bash", {"command": "cat x"}),
                                  ("apres-lecture", "view", {"path": "/p/x.txt"}),
                                  ("coffre-temoin", "bash", {"command": "cat x"})):
            c = charge_camel(outil, args, "/p", toolResult={
                "resultType": "success", "textResultForLlm": "cle=" + cle})
            o = lance(sous, c)
            self.assertEqual(o.returncode, 0, (sous, o.stderr))
            self.assertIn("Supabase, cl", json.loads(o.stdout)["systemMessage"], sous)
            self.assertNotIn(cle.encode(), o.stdout, sous)
            # TÉMOIN : sans clé, rien.
            c["toolResult"]["textResultForLlm"] = "rien a signaler"
            o = lance(sous, c)
            self.assertEqual((o.returncode, o.stdout), (0, b""), (sous, o.stderr))

    def test_le_juge_muet_fait_taire_les_trois(self):
        c = charge_camel("bash", {"command": "cat x"}, "/p", toolResult={
            "resultType": "success", "textResultForLlm": _fausse("sbp_")})
        for sous in ("apres-bash", "apres-lecture", "coffre-temoin"):
            o = lance(sous, c, {"HARNAIS_JUGE": "1"})
            self.assertEqual((o.returncode, o.stdout), (0, b""), sous)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Teste puis assemble l'archive locale du paquet — sans compilation (Python >= 3.9).

Le programme EST son source : il n'y a plus de binaire à construire, donc plus
de binaire à rapatrier ni à comparer à son étiquette. Ce que la chaîne prouve :
  - les trois versions (plugin, marketplace, étiquette) sont la même ;
  - hooks/copilot.json est celui que son générateur écrit ;
  - la suite de tests passe, dans un HOME jetable, sur l'instantané livré ;
  - l'archive, extraite, répond `version` avec la version et l'empreinte de py/
    calculée ICI, séparément de celle du programme.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOSSIERS = (".github/plugin/", "skills/", "py/", "tests/", "outils/")
FICHIERS = {
    "hooks/copilot.json", "bin/harnais", "bin/harnais.cmd", "README.md",
    "COMMENT-CA-MARCHE.md", ".github/workflows/paquet.yml", "criteres-passe.md",
    "criteres-relecture.md", "rechutes.md", ".gitignore",
    "controles/portable-smoke.ps1", "controles/install-windows.ps1",
    "controles/hook-contract.ps1", "controles/cto-start.ps1",
    "controles/hooks-powershell.ps1", "controles/atelier-deplace.ps1", "controles/LISEZMOI.md",
}
# Ce qui ne part jamais, même suivi par git : l'état d'un poste.
JAMAIS = ("__pycache__/", ".pyc")


def run(*args, cwd=ROOT, env=None):
    return subprocess.check_output(args, cwd=cwd, env=env, text=True).strip()


def snapshot():
    # Entrées suivies par git seulement : jamais la mémoire, les rapports ni les caches.
    if (ROOT / ".git").exists():
        suivis = run("git", "ls-files", "-z").split("\0")
    else:
        manifeste = ROOT / "release-manifest.json"
        if not manifeste.is_file():
            raise RuntimeError("checkout Git ou archive source avec release-manifest.json requis")
        suivis = list(json.loads(manifeste.read_bytes())["files_sha256"])
    choisis = {p for p in suivis if p and not any(j in p for j in JAMAIS)
               and (p.startswith(DOSSIERS) or p in FICHIERS)}
    choisis.update({"install.ps1", "scripts/package_release.py", "scripts/test_package_release.py",
                    "scripts/RELEASE.md"})
    data = {}
    for nom in sorted(choisis):
        chemin = ROOT / nom
        if chemin.is_symlink() or not chemin.is_file() or not chemin.resolve().is_relative_to(ROOT):
            raise RuntimeError(f"source requise absente ou lien symbolique: {nom}")
        data[nom] = chemin.read_bytes()
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def empreinte_py(files):
    """L'empreinte de py/ — la MÊME recette que `harnais version` (py/main.py),
    écrite ici une seconde fois à dessein : une seule copie ne se vérifie pas."""
    h = hashlib.sha1()
    for nom in sorted(n[3:] for n in files if n.startswith("py/") and n.count("/") == 1
                      and n.endswith(".py")):
        h.update(nom.encode("utf-8") + b"\0")
        h.update(files["py/" + nom])
    return h.hexdigest()[:12]


def versions(files):
    v = {"plugin.json": json.loads(files[".github/plugin/plugin.json"])["version"]}
    marche = json.loads(files[".github/plugin/marketplace.json"])
    for p in marche.get("plugins", []):
        if "version" in p:
            v["marketplace.json:" + p.get("name", "?")] = p["version"]
    return v


def write_archive(path, files, epoch):
    stamp = time.gmtime(epoch)[:6]
    stamp = (*stamp[:5], stamp[5] // 2 * 2)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, stamp)
            info.create_system = 3
            executable = name == "bin/harnais" or name.endswith(".sh")
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            archive.writestr(info, content)


def _supprime(fonction, chemin, erreur):
    os.chmod(chemin, stat.S_IWRITE)
    fonction(chemin)


def env_jetable(base, scratch):
    """Un poste vide : ni le HOME, ni les plugins, ni l'état de celui qui construit."""
    env = os.environ.copy()
    for n in ("COPILOT_PLUGIN_ROOT", "PLUGIN_ROOT", "COPILOT_PLUGIN_DATA", "PLUGIN_DATA",
              "COPILOT_PROJECT_DIR", "HARNAIS_JUGE", "HARNAIS_PYTHON", "PYTHONPATH"):
        env.pop(n, None)
    env.update(HOME=str(base), USERPROFILE=str(base), COPILOT_HOME=str(base / ".copilot"),
               TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch),
               GIT_CEILING_DIRECTORIES=str(scratch), PYTHONDONTWRITEBYTECODE="1")
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="release", help="dossier DANS ce checkout")
    parser.add_argument("--sans-tests", action="store_true", help="n'exécute pas la suite (essai de l'assemblage)")
    args = parser.parse_args()
    if sys.version_info < (3, 9):
        raise RuntimeError("Python 3.9 au moins")
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise RuntimeError("--output doit etre un sous-dossier du checkout")
    output.mkdir(parents=True, exist_ok=True)
    files = snapshot()
    original = files.copy()
    vs = versions(files)
    if len(set(vs.values())) != 1:
        raise RuntimeError(f"versions incoherentes: {vs}")
    version = next(iter(vs.values()))
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/") and ref != f"refs/tags/v{version}":
        raise RuntimeError("l'etiquette ne correspond pas a la version du paquet")
    # Le fichier des hooks n'est jamais édité à la main.
    sys.path.insert(0, str(ROOT / "outils"))
    import genere_hooks
    if files["hooks/copilot.json"].decode("utf-8") != genere_hooks.contenu():
        raise RuntimeError("hooks/copilot.json differe de son generateur (python outils/genere_hooks.py)")
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "315532800"))
    if not 315532800 <= epoch <= 4354819198:
        raise RuntimeError("SOURCE_DATE_EPOCH doit etre dans la plage ZIP 1980-2107")

    # L'instantané LIVRÉ, extrait à part : on teste ce qui partira, pas le checkout.
    travail = Path(tempfile.mkdtemp(prefix=".essai-", dir=output))
    try:
        copie = travail / "paquet"
        for nom, contenu in files.items():
            cible = copie / nom
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_bytes(contenu)
        poste = travail / "poste"
        scratch = poste / "scratch"
        scratch.mkdir(parents=True)
        env = env_jetable(poste, scratch)
        env["COPILOT_PLUGIN_ROOT"] = str(copie)
        if not args.sans_tests:
            subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                           cwd=copie, env=env, check=True)
        identite = run(sys.executable, str(copie / "py" / "main.py"), "version", cwd=copie, env=env)
        attendue = f"{version} {empreinte_py(files)}"
        if identite != attendue:
            raise RuntimeError(f"identite inattendue: {identite!r} au lieu de {attendue!r}")
        # Le lanceur sh, s'il y a un sh (pas sous Windows nu).
        lanceur = shutil.which("sh")
        if lanceur and os.name != "nt":
            env2 = dict(env, HARNAIS_PYTHON=sys.executable)
            vu = run(lanceur, str(copie / "bin" / "harnais"), "version", cwd=copie, env=env2)
            if vu != attendue:
                raise RuntimeError(f"le lanceur sh rend {vu!r} au lieu de {attendue!r}")
        git_head = run("git", "rev-parse", "HEAD") if (ROOT / ".git").exists() else None
    finally:
        shutil.rmtree(travail, onerror=_supprime)
    if snapshot() != original:
        raise RuntimeError("source modifie pendant la construction; relancer pour une archive coherente")
    evidence = {
        "version": version, "source_py_sha1": empreinte_py(files), "git_head": git_head,
        "python": sys.version.split()[0], "source_date_epoch": epoch, "identity": identite,
        "tests": "non executes (--sans-tests)" if args.sans_tests
                 else "python -m unittest discover -s tests (HOME jetable, instantane livre)",
        "files_sha256": {n: sha(b) for n, b in sorted(files.items())},
    }
    files["release-manifest.json"] = (json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    files["SHA256SUMS"] = "".join(f"{sha(b)}  {n}\n" for n, b in sorted(files.items())).encode()
    archive = output / f"harnais-{version}.zip"
    write_archive(archive, files, epoch)
    checksum = sha(archive.read_bytes())
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii", newline="\n")
    print(f"Artifact: {archive}\nSHA256: {checksum}\nIdentity: {identite}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as error:
        sys.exit(f"release refusee: {error}")

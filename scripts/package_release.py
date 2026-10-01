#!/usr/bin/env python3
"""Build, test and assemble a native, offline local plugin release (Python >= 3.11)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import time
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "x86_64-pc-windows-gnu": ("windows-x86_64", "harnais.exe", "harnais-windows-x86_64.exe"),
    "x86_64-pc-windows-msvc": ("windows-x86_64", "harnais.exe", "harnais-windows-x86_64.exe"),
    "aarch64-apple-darwin": ("darwin-arm64", "harnais", "harnais-darwin-arm64"),
}
SYSTEM_DLLS = {
    "advapi32.dll", "bcrypt.dll", "bcryptprimitives.dll", "crypt32.dll",
    "dbghelp.dll", "gdi32.dll", "iphlpapi.dll", "kernel32.dll", "msvcrt.dll",
    "ntdll.dll", "ole32.dll", "oleaut32.dll", "psapi.dll", "rpcrt4.dll",
    "secur32.dll", "shell32.dll", "shlwapi.dll", "ucrtbase.dll", "user32.dll",
    "userenv.dll", "version.dll", "winmm.dll", "ws2_32.dll",
}


def run(*args, cwd=ROOT, env=None):
    return subprocess.check_output(args, cwd=cwd, env=env, text=True).strip()


def tool(name):
    found = shutil.which(name)
    if found:
        return found
    candidate = Path.home() / ".cargo" / "bin" / (name + (".exe" if os.name == "nt" else ""))
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError(f"{name} absent; installer l'outillage avant de construire")


def snapshot():
    # Tracked plugin/source inputs only; never memory, reports, fixtures or caches.
    if (ROOT / ".git").exists():
        tracked = run("git", "ls-files", "-z").split("\0")
    else:
        manifest = ROOT / "release-manifest.json"
        if not manifest.is_file():
            raise RuntimeError("checkout Git ou archive source avec release-manifest.json requis")
        tracked = list(json.loads(manifest.read_bytes())["files_sha256"])
    selected = {
        p for p in tracked if (
            p.startswith((".github/plugin/", "skills/", "harnais/src/"))
            or p in {
                "hooks/copilot.json", "harnais/Cargo.toml",
                "harnais/Cargo.lock", "harnais/.cargo/config.toml", "rappels/Rappels.swift",
                "rappels/construire.sh", "bin/harnais", "bin/harnais.cmd",
                "README.md", "COMMENT-CA-MARCHE.md", ".github/workflows/binaires.yml",
                "criteres-passe.md", "criteres-relecture.md", "rechutes.md",
                ".gitignore", "controles/portable-smoke.ps1",
                "controles/install-windows.ps1", "controles/hook-contract.ps1",
                "controles/cto-start.ps1",
            }
        )
    }
    selected.update({"install.ps1", "scripts/package_release.py", "scripts/test_package_release.py", "scripts/RELEASE.md"})
    data = {}
    for name in sorted(selected):
        path = ROOT / name
        if not path.resolve().is_relative_to(ROOT) or path.is_symlink() or not path.is_file():
            raise RuntimeError(f"source requise absente ou lien symbolique: {name}")
        data[name] = path.read_bytes()
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def windows_imports(path):
    """Inspect PE imports without dumpbin/objdump dependencies."""
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise RuntimeError("le programme Windows n'est pas un PE")
    machine, count = struct.unpack_from("<HH", data, pe + 4)
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    if machine != 0x8664 or struct.unpack_from("<H", data, optional)[0] != 0x20B:
        raise RuntimeError("le programme Windows n'est pas x86_64 PE32+")
    directories = optional + 112
    sections = optional + optional_size

    def offset(rva):
        for index in range(count):
            entry = sections + index * 40
            size, address, raw_size, raw = struct.unpack_from("<IIII", data, entry + 8)
            if address <= rva < address + max(size, raw_size):
                return raw + rva - address
        raise RuntimeError(f"RVA PE non reconnue: {rva:x}")

    imports = []
    rva = struct.unpack_from("<I", data, directories + 8)[0]
    if rva:
        entry = offset(rva)
        while any(struct.unpack_from("<IIIII", data, entry)):
            name = offset(struct.unpack_from("<I", data, entry + 12)[0])
            imports.append(data[name:data.index(b"\0", name)].decode("ascii").lower())
            entry += 20
    if struct.unpack_from("<I", data, directories + 13 * 8)[0]:
        raise RuntimeError("imports DLL differes non verifies")
    unexpected = [dll for dll in imports if dll not in SYSTEM_DLLS
                  and not dll.startswith(("api-ms-win-", "ext-ms-win-"))]
    if unexpected:
        raise RuntimeError(f"DLL non systeme interdites (reconstruire en statique): {unexpected}")
    return sorted(set(imports))


def write_archive(path, files, epoch):
    stamp = time.gmtime(epoch)[:6]
    stamp = (*stamp[:5], stamp[5] // 2 * 2)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, stamp)
            info.create_system = 3
            executable = name == "bin/harnais" or name.endswith((".sh", ".py")) or (
                name.startswith("bin/") and not name.endswith((".cmd", ".exe", ".identite")))
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            archive.writestr(info, content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS)
    parser.add_argument("--output", default="release", help="directory inside this checkout")
    parser.add_argument("--online", action="store_true", help="allow Cargo downloads (default: offline)")
    args = parser.parse_args()
    cargo, rustc = tool("cargo"), tool("rustc")
    host = next(line.split(": ", 1)[1] for line in run(rustc, "-vV").splitlines() if line.startswith("host: "))
    target = args.target or host
    if target not in TARGETS:
        raise RuntimeError(f"plateforme non livree: {target}; macOS ARM64 / Windows x86_64 seulement")
    native_windows = host.startswith("x86_64-pc-windows-") and target.startswith("x86_64-pc-windows-")
    if target != host and not native_windows:
        raise RuntimeError("construction native requise pour verifier le programme sur sa plateforme")
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise RuntimeError("--output doit etre un sous-dossier du checkout")
    output.mkdir(parents=True, exist_ok=True)
    files = snapshot()
    original = files.copy()
    version = json.loads(files[".github/plugin/plugin.json"])["version"]
    versions = {version,
                tomllib.loads(files["harnais/Cargo.toml"].decode())["package"]["version"]}
    lock = tomllib.loads(files["harnais/Cargo.lock"].decode())
    versions.update(p["version"] for p in lock["package"] if p["name"] == "harnais")
    if len(versions) != 1:
        raise RuntimeError(f"versions incoherentes: {sorted(versions)}")
    if os.environ.get("GITHUB_REF", "").startswith("refs/tags/") and os.environ["GITHUB_REF"] != f"refs/tags/v{version}":
        raise RuntimeError("l'etiquette ne correspond pas a la version du paquet")
    source_files = {n: sha(b) for n, b in files.items()
                    if n.startswith(("harnais/", "hooks/", "skills/"))}
    source = sha(json.dumps(source_files, sort_keys=True, separators=(",", ":")).encode())
    env = os.environ.copy()
    env.update(HARNAIS_VERSION=version, HARNAIS_SOURCE=source)
    # Aucun chemin du poste de construction dans le binaire : ni le checkout, ni
    # les sources des dépendances (registre Cargo), ni la chaîne d'outils.
    cargo_home = Path(env.get("CARGO_HOME") or Path.home() / ".cargo")
    rustup_home = Path(env.get("RUSTUP_HOME") or Path.home() / ".rustup")
    flags = [f"--remap-path-prefix={cargo_home}=cargo",
             f"--remap-path-prefix={rustup_home}=rustup",
             f"--remap-path-prefix={ROOT}=harnais-portable"]
    if native_windows:
        flags += ["-C", "target-feature=+crt-static"]
        if target.endswith("-gnu"):
            flags += ["-C", "link-arg=-static", "-C", "link-arg=-Wl,--no-insert-timestamp"]
        else:
            flags += ["-C", "link-arg=/Brepro"]
    env.pop("RUSTFLAGS", None)
    env["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(flags)
    epoch = int(env.get("SOURCE_DATE_EPOCH", "315532800"))
    if not 315532800 <= epoch <= 4354819198:
        raise RuntimeError("SOURCE_DATE_EPOCH doit etre dans la plage ZIP 1980-2107")
    env["SOURCE_DATE_EPOCH"] = str(epoch)
    env["CARGO_TARGET_DIR"] = str(ROOT / "harnais" / "target")
    common = ["--release", "--locked", "--target", target]
    if not args.online:
        common += ["--offline"]
    # Test discovery must not be influenced by the host's installed plugin/state.
    test_home = output / ".test-home"
    def writable_remove(function, path, error):
        os.chmod(path, stat.S_IWRITE)
        function(path)

    test_home.mkdir(parents=True)
    test_temp = test_home / "scratch"
    test_temp.mkdir(exist_ok=True)
    test_env = env.copy()
    test_env.setdefault("CARGO_HOME", str(Path.home() / ".cargo"))
    test_env.setdefault("RUSTUP_HOME", str(Path.home() / ".rustup"))
    test_env.update(HOME=str(test_home), USERPROFILE=str(test_home),
                    COPILOT_HOME=str(test_home / ".copilot"),
                    TEMP=str(test_temp), TMP=str(test_temp), TMPDIR=str(test_temp),
                    GIT_CEILING_DIRECTORIES=str(test_temp))
    for name in ("COPILOT_PLUGIN_ROOT", "PLUGIN_ROOT", "COPILOT_PLUGIN_DATA", "PLUGIN_DATA", "COPILOT_PROJECT_DIR"):
        test_env.pop(name, None)
    try:
        subprocess.run([cargo, "test", *common], cwd=ROOT / "harnais", env=test_env, check=True)
    finally:
        shutil.rmtree(test_home, onerror=writable_remove)
    subprocess.run([cargo, "build", *common], cwd=ROOT / "harnais", env=env, check=True)
    label, filename, shipped = TARGETS[target]
    binary = ROOT / "harnais" / "target" / target / "release" / filename
    imports = windows_imports(binary) if native_windows else []
    runtime_env = env.copy()
    if native_windows:
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        runtime_env["PATH"] = os.pathsep.join(map(str, [windows / "System32", windows]))
    identity = run(str(binary), "version", env=runtime_env)
    if identity != f"{version} {source}":
        raise RuntimeError(f"identite inattendue: {identity!r}")
    files[f"bin/{shipped}"] = binary.read_bytes()
    files[f"bin/{shipped}.identite"] = (identity + "\n").encode()
    if target == "aarch64-apple-darwin":
        helper = ROOT / "harnais" / "target" / target / "release" / "rappels-darwin-arm64"
        subprocess.run(["swiftc", "-O", "-swift-version", "5", str(ROOT / "rappels" / "Rappels.swift"),
                        "-o", str(helper)], check=True, cwd=ROOT)
        result = subprocess.run([str(helper), "acces"], cwd=ROOT)
        if result.returncode not in (0, 3):
            raise RuntimeError(f"rappels acces: code inattendu {result.returncode}")
        files["bin/rappels-darwin-arm64"] = helper.read_bytes()
    if snapshot() != original:
        raise RuntimeError("source modifie pendant la construction; relancer pour une archive coherente")
    evidence = {
        "version": version, "target": target, "source_sha256": source,
        "git_head": run("git", "rev-parse", "HEAD") if (ROOT / ".git").exists() else None,
        "rustc": run(rustc, "--version"),
        "cargo": run(cargo, "--version"), "rustflags": [flag.replace(str(ROOT), "<checkout>").replace(str(cargo_home), "<cargo>")
                                     .replace(str(rustup_home), "<rustup>") for flag in flags],
        "source_date_epoch": epoch, "identity": identity, "windows_system_imports": imports,
        "tests": "cargo test --release --locked --target " + target,
        "runtime": "version OK; PATH restricted to Windows system directories" if native_windows else "version OK; rappels acces OK",
        "files_sha256": {n: sha(b) for n, b in sorted(files.items())},
    }
    files["release-manifest.json"] = (json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    files["SHA256SUMS"] = "".join(f"{sha(b)}  {n}\n" for n, b in sorted(files.items())).encode()
    archive = output / f"harnais-{version}-{label}.zip"
    write_archive(archive, files, epoch)
    checksum = sha(archive.read_bytes())
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii", newline="\n")
    print(f"Artifact: {archive}\nSHA256: {checksum}\nIdentity: {identity}\nDLL: {', '.join(imports) or 'not Windows'}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as error:
        sys.exit(f"release refusee: {error}")

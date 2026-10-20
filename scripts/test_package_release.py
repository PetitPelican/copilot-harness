"""Tests du conditionnement : locaux, sans téléchargement ni écriture hors du checkout."""
import hashlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import package_release as release


class ReleaseTests(unittest.TestCase):
    def test_archive_bytes_ignore_input_order(self):
        first, second = io.BytesIO(), io.BytesIO()
        release.write_archive(first, {"b.txt": b"b", "bin/harnais": b"a"}, 315532801)
        release.write_archive(second, {"bin/harnais": b"a", "b.txt": b"b"}, 315532800)
        self.assertEqual(first.getvalue(), second.getvalue())
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.namelist(), ["b.txt", "bin/harnais"])
            for entry in archive.infolist():
                self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(entry.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.getinfo("bin/harnais").external_attr >> 16, 0o100755)
            self.assertEqual(archive.getinfo("b.txt").external_attr >> 16, 0o100644)

    def test_snapshot_excludes_state_and_old_binaries(self):
        paths = "\0".join([
            "py/main.py", "py/__pycache__/main.cpython-313.pyc", "tests/test_hote.py",
            "hooks/copilot.json", "bin/harnais", "bin/harnais.cmd",
            "bin/harnais-windows-x86_64.exe", "bin/harnais-darwin-arm64",
            "bin/harnais-windows-x86_64.exe.identite", "bin/rappels-darwin-arm64",
            "harnais/src/main.rs", "harnais/Cargo.lock",
            "controles/verdict.txt", "atelier/controles/personal.jsonl",
            "criteres-passe.md", "criteres-relecture.md", "rechutes.md", ".gitignore",
            "controles/portable-smoke.ps1", "controles/hooks-powershell.ps1",
            "brain/mind/memory.md", ".git/config", "outils/genere_hooks.py",
        ])
        with patch.object(release, "run", return_value=paths), patch.object(Path, "is_file", return_value=True), \
                patch.object(Path, "is_symlink", return_value=False), patch.object(Path, "read_bytes", return_value=b"x"):
            files = release.snapshot()
        self.assertEqual(set(files), {
            "py/main.py", "tests/test_hote.py", "hooks/copilot.json", "bin/harnais", "bin/harnais.cmd",
            "criteres-passe.md", "criteres-relecture.md", "rechutes.md", ".gitignore",
            "controles/portable-smoke.ps1", "controles/hooks-powershell.ps1", "outils/genere_hooks.py",
            "install.ps1", "scripts/package_release.py", "scripts/test_package_release.py", "scripts/RELEASE.md"})

    def test_snapshot_requires_installer(self):
        with patch.object(release, "run", return_value=""), patch.object(Path, "is_symlink", return_value=False), \
                patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "install.ps1"):
                release.snapshot()

    def test_snapshot_rejects_links(self):
        with patch.object(release, "run", return_value="hooks/copilot.json"), patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "lien symbolique"):
                release.snapshot()

    def test_l_empreinte_suit_chaque_octet_de_py(self):
        base = {"py/a.py": b"1", "py/b.py": b"2", "py/sous/c.py": b"3", "README.md": b"x"}
        e = release.empreinte_py(base)
        self.assertRegex(e, r"^[0-9a-f]{12}$")
        self.assertNotEqual(e, release.empreinte_py(dict(base, **{"py/b.py": b"3"})), "un octet change")
        self.assertNotEqual(e, release.empreinte_py(dict(base, **{"py/d.py": b"4"})), "un module de plus")
        self.assertEqual(e, release.empreinte_py(dict(base, **{"README.md": b"y", "py/sous/c.py": b"9"})),
                         "ni la doc ni un sous-dossier n'entrent dans l'empreinte")

    def test_l_empreinte_est_celle_que_le_programme_annonce(self):
        # TÉMOIN CROISÉ : deux copies de la recette, qui doivent rester d'accord.
        ici = Path(release.ROOT, "py")
        files = {f"py/{p.name}": p.read_bytes() for p in ici.glob("*.py")}
        attendu = release.empreinte_py(files)
        h = hashlib.sha1()
        for nom in sorted(p.name for p in ici.glob("*.py")):
            h.update(nom.encode("utf-8") + b"\0" + (ici / nom).read_bytes())
        self.assertEqual(attendu, h.hexdigest()[:12])
        sys.path.insert(0, str(ici))
        try:
            import main as programme
            self.assertTrue(programme._identite().endswith(" " + attendu))
        finally:
            sys.path.remove(str(ici))

    def test_les_versions_incoherentes_sont_vues(self):
        f = {".github/plugin/plugin.json": b'{"version":"2.0.0"}',
             ".github/plugin/marketplace.json": b'{"plugins":[{"name":"harnais","version":"1.9.0"}]}'}
        self.assertEqual(len(set(release.versions(f).values())), 2)
        f[".github/plugin/marketplace.json"] = b'{"plugins":[{"name":"harnais"}]}'
        self.assertEqual(len(set(release.versions(f).values())), 1)

    def test_profile_sheets_reference_roles_and_allow_customization(self):
        for profile in ("OPS", "PO", "QA"):
            text = (release.ROOT / "skills" / "agentic-agents" / "references" / "profiles" /
                    (profile + ".md")).read_text(encoding="utf-8")
            self.assertIn("../roles.md", text)
            for field in ("Identifiant", "Nom", "Périmètre", "Règles", "Ton"):
                self.assertIn(field, text)
            self.assertIn("personnalisation", text)


if __name__ == "__main__":
    unittest.main()

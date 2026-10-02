"""Local packaging tests, no downloads or writes outside the checkout."""
import io
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock, patch
import zipfile

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
            "harnais/src/main.rs", "harnais/Cargo.lock", "hooks/copilot.json",
            "bin/harnais", "bin/harnais-windows-x86_64.exe", "bin/harnais-darwin-arm64",
            "bin/harnais-windows-x86_64.exe.identite", "bin/rappels-darwin-arm64",
            "controles/verdict.txt", "atelier/controles/personal.jsonl",
            "criteres-passe.md", "criteres-relecture.md", "rechutes.md",
            ".gitignore", "controles/portable-smoke.ps1", "controles/install-windows.ps1",
            "controles/hook-contract.ps1",
            "controles/cto-start.ps1",
            "brain/mind/memory.md", ".git/config", "harnais/target/release/harnais.exe",
        ])
        with patch.object(release, "run", return_value=paths), patch.object(Path, "is_file", return_value=True), \
                patch.object(Path, "is_symlink", return_value=False), patch.object(Path, "read_bytes", return_value=b"x"):
            files = release.snapshot()
        self.assertEqual(set(files), {"harnais/src/main.rs", "harnais/Cargo.lock", "hooks/copilot.json",
                                     "criteres-passe.md", "criteres-relecture.md", "rechutes.md",
                                     ".gitignore", "controles/portable-smoke.ps1", "controles/install-windows.ps1",
                                     "controles/hook-contract.ps1",
                                     "controles/cto-start.ps1",
                                     "bin/harnais", "install.ps1", "scripts/package_release.py", "scripts/test_package_release.py", "scripts/RELEASE.md"})

    def test_snapshot_requires_installer(self):
        with patch.object(release, "run", return_value=""), patch.object(Path, "is_symlink", return_value=False), \
                patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "install.ps1"):
                release.snapshot()

    def test_profile_sheets_reference_roles_and_allow_customization(self):
        for profile in ("OPS", "PO", "QA"):
            text = (release.ROOT / "skills" / "agentic-agents" / "references" / "profiles" /
                    (profile + ".md")).read_text(encoding="utf-8")
            self.assertIn("../roles.md", text)
            for field in ("Identifiant", "Nom", "Périmètre", "Règles", "Ton"):
                self.assertIn(field, text)
            self.assertIn("personnalisation", text)
        qa = (release.ROOT / "skills" / "agentic-agents" / "references" / "profiles" /
              "QA.md").read_text(encoding="utf-8")
        self.assertIn("validation explicite", qa)
        self.assertIn(" # fact-ok", qa)
        self.assertIn("sources d'audit", qa)
        self.assertNotIn("aucune écriture", qa)
        self.assertIn("Ne jamais réparer", qa)

    def test_snapshot_rejects_links(self):
        with patch.object(release, "run", return_value="hooks/copilot.json"), patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "lien symbolique"):
                release.snapshot()

    @staticmethod
    def pe(dll, delayed=False):
        data = bytearray(1024)
        struct.pack_into("<I", data, 0x3C, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<HH", data, 0x84, 0x8664, 1)
        struct.pack_into("<H", data, 0x94, 240)
        struct.pack_into("<H", data, 0x98, 0x20B)
        struct.pack_into("<II", data, 0x98 + 112 + 8, 0x1000, 40)
        if delayed:
            struct.pack_into("<II", data, 0x98 + 112 + 13 * 8, 0x1000, 32)
        struct.pack_into("<IIII", data, 0x98 + 240 + 8, 512, 0x1000, 512, 512)
        struct.pack_into("<IIIII", data, 512, 0, 0, 0, 0x1080, 0)
        name = dll.encode() + b"\0"
        data[640:640 + len(name)] = name
        return Mock(read_bytes=Mock(return_value=bytes(data)))

    def test_windows_system_imports(self):
        self.assertEqual(release.windows_imports(self.pe("KERNEL32.dll")), ["kernel32.dll"])
        self.assertEqual(release.windows_imports(self.pe("api-ms-win-crt-runtime-l1-1-0.dll")),
                         ["api-ms-win-crt-runtime-l1-1-0.dll"])

    def test_windows_rejects_mingw_dll(self):
        for dll in ("libwinpthread-1.dll", "libgcc_s_seh-1.dll", "VCRUNTIME140.dll"):
            with self.subTest(dll=dll), self.assertRaisesRegex(RuntimeError, "DLL non systeme"):
                release.windows_imports(self.pe(dll))

    def test_windows_rejects_delayed_import(self):
        with self.assertRaisesRegex(RuntimeError, "differes"):
            release.windows_imports(self.pe("KERNEL32.dll", delayed=True))


if __name__ == "__main__":
    unittest.main()

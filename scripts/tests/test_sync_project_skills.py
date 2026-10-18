from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[2]
SYNC_SCRIPT: Path = ROOT / "scripts/sync_project_skills.py"
REGISTRY_SCRIPT: Path = ROOT / ".agents/skills/project-mgr/scripts/registry.py"


class SyncProjectSkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root: Path = Path(self.temporary.name)
        self.source_root: Path = self.root / "projects/demo/skills"
        self.source_root.mkdir(parents=True)
        self.skills: Path = self.root / ".agents/skills"
        self.skills.mkdir(parents=True)
        self.registry: list[dict] = [
            {"name": "workspace", "self": True},
            {"name": "demo", "local_path": "demo", "skills": [{"dir": "skills"}]},
        ]
        self._write_registry()

    def _write_registry(self) -> None:
        (self.root / "repos.json").write_text(json.dumps(self.registry))

    def _skill(self, name: str) -> Path:
        source: Path = self.source_root / name
        source.mkdir()
        (source / "SKILL.md").write_text(f"name: {name}\n")
        return source

    def _sync(self, success: bool = True) -> subprocess.CompletedProcess[str]:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--root", str(self.root),
             "--registry-script", str(REGISTRY_SCRIPT)],
            env={**os.environ, "PROJECTS_ROOT": str(self.root / "projects")},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def test_rename_removes_old_link_even_when_old_target_still_exists(self) -> None:
        old: Path = self._skill("old")
        (self.skills / "old").symlink_to(old)
        (old / "SKILL.md").unlink()
        new: Path = self._skill("bkm-rum")
        self._sync()
        self.assertFalse((self.skills / "old").is_symlink())
        self.assertEqual((self.skills / "bkm-rum").resolve(), new.resolve())
        self._sync()

    def test_removes_broken_project_link_and_preserves_other_links(self) -> None:
        (self.skills / "old").symlink_to(self.source_root / "removed")
        external: Path = self.skills / "external"
        external.symlink_to(self.root / "other/missing")
        local: Path = self.skills / "local"
        local.mkdir()
        self._sync()
        self.assertFalse((self.skills / "old").is_symlink())
        self.assertTrue(external.is_symlink())
        self.assertTrue(local.is_dir())

    def test_state_removes_link_after_project_is_unregistered(self) -> None:
        self._skill("old")
        self._sync()
        self.registry.pop()
        self._write_registry()
        self._sync()
        self.assertFalse((self.skills / "old").is_symlink())

    def test_failure_does_not_remove_existing_links(self) -> None:
        stale: Path = self.skills / "old"
        stale.symlink_to(self.source_root / "missing")
        self.registry[1]["skills"] = [{"dir": "../escape"}]
        self._write_registry()
        self._sync(success=False)
        self.assertTrue(stale.is_symlink())

    def test_directory_conflict_is_detected_before_mutation(self) -> None:
        self._skill("a")
        self._skill("z")
        (self.skills / "z").mkdir()
        self._sync(success=False)
        self.assertFalse((self.skills / "a").is_symlink())

    def test_duplicate_names_are_rejected_before_mutation(self) -> None:
        self._skill("same")
        another: Path = self.root / "projects/demo/other/same"
        another.mkdir(parents=True)
        (another / "SKILL.md").write_text("test")
        self.registry[1]["skills"].append({"dir": "other"})
        self._write_registry()
        self._sync(success=False)
        self.assertFalse((self.skills / "same").is_symlink())

    def test_mount_removes_retired_names_and_keeps_unrelated_links(self) -> None:
        (self.skills / "local-new").mkdir()
        for target in [".claude", ".codebuddy", ".cursor"]:
            folder: Path = self.root / target / "skills"
            folder.mkdir(parents=True)
            (folder / "old").symlink_to("../../.agents/skills/old")
            (folder / "external").symlink_to(self.root / "other/missing")
        result = subprocess.run(
            ["make", "-f", str(ROOT / "Makefile"), "skills-mount"],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for target in [".claude", ".codebuddy", ".cursor"]:
            folder = self.root / target / "skills"
            self.assertFalse((folder / "old").is_symlink())
            self.assertTrue((folder / "external").is_symlink())
            self.assertEqual((folder / "local-new").is_symlink(), target != ".cursor")


if __name__ == "__main__":
    unittest.main()

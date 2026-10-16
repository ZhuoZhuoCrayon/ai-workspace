from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

PROJECT_MGR_ROOT: Path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_MGR_ROOT))

from scripts.registry import (  # noqa: E402
    RegistryError,
    load,
    normalize_git_url,
    skill_paths,
    sync,
)


class RegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace_root: Path = Path(self.temporary_directory.name)
        self.projects_root: Path = self.workspace_root / "projects"
        self.projects_root.mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write(self, relative: str, payload: Any) -> None:
        path: Path = self.workspace_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n", encoding="utf-8"
        )

    def _public(self, projects: list[dict[str, Any]] | None = None) -> None:
        payload: list[dict[str, Any]] = projects or [
            {
                "name": "ai-workspace",
                "git_url": "https://github.com/example/ai-workspace.git",
                "self": True,
                "language": "zh",
            }
        ]
        self._write("repos.json", payload)


class ResolveTest(RegistryTestCase):
    def test_joins_relative_path_with_projects_root(self) -> None:
        self._public(
            [
                {"name": "ai-workspace", "self": True, "language": "zh"},
                {
                    "name": "demo",
                    "git_url": "https://github.com/example/demo.git",
                    "local_path": "github/example/demo",
                    "subdir": "pkg",
                    "language": "en",
                },
            ]
        )
        with unittest.mock.patch.dict(
            "os.environ", {"PROJECTS_ROOT": str(self.projects_root)}
        ):
            entry = next(item for item in load(self.workspace_root) if item.name == "demo")

        self.assertEqual(entry.clone_dir(), self.projects_root / "github/example/demo")
        self.assertEqual(entry.project_dir(), entry.clone_dir() / "pkg")
        self.assertEqual(entry.language, "en")

    def test_override_precedes_environment(self) -> None:
        override: Path = self.workspace_root / "override"
        self._public(
            [
                {"name": "ai-workspace", "self": True},
                {
                    "name": "demo",
                    "git_url": "https://github.com/example/demo.git",
                    "local_path": "github/example/demo",
                },
            ]
        )
        self._write("repos.local.json", {"projects": {"demo": str(override)}})
        with unittest.mock.patch.dict(
            "os.environ", {"PROJECTS_ROOT": str(self.projects_root)}
        ):
            entry = next(item for item in load(self.workspace_root) if item.name == "demo")

        self.assertEqual(entry.clone_dir(), override)

    def test_self_entry_returns_workspace_root(self) -> None:
        self._public()
        entry = next(item for item in load(self.workspace_root) if item.self_entry)
        self.assertEqual(entry.project_dir(), self.workspace_root.resolve())

    def test_keeps_public_and_private_entries_with_the_same_name(self) -> None:
        self._public(
            [
                {"name": "ai-workspace", "self": True},
                {
                    "name": "shared",
                    "git_url": "https://github.com/example/shared.git",
                    "local_path": "github/example/shared",
                },
            ]
        )
        self._write(
            "private/repos.json",
            [
                {
                    "name": "shared",
                    "git_url": "https://git.example.com/internal/shared.git",
                    "local_path": "git.example.com/internal/shared",
                }
            ],
        )
        keys: set[str] = {entry.key for entry in load(self.workspace_root)}
        self.assertEqual(keys, {"ai-workspace", "shared", "private/shared"})

    def test_rejects_absolute_local_path(self) -> None:
        self._public(
            [
                {"name": "ai-workspace", "self": True},
                {"name": "demo", "git_url": "https://example.com/demo.git", "local_path": "/tmp/demo"},
            ]
        )
        with self.assertRaisesRegex(RegistryError, "relative"):
            load(self.workspace_root)

    def test_rejects_clone_directory_conflict(self) -> None:
        self._public(
            [
                {"name": "ai-workspace", "self": True},
                {"name": "one", "git_url": "https://github.com/a/one.git", "local_path": "same"},
                {"name": "two", "git_url": "git@github.com:b/two.git", "local_path": "same"},
            ]
        )
        with self.assertRaisesRegex(RegistryError, "conflict"):
            load(self.workspace_root)

    def test_loads_optional_private_git_identity(self) -> None:
        self._public([{"name": "ai-workspace", "self": True}])
        self._write(
            "private/repos.json",
            [
                {
                    "name": "shared",
                    "git_url": "https://git.example.com/internal/shared.git",
                    "local_path": "git.example.com/internal/shared",
                    "user_name": "sandrincai",
                    "user_email": "sandrincai@tencent.com",
                },
                {
                    "name": "plain",
                    "git_url": "https://git.example.com/internal/plain.git",
                    "local_path": "git.example.com/internal/plain",
                },
            ],
        )
        entries: dict[str, Any] = {entry.key: entry for entry in load(self.workspace_root)}
        self.assertEqual(entries["private/shared"].user_name, "sandrincai")
        self.assertEqual(entries["private/shared"].user_email, "sandrincai@tencent.com")
        self.assertEqual(entries["private/plain"].user_name, "")
        self.assertEqual(entries["private/plain"].user_email, "")

    def test_rejects_public_git_identity(self) -> None:
        self._public(
            [
                {"name": "ai-workspace", "self": True},
                {
                    "name": "demo",
                    "git_url": "https://github.com/example/demo.git",
                    "local_path": "github/example/demo",
                    "user_name": "demo",
                    "user_email": "demo@example.com",
                },
            ]
        )
        with self.assertRaisesRegex(RegistryError, "private registry"):
            load(self.workspace_root)

    def test_rejects_incomplete_or_invalid_git_identity(self) -> None:
        self._public([{"name": "ai-workspace", "self": True}])
        self._write(
            "private/repos.json",
            [
                {
                    "name": "shared",
                    "git_url": "https://git.example.com/internal/shared.git",
                    "local_path": "git.example.com/internal/shared",
                    "user_name": "sandrincai",
                }
            ],
        )
        with self.assertRaisesRegex(RegistryError, "together"):
            load(self.workspace_root)

        self._write(
            "private/repos.json",
            [
                {
                    "name": "shared",
                    "git_url": "https://git.example.com/internal/shared.git",
                    "local_path": "git.example.com/internal/shared",
                    "user_name": "sandrincai",
                    "user_email": "not-an-email",
                }
            ],
        )
        with self.assertRaisesRegex(RegistryError, "user_email"):
            load(self.workspace_root)

    def test_accepts_equivalent_git_urls(self) -> None:
        self.assertEqual(
            normalize_git_url("https://GitHub.com/Example/Demo.git"),
            normalize_git_url("git@github.com:example/demo"),
        )


class SkillsTest(RegistryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.skills_root: Path = self.projects_root / "demo" / "skills"
        self.skills_root.mkdir(parents=True)

    def _create_skill(self, name: str) -> Path:
        skill_path: Path = self.skills_root / name
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("test", encoding="utf-8")
        return skill_path.resolve()

    def _registry(self, source: dict[str, Any]) -> None:
        self._public(
            [
                {"name": "ai-workspace", "self": True},
                {
                    "name": "demo",
                    "git_url": "https://github.com/example/demo.git",
                    "local_path": "demo",
                    "skills": [source],
                },
            ]
        )

    def test_scans_all_skills_when_names_are_omitted(self) -> None:
        rum_search: Path = self._create_skill("rum-search")
        kube_switch: Path = self._create_skill("kube-switch")
        self._registry({"dir": "skills"})
        with unittest.mock.patch.dict(
            "os.environ", {"PROJECTS_ROOT": str(self.projects_root)}
        ):
            self.assertEqual(
                [kube_switch, rum_search], skill_paths(load(self.workspace_root))
            )

    def test_selects_only_configured_skills(self) -> None:
        self._create_skill("rum-search")
        kube_switch: Path = self._create_skill("kube-switch")
        self._registry({"dir": "skills", "skills": ["kube-switch"]})
        with unittest.mock.patch.dict(
            "os.environ", {"PROJECTS_ROOT": str(self.projects_root)}
        ):
            self.assertEqual([kube_switch], skill_paths(load(self.workspace_root)))

    def test_skips_missing_skill_directory(self) -> None:
        kept: Path = self._create_skill("kept")
        self._registry({"dir": "skills", "skills": ["kept", "missing"]})
        with unittest.mock.patch.dict(
            "os.environ", {"PROJECTS_ROOT": str(self.projects_root)}
        ):
            self.assertEqual([kept], skill_paths(load(self.workspace_root)))


class SyncTest(RegistryTestCase):
    def _bare(self, name: str) -> str:
        source: Path = self.workspace_root / f"{name}-src"
        source.mkdir()
        subprocess.run(["git", "init", "-b", "master", str(source)], check=True, capture_output=True)
        (source / "README.md").write_text(name, encoding="utf-8")
        subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(source), "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-m", "init"],
            check=True,
            capture_output=True,
        )
        bare: Path = self.workspace_root / f"{name}.git"
        subprocess.run(["git", "clone", "--bare", str(source), str(bare)], check=True, capture_output=True)
        return str(bare)

    def test_clones_missing_and_keeps_existing(self) -> None:
        first: str = self._bare("one")
        second: str = self._bare("two")
        existing: Path = self.projects_root / "two"
        existing.mkdir()
        (existing / "keep.txt").write_text("kept", encoding="utf-8")
        self._public(
            [
                {"name": "ai-workspace", "self": True},
                {"name": "one", "git_url": first, "branch": "master", "local_path": "one"},
                {"name": "two", "git_url": second, "local_path": "two"},
                {"name": "empty", "local_path": "empty"},
            ]
        )
        with unittest.mock.patch.dict(
            "os.environ", {"PROJECTS_ROOT": str(self.projects_root)}
        ):
            rows: dict[str, str] = {key: state for key, state, _detail in sync(self.workspace_root)}

        self.assertEqual(rows["private-repo"], "skipped")
        self.assertEqual(rows["one"], "cloned")
        self.assertEqual(rows["two"], "present")
        self.assertEqual(rows["empty"], "skipped")
        self.assertEqual((existing / "keep.txt").read_text(encoding="utf-8"), "kept")
        self.assertTrue((self.projects_root / "one" / ".git").exists())

    def test_failed_clone_does_not_stop_later_targets(self) -> None:
        valid: str = self._bare("valid")
        self._public(
            [
                {"name": "ai-workspace", "self": True},
                {
                    "name": "broken",
                    "git_url": str(self.workspace_root / "missing.git"),
                    "local_path": "broken",
                },
                {"name": "valid", "git_url": valid, "branch": "master", "local_path": "valid"},
            ]
        )
        with unittest.mock.patch.dict(
            "os.environ", {"PROJECTS_ROOT": str(self.projects_root)}
        ):
            rows: dict[str, str] = {key: state for key, state, _detail in sync(self.workspace_root)}

        self.assertEqual(rows["broken"], "failed")
        self.assertEqual(rows["valid"], "cloned")


if __name__ == "__main__":
    unittest.main()

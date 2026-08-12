from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

PROJECT_MGR_ROOT: Path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_MGR_ROOT))

from scripts.list_skills import ProjectSkillsError, list_skill_paths


class ListSkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace_root: Path = Path(self.temporary_directory.name)
        self.project_root: Path = self.workspace_root / "project"
        self.skills_root: Path = self.project_root / "apm-rum" / "skills"
        self.skills_root.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _create_skill(self, name: str) -> Path:
        skill_path: Path = self.skills_root / name
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("test", encoding="utf-8")
        return skill_path.resolve()

    def _write_registry(
        self, source_config: dict[str, Any], private: bool = False
    ) -> None:
        payload: list[dict[str, Any]] = [
            {
                "name": "ai-docs",
                "local_path": str(self.project_root),
                "skills": [source_config],
            }
        ]
        registry_path: Path = self.workspace_root / "repos.json"
        if private:
            registry_path = self.workspace_root / "private" / "repos.json"
            registry_path.parent.mkdir()
        registry_path.write_text(
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n", encoding="utf-8"
        )

    def test_scans_all_skills_when_names_are_omitted(self) -> None:
        rum_search: Path = self._create_skill("rum-search")
        kube_switch: Path = self._create_skill("kube-switch")
        self._write_registry({"dir": "apm-rum/skills"})

        self.assertEqual(
            [kube_switch, rum_search], list_skill_paths(self.workspace_root)
        )

    def test_selects_only_configured_skills(self) -> None:
        self._create_skill("rum-search")
        kube_switch: Path = self._create_skill("kube-switch")
        self._write_registry(
            {"dir": "apm-rum/skills", "skills": ["kube-switch"]}
        )

        self.assertEqual([kube_switch], list_skill_paths(self.workspace_root))

    def test_reads_private_registry(self) -> None:
        rum_search: Path = self._create_skill("rum-search")
        self._write_registry({"dir": "apm-rum/skills"}, private=True)

        self.assertEqual([rum_search], list_skill_paths(self.workspace_root))

    def test_rejects_a_source_outside_project_root(self) -> None:
        self._write_registry({"dir": "../outside"})

        with self.assertRaisesRegex(ProjectSkillsError, "inside project local_path"):
            list_skill_paths(self.workspace_root)


if __name__ == "__main__":
    unittest.main()

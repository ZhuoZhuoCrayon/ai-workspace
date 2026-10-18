from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT: Path = Path(__file__).resolve().parents[1] / "normalize_skill_sources.py"


class NormalizeSkillSourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root: Path = Path(self.temporary.name)
        self.lock: Path = self.root / "skills-lock.json"

    def _run(self, skills: dict) -> subprocess.CompletedProcess[str]:
        self.lock.write_text(json.dumps({"version": 1, "skills": skills}))
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root)],
            capture_output=True, text=True,
        )

    def test_legacy_github_source_becomes_cloneable_and_is_idempotent(self) -> None:
        result = self._run({"demo": {
            "sourceType": "github", "source": "owner/repo", "ref": "release/v1",
            "computedHash": "original", "skillPath": "skills/demo/SKILL.md",
        }})
        self.assertEqual(result.returncode, 0, result.stderr)
        skill: dict = json.loads(self.lock.read_text())["skills"]["demo"]
        self.assertEqual(skill["sourceUrl"], "https://github.com/owner/repo.git")
        self.assertEqual(skill["ref"], "release/v1")
        self.assertEqual(skill["computedHash"], "original")
        before: bytes = self.lock.read_bytes()
        subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root)], check=True)
        self.assertEqual(self.lock.read_bytes(), before)

    def test_explicit_source_and_other_hosts_keep_their_values(self) -> None:
        skills: dict = {
            "explicit": {"sourceType": "github", "source": "owner/repo", "sourceUrl": "https://github.example/team/repo.git"},
            "internal": {"sourceType": "git", "source": "https://git.example.org/team/repo.git"},
        }
        result = self._run(skills)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.lock.read_text())["skills"], skills)

    def test_invalid_source_fails_before_writing_any_change(self) -> None:
        skills: dict = {
            "valid": {"sourceType": "github", "source": "owner/repo"},
            "invalid": {"sourceType": "github", "source": "../escape/repo"},
        }
        result = self._run(skills)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(self.lock.read_text())["skills"], skills)

    def test_invalid_entry_does_not_replace_the_lock(self) -> None:
        result = self._run({"invalid": []})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(self.lock.read_text())["skills"], {"invalid": []})


if __name__ == "__main__":
    unittest.main()

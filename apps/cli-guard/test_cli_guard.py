"""Verify command interception, snapshots, CLI compatibility and repeatable setup."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import betterleaks
import guard
import scanner

ROOT: Path = Path(__file__).resolve().parent
TEST_CONFIG: str = """[scan.network]
blocked_domains = ["baidu.com"]
allowed_ip_networks = []

[commands.gongfeng]
mr = ["create", "update", "accept"]
issue = ["create", "update"]
review = ["approve", "reject", "commit-create", "commit-update", "commit-approve", "commit-reject"]
note = ["issue-create", "issue-update", "mr-create", "mr-update", "review-create", "review-update"]
commit = ["create-comment"]
"""


def copy_runtime(destination: Path) -> None:
    for path in ROOT.glob("*.py"):
        if not path.name.startswith("test_"):
            shutil.copy2(path, destination / path.name)
    for name in ["betterleaks.lock", "config.toml"]:
        shutil.copy2(ROOT / name, destination / name)
    shutil.copytree(
        ROOT / "adapters",
        destination / "adapters",
        ignore=shutil.ignore_patterns("__pycache__"),
    )


class ConfigTests(unittest.TestCase):
    def test_tables_merge_and_same_key_values_replace_defaults(self) -> None:
        defaults: dict = guard.load_config()
        with tempfile.TemporaryDirectory(prefix="cli-guard-config-") as directory:
            path: Path = Path(directory) / "config.toml"
            path.write_text(
                '[commands.gh]\npr = ["review"]\napi = false\n'
                '[scan.network]\nblocked_domains = ["baidu.com"]\nallowed_ip_networks = []\n'
                '[scan.secrets.patterns]\nexample = "test-value"\n'
                '[commands.gongfeng]\nreview = ["approve"]\n'
            )
            merged: dict = guard.load_config(path)
        self.assertEqual(merged["commands"]["gh"]["pr"], ["review"])
        self.assertFalse(merged["commands"]["gh"]["api"])
        self.assertEqual(merged["commands"]["gh"]["issue"], defaults["commands"]["gh"]["issue"])
        self.assertEqual(merged["scan"]["network"]["blocked_domains"], ["baidu.com"])
        self.assertEqual(merged["scan"]["network"]["allowed_ip_networks"], [])
        self.assertEqual(merged["commands"]["gongfeng"], {"review": ["approve"]})
        self.assertTrue(merged["scan"]["secrets"]["enabled"])
        patterns: dict = merged["scan"]["secrets"]["patterns"]
        self.assertEqual(patterns["example"], "test-value")
        self.assertLessEqual(defaults["scan"]["secrets"]["patterns"].items(), patterns.items())
        self.assertEqual(guard.load_config(), defaults)
        self.assertEqual(set(defaults["commands"]), {"gh"})


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        config: dict = guard.load_config()["scan"]
        config["network"].update(blocked_domains=["baidu.com"], allowed_ip_networks=[])
        self.policy = scanner.Policy.from_config(config)

    def test_sensitive_and_encoded_values(self) -> None:
        for value in [
            "baidu.com",
            "https://iam.baidu.com/path",
            "IAM.BAIDU.COM",
            "https%3A%2F%2Fiam%2Ebaidu%2Ecom",
            "iam&#46;baidu&#46;com",
            "127.0.0.1",
            "127.0.0.1.",
            "https://[::1]",
            "::1.",
            "::ffff:127.0.0.1",
            '{"body":"\\u0031' + '27.0.0.1"}',
            '{"comments":[{"body":"iam.baidu.com"}]}',
        ]:
            with self.subTest(value=value):
                self.assertIsNotNone(scanner.inspect([("body", value)], self.policy))

    def test_local_and_documentation_addresses(self) -> None:
        self.assertIsNone(
            scanner.inspect(
                [
                    (
                        "body",
                        (
                            "127.0.0.1 127.1.2.3 0.0.0.0 ::1 :: ::ffff:127.0.0.1 "
                            "192.0.2.1 198.51.100.1 203.0.113.1 2001:db8::1 "
                            "localhost github.com notbaidu.com"
                        ),
                    )
                ],
                scanner.Policy.from_config(guard.load_config()["scan"]),
            )
        )

    def test_batch_inspection_keeps_field_locations_and_runs_engine_once(self) -> None:
        values: list[tuple[str, str]] = [("title", "Heading"), ("body", "intro\ncandidate")]
        with patch.object(betterleaks, "check", return_value=(3, "github-pat")) as engine:
            self.assertEqual(
                scanner.inspect(values, self.policy), scanner.Finding("body", 2, "github-pat")
            )
            engine.assert_called_once_with("Heading\nintro\ncandidate", self.policy.patterns)


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cli-guard-test-")
        self.directory: Path = Path(self.temp.name)
        self.record: Path = self.directory / "published.json"
        self.wrapper: Path = ROOT / "guard.py"
        self.config: Path = self.directory / "override.toml"
        self.config.write_text(TEST_CONFIG)
        self.fake: Path = self.directory / "gh-real"
        self.fake.write_text(
            "#!" + sys.executable + "\n"
            "import json,sys\nfrom pathlib import Path\n"
            "args=sys.argv[1:]; files={}\n"
            "for index,arg in enumerate(args):\n"
            " if arg in ['--body-file','-F','--input'] and index+1<len(args):\n"
            "  value=args[index+1]\n"
            "  if arg=='-F' and '=@' in value: value=value.split('=@',1)[1]\n"
            "  if Path(value).is_file(): files[value]=Path(value).read_text()\n"
            f"Path({str(self.record)!r}).write_text(json.dumps({{'args':args,'files':files}}))\n"
            "sys.exit(7)\n"
        )
        self.fake.chmod(0o755)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def invoke(
        self, args: list[str], stdin: str = "", tool: str = "gh"
    ) -> subprocess.CompletedProcess:
        self.record.unlink(missing_ok=True)
        return subprocess.run(
            [
                sys.executable,
                str(self.wrapper),
                "--config",
                str(self.config),
                tool,
                str(self.fake),
                *args,
            ],
            input=stdin,
            text=True,
            capture_output=True,
        )

    def test_config_controls_scope_and_rules(self) -> None:
        self.config.write_text(
            TEST_CONFIG.replace('blocked_domains = ["baidu.com"]', "blocked_domains = []")
        )
        self.assertEqual(self.invoke(["pr", "review", "1", "-c", "-b", "baidu.com"]).returncode, 7)
        self.config.write_text(TEST_CONFIG + '\n[commands.gh]\npr = ["edit"]\n')
        self.assertEqual(self.invoke(["pr", "review", "1", "-c", "-b", "baidu.com"]).returncode, 7)
        self.assertEqual(self.invoke(["pr", "edit", "1", "-b", "baidu.com"]).returncode, 1)
        self.config.write_text(TEST_CONFIG + "\n[commands.gh]\napi = false\n")
        self.assertEqual(
            self.invoke(["api", "repos/a/b/pulls/1/reviews", "-f", "body=baidu.com"]).returncode, 7
        )
        self.config.write_text(TEST_CONFIG + "\n[scan.secrets]\nenabled = false\n")
        token: str = "ghp_" + "aB3xY8mQ2pL7kR4sU9vW6zN1cD5eF0gH8jK2"
        self.assertEqual(self.invoke(["pr", "review", "1", "-c", "-b", token]).returncode, 7)
        self.assertEqual(self.invoke(["pr", "review", "1", "-c", "-b", "baidu.com"]).returncode, 1)
        for invalid in [TEST_CONFIG + "\nblock_ipss = true\n", "invalid toml ["]:
            self.config.write_text(invalid)
            self.assertEqual(self.invoke(["pr", "review", "1", "-c", "-b", "safe"]).returncode, 2)
            self.assertFalse(self.record.exists())
            self.assertEqual(self.invoke(["pr", "view", "1"]).returncode, 7)
        self.config.unlink()
        self.assertEqual(self.invoke(["pr", "review", "1", "-abSafe"]).returncode, 2)
        self.assertEqual(self.invoke(["pr", "view", "1"]).returncode, 7)

    def test_default_loopback_exemption_can_be_overridden(self) -> None:
        self.config.write_text('[scan.network]\nblocked_domains = ["baidu.com"]\n')
        args: list[str] = ["pr", "review", "1", "-ab127.0.0.1"]
        self.assertEqual(self.invoke(args).returncode, 7)
        self.config.write_text(TEST_CONFIG)
        self.assertEqual(self.invoke(args).returncode, 1)
        self.config.write_text(TEST_CONFIG.replace("allowed_ip_networks = []", "block_ips = false"))
        self.assertEqual(self.invoke(args).returncode, 7)

    def test_credentials_and_extra_patterns_block_publication(self) -> None:
        token: str = "ghp_" + "aB3xY8mQ2pL7kR4sU9vW6zN1cD5eF0gH8jK2"
        password: str = "q7R9s2" + "!vX4z"
        private: str = (
            "-----BEGIN "
            + "PRIVATE KEY-----\n"
            + "QWJjMTIz" * 20
            + "\n-----END "
            + "PRIVATE KEY-----"
        )
        values: list[tuple[str, str]] = [
            (token, "github-pat"),
            ('password="' + password + '"', "generic-password"),
            (private, "private-key"),
            ("postgres://app:" + password + "@db.example.org/data", "connection-password"),
            ("redis://:" + password + "@cache.example.org", "connection-password"),
            ("Server=db.example.org;Database=demo;UID=app;PWD=" + password + ";", "dsn-password"),
            ("登录密码是 " + password + "，请使用它。", "chinese-password"),
            ("**密码**：`" + password + "`", "chinese-password"),
            ("口令设置为 “" + password + "”", "chinese-password"),
            ("".join("&#%d;" % ord(char) for char in token), "github-pat"),
            ("".join(chr(ord(char) + 0xFEE0) for char in token), "github-pat"),
        ]
        for content, rule in values:
            with self.subTest(rule=rule):
                result = self.invoke(["pr", "review", "1", "--comment", "--body", content])
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("Rule: " + rule, result.stderr)
                self.assertFalse(self.record.exists())
                self.assertNotIn(password, result.stderr)
                self.assertNotIn(token, result.stderr)
                self.assertTrue(result.stderr.isascii())
        for args, content in [
            (["pr", "review", "1", "--comment", "--body-file", "-"], token),
            (
                ["api", "repos/a/b/pulls/1/reviews", "--input", "-"],
                json.dumps({"comments": [{"body": token}]}),
            ),
            (["api", "graphql", "-f", "query=mutation {x}", "-f", "body=" + token], ""),
        ]:
            self.assertEqual(self.invoke(args, content).returncode, 1)
            self.assertFalse(self.record.exists())

    def test_missing_engine_blocks_writes_but_preserves_reads(self) -> None:
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.directory / "no-engine")}):
            result = self.invoke(["pr", "review", "1", "--comment", "--body", "Routine review"])
            self.assertEqual(result.returncode, 2)
            self.assertIn("Betterleaks is unavailable", result.stderr)
            self.assertIn("install.sh", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(self.record.exists())
            self.assertEqual(self.invoke(["pr", "view", "1"]).returncode, 7)

    def test_password_prose_and_environment_references_are_allowed(self) -> None:
        for content in [
            "修改密码检查逻辑，密码不能为空。",
            'password = os.environ["DB_PASSWORD"]',
            "postgres://db.example.org/data",
            "口令校验失败时显示提示。",
            "postgres://app:${DB_PASSWORD}@db.example.org/data",
            "Server=db.example.org;UID=app;PWD=${DB_PASSWORD};",
        ]:
            result = self.invoke(["pr", "review", "1", "--comment", "--body", content])
            self.assertEqual(result.returncode, 7, result.stderr)

    def test_blocked_commands_never_reach_publisher(self) -> None:
        cases: list[list[str]] = [
            ["pr", "create", "--title", "127.0.0.1", "--body", "safe"],
            ["pr", "edit", "1", "--body=iam.baidu.com"],
            ["-R", "owner/repo", "pr", "review", "1", "-a", "-b127.0.0.1"],
            ["pr", "review", "1", "-c", "-b", "iam.baidu.com"],
            ["pr", "review", "1", "--comment", "--body", "127.0.0.1"],
            ["pr", "comment", "1", "--edit-last", "--body", "127.0.0.1"],
            ["pr", "close", "1", "--comment", "127.0.0.1"],
            ["issue", "comment", "1", "-b", "127.0.0.1"],
            ["api", "repos/a/b/pulls/1/reviews", "-f", "body=iam.baidu.com"],
            ["api", "-X", "PATCH", "repos/a/b/pulls/comments/1", "-fbody=127.0.0.1"],
            ["api", "-XPOST", "repos/a/b/issues/1/comments?body=127.0.0.1"],
            ["api", "graphql", "-f", 'query=mutation { x(body:"iam.baidu.com") }'],
            [
                "api",
                "graphql",
                "-f",
                "query=mutation X($body:String!){x}",
                "-f",
                "body=127.0.0.1",
            ],
            ["pr", "create", "-t", "safe", "-b", "127.0.0.1", "--label", "--help"],
            ["pr", "review", "-a", "--body", "--help", "--body", "127.0.0.1"],
        ]
        for args in cases:
            with self.subTest(args=args):
                result = self.invoke(args)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(self.record.exists())
                self.assertNotIn("127.0.0.1", result.stderr)
                self.assertNotIn("iam.baidu.com", result.stderr)

    def test_body_and_api_stdin_are_checked(self) -> None:
        for args, stdin in [
            (["pr", "review", "1", "-c", "-F", "-"], "127.0.0.1"),
            (
                ["api", "repos/a/b/pulls/1/reviews", "--input", "-"],
                '{"comments":[{"body":"iam.baidu.com"}]}',
            ),
            (["api", "repos/a/b/issues/1/comments", "-F", "body=@-"], "127.0.0.1"),
            (
                ["api", "graphql", "--input", "-"],
                '{"query":"m\\u0075tation {x}","variables":{"body":"127.0.0.1"}}',
            ),
        ]:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(args, stdin).returncode, 1)
                self.assertFalse(self.record.exists())

    def test_failures_are_actionable_english_on_stderr(self) -> None:
        result = self.invoke(["pr", "review", "1", "-c", "-b", "safe line\n127.0.0.1"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("BLOCKED [sensitive_content]", result.stderr)
        self.assertIn("Location: body:2", result.stderr)
        self.assertIn("Rule: ip_address", result.stderr)
        self.assertIn("Action: Redact", result.stderr)
        self.assertIn("Original gh was not executed.", result.stderr)
        self.assertNotIn("127.0.0.1", result.stderr)
        self.assertTrue(result.stderr.isascii())
        self.assertFalse(self.record.exists())

        result = self.invoke(["pr", "review", "1", "-c", "-F", str(self.directory / "missing")])
        self.assertEqual(result.returncode, 2)
        self.assertIn("ERROR [check_failed]", result.stderr)
        self.assertIn("Reason: FileNotFoundError", result.stderr)
        self.assertIn("Action: Check", result.stderr)
        self.assertIn("Original gh was not executed.", result.stderr)
        self.assertTrue(result.stderr.isascii())
        self.assertFalse(self.record.exists())

        result = self.invoke(["pr", "create", "--fill"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("BLOCKED [uninspectable_content]", result.stderr)
        self.assertIn("Action:", result.stderr)
        self.assertTrue(result.stderr.isascii())
        self.assertFalse(self.record.exists())

    def test_group_flags_and_false_help_cannot_bypass_scan(self) -> None:
        for args in [
            ["pr", "-R", "owner/repo", "review", "1", "--comment", "--body", "127.0.0.1"],
            ["pr", "--repo=owner/repo", "edit", "1", "--body", "iam.baidu.com"],
            ["pr", "review", "1", "--help=false", "--comment", "--body", "127.0.0.1"],
            ["pr", "review", "1", "--approve=false"],
            ["pr", "review", "1", "-a=false"],
            ["pr", "comment", "1", "--delete-last=false"],
        ]:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(args).returncode, 1)
                self.assertFalse(self.record.exists())

    def test_native_content_flags_before_subcommands_are_also_inspected(self) -> None:
        for args, stdin in [
            (["pr", "--body", "baidu.com", "review", "1", "--comment"], ""),
            (["--title", "baidu.com", "pr", "create", "--body", "safe"], ""),
            (["-f", "body=baidu.com", "api", "repos/a/b/issues/1/comments"], ""),
            (["--input", "-", "api", "graphql"], '{"query":"mutation {x}","body":"baidu.com"}'),
        ]:
            result = self.invoke(args, stdin)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(self.record.exists())
        args = ["pr", "--body", "LGTM", "review", "1", "--comment"]
        self.assertEqual(self.invoke(args).returncode, 7)
        self.assertEqual(json.loads(self.record.read_text())["args"], args)
        args = ["mr", "--description", "baidu.com", "create", "--title", "Fix"]
        self.assertEqual(self.invoke(args, tool="gongfeng").returncode, 1)
        self.assertFalse(self.record.exists())

    def test_combined_short_options_cannot_hide_content_or_editing(self) -> None:
        for args in [
            ["pr", "review", "1", "--approve", "-abbaidu.com"],
            ["pr", "review", "1", "-cb127.0.0.1"],
            ["pr", "review", "1", "-ab=baidu.com"],
            ["pr", "review", "1", "-ah=false", "-bbaidu.com"],
            ["-abbaidu.com", "pr", "review", "1"],
            ["pr", "create", "-t", "Safe", "-b", "Safe", "-wbbaidu.com"],
        ]:
            with self.subTest(args=args):
                result = self.invoke(args)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(self.record.exists())
        for args in [
            ["pr", "review", "1", "-abLGTM"],
            ["pr", "review", "1", "-ab", "--web"],
            ["pr", "review", "1", "-abLGTM", "--", "-web"],
        ]:
            with self.subTest(args=args):
                result = self.invoke(args)
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(json.loads(self.record.read_text())["args"], args)
        source: Path = self.directory / "review.txt"
        source.write_text("baidu.com")
        self.assertEqual(self.invoke(["pr", "review", "1", "-aF", str(source)]).returncode, 1)
        self.assertFalse(self.record.exists())
        source.write_text("LGTM\n")
        result = self.invoke(["pr", "review", "1", "-aF", str(source)])
        self.assertEqual(result.returncode, 7, result.stderr)
        published: dict = json.loads(self.record.read_text())
        self.assertEqual(published["args"][:5], ["pr", "review", "1", "-a", "-F"])
        self.assertEqual(list(published["files"].values()), ["LGTM\n"])
        self.assertNotEqual(published["args"][-1], str(source))
        self.assertFalse(Path(published["args"][-1]).exists())

    def test_files_are_checked_and_safe_bytes_are_frozen(self) -> None:
        source: Path = self.directory / "review draft.md"
        source.write_text("127.0.0.1")
        self.assertEqual(self.invoke(["pr", "review", "1", "-c", "-F", str(source)]).returncode, 1)
        self.assertFalse(self.record.exists())
        content: str = "LGTM\n\n```text\nlocalhost\n```\n"
        source.write_text(content)
        result = self.invoke(["pr", "review", "1", "-c", "-F", str(source)])
        self.assertEqual(result.returncode, 7, result.stderr)
        published: dict = json.loads(self.record.read_text())
        self.assertEqual(list(published["files"].values()), [content])
        frozen: Path = Path(published["args"][-1])
        self.assertNotEqual(frozen, source)
        self.assertFalse(frozen.exists())
        self.assertEqual(source.read_text(), content)

    def test_api_file_field_is_snapshotted(self) -> None:
        source: Path = self.directory / "body.txt"
        source.write_text("LGTM\n")
        result = self.invoke(["api", "repos/a/b/pulls/1/reviews", "-F", "body=@" + str(source)])
        self.assertEqual(result.returncode, 7)
        self.assertEqual(list(json.loads(self.record.read_text())["files"].values()), ["LGTM\n"])

    def test_reads_metadata_and_clean_content_keep_exit_code(self) -> None:
        cases: list[list[str]] = [
            ["--version"],
            ["auth", "status"],
            ["pr", "view", "1"],
            ["pr", "diff", "1"],
            ["pr", "create", "--help"],
            ["pr", "review", "1", "--approve"],
            ["pr", "edit", "1", "--add-label", "bug"],
            ["pr", "edit", "1", "--remove-milestone"],
            ["pr", "-R", "owner/repo", "review", "1", "--comment", "--body", "LGTM"],
            ["pr", "review", "1", "--help=false", "--comment", "--body", "LGTM"],
            ["pr", "create", "-t", "Fix", "--body", "Use localhost"],
            ["pr", "review", "1", "--comment", "--body", "LGTM"],
            ["pr", "review", "1", "--request-changes", "--body", "Please fix"],
            ["api", "repos/a/b/pulls/1"],
            ["api", "-XGET", "search/issues", "-f", "q=iam.baidu.com"],
        ]
        for args in cases:
            with self.subTest(args=args):
                result = self.invoke(args)
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(json.loads(self.record.read_text())["args"], args)

    def test_read_commands_do_not_depend_on_scan_policy(self) -> None:
        with patch.object(guard, "ROOT", self.directory / "missing-policy"):
            self.assertEqual(guard.run("gh", str(self.fake), ["pr", "view", "1"]), 7)
            self.assertEqual(guard.run("gh", str(self.fake), ["api", "repos/a/b/pulls/1"]), 7)

    def test_unconfigured_adapter_and_groups_pass_through(self) -> None:
        args: list[str] = ["review", "approve", "1", "--message", "baidu.com"]
        self.config.write_text('[scan.network]\nblocked_domains = ["baidu.com"]\n')
        self.assertEqual(self.invoke(args, tool="gongfeng").returncode, 7)
        self.config.write_text(
            '[scan.network]\nblocked_domains = ["baidu.com"]\n'
            '[commands.gongfeng]\nreview = ["approve"]\n'
        )
        self.assertEqual(self.invoke(args, tool="gongfeng").returncode, 1)
        self.assertEqual(
            self.invoke(["mr", "create", "--title", "baidu.com"], tool="gongfeng").returncode, 7
        )

    def test_unresolved_content_and_read_errors_stop_publication(self) -> None:
        for args in [
            ["pr", "create", "--fill"],
            ["pr", "create", "--title", "safe"],
            ["pr", "edit", "1"],
            ["pr", "review", "1"],
            ["pr", "comment", "1", "--editor"],
            ["pr", "create", "-t", "safe", "-b", "safe", "--attach", "image.png"],
            ["pr", "review", "1", "-c", "-F", str(self.directory / "absent")],
        ]:
            with self.subTest(args=args):
                self.assertIn(self.invoke(args).returncode, {1, 2})
                self.assertFalse(self.record.exists())

    def test_gongfeng_content_flags_use_the_same_scanning_policy(self) -> None:
        cases: list[list[str]] = [
            ["--project-id", "123", "mr", "create", "--title", "Fix", "--description", "baidu.com"],
            ["mr", "--project-id", "123", "update", "1", "--description=127.0.0.1"],
            ["mr", "accept", "1", "--merge-commit-message", "baidu.com"],
            ["review", "approve", "1", "--message", "baidu.com"],
            ["note", "mr-create", "1", "--body", "baidu.com"],
            ["commit", "create-comment", "a1b2c3", "--note", "baidu.com"],
            ["issue", "create", "--title", "baidu.com"],
        ]
        for args in cases:
            with self.subTest(args=args):
                result = self.invoke(args, tool="gongfeng")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("Original gongfeng was not executed.", result.stderr)
                self.assertNotIn("baidu.com", result.stderr)
                self.assertFalse(self.record.exists())
        token: str = "ghp_" + "aB3xY8mQ2pL7kR4sU9vW6zN1cD5eF0gH8jK2"
        result = self.invoke(["note", "mr-create", "1", "--body", token], tool="gongfeng")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Rule: github-pat", result.stderr)

    def test_gongfeng_read_and_metadata_semantics_are_preserved(self) -> None:
        for args in [
            ["--help"],
            ["mr", "show", "1"],
            ["review", "mr-show", "1"],
            ["note", "mr-list", "1"],
            ["mr", "update", "1", "--assignee-id", "2"],
            ["mr", "create", "--help"],
            ["review", "approve", "1", "--message", "LGTM"],
        ]:
            result = self.invoke(args, tool="gongfeng")
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(json.loads(self.record.read_text())["args"], args)
        with patch.object(guard, "ROOT", self.directory / "missing-policy"):
            self.assertEqual(guard.run("gongfeng", str(self.fake), ["mr", "show", "1"]), 7)

    def test_new_adapter_reuses_the_guard_and_scanner_without_changes(self) -> None:
        copy_runtime(self.directory)
        self.wrapper = self.directory / "guard.py"
        module: Path = self.directory / "adapters" / "demo.py"
        module.write_text(
            "from adapters import Contents, Operation, arguments, command\n"
            'COMMANDS = {"publish": 1}\n'
            "def classify(args):\n"
            " route,start=command(args,COMMANDS,set())\n"
            ' if route!=("publish",): return None\n'
            ' return Operation(route,start,list(arguments(args,{"--text"},start)))\n'
            "def prepare(args,operation,contents):\n"
            " for item in operation.items:\n"
            '  if item.flag=="--text": contents.add("body",item.value)\n'
            " return args\n"
        )
        self.config.write_text(TEST_CONFIG + "\n[commands.demo]\npublish = true\n")
        self.assertEqual(self.invoke(["publish", "--text", "baidu.com"], tool="demo").returncode, 1)
        self.assertFalse(self.record.exists())
        self.assertEqual(self.invoke(["publish", "--text", "LGTM"], tool="demo").returncode, 7)


class EngineTests(unittest.TestCase):
    def test_project_settings_and_allow_comments_cannot_bypass_detection(self) -> None:
        token: str = "ghp_" + "aB3xY8mQ2pL7kR4sU9vW6zN1cD5eF0gH8jK2"
        with patch.dict(
            os.environ,
            {
                "BETTERLEAKS_CONFIG": "/missing",
                "GITLEAKS_CONFIG_TOML": "invalid",
                "BETTERLEAKS_VALIDATE": "true",
            },
        ):
            self.assertEqual(
                betterleaks.check(token + " # betterleaks:allow", {}), (1, "github-pat")
            )

    def test_invalid_reports_and_timeouts_fail_closed(self) -> None:
        for code, stdout in [
            (1, "raw sensitive stderr"),
            (0, "not-json"),
            (23, "[]"),
            (0, '[{"StartLine":1,"RuleID":"private-key"}]'),
            (23, '[{"StartLine":0,"RuleID":"private-key"}]'),
            (23, '[{"StartLine":1,"RuleID":"unsafe\\nvalue"}]'),
        ]:
            with (
                self.subTest(code=code, stdout=stdout),
                patch.object(
                    betterleaks.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [], code, stdout, "sensitive raw output"
                    ),
                ),
            ):
                with self.assertRaises(betterleaks.EngineError) as caught:
                    betterleaks.check("text", {})
                self.assertNotIn("sensitive", str(caught.exception))
        with (
            patch.object(
                betterleaks.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("betterleaks", 3),
            ),
            self.assertRaises(betterleaks.EngineError),
        ):
            betterleaks.check("text", {})
        with self.assertRaises(betterleaks.EngineError):
            betterleaks.check("text", {"invalid-pattern": "["})


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cli-guard-install-")
        self.directory: Path = Path(self.temp.name)
        self.source: Path = self.directory / "source with ' quotes"
        self.source.mkdir()
        copy_runtime(self.source)
        for filename in ["install.sh"]:
            shutil.copy2(ROOT / filename, self.source / filename)
        self.home: Path = self.directory / "home with ' quotes"
        self.home.mkdir()
        self.tools: Path = self.directory / "tools with ' quotes"
        self.tools.mkdir()
        self.real: Path = self.tools / "gh"
        self.real.write_text("#!/bin/sh\nexit 7\n")
        self.real.chmod(0o755)
        self.data: Path = self.home / ".local/share"
        self.counter: Path = self.directory / "downloads"
        binary: bytes = b"#!/bin/sh\nexit 0\n"
        bundle: io.BytesIO = io.BytesIO()
        with tarfile.open(fileobj=bundle, mode="w:gz") as archive:
            member: tarfile.TarInfo = tarfile.TarInfo("betterleaks")
            member.size = len(binary)
            archive.addfile(member, io.BytesIO(binary))
        self.archive: Path = self.directory / "release.tar.gz"
        self.archive.write_bytes(bundle.getvalue())
        self.lock: str = "1.9.0\n" + "".join(
            target
            + " "
            + hashlib.sha256(bundle.getvalue()).hexdigest()
            + " "
            + hashlib.sha256(binary).hexdigest()
            + "\n"
            for target in ["darwin_arm64", "darwin_x64", "linux_arm64", "linux_x64"]
        )
        (self.source / "betterleaks.lock").write_text(self.lock)
        curl: Path = self.tools / "curl"
        curl.write_text(
            "#!"
            + sys.executable
            + "\nimport shutil,sys\nfrom pathlib import Path\n"
            + f"Path({str(self.counter)!r}).open('a').write('download\\n')\n"
            + f"shutil.copyfile({str(self.archive)!r},sys.argv[sys.argv.index('-o')+1])\n"
        )
        curl.chmod(0o755)
        self.env: dict[str, str] = dict(
            os.environ,
            HOME=str(self.home),
            XDG_DATA_HOME=str(self.data),
            PYTHON=sys.executable,
            PATH=str(self.tools) + os.pathsep + os.environ["PATH"],
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def invoke(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["sh", str(self.source / "install.sh"), *args],
            env=self.env,
            text=True,
            capture_output=True,
        )

    def test_reinstall_symlinks_and_remove(self) -> None:
        original: str = "# User configuration\nexport USER_SETTING=yes\n"
        (self.home / ".zshenv").write_text(original)
        old: str = "# >>> cli-guard >>>\n: old-entry\n# <<< cli-guard <<<\n"
        (self.home / ".zprofile").write_text(original + old)
        linked: Path = self.directory / "user-bashrc"
        linked.write_text(original)
        linked.chmod(0o600)
        (self.home / ".bashrc").symlink_to(linked)
        first = self.invoke()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(first.stdout.isascii())
        files: dict = {
            str(path): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.home.rglob("*")
            if path.is_file()
        }
        again = self.invoke()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(
            files,
            {
                str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.home.rglob("*")
                if path.is_file()
            },
        )
        self.assertEqual(self.counter.read_text(), "download\n")
        self.assertNotIn("old-entry", (self.home / ".zprofile").read_text())
        self.assertEqual((self.home / ".zprofile").read_text().count("# >>> cli-guard >>>"), 1)
        self.assertTrue((self.home / ".bashrc").is_symlink())
        self.assertEqual(linked.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.home / ".bash_profile").exists())
        launcher: Path = self.data / "cli_guard/bin/gh"
        for shell in ["sh", "bash", "zsh"]:
            if shutil.which(shell):
                result = subprocess.run(
                    [
                        shell,
                        "-c",
                        '. "$1"; . "$1"; command -v gh',
                        shell,
                        str(self.data / "cli_guard/env.sh"),
                    ],
                    env=self.env,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(launcher))
        self.assertEqual(subprocess.run([str(launcher), "--version"], env=self.env).returncode, 7)
        help_result = subprocess.run(
            [str(self.data / "cli_guard/bin/cli-guard"), "--help"],
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Usage: cli-guard", help_result.stdout)
        if shutil.which("zsh"):
            for mode in ["-lc", "-ic", "-c"]:
                result = subprocess.run(
                    ["zsh", mode, "command -v gh"], env=self.env, text=True, capture_output=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(launcher))
        launcher.chmod(0o644)
        engine: Path = betterleaks.executable(self.data)
        engine.chmod(0o644)
        self.assertEqual(self.invoke().returncode, 0)
        self.assertTrue(os.access(launcher, os.X_OK) and os.access(engine, os.X_OK))
        self.assertEqual(self.invoke("--remove").returncode, 0)
        self.assertEqual(self.invoke("--remove").returncode, 0)
        self.assertEqual((self.home / ".zshenv").read_text(), original)
        self.assertEqual(linked.read_text(), original)
        self.assertFalse(launcher.exists())

    def test_dry_run_has_no_downloads_or_persistent_writes(self) -> None:
        before: set[Path] = set(self.source.rglob("*"))
        result = self.invoke("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertFalse(self.counter.exists())
        self.assertEqual(set(self.source.rglob("*")), before)

    def test_install_uses_live_overrides_and_only_configured_adapters(self) -> None:
        native: Path = self.tools / "gongfeng"
        shutil.copy2(self.real, native)
        self.assertEqual(self.invoke().returncode, 0)
        self.assertFalse((self.data / "cli_guard/bin/gongfeng").exists())
        config: Path = self.directory / "config with ' quotes.toml"
        config.write_text(TEST_CONFIG + "\n[scan.secrets]\nenabled = false\n")
        result = self.invoke("--config", str(config))
        self.assertEqual(result.returncode, 0, result.stderr)
        for tool, args in [
            ("gh", ["pr", "review", "1", "-ab127.0.0.1"]),
            ("gongfeng", ["review", "approve", "1", "--message", "baidu.com"]),
        ]:
            launcher: Path = self.data / "cli_guard/bin" / tool
            result = subprocess.run([str(launcher), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("BLOCKED [sensitive_content]", result.stderr)
        dispatcher: Path = self.data / "cli_guard/bin/cli-guard"
        before: tuple[bytes, int] = (dispatcher.read_bytes(), dispatcher.stat().st_mtime_ns)
        self.assertEqual(self.invoke("--config", str(config)).returncode, 0)
        self.assertEqual(before, (dispatcher.read_bytes(), dispatcher.stat().st_mtime_ns))
        config.write_text("[commands.gh]\npr = []\n")
        result = subprocess.run(
            [str(self.data / "cli_guard/bin/gh"), "pr", "review", "1", "-abbaidu.com"]
        )
        self.assertEqual(result.returncode, 7)

    def test_invalid_override_stops_before_installation(self) -> None:
        config: Path = self.directory / "override.toml"
        for content in [
            None,
            "invalid [",
            "[unknown]\nenabled = true\n",
            "commands = []\n",
            "[commands]\ngh = []\n",
            "[commands.gh]\npr = false\n",
        ]:
            if content is not None:
                config.write_text(content)
            result = self.invoke("--config", str(config))
            self.assertEqual(result.returncode, 1)
            self.assertIn("Invalid configuration", result.stderr)
            self.assertEqual(list(self.home.iterdir()), [])
            self.assertFalse(self.counter.exists())

    def test_bad_checksum_and_corrupted_cache(self) -> None:
        (self.source / "betterleaks.lock").write_text(
            self.lock.replace(hashlib.sha256(self.archive.read_bytes()).hexdigest(), "0" * 64)
        )
        failed = self.invoke()
        self.assertEqual(failed.returncode, 1)
        self.assertIn("checksum mismatch", failed.stderr)
        self.assertFalse((self.data / "cli_guard/bin/gh").exists())
        (self.source / "betterleaks.lock").write_text(self.lock)
        self.assertEqual(self.invoke().returncode, 0)
        engine: Path = betterleaks.executable(self.data)
        engine.write_text("corrupted")
        self.assertEqual(self.invoke().returncode, 0)
        self.assertEqual(engine.read_bytes(), b"#!/bin/sh\nexit 0\n")

    def test_unmanaged_launcher_and_unclosed_block_are_preserved(self) -> None:
        launcher: Path = self.data / "cli_guard/bin/gh"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\n# User gh\n")
        self.assertEqual(self.invoke().returncode, 1)
        self.assertIn("unmanaged gh", self.invoke().stderr)
        self.assertEqual(launcher.read_text(), "#!/bin/sh\n# User gh\n")
        launcher.unlink()
        malformed: str = "# >>> cli-guard >>>\n# Keep this user content\n"
        (self.home / ".zshenv").write_text(malformed)
        self.assertEqual(self.invoke().returncode, 1)
        self.assertEqual((self.home / ".zshenv").read_text(), malformed)


if __name__ == "__main__":
    unittest.main()

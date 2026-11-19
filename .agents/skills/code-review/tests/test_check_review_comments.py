import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

CODE_REVIEW_ROOT: Path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_REVIEW_ROOT))

from scripts.check_review_comments import check_comment, main  # noqa: E402

GOOD_COMMENT = """**`pkg/timing/view.py:40`** [P1]
> return (self.stable_end() or load_end) - start

问题：旧分支的总耗时取 loading_time，这里改成导航结束时间，同一个 View 会出现两种口径。

建议：保持既有字段含义：

~~~python
total = loading_time if loading_time is not None else layout.navigation_end()
~~~
"""

PROSE_ONLY_COMMENT = """**`pkg/timing/view.py:40`** [P1]
> return (self.stable_end() or load_end) - start

问题：旧分支的总耗时取 loading_time，这里改成导航结束时间，同一个 View 会出现两种口径。

建议：保持既有字段含义，导航结束时间只用来画阶段。
"""


class CheckReviewCommentsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root: Path = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write(self, name: str, content: str) -> Path:
        path: Path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def _errors(self, content: str) -> list[str]:
        return check_comment(self._write("comment.md", content)).errors

    def test_comment_with_core_code_block_passes(self) -> None:
        self.assertEqual(self._errors(GOOD_COMMENT), [])

    def test_prose_only_comment_requires_code_block(self) -> None:
        errors = self._errors(PROSE_ONLY_COMMENT)
        self.assertEqual(len(errors), 1)
        self.assertIn("缺少核心伪代码块", errors[0])

    def test_short_review_may_omit_code_block(self) -> None:
        content = "**`a.py:42`** [P2]\n> data = load_users()\n\nRename `data` to `users_by_id`.\n"
        self.assertEqual(self._errors(content), [])

    def test_short_review_limit_is_exclusive(self) -> None:
        body = " ".join(f"word{index}" for index in range(15))
        content = f"**`a.py:42`** [P2]\n> data = load_users()\n\n{body}\n"
        self.assertIn("缺少核心伪代码块", self._errors(content)[0])

    def test_legacy_inline_level_header_fails(self) -> None:
        content = "[P1] 问题：这里会丢失明细。\n\n建议：按新旧前缀分开判定。\n"
        errors = self._errors(content)
        self.assertTrue(any("首行应为" in message for message in errors))
        self.assertTrue(any("> 引用" in message for message in errors))

    def test_unclosed_code_block_fails(self) -> None:
        content = GOOD_COMMENT.rsplit("~~~", 1)[0]
        self.assertTrue(any("未闭合" in message for message in self._errors(content)))

    def test_shorter_fence_does_not_close_block(self) -> None:
        content = GOOD_COMMENT.replace("~~~python", "~~~~python").replace("~~~\n", "~~~~\n")
        self.assertEqual(self._errors(content), [])
        nested = GOOD_COMMENT.replace("~~~python", "~~~~python")
        self.assertTrue(any("未闭合" in message for message in self._errors(nested)))

    def test_empty_code_block_fails(self) -> None:
        content = PROSE_ONLY_COMMENT + "\n~~~python\n\n~~~\n"
        self.assertTrue(any("代码块为空" in message for message in self._errors(content)))

    def test_long_code_block_only_warns(self) -> None:
        code = "\n".join(f"step_{index}()" for index in range(31))
        report = check_comment(self._write("long.md", PROSE_ONLY_COMMENT + f"\n~~~python\n{code}\n~~~\n"))
        self.assertEqual(report.errors, [])
        self.assertEqual(len(report.warnings), 1)

    def test_main_returns_failure_when_any_comment_fails(self) -> None:
        self._write("01.md", GOOD_COMMENT)
        self._write("02.md", PROSE_ONLY_COMMENT)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(self.root)]), 1)
        self.assertIn("1/2", output.getvalue())

    def test_main_rejects_missing_or_empty_targets(self) -> None:
        for target in (self.root / "missing", self.root):
            with self.subTest(target=target), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main([str(target)])
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

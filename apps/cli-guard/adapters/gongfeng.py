"""Gongfeng CLI grammar and publication payload extraction."""

from __future__ import annotations

from adapters import FALSE_VALUES, Contents, Operation, arguments, command

COMMANDS: dict[str, int] = dict.fromkeys(["mr", "issue", "review", "note", "commit"], 2)
FIELDS: dict[str, str] = {
    "--title": "title",
    "--description": "body",
    "--message": "body",
    "--merge-commit-message": "body",
    "--note": "body",
    "--body": "body",
}
GLOBAL_FLAGS: set[str] = {"--project-id", "--base-url", "--token"}
VALUE_FLAGS: set[str] = (
    GLOBAL_FLAGS
    | set(FIELDS)
    | set(
        """
    --source-branch --target-branch --source-commit --target-commit --target-project-id
    --assignee-id --approver-rule --reviewers --necessary-approver-rule
    --necessary-reviewer-ids --reviewer-ids --labels --grade --milestone-id
    --resolve-state --state-event --line --line-type --path --reviewer-state
""".split()
    )
)
READ_ACTIONS: set[str] = {
    "show",
    "list",
    "my-list",
    "comments",
    "changes",
    "commits",
    "diff",
    "refs",
}


def classify(args: list[str]) -> Operation | None:
    route, start = command(args, COMMANDS, VALUE_FLAGS)
    if len(route) != 2 or route[0] not in COMMANDS:
        return None
    if route[1] in READ_ACTIONS or route[1].endswith(("-show", "-list")):
        return None
    items = list(arguments(args, VALUE_FLAGS))
    if any(item.flag in {"--help", "-h"} and item.value not in FALSE_VALUES for item in items):
        return None
    return Operation(route, start, items)


def prepare(args: list[str], operation: Operation, contents: Contents) -> list[str]:
    for item in operation.items:
        if item.flag in FIELDS:
            contents.add(FIELDS[item.flag], item.value)
    return args

"""GitHub CLI grammar and publication payload extraction."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

from adapters import (
    FALSE_VALUES,
    Argument,
    Blocked,
    Contents,
    Operation,
    arguments,
    command,
    expand_short_options,
)

COMMANDS: dict[str, int] = {"pr": 2, "issue": 2, "api": 1}
READ_ACTIONS: set[str] = {"view", "list", "diff", "checks", "status"}
TEXT_FLAGS: dict[str, str] = {"--title": "title", "-t": "title", "--body": "body", "-b": "body"}
FILE_FLAGS: set[str] = {"--body-file", "-F"}
COMMENT_FLAGS: set[str] = {"--comment", "-c"}
API_FIELDS: set[str] = {"--field", "-F", "--raw-field", "-f"}
METADATA_FLAGS: set[str] = set(
    """
    --base -B --add-assignee --remove-assignee --add-label --remove-label
    --add-project --remove-project --add-reviewer --remove-reviewer
    --milestone -m --remove-milestone
""".split()
)
BLOCKED_FLAGS: set[str] = set(
    """
    --web -w --editor -e --fill --fill-first --fill-verbose
    --template -T --recover --attach
""".split()
)
VALUE_FLAGS: set[str] = (
    set(
        """
        --repo -R --hostname --method -X --comment -c --input
        --header -H --jq -q --template --head --label -l
        --assignee -a --reviewer -r --project -p --recover --cache --preview
    """.split()
    )
    | set(TEXT_FLAGS)
    | FILE_FLAGS
    | API_FIELDS
    | (METADATA_FLAGS - {"--remove-milestone"})
)


def classify(args: list[str]) -> Operation | None:
    route, start = command(args, COMMANDS, VALUE_FLAGS)
    if not route or route[0] not in COMMANDS:
        return None
    if route != ("api",) and (len(route) != 2 or route[1] in READ_ACTIONS):
        return None
    values: set[str] = VALUE_FLAGS
    if route[-1] == "review":
        values = values - {"-a", "-c", "-r", "--comment"}
    expanded: list[str] = expand_short_options(args, values)
    parsed_route, start = command(expanded, COMMANDS, VALUE_FLAGS)
    if parsed_route != route:
        raise Blocked(
            "Cannot determine the command from combined options.\n"
            "Action: Place command names before options and retry."
        )
    items: list[Argument] = list(arguments(expanded, values))
    if any(item.flag in {"--help", "-h"} and item.value not in FALSE_VALUES for item in items):
        return None
    operation: Operation = Operation(route, start, items, expanded)
    if route == ("api",) and not api_writes(operation):
        return None
    return operation


def prepare_text(args: list[str], operation: Operation, contents: Contents) -> list[str]:
    action: str = operation.route[1]
    result: list[str] = []
    found: set[str] = set()
    fields: dict[str, str] = dict(TEXT_FLAGS)
    if action in {"close", "reopen"}:
        fields.update({flag: "body" for flag in COMMENT_FLAGS})
    for item in operation.items:
        flag, value = item.flag, item.value
        if flag in BLOCKED_FLAGS:
            raise Blocked(
                "This option can generate or change content after inspection.\n"
                "Action: Prepare the final text and use --title / --body / --body-file."
            )
        if flag in FILE_FLAGS:
            value = contents.freeze("body", value)
            found.add("body")
            result.extend([flag, value])
        else:
            if flag in fields:
                contents.add(fields[flag], value)
                found.add(fields[flag])
            elif flag in METADATA_FLAGS:
                found.add("metadata")
            elif flag in {"--approve", "-a", "--delete-last"} and value not in FALSE_VALUES:
                found.add(flag)
            result.extend(args[item.start : item.end])
    if action in {"create", "new"} and not {"title", "body"} <= found:
        raise Blocked(
            "The final title and body are required.\n"
            "Action: Use --title with --body or --body-file."
        )
    required: dict[str, set[str]] = {
        "comment": {"body", "--delete-last"},
        "edit": {"title", "body", "metadata"},
        "review": {"body", "--approve", "-a"},
    }
    if action in required and not found.intersection(required[action]):
        raise Blocked(
            "The final publication content is required.\n"
            "Action: Use --title / --body / --body-file instead of interactive editing."
        )
    return result


def endpoint(operation: Operation) -> str:
    return next(
        (
            item.value
            for item in operation.items
            if item.flag is None and item.start >= operation.start
        ),
        "",
    )


def api_writes(operation: Operation) -> bool:
    items: list[Argument] = operation.items
    method: str = next(
        (item.value.upper() for item in reversed(items) if item.flag in {"--method", "-X"}), ""
    )
    if endpoint(operation).strip("/") == "graphql":
        return True
    if not method:
        method = "POST" if any(item.flag in API_FIELDS | {"--input"} for item in items) else "GET"
    return method not in {"GET", "HEAD", "OPTIONS", "DELETE"}


def prepare_api(args: list[str], operation: Operation, contents: Contents) -> list[str]:
    result: list[str] = []
    for item in operation.items:
        flag, value = item.flag, item.value
        if flag == "--input":
            result.extend([flag, contents.freeze("input", value)])
        elif flag in API_FIELDS:
            key, _, content = value.partition("=")
            if flag in {"--field", "-F"} and content.startswith("@"):
                value = key + "=@" + contents.freeze(key, content[1:])
            else:
                contents.add(key, content)
            result.extend([flag, value])
        else:
            result.extend(args[item.start : item.end])
    for label, value in parse_qsl(urlsplit(endpoint(operation)).query, keep_blank_values=True):
        contents.add(label, value)
    return result


def prepare(args: list[str], operation: Operation, contents: Contents) -> list[str]:
    handler = prepare_api if operation.route == ("api",) else prepare_text
    expanded: list[str] = operation.argv if operation.argv is not None else args
    prepared: list[str] = handler(expanded, operation, contents)
    return args if prepared == expanded else prepared

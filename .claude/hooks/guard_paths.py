#!/usr/bin/env python3
"""PreToolUse hook: keep each subagent inside its own part of the repository.

Claude Code passes the hook input as JSON on stdin. Inside a subagent the input
contains `agent_type` (the agent's name). Edits outside the agent's allowed
paths are blocked with exit code 2; the stderr message is shown to the agent.

The main session (no `agent_type`) is not restricted by this hook; the
coordinator rules in CLAUDE.md apply to it instead.
"""

import fnmatch
import json
import os
import subprocess
import sys

# Glob patterns are matched against the path relative to the repository root.
# DENY wins over ALLOW.
RULES = {
    "backend": {
        "allow": ["backend/*"],
        "deny": ["backend/transit_data/*", "backend/assistant/*", "backend/*/tests/*", "backend/tests/*"],
    },
    "data": {
        "allow": ["backend/transit_data/*", "otp/*"],
        "deny": ["backend/transit_data/tests/*"],
    },
    "ai": {
        "allow": ["backend/assistant/*"],
        "deny": ["backend/assistant/tests/*"],
    },
    "frontend": {
        "allow": ["frontend/*"],
        "deny": ["frontend/tests/*"],
    },
    "tester": {
        "allow": ["backend/*/tests/*", "backend/tests/*", "frontend/tests/*", "e2e/*"],
        "deny": [],
    },
    "devops": {
        "allow": [
            ".github/*",
            "docker-compose*.yml",
            "*Dockerfile",
            "*/Dockerfile",
            "Makefile",
            ".gitignore",
            ".dockerignore",
            ".env.example",
        ],
        "deny": [],
    },
    "docs": {
        "allow": ["docs/*", "README.md", "CHANGELOG.md"],
        "deny": [],
    },
    "reviewer": {"allow": [], "deny": ["*"]},
}


def repo_root(path: str, fallback: str) -> str:
    """Return the git top-level directory that contains `path` (works in worktrees)."""
    directory = os.path.dirname(os.path.abspath(path))
    while directory and not os.path.isdir(directory):
        directory = os.path.dirname(directory)
    try:
        out = subprocess.run(
            ["git", "-C", directory, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return fallback


def matches(rel_path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, p) for p in patterns)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # Unknown input: do not block.

    agent = data.get("agent_type")
    if not agent or agent not in RULES:
        return 0  # Main session or an agent without rules.

    tool_input = data.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return 0

    cwd = data.get("cwd") or os.getcwd()
    abs_target = target if os.path.isabs(target) else os.path.join(cwd, target)
    root = repo_root(abs_target, cwd)
    rel_path = os.path.relpath(os.path.realpath(abs_target), os.path.realpath(root)).replace(os.sep, "/")

    rules = RULES[agent]
    if rel_path.startswith("../"):
        allowed = False
    else:
        allowed = matches(rel_path, rules["allow"]) and not matches(rel_path, rules["deny"])

    if allowed:
        return 0

    print(
        f"Blocked: agent '{agent}' may not edit '{rel_path}'. "
        f"Allowed: {', '.join(rules['allow']) or 'nothing (read-only)'}"
        + (f"; excluded: {', '.join(rules['deny'])}" if rules["deny"] else "")
        + ". If this change is needed, report it to the coordinator instead of making it.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

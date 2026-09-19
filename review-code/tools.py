#!/usr/bin/env python3
# Copyright 2026 Ziee. All rights reserved.
# License can be found in the LICENSE file.
#
# Answers file_read / list_files / code_search / file_read_diff against a
# local checkout. Pass the directory in; do not clone from here.

import subprocess
from pathlib import Path

READ_MAX_LINES = 500
LIST_MAX = 500
SEARCH_MAX = 100
ROOT = Path("/Users/clivern/space/glitch")
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read file content when you need context for a git diff. The hunk header @@ -x,y +m,n @@ means the new file has n lines starting at line m; set start_line/end_line around that range. Returns at most 500 lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Repository-relative path."},
                    "start_line": {"type": "integer", "description": "First line to return. Defaults to 1."},
                    "end_line": {"type": "integer", "description": "Last line to return. Defaults to end of file."},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories under a repository-relative path on the PR head.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to list. Defaults to the repository root.",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Include nested files. Defaults to false.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_search",
            "description": "Search for specific text in files, directories, or the whole codebase. Literal match by default; set use_perl_regexp for a regex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_text": {"type": "string", "description": "Literal text or regular expression."},
                    "file_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Globs to include or exclude, e.g. ['*.go'] or [':(exclude)*_test.go'].",
                    },
                    "case_sensitive": {"type": "boolean", "description": "Defaults to false."},
                    "use_perl_regexp": {"type": "boolean", "description": "Treat search_text as a regex. Defaults to false."},
                },
                "required": ["search_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read_diff",
            "description": "View diffs of other changed files when you need them to confirm a suspected issue. Context only — do not comment on those files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_array": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File paths whose diffs to return.",
                    },
                },
                "required": ["path_array"],
            },
        },
    },
]


def format_search(hits):
    if not hits:
        return "No matches."
    parts = [f"Search results ({len(hits)}):"]
    for path, line, body in hits:
        loc = f"{line}| " if line else ""
        parts.append(f"File: {path}\n{loc}{body}")
    return "\n\n".join(parts)


class Workspace:
    def __init__(self, root=ROOT, sha=None, base_sha=None):
        self.root = Path(root)
        self.sha = sha
        self.base_sha = base_sha

    def run(self, name, args):
        return getattr(self, name)(**args)

    def git(self, *args, check=True):
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=check,
            capture_output=True,
            text=True,
        )

    def file_read(self, file_path, start_line=None, end_line=None):
        lines = (self.root / file_path).read_text().splitlines()
        start = start_line or 1
        end = min(len(lines), end_line or len(lines))
        truncated = end - start + 1 > READ_MAX_LINES
        if truncated:
            end = start + READ_MAX_LINES - 1
        numbered = "\n".join(
            f"{start + i}| {line}" for i, line in enumerate(lines[start - 1 : end])
        )
        return (
            f"File: {file_path} (Total lines: {len(lines)})\n"
            f"IS_TRUNCATED: {str(truncated).lower()}\n"
            f"LINE_RANGE: {start}-{end}\n"
            f"{numbered}"
        )

    def list_files(self, path=".", recursive=False):
        target = self.root / path
        entries = []
        if recursive:
            for p in sorted(target.rglob("*")):
                if ".git" in p.relative_to(self.root).parts or not p.is_file():
                    continue
                entries.append(p.relative_to(self.root).as_posix())
                if len(entries) >= LIST_MAX:
                    break
        else:
            for p in sorted(target.iterdir(), key=lambda item: item.name.lower()):
                if p.name == ".git":
                    continue
                rel = p.relative_to(self.root).as_posix()
                entries.append(rel + ("/" if p.is_dir() else ""))
        return "\n".join(entries) if entries else "No files."

    def code_search(
        self,
        search_text,
        file_patterns=None,
        case_sensitive=False,
        use_perl_regexp=False,
    ):
        args = ["rg", "--line-number", "--no-heading", "--color=never"]
        if not case_sensitive:
            args.append("--ignore-case")
        args.append("--pcre2" if use_perl_regexp else "--fixed-strings")
        for pattern in file_patterns or []:
            glob = f"!{pattern[10:]}" if pattern.startswith(":(exclude)") else pattern
            args += ["--glob", glob]
        args += ["-e", search_text]
        proc = subprocess.run(args, cwd=self.root, capture_output=True, text=True)
        hits = []
        for raw in proc.stdout.splitlines():
            path, line, body = raw.split(":", 2)
            hits.append((path, int(line), body))
            if len(hits) >= SEARCH_MAX:
                break
        return format_search(hits)

    def file_read_diff(self, path_array):
        parts = []
        for path in path_array:
            args = ["diff"]
            if self.base_sha:
                args += [self.base_sha, self.sha or "HEAD"]
            args += ["--", path]
            proc = self.git(*args, check=False)
            parts.append(f"==== FILE: {path} ====\n{proc.stdout or '(no diff)'}")
        return "\n\n".join(parts)

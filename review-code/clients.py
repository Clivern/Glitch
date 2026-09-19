#!/usr/bin/env python3
# Copyright 2026 Ziee. All rights reserved.
# License can be found in the LICENSE file.

import base64
import json
import re
import ssl
import urllib.request
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import quote, urlencode

import certifi

READ_MAX_LINES = 500
SEARCH_MAX = 100
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
            "name": "code_search",
            "description": "Search for specific text in files, directories, or the whole codebase. Literal match by default; set use_perl_regexp for a regex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_text": {"type": "string", "description": "Literal text or regular expression."},
                    "file_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Git pathspecs to include or exclude, e.g. ['*.go'] or [':(exclude)*_test.go'].",
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
            "name": "file_find",
            "description": "Find files by name keyword when they are not in the current change list. A query with '/' also matches the repository-relative path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_name": {"type": "string", "description": "Filename keyword or path fragment."},
                    "case_sensitive": {"type": "boolean", "description": "Defaults to false."},
                },
                "required": ["query_name"],
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


def _match(path, pattern):
    return fnmatch(path, pattern) or fnmatch(path.split("/")[-1], pattern) or pattern in path


def path_matches(path, patterns):
    if not patterns:
        return True
    include = [p for p in patterns if not p.startswith(":(exclude)")]
    exclude = [p[10:] for p in patterns if p.startswith(":(exclude)")]
    return (not include or any(_match(path, p) for p in include)) and not any(
        _match(path, p) for p in exclude
    )


def collect_hits(path, text, pattern, file_patterns, hits, seen):
    for i, line in enumerate(text.splitlines(), 1):
        if not pattern.search(line):
            continue
        key = (path, i, line)
        if key in seen or not path_matches(path, file_patterns):
            continue
        seen.add(key)
        hits.append((path, i, line))
        if len(hits) >= SEARCH_MAX:
            return True
    return False


def format_search(hits):
    if not hits:
        return "No matches."
    parts = [f"Search results ({len(hits)}):"]
    for path, line, body in hits:
        loc = f"{line}| " if line else ""
        parts.append(f"File: {path}\n{loc}{body}")
    return "\n\n".join(parts)


class GitHub:
    def __init__(self, token, agent="ziee-tools-playground"):
        self.token = token
        self.agent = agent
        self.ssl = ssl.create_default_context(cafile=certifi.where())

    def call(self, method, path, payload=None, accept="application/vnd.github+json"):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": self.agent,
        }
        data = json.dumps(payload).encode() if payload is not None else None
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"https://api.github.com{path}", data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(req, context=self.ssl) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else {}

    def get(self, path, accept="application/vnd.github+json"):
        return self.call("GET", path, accept=accept)

    def post(self, path, payload):
        return self.call("POST", path, payload)


class Repository:
    def __init__(self, github, owner, repo, sha, patches=None):
        self.github = github
        self.owner = owner
        self.repo = repo
        self.sha = sha
        self.patches = patches or {}
        self.cache = {}
        self.tree = None

    def run(self, name, args):
        return getattr(self, name)(**args)

    def load_file(self, path):
        if path in self.cache:
            return self.cache[path]
        data = self.github.get(
            f"/repos/{self.owner}/{self.repo}/contents/{quote(path, safe='/')}?ref={self.sha}"
        )
        text = (
            "\n".join(item["path"] for item in data)
            if isinstance(data, list)
            else base64.b64decode(data["content"]).decode()
        )
        self.cache[path] = text
        return text

    def load_tree(self):
        if self.tree is None:
            data = self.github.get(
                f"/repos/{self.owner}/{self.repo}/git/trees/{self.sha}?recursive=1"
            )
            self.tree = [item["path"] for item in data["tree"] if item["type"] == "blob"]
        return self.tree

    def file_read(self, file_path, start_line=None, end_line=None):
        lines = self.load_file(file_path).splitlines()
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

    def file_find(self, query_name, case_sensitive=False):
        needle = query_name if case_sensitive else query_name.lower()
        use_path = "/" in query_name or "\\" in query_name
        hits = []
        for path in self.load_tree():
            hay = path if use_path else path.split("/")[-1]
            if not case_sensitive:
                hay = hay.lower()
            if needle in hay:
                hits.append(path)
                if len(hits) >= SEARCH_MAX:
                    break
        return "\n".join(hits) if hits else "No matching files."

    def file_read_diff(self, path_array):
        return "\n\n".join(
            f"==== FILE: {path} ====\n{self.patches.get(path, '(no diff)')}"
            for path in path_array
        )

    def code_search(
        self,
        search_text,
        file_patterns=None,
        case_sensitive=False,
        use_perl_regexp=False,
    ):
        flags = 0 if case_sensitive else re.I
        pattern = re.compile(
            search_text if use_perl_regexp else re.escape(search_text), flags
        )
        hits, seen = [], set()
        sources = list(self.cache.items())
        for path in file_patterns or []:
            if any(ch in path for ch in "*?") or path.startswith(":(exclude)") or path.endswith("/"):
                continue
            sources.append((path, self.load_file(path)))
        sources.extend(self.patches.items())
        for path, text in sources:
            if collect_hits(path, text, pattern, file_patterns, hits, seen):
                return format_search(hits)

        q = {"q": f"{search_text} repo:{self.owner}/{self.repo}", "per_page": 20}
        data = self.github.get(
            f"/search/code?{urlencode(q)}",
            accept="application/vnd.github.text-match+json",
        )
        for item in data["items"]:
            path = item["path"]
            for match in item.get("text_matches") or []:
                body = match["fragment"].replace("\n", " / ")
                key = (path, 0, body)
                if key in seen or not path_matches(path, file_patterns):
                    continue
                seen.add(key)
                hits.append((path, 0, body))
                if len(hits) >= SEARCH_MAX:
                    return format_search(hits)
        return format_search(hits)


def main():
    secrets = dict(
        line.split("=", 1)
        for line in Path(__file__).with_name(".secrets").read_text().splitlines()
        if "=" in line
    )
    owner, name = "clivern", "ziee"
    github = GitHub(secrets["GITHUB_TOKEN"])
    info = github.get(f"/repos/{owner}/{name}")
    branch = github.get(f"/repos/{owner}/{name}/branches/{info['default_branch']}")
    sha = branch["commit"]["sha"]
    commit = github.get(f"/repos/{owner}/{name}/commits/{sha}")
    patches = {
        item["filename"]: item.get("patch") or ""
        for item in commit.get("files") or []
    }
    repo = Repository(github, owner, name, sha, patches)

    print(f"{owner}/{name}@{sha[:7]} on {info['default_branch']}")
    print(f"latest commit files: {', '.join(patches) or '(none)'}")
    print()
    print("=== file_read ===")
    print(repo.file_read("README.md", start_line=1, end_line=25))
    print()
    print("=== file_find ===")
    print(repo.file_find("config"))
    print()
    print("=== code_search ===")
    print(repo.code_search("func main", file_patterns=["*.go"]))
    print()
    print("=== file_read_diff ===")
    print(repo.file_read_diff(list(patches)[:3] or ["README.md"]))


if __name__ == "__main__":
    main()

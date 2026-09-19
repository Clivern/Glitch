#!/usr/bin/env python3
# Copyright 2026 Ziee. All rights reserved.
# License can be found in the LICENSE file.
#
# Last run
#   repo: clivern/ziee#60
#   head: 84dfacf
#   model: anthropic/claude-sonnet-5
#   files: go.mod (default.md), go.sum (default.md)
#   findings: none (no GitHub review posted)
#
# Tokens live in scripts/.secrets (gitignored):
#   GITHUB_TOKEN=...
#   OPENROUTER_API_KEY=...

import json
import re
import ssl
import urllib.request
from pathlib import Path

import certifi

from tools import TOOLS, Workspace

_secrets = dict(
    line.split("=", 1)
    for line in Path(__file__).with_name(".secrets").read_text().splitlines()
    if "=" in line
)

GITHUB_TOKEN = _secrets["GITHUB_TOKEN"]
OPENROUTER_API_KEY = _secrets["OPENROUTER_API_KEY"]
OWNER = "clivern"
REPO = "glitch"
PR = 3
MODEL = "anthropic/claude-sonnet-5"
RULES_DIR = Path(__file__).resolve().parents[1] / "files" / "rules"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def github(method, path, payload=None):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ziee-pr-review-poc",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, context=SSL_CTX) as resp:
        raw = resp.read()

    return json.loads(raw) if raw else {}


def openrouter(messages, tools=None):
    body = {"model": MODEL, "messages": messages}
    if tools:
        body["tools"] = tools
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, context=SSL_CTX) as resp:
        data = json.loads(resp.read())

    return data["choices"][0]["message"]


def expand_braces(pattern):
    match = re.search(r"\{([^{}]+)\}", pattern)
    if not match:
        return [pattern]

    out = []
    for part in match.group(1).split(","):
        out.extend(expand_braces(pattern[: match.start()] + part + pattern[match.end() :]))

    return out


def glob_re(pattern):
    i = 0
    out = ["^"]
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    out.append("$")

    return re.compile("".join(out))


def load_rules():
    spec = json.loads((RULES_DIR / "rules.json").read_text())
    rules = []
    for pattern, name in spec["path_rule_map"].items():
        body = (RULES_DIR / name).read_text()
        for expanded in expand_braces(pattern):
            rules.append((glob_re(expanded), body, name))

    default = (RULES_DIR / spec["default_rule"]).read_text()
    prompt = (RULES_DIR / spec["system_prompt"]).read_text()

    return rules, default, prompt


def rule_for(path, rules, default):
    for matcher, body, name in rules:
        if matcher.match(path):
            return body, name

    return default, "default.md"


def strip_tag(value, tag):
    return value.replace(f"<{tag}>", "").replace(f"</{tag}>", "")


def diff_lines(patch):
    lines = set()
    new_line = 0
    for raw in patch.splitlines():
        if raw.startswith("@@"):
            new_line = int(re.search(r"\+(\d+)", raw).group(1))
            continue
        if raw.startswith("-") or raw.startswith("\\"):
            continue
        lines.add(new_line)
        new_line += 1

    return lines


def fence(lang, code):
    tag = f"```{lang}" if lang else "```"
    return f"{tag}\n{code.rstrip()}\n```"


def format_comment(finding):
    lang = Path(finding["path"]).suffix.lstrip(".")
    parts = [f"**{finding['severity']} {finding['title']}**", "", finding["body"]]
    if finding.get("evidence"):
        parts += ["", fence("", finding["evidence"])]
    if finding.get("fix"):
        parts += ["", fence(lang, finding["fix"])]
    if finding.get("why"):
        parts += ["", f"**Why this wasn't caught:** {finding['why']}"]

    visible = "\n".join(parts)
    prompt = (
        "This is a comment left during a code review.\n"
        f"Path: {finding['path']}\n"
        f"Line: {finding['line']}\n"
        f"\nComment:\n{visible}\n"
        "\nHow can I resolve this? If you propose a fix, please make it concise."
    )
    parts += [
        "",
        "<details>",
        "<summary>Prompt To Fix With AI</summary>",
        "",
        f"````\n{prompt}\n````",
        "</details>",
    ]

    return "\n".join(parts)


def review_comment(finding, allowed):
    line = finding["line"]
    start = finding.get("start_line", line)
    body = format_comment(finding)
    comment = {
        "path": finding["path"],
        "line": line,
        "side": "RIGHT",
        "body": body,
    }
    if start in allowed and start < line:
        comment["start_line"] = start
        comment["start_side"] = "RIGHT"

    return comment, line in allowed


def parse_findings(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text[: text.rfind("```")]

    return json.loads(text).get("findings", [])


def list_changes():
    files = []
    page = 1
    while True:
        batch = github(
            "GET",
            f"/repos/{OWNER}/{REPO}/pulls/{PR}/files?per_page=100&page={page}",
        )
        files.extend(batch)
        if len(batch) < 100:
            return files
        page += 1


def review_file(path, patch, checklist, prompt, workspace):
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                f"<current_file_path>{strip_tag(path, 'current_file_path')}</current_file_path>\n\n"
                f"<current_file_diff>\n{strip_tag(patch, 'current_file_diff')}\n</current_file_diff>\n\n"
                f"<user_task>\n"
                f"### Review Checklist\n{checklist}\n\n"
                f"Now please review the code changes in <current_file_diff>\n"
                f"</user_task>"
            ),
        },
    ]
    while True:
        message = openrouter(messages, TOOLS)
        calls = message.get("tool_calls") or []
        if not calls:
            return parse_findings(message["content"] or "")

        messages.append(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": calls,
            }
        )
        for call in calls:
            fn = call["function"]
            args = json.loads(fn["arguments"] or "{}")
            print(f"  tool {fn['name']} {args}")
            handler = getattr(workspace, fn["name"], None)
            result = handler(**args) if handler else f"unknown tool: {fn['name']}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                }
            )


def main():
    rules, default, prompt = load_rules()
    pr = github("GET", f"/repos/{OWNER}/{REPO}/pulls/{PR}")
    sha = pr["head"]["sha"]
    workspace = Workspace(sha=sha, base_sha=pr["base"]["sha"])
    print(f"reviewing {OWNER}/{REPO}#{PR} @ {sha[:7]}")

    inline = []
    leftover = []
    for file in list_changes():
        patch = file.get("patch") or ""
        if not patch:
            print(f"skip {file['filename']} (no patch)")
            continue

        checklist, rule_name = rule_for(file["filename"], rules, default)
        print(f"review {file['filename']} [{rule_name}]")
        allowed = diff_lines(patch)
        for finding in review_file(file["filename"], patch, checklist, prompt, workspace):
            comment, on_diff = review_comment(finding, allowed)
            print(f"  {finding['severity']} L{finding['line']}: {finding['title']}")
            if on_diff:
                inline.append(comment)
            else:
                leftover.append(comment["body"])

    if inline or leftover:
        body = "Ziee's AI review."
        if leftover:
            body += "\n\n" + "\n".join(leftover)
    else:
        body = "LGTM"
        print("LGTM")

    review = github(
        "POST",
        f"/repos/{OWNER}/{REPO}/pulls/{PR}/reviews",
        {
            "commit_id": sha,
            "body": body,
            "event": "COMMENT",
            "comments": inline,
        },
    )
    print(review["html_url"])


if __name__ == "__main__":
    main()

"""Check publishable Git files, documentation links and acceptance-case coverage.

This deliberately reports locations only, never matched secret values. It is a
repository hygiene check, not a substitute for a security audit or semantic eval.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {
    ".venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}
FORBIDDEN_PREFIXES = ("var/", "work/", "docs/_planning/", "apps/web/public/pdfjs/")
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "API key": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "personal gateway": re.compile(r"\bllm-[a-z0-9]{8,}\."),
    "local home path": re.compile("/" + r"(?:Users|home)/[A-Za-z0-9_.-]+/"),
}
LINK = re.compile(r"\[[^\]\n]*\]\(<?([^\s)>]+)>?(?:\s+[^)]*)?\)")


def candidates() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return sorted({Path(name) for name in result.stdout.decode().split("\0") if name})


def main() -> int:
    problems: list[str] = []
    paths = candidates()
    for relative in paths:
        name = relative.as_posix()
        if (
            FORBIDDEN_PARTS.intersection(relative.parts)
            or name.startswith(FORBIDDEN_PREFIXES)
            or (relative.name.startswith(".env") and relative.name != ".env.example")
            or relative.name.endswith((".log", ".tsbuildinfo", ".pyc"))
        ):
            problems.append(f"{name}: private/generated file in publishable candidates")
        path = ROOT / relative
        if not path.is_file():
            problems.append(f"{name}: missing candidate file")
            continue
        if path.suffix.lower() in {".pdf", ".webp", ".png", ".jpg", ".jpeg", ".zip"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            problems.append(f"{name}: unexpected non-UTF-8 text")
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                line = content.count("\n", 0, match.start()) + 1
                problems.append(f"{name}:{line}: {label}")
        if path.suffix == ".md":
            # Examples in code fences are not actual Markdown navigation links.
            markdown = re.sub(r"(?ms)^```.*?^```[^\n]*", "", content)
            for match in LINK.finditer(markdown):
                target = unquote(match.group(1))
                parsed = urlsplit(target)
                if parsed.scheme or target.startswith(("#", "/")) or not parsed.path:
                    continue
                destination = (path.parent / parsed.path).resolve()
                if not destination.is_relative_to(ROOT) or not destination.exists():
                    problems.append(f"{name}: unresolved local link {target}")

    acceptance = json.loads((ROOT / "tests/acceptance/cases.json").read_text())
    cases = acceptance["cases"]
    required = {"rag", "sql", "hybrid", "ambiguity", "conflict"}
    missing = required - {case["category"] for case in cases}
    if missing:
        problems.append("acceptance: missing categories " + ", ".join(sorted(missing)))
    if len({case["id"] for case in cases}) != len(cases):
        problems.append("acceptance: duplicate IDs")
    if len({case["question"] for case in cases}) != len(cases):
        problems.append("acceptance: duplicate questions")
    groups = acceptance.get("groups", [])
    for group in groups:
        size = sum(case.get("group") == group for case in cases)
        if not 2 <= size <= 4:
            problems.append(f"acceptance: {group} needs 2–4 representative cases")
    components = {name for case in cases for name in case.get("components", [])}
    required_components = {
        "指标卡",
        "柱状图",
        "折线图",
        "数据表",
        "冲突核对卡",
        "缺失核对卡",
        "小样本核对卡",
        "澄清选项卡",
        "原文引用",
    }
    if required_components - components:
        problems.append("acceptance: incomplete UI component coverage")
    for case in cases:
        if not case.get("question") or not case.get("checks"):
            problems.append(f"acceptance {case['id']}: empty question/checks")
        if case.get("group") not in groups or not case.get("label"):
            problems.append(f"acceptance {case['id']}: invalid group/label")
        if (
            not case.get("expected_answer")
            or not case.get("reference")
            or not case.get("components")
        ):
            problems.append(f"acceptance {case['id']}: missing review details")
        for name in case["required_documents"]:
            if not (ROOT / "data/examples" / name).is_file():
                problems.append(f"acceptance {case['id']}: missing corpus {name}")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"Repository checks passed: {len(paths)} publishable files, {len(cases)} cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

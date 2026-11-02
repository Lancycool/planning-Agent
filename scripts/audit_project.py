"""Check deliverable links and accidental inclusion of the locally configured key."""

import json
import re
from pathlib import Path

from dotenv import dotenv_values

from content_agent.cli import write_json


def main():
    root = Path.cwd()
    files = [Path("README.md"), Path("pyproject.toml"), Path("uv.lock"), Path("env.sample"),
             Path(".env.example"), Path(".gitignore"), Path("题目.md"), Path("考核规则.md")]
    for directory in ("src", "tests", "data", "docs", "examples", "scripts", "web"):
        files.extend(p for p in Path(directory).rglob("*") if p.is_file()
                     and p.suffix in {".py", ".json", ".xml", ".md", ".js", ".cjs", ".html", ".css", ".tap"})
    key = dotenv_values(root / ".env").get("DASHSCOPE_API_KEY")
    broken = []
    leak_paths = []
    for file in files:
        content = file.read_text(encoding="utf-8-sig")
        if key and key in content:
            leak_paths.append(file.as_posix())
        if file.suffix == ".md":
            for link in re.findall(r"\]\(([^)]+)\)", content):
                if "://" in link or link.startswith("#"):
                    continue
                target = link.strip("<>").split("#")[0]
                if target and not (file.parent / target).exists():
                    broken.append({"file": file.as_posix(), "target": target})
    report = {"files_checked": len(files), "broken_links": broken, "local_key_found_in_deliverables": bool(leak_paths),
              "leak_paths": leak_paths, "passed": not broken and not leak_paths,
              "scope": "Explicit deliverable files only; .env and runtime directories are excluded."}
    write_json(root / "examples" / "project-audit.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

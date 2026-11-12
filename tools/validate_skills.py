"""Validate actual installable directories without executing their scripts."""

from pathlib import Path

from dcc_mcp_core import validate_skill

root = Path(__file__).resolve().parents[1] / "skills"
failed = False
for path in sorted(root.iterdir()):
    if not path.is_dir():
        continue
    report = validate_skill(str(path))
    print("{}: {} issue(s)".format(path.name, len(report.issues)))
    for issue in report.issues:
        print(issue)
    failed = failed or bool(report.issues)
raise SystemExit(1 if failed else 0)

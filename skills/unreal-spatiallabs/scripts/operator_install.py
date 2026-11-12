"""Human-operated project installer. Agents must never provide the acceptance input."""

import argparse
import json
import sys
from pathlib import Path

from spatiallabs_project import _hash, _json_bytes, _validate_plan, install_plan, plan_install, rollback


class _ConsoleAuthority:
    """A process-local, one-operation capability, never serialized as approval."""

    def __init__(self, plan_id, action):
        self.plan_id = plan_id
        self.action = action
        self.used = False

    def require(self, scope, action):
        if self.used or action != self.action or scope.get("plan_id") != self.plan_id:
            raise PermissionError("Console authorization is absent, consumed or scoped to another plan/action")
        self.used = True


def _confirm(plan, action):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise PermissionError("authorization_required: acceptance needs a visible interactive operator terminal")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    if action == "install":
        print("Read the exact Acer license URL above and the current official support evidence.")
        print("Verify that the current license content matches the displayed content_sha256; changed terms need a new plan.")
        print("This action downloads vendor code and enables it in the named project only.")
        print("Installing this skill does not accept any vendor license. An agent must not answer this prompt.")
        phrase = "ACCEPT LICENSE AND INSTALL " + plan["plan_id"]
    else:
        print("Restore the recorded project descriptor and remove only the unchanged managed plugin.")
        phrase = "ROLL BACK " + plan["plan_id"]
    print("If you are the authorized human operator and agree to this exact scope, type:")
    print(phrase)
    if input("> ") != phrase:
        raise PermissionError("Operator did not accept; no download or project changes")
    return _ConsoleAuthority(plan["plan_id"], action)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("plan", help="Read-only plan; writes JSON to stdout only")
    prepare.add_argument("project")
    prepare.add_argument("--plugin-version", required=True)
    prepare.add_argument("--engine-version", required=True)
    prepare.add_argument("--source-url", required=True)
    prepare.add_argument("--support-evidence", help="Reviewed official matrix record JSON, not a consent grant")
    prepare.add_argument("--license-evidence", help="Reviewed exact license content hash/date/official URL JSON, not consent")
    install = sub.add_parser("install", help="Human console acceptance followed by official download and project-only install")
    install.add_argument("plan", help="Reviewed JSON plan prepared by plan_install")
    restore = sub.add_parser("rollback", help="Human console authorization; refuse post-install user edits")
    restore.add_argument("project")
    restore.add_argument("plan_id")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            evidence = json.loads(Path(args.support_evidence).read_text(encoding="utf-8-sig")) if args.support_evidence else None
            license_record = json.loads(Path(args.license_evidence).read_text(encoding="utf-8-sig")) if args.license_evidence else None
            result = plan_install(args.project, args.plugin_version, args.engine_version, args.source_url, evidence, license_record)
        elif args.action == "install":
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
            _validate_plan(plan)
            if plan.get("compatibility_status") != "supported":
                raise ValueError("Current official compatibility is unknown/unsupported; prepare a reviewed plan first")
            if plan.get("license_evidence") is None:
                raise ValueError("Exact license content review is missing; no consent prompt or download")
            authority = _confirm(plan, "install")
            result = install_plan(plan, authority)
        else:
            # Validate requested project and load its exact, hash-bound plan before displaying scope.
            from spatiallabs_project import STATE_DIR, _inside, _project

            root, path, _data = _project(args.project)
            import re

            if not re.fullmatch(r"[a-f0-9]{64}", args.plan_id):
                raise ValueError("Invalid plan ID")
            receipt_path = _inside(root, root / STATE_DIR / args.plan_id / "receipt.json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            plan = receipt["plan"]
            payload = dict(plan)
            payload.pop("plan_id", None)
            if plan.get("project_path") != str(path) or _hash(_json_bytes(payload)) != args.plan_id:
                raise ValueError("Receipt scope/hash mismatch")
            authority = _confirm(plan, "rollback")
            result = rollback(str(path), args.plan_id, authority)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, EOFError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

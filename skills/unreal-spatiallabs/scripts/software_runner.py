"""Operator-authorized, unattended software checks through the official DCC CLI.

No shell commands, vendor installation, raw code execution, instance takeover,
or implicit retries are provided. Unknown CLI envelopes fail closed.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_PROBE = "unreal_pie__pie_get_status"
PROJECT_RESULT_PATH = ["context", "perf", "project_name"]


def _payload(value):
    if not isinstance(value, dict):
        raise ValueError("DCC CLI returned no structured object")
    if value.get("isError") is True or value.get("success") is False or value.get("status") in ("failed", "error", "cancelled"):
        raise ValueError("DCC envelope explicitly reports an error")
    if isinstance(value.get("output"), dict):
        return value["output"]
    result = value.get("result", value)
    if (not isinstance(result, dict) or result.get("isError") is True or result.get("success") is False
            or result.get("status") in ("failed", "error", "cancelled")):
        raise ValueError("DCC call reported a transport/tool error")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    if "content" in result:
        texts = [item.get("text") for item in result["content"] if item.get("type") == "text"]
        if len(texts) != 1:
            raise ValueError("DCC response lacks one unambiguous structured result")
        parsed = json.loads(texts[0])
        if not isinstance(parsed, dict):
            raise ValueError("DCC response text must contain an object")
        return parsed
    return result


def normalize(value):
    raw = _payload(value)
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    result = dict(context)
    status = raw.get("status", context.get("status"))
    def has_error(item):
        if not isinstance(item, dict):
            return False
        if item.get("success") is False or item.get("isError") is True or item.get("status") in ("failed", "error", "cancelled"):
            return True
        return any(has_error(item.get(key)) for key in ("output", "result", "context", "structuredContent"))

    if has_error(raw):
        status = "failed"
    elif status in ("ok", "success", "succeeded", "done"):
        status = "completed"
    elif status is None and raw.get("success") is True:
        status = "pending" if raw.get("job_id") or context.get("job_id") else "completed"
    if status not in ("completed", "pending", "running", "queued", "failed", "cancelled", "error"):
        raise ValueError("Unrecognized DCC outcome; query state before any repeated action")
    result["status"] = "pending" if status in ("pending", "running", "queued") else "failed" if status in ("error", "cancelled") else status
    for key in ("job_id", "recording_id"):
        if key in raw:
            result[key] = raw[key]
    nested = raw.get("result")
    if isinstance(nested, dict) and (nested.get("success") is False or nested.get("isError") is True
                                     or nested.get("status") in ("failed", "error", "cancelled")):
        result["status"] = "failed"
    result["output"] = raw
    if result["status"] == "completed" and isinstance(nested, dict):
        completed_payload = _payload(nested)
        result["output"] = completed_payload
        completed_context = completed_payload.get("context", {})
        for key in ("recording_id",):
            if key in completed_payload:
                result[key] = completed_payload[key]
            elif isinstance(completed_context, dict) and key in completed_context:
                result[key] = completed_context[key]
        result["job_metadata"] = {"status": raw.get("status"), "job_id": result.get("job_id")}
    return result


def _select(value, path):
    if not isinstance(path, list) or not path or any(not isinstance(key, (str, int)) or isinstance(key, bool) for key in path):
        raise ValueError("An explicit structured result path is required")
    for key in path:
        value = value[key]
    return value


class CliTransport:
    def __init__(self, plan, runner=None, executable=None):
        self.plan = plan
        self.runner = runner or subprocess.run
        self.jobs = set()
        self.recordings = set()
        self.stop_jobs = {}
        project_root = Path(plan.get("project_root", str(Path(plan["project_path"]).parent))).resolve()
        if executable is None:
            filename = "dcc-mcp-cli.exe" if os.name == "nt" else "dcc-mcp-cli"
            for entry in os.get_exec_path():
                directory = Path(entry)
                if not directory.is_absolute() or ".." in directory.parts:
                    continue
                # Reject the untrusted PATH spelling before following a link or
                # junction into an otherwise trusted-looking external directory.
                try:
                    directory.relative_to(project_root)
                    continue
                except ValueError:
                    pass
                candidate = (directory / filename).resolve()
                try:
                    candidate.relative_to(project_root)
                    continue
                except ValueError:
                    pass
                if candidate.is_file() and os.access(str(candidate), os.X_OK):
                    executable = str(candidate)
                    break
        if executable is None or not Path(executable).is_absolute() or not Path(executable).is_file():
            raise ValueError("A trusted installed absolute DCC CLI executable is required; project-local shadows are refused")
        self.executable = str(Path(executable).resolve())
        self.executable_sha256 = hashlib.sha256(Path(self.executable).read_bytes()).hexdigest()
        self.entries = {}
        for step in plan["steps"]:
            self.entries.setdefault(step["tool_slug"], []).append((step, step["input_schema"], False))
            if step.get("poll_tool_slug"):
                self.entries.setdefault(step["poll_tool_slug"], []).append((step, step["status_schema"], True))
        for slug, entries in self.entries.items():
            safe_project_reuse = (slug.split(".", 2)[-1] == PROJECT_PROBE
                                  and all(not item[2] and item[0]["kind"] in ("preflight", "performance", "logs") for item in entries))
            if not safe_project_reuse and len({item[0]["kind"] == "preflight" or item[2] for item in entries}) > 1:
                raise ValueError("A tool cannot serve both observation and mutation roles in one plan")
            if any(item[1] != entries[0][1] for item in entries):
                raise ValueError("Conflicting reviewed schemas for a reused tool")
        self.probe = next((step for step in plan["steps"] if step["kind"] == "preflight" and step.get("dcc_type", "unreal") == "unreal"), None)
        if self.probe is None or not self.probe.get("project_result_path"):
            raise ValueError("Software execution needs a read-only Unreal project probe and project_result_path")
        if (self.probe["tool_slug"].split(".", 2)[-1] != PROJECT_PROBE or self.probe["arguments"] != {}
                or self.probe["project_result_path"] != PROJECT_RESULT_PATH):
            raise ValueError("Project identity must come from the supported empty-argument host-current-project capability; filesystem echoes are refused")

    def _json(self, arguments, input_value=None):
        if hashlib.sha256(Path(self.executable).read_bytes()).hexdigest() != self.executable_sha256:
            raise ValueError("DCC CLI executable changed after operator review")
        command = [self.executable, "--no-update-maintenance", "--non-interactive", "--output", "json"] + arguments
        completed = self.runner(command, input=json.dumps(input_value, allow_nan=False) if input_value is not None else None,
                                capture_output=True, text=True, timeout=30, shell=False)
        if completed.returncode:
            raise RuntimeError("DCC CLI refused/failed (exit {}); no automatic retry: {}".format(
                completed.returncode, completed.stderr[:1000]))
        if len(completed.stdout) > 4 * 1024 * 1024:
            raise ValueError("DCC CLI response exceeds report limit")
        value = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise ValueError("DCC CLI JSON root must be an object")
        return value

    def _entry(self, slug, arguments, observation_only=False):
        def match(expected, actual):
            if expected == "$job_id":
                return isinstance(actual, str) and bool(actual.strip()) and (observation_only or actual in self.jobs)
            if expected == "$recording_id":
                return isinstance(actual, str) and actual in self.recordings
            if type(expected) is not type(actual):
                return False
            if isinstance(expected, dict):
                return set(expected) == set(actual) and all(match(expected[k], actual[k]) for k in expected)
            if isinstance(expected, list):
                return len(expected) == len(actual) and all(match(a, b) for a, b in zip(expected, actual))
            return expected == actual

        candidates = [entry for entry in self.entries.get(slug, [])
                      if (not observation_only or entry[2])
                      and match(entry[0]["status_arguments_template"] if entry[2] else entry[0]["arguments"], arguments)]
        if not candidates:
            raise ValueError("Tool arguments were not included in the reviewed plan or do not bind an owned job/recording")
        if len({(entry[0]["kind"], entry[2], entry[0].get("lease_owner")) for entry in candidates}) > 1:
            if not (slug.split(".", 2)[-1] == PROJECT_PROBE
                    and all(not entry[2] and entry[0]["kind"] in ("preflight", "performance", "logs") for entry in candidates)
                    and len({entry[0].get("lease_owner") for entry in candidates}) == 1):
                raise ValueError("Ambiguous reused tool arguments/roles; split the plan")
        return candidates[0]

    def _describe(self, slug, entry):
        if slug not in self.entries:
            raise ValueError("Tool was not included in the reviewed software plan")
        step, expected_schema, polling = entry
        dcc_type, routing_token, _name = slug.split(".", 2)
        inventory = self._json(["list", "--timeout-secs", "30"])
        rows = [row for row in inventory.get("instances", [])
                if row.get("dcc_type") == dcc_type and row.get("instance_short") == routing_token]
        if len(rows) != 1 or rows[0].get("direct_control", {}).get("ready") is not True:
            raise ValueError("Exact reviewed DCC instance is missing, ambiguous, stale or not ready")
        row = rows[0]
        expected_id = step.get("instance_id") if dcc_type == "obs" else self.plan["instance_id"]
        if expected_id not in (row.get("instance_id"), row.get("instance_short")):
            raise ValueError("DCC full/short instance identity drift")
        described = self._json(["describe", slug, "--timeout-secs", "30"])
        record = described.get("record", {})
        tool = described.get("tool", {})
        if record.get("tool_slug") != slug or record.get("instance_id") != row.get("instance_id"):
            raise ValueError("Describe result does not prove the exact selected instance")
        if tool.get("name") != slug.split(".", 2)[-1]:
            raise ValueError("Describe tool name does not match its reviewed backend identity")
        if tool.get("inputSchema") != expected_schema:
            raise ValueError("Tool schema changed since plan review; prepare a new plan")
        annotations = tool.get("annotations", {})
        readonly = annotations.get("readOnlyHint", annotations.get("read_only_hint")) is True
        if slug.split(".", 2)[-1] == PROJECT_PROBE and (tool.get("name") != PROJECT_PROBE or not readonly):
            raise ValueError("Host-current-project capability identity/annotation mismatch")
        destructive = annotations.get("destructiveHint", annotations.get("destructive_hint")) is True
        if readonly and destructive:
            raise ValueError("Contradictory read-only/destructive tool annotations")
        if (polling or step["kind"] == "preflight") and not readonly:
            raise ValueError("Preflight/status tools must be independently declared read-only")
        if dcc_type == "obs" and step["kind"] not in ("obs_start", "obs_stop") and not readonly:
            raise ValueError("OBS log/probe roles require a genuinely read-only tool; no recording takeover")
        if step["kind"] == "obs_start" and not polling:
            output_schema = tool.get("outputSchema", {})
            context_schema = output_schema.get("properties", {}).get("context", {})
            candidates = [output_schema]
            if "context" in output_schema.get("required", []):
                candidates.append(context_schema)
            guaranteed_id = any(isinstance(schema, dict) and "recording_id" in schema.get("required", [])
                                and schema.get("properties", {}).get("recording_id", {}).get("type") == "string"
                                for schema in candidates)
            if not guaranteed_id:
                raise ValueError("OBS start output schema does not guarantee a recording_id; automation is NOT_RUN")
        return step, readonly

    def _invoke(self, slug, arguments, step, polling=False, observation_only=False):
        metadata = {"agent_context": {"session_id": "spatiallabs-software-" + self.plan["plan_id"]}}
        if step.get("lease_owner"):
            metadata["lease_owner"] = step["lease_owner"]
        response = self._json(["call", slug, "--json-file", "-", "--meta-json", json.dumps(metadata),
                               "--timeout-secs", "30"], arguments)
        observed = normalize(response)
        if observation_only:
            return observed  # Disk journal IDs can authorize observation, never mutation ownership.
        if observed["status"] == "pending" and isinstance(observed.get("job_id"), str):
            self.jobs.add(observed["job_id"])
        owned_poll = polling and observed.get("job_id") in self.jobs
        if (step["kind"] == "obs_start" and observed["status"] == "completed" and (not polling or owned_poll)
                and isinstance(observed.get("recording_id"), str)):
            self.recordings.add(observed["recording_id"])
        if step["kind"] == "obs_stop":
            def owned_values(item):
                if isinstance(item, dict):
                    return set().union(*(owned_values(v) for v in item.values())) if item else set()
                if isinstance(item, list):
                    return set().union(*(owned_values(v) for v in item)) if item else set()
                return {item} if isinstance(item, str) and item in self.recordings else set()

            owned = owned_values(arguments) if not polling else self.stop_jobs.get(observed.get("job_id"), set())
            if observed["status"] == "completed" and observed.get("recording_id") not in owned:
                raise ValueError("OBS stop did not confirm the exact owned recording ID; do not repeat it")
            if observed["status"] == "pending" and not polling:
                self.stop_jobs[observed.get("job_id")] = owned
            elif observed["status"] == "completed":
                self.recordings.difference_update(owned)
        return observed

    def _project_probe(self):
        step = self.probe
        self._describe(step["tool_slug"], (step, step["input_schema"], False))
        observed = self._invoke(step["tool_slug"], step["arguments"], step)
        if observed["status"] != "completed":
            raise ValueError("Project identity probe did not complete")
        path = _select(observed["output"], step["project_result_path"])
        if (not isinstance(path, str) or not Path(path).is_absolute() or ".." in Path(path).parts
                or os.path.normcase(os.path.abspath(path)) != os.path.normcase(os.path.abspath(self.plan["project_path"]))):
            raise ValueError("Live Unreal project differs from the reviewed isolated project")
        return observed

    def call(self, slug, arguments):
        entry = self._entry(slug, arguments)
        step, _schema, polling = entry
        step, readonly = self._describe(slug, entry)
        if slug == self.probe["tool_slug"]:
            return self._project_probe()
        if not readonly and step.get("dcc_type", "unreal") == "unreal":
            self._project_probe()  # observe project switches before every mutation
        if step["kind"] == "obs_start" and not polling:
            # Require a separate reviewed idle probe; never start/stop an existing recording.
            guard = step.get("idle_guard")
            if not isinstance(guard, dict) or guard.get("tool_slug") not in self.entries:
                raise ValueError("OBS start requires a reviewed read-only idle guard")
            guards = [item for item in self.entries[guard["tool_slug"]] if item[0]["kind"] == "preflight" and not item[2]]
            if len(guards) != 1:
                raise ValueError("OBS idle guard must identify one exact reviewed preflight step")
            guard_step, guard_readonly = self._describe(guard["tool_slug"], guards[0])
            if (not guard_readonly or guard_step.get("dcc_type") != "obs"
                    or guard["tool_slug"].split(".", 2)[:2] != slug.split(".", 2)[:2]):
                raise ValueError("OBS idle guard must be a read-only tool on the selected OBS instance")
            idle = self._invoke(guard["tool_slug"], guard_step["arguments"], guard_step)
            if idle["status"] != "completed" or _select(idle["output"], guard.get("recording_result_path")) is not False:
                raise ValueError("OBS has an existing/unknown recording; no takeover")
        if step["kind"] == "obs_stop" and not polling:
            parameter = step.get("recording_id_parameter")
            if not isinstance(parameter, list) or not parameter or parameter[-1] not in ("recording_id", "session_id"):
                raise ValueError("OBS stop needs an explicit recording_id/session_id parameter binding")
            if _select(arguments, parameter) not in self.recordings:
                raise ValueError("OBS stop must bind a recording confirmed started in this process")
        return self._invoke(slug, arguments, step, polling)

    def observe(self, slug, arguments):
        entry = self._entry(slug, arguments, observation_only=True)
        step, _readonly = self._describe(slug, entry)  # polling entries must be freshly read-only
        return self._invoke(slug, arguments, step, polling=True, observation_only=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare", help="Read-only: prepare a reviewable plan from a discovered typed-step spec")
    prepare.add_argument("spec")
    execute = sub.add_parser("run", help="One human authorization, followed by bounded unattended software checks")
    execute.add_argument("plan")
    args = parser.parse_args(argv)
    try:
        from spatiallabs_software import prepare_software_plan, run_software_plan

        if args.action == "prepare":
            spec = json.loads(Path(args.spec).read_text(encoding="utf-8-sig"))
            result = prepare_software_plan(**spec)
        else:
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise PermissionError("authorization_required: software execution needs an initial visible operator authorization")
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
            transport = CliTransport(plan)
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            print("Pinned CLI: {} (SHA-256 {})".format(transport.executable, transport.executable_sha256))
            print("Authorize only these software steps in the isolated project and task-owned Unreal/OBS instances.")
            print("This grant does not install vendor code, accept licenses or authorize hardware acceptance.")
            phrase = "RUN SOFTWARE CHECKS " + plan["plan_id"]
            print("Type exactly: " + phrase)
            if input("> ") != phrase:
                raise PermissionError("Software plan was not authorized")
            from operator_install import _ConsoleAuthority

            result = run_software_plan(plan, transport, _ConsoleAuthority(plan["plan_id"], "software_validation"))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result.get("status") not in ("failed", "blocked", "uncertain", "repair_required") else 2
    except (ValueError, OSError, KeyError, TypeError, EOFError, RuntimeError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

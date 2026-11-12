"""Reviewable, bounded software validation through an injected typed transport.

This module neither launches a CLI nor accepts vendor terms. An in-process
authority must authorize the entire hash-bound plan before any call or write.
Transports must bound each call to 30 seconds; no polling sleeps or action
retries are implemented. Restart recovery is deliberately observation-only.
"""

import copy
import json
import os
import re
import tempfile
from pathlib import Path

from spatiallabs_project import _file_hash, _hash, _inside, _json_bytes, _lineage, _project, _walk

KINDS = frozenset(("preflight", "build", "launch", "interaction", "logs", "performance", "obs_start", "obs_stop", "repair"))
MAX_STEPS = 32
MAX_POLLS = 30
MAX_JSON = 1024 * 1024
MAX_JOURNAL = 40 * 1024 * 1024
EVIDENCE_ROOT = "Evidence/SpatialLabsSoftware"
PROJECT_PROBE_NAME = "unreal_pie__pie_get_status"
PROJECT_RESULT_PATH = ["context", "perf", "project_name"]
RAW_WORDS = re.compile(r"(?:^|_)(?:code|command|exec|eval|evaluate|python|script|shell|raw|bridge)(?:_|$)", re.I)
VENDOR_ACTIONS = re.compile(
    r"(?:^|_)(?:install|uninstall|download|upgrade|activate_runtime|set_runtime|update_driver|"
    r"license_accept|accept_license|accept_terms|accept_eula|eula_accept|accept_vendor_terms)(?:_|$)", re.I)
STEP_FIELDS = frozenset((
    "id", "kind", "tool_slug", "input_schema", "arguments", "dcc_type", "instance_id", "instance_short",
    "poll_tool_slug", "status_arguments_template", "status_schema", "max_poll_count", "assertions",
    "project_result_path", "idle_guard", "lease_owner", "annotations", "idempotent", "retry_safe", "reviewed_repair",
    "recording_id_parameter", "output_schema",
))


def _text(value, label, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("{} must be a nonempty bounded string".format(label))
    return value


def _bounded_json(value, label, max_bytes=MAX_JSON, max_depth=24):
    def walk(item, depth=0):
        if depth > max_depth:
            raise ValueError("{} nesting exceeds {} levels".format(label, max_depth))
        if isinstance(item, dict):
            if len(item) > 256 or any(not isinstance(key, str) for key in item):
                raise ValueError("{} object is not bounded JSON".format(label))
            for child in item.values():
                walk(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 10000:
                raise ValueError("{} array exceeds its bound".format(label))
            for child in item:
                walk(child, depth + 1)
    walk(value)
    try:
        encoded = _json_bytes(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("{} must contain finite JSON data".format(label))
    if len(encoded) > max_bytes:
        raise ValueError("{} exceeds its {} byte bound".format(label, max_bytes))
    return json.loads(encoded.decode("utf-8"))


def _integer(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError("{} must be an integer from {} to {}".format(label, low, high))
    return value


def _schema(schema, arguments=None):
    schema = _bounded_json(schema, "JSON Schema")
    if not isinstance(schema, dict) or schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
        raise ValueError("A complete object input_schema with properties is required")

    def inspect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("$ref", "$dynamicRef") and (not isinstance(child, str) or not child.startswith("#")):
                    raise ValueError("External schema references are forbidden; no network resolution")
                if key == "properties" and isinstance(child, dict):
                    if any(RAW_WORDS.search(name.lower().replace("-", "_")) for name in child):
                        raise ValueError("Raw command/code/script parameters are outside software-validation scope")
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    inspect(schema)
    try:
        from jsonschema import validators
    except ImportError:
        raise ValueError("jsonschema runtime is required for full parameter validation; execution refused")
    try:
        validator_type = validators.validator_for(schema)
        validator_type.check_schema(schema)
        if arguments is not None:
            if not isinstance(arguments, dict) or set(arguments) - set(schema["properties"]):
                raise ValueError("Arguments must be an exact object of declared schema properties")
            validator_type(schema).validate(arguments)
    except (ValueError, RecursionError):
        raise
    except Exception as exc:
        raise ValueError("JSON Schema validation failed: {}".format(str(exc)[:1000]))
    return schema


def _binding(instance_id, short=None):
    instance_id = _text(instance_id, "instance_id")
    if short is None:
        if len(instance_id) > 32:
            raise ValueError("A full instance_id needs the explicit instance_short from live inventory")
        short = instance_id
    short = _text(short, "instance_short", 128)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", short):
        raise ValueError("instance_short must be the exact inventory routing token")
    return instance_id, short


def _slug(slug, dcc_type, short):
    slug = _text(slug, "tool_slug", 512)
    parts = slug.split(".")
    if len(parts) != 3 or parts[0] != dcc_type or parts[1] != short or not parts[2]:
        raise ValueError("Tool/poll slug is not bound to the exact reviewed DCC routing token")
    if RAW_WORDS.search(parts[2]) or VENDOR_ACTIONS.search(parts[2]):
        raise ValueError("Raw execution and vendor installation tools are outside software-validation scope")
    return slug


def _path_selector(value, label):
    if not isinstance(value, list) or not 1 <= len(value) <= 16:
        raise ValueError("{} needs a nonempty result path with at most 16 keys".format(label))
    if any(isinstance(key, bool) or not isinstance(key, (str, int)) or (isinstance(key, int) and key < 0) for key in value):
        raise ValueError("{} result path contains an invalid key".format(label))
    return list(value)


def _select(value, path):
    for key in path:
        value = value[key]
    return value


def _paths(root, value, key=""):
    if isinstance(value, dict):
        for name, child in value.items():
            if RAW_WORDS.search(name.lower().replace("-", "_")):
                raise ValueError("Raw command/code/script arguments are forbidden")
            _paths(root, child, name)
    elif isinstance(value, list):
        for child in value:
            _paths(root, child, key)
    elif isinstance(value, str) and value not in ("$job_id", "$recording_id"):
        normalized = key.lower().replace("-", "_")
        path_key = bool(re.search(r"(?:^|_)(?:path|directory|dir|folder|filename|file)(?:_|$)", normalized))
        path_key = path_key or normalized in ("project", "projectpath", "filepath", "outputpath", "destinationpath")
        if path_key:
            path = Path(value)
            if not path.is_absolute():
                raise ValueError("Filesystem path arguments must be absolute and project-scoped")
            _inside(root, path)


def _tokens(value):
    if isinstance(value, dict):
        return [token for child in value.values() for token in _tokens(child)]
    if isinstance(value, list):
        return [token for child in value for token in _tokens(child)]
    if isinstance(value, str) and "$" in value:
        if value not in ("$job_id", "$recording_id"):
            raise ValueError("Only exact $job_id and $recording_id placeholders are supported")
        return [value]
    return []


def _render(value, job_id=None, recording_id=None):
    if isinstance(value, dict):
        return {key: _render(child, job_id, recording_id) for key, child in value.items()}
    if isinstance(value, list):
        return [_render(child, job_id, recording_id) for child in value]
    if value == "$job_id":
        return _text(job_id, "current job_id")
    if value == "$recording_id":
        return _text(recording_id, "current owned recording_id")
    return value


def _source(root):
    _digest, files = _lineage(root)
    files = [(name, digest) for name, digest in files
             if name != EVIDENCE_ROOT and not name.startswith(EVIDENCE_ROOT + "/")]
    plugin = _inside(root, root / "Plugins" / "SpatialLabs")
    if plugin.is_dir():
        total = 0
        for path, directory in _walk(plugin, exclude_generated=True):
            if not directory:
                total += path.stat().st_size
                if total > 8 * 1024 ** 3 or len(files) >= 100000:
                    raise ValueError("Software source lineage exceeds bounded inventory")
                files.append((path.relative_to(root).as_posix(), _file_hash(path)))
    files.sort()
    return _hash(_json_bytes(files)), len(files)


def prepare_software_plan(project_path, instance_id, steps, max_attempts=1, instance_short=None):
    """Prepare without writing/calling. Schemas/slugs must come from discovery.

    ``status_schema`` is the poll tool's *input* JSON Schema. Its concrete
    arguments are validated again after exact current-job token replacement.
    OBS steps carry their own dcc_type='obs', instance_id and instance_short.
    The CLI transport must freshly recheck all identities and schemas.
    """
    root, path, descriptor = _project(project_path)
    association = descriptor.get("EngineAssociation")
    if not isinstance(association, str) or not re.fullmatch(r"5\.\d+(?:\.\d+)?", association):
        raise ValueError("Only explicit UE 5.x source/Blueprint projects are supported; custom/other engines need review")
    modules = descriptor.get("Modules", [])
    if not isinstance(modules, list):
        raise ValueError("Project Modules must be an array")
    source = _inside(root, root / "Source")
    content = _inside(root, root / "Content")
    if modules and not source.is_dir():
        raise ValueError("C++ project is missing its editable Source directory")
    if not source.is_dir() and (modules or not content.is_dir()):
        raise ValueError("An editable Source or non-module Blueprint Content project is required")
    _integer(max_attempts, "max_attempts", 1, 2)
    instance_id, short = _binding(instance_id, instance_short)
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError("Software plan requires one to 32 explicitly reviewed typed steps")
    normalized = []
    ids = set()
    obs_binding = None
    for original in steps:
        step = _bounded_json(original, "software step")
        if not isinstance(step, dict) or set(step) - STEP_FIELDS:
            raise ValueError("Unsupported software step fields")
        identifier = _text(step.get("id"), "step.id", 64)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier) or identifier in ids:
            raise ValueError("Step IDs must be unique safe identifiers")
        ids.add(identifier)
        kind = step.get("kind")
        if kind not in KINDS:
            raise ValueError("Unsupported software step kind")
        dcc_type = step.get("dcc_type", "unreal")
        if dcc_type not in ("unreal", "obs") or (kind.startswith("obs_") and dcc_type != "obs"):
            raise ValueError("OBS operations need an explicit OBS binding")
        if dcc_type == "obs":
            if kind not in ("preflight", "obs_start", "obs_stop", "logs"):
                raise ValueError("Only recording and read-only probe/log operations target OBS")
            binding = _binding(step.get("instance_id"), step.get("instance_short"))
            if obs_binding is not None and obs_binding != binding:
                raise ValueError("One plan cannot operate multiple OBS instances")
            obs_binding = binding
        else:
            binding = (instance_id, short)
            if step.get("instance_id", instance_id) != instance_id or step.get("instance_short", short) != short:
                raise ValueError("Unreal step cannot select a foreign instance")
        step.update(dcc_type=dcc_type, instance_id=binding[0], instance_short=binding[1])
        _slug(step.get("tool_slug"), dcc_type, binding[1])
        arguments = step.get("arguments")
        if not isinstance(arguments, dict):
            raise ValueError("Step arguments must be an exact object")
        _paths(root, arguments)
        tokens = _tokens(arguments)
        if kind == "obs_stop":
            if tokens != ["$recording_id"]:
                raise ValueError("OBS stop must identify only this run's $recording_id")
            selector = _path_selector(step.get("recording_id_parameter"), "recording_id_parameter")
            if selector[-1] not in ("recording_id", "session_id"):
                raise ValueError("OBS stop must bind an actual recording_id/session_id parameter, never a note")
            try:
                if _select(arguments, selector) != "$recording_id":
                    raise ValueError("OBS stop parameter selector does not bind the owned recording ID")
            except (KeyError, IndexError, TypeError):
                raise ValueError("OBS recording_id_parameter does not select an actual argument")
            # The concrete owned ID is schema-validated immediately before its call.
            step["input_schema"] = _schema(step.get("input_schema"))
        else:
            if tokens:
                raise ValueError("Action arguments cannot contain runtime placeholders")
            step["input_schema"] = _schema(step.get("input_schema"), arguments)
        if "poll_tool_slug" in step:
            _slug(step["poll_tool_slug"], dcc_type, binding[1])
            template = step.get("status_arguments_template")
            if not isinstance(template, dict):
                raise ValueError("Status arguments need an exact reviewed template object")
            _paths(root, template)
            _tokens(template)
            step["status_schema"] = _schema(step.get("status_schema"))
            if not _tokens(template):
                _schema(step["status_schema"], template)
        elif any(key in step for key in ("status_arguments_template", "status_schema")):
            raise ValueError("A status template/schema requires a discovered poll_tool_slug")
        step["max_poll_count"] = _integer(step.get("max_poll_count", 3), "max_poll_count", 1, MAX_POLLS)
        assertions = step.get("assertions", [])
        if not isinstance(assertions, list) or len(assertions) > 16:
            raise ValueError("Each step supports at most 16 simple assertions")
        for assertion in assertions:
            if not isinstance(assertion, dict) or set(assertion) - {"path", "op", "value"}:
                raise ValueError("Assertion must contain only path, op and optional value")
            _path_selector(assertion.get("path"), "assertion.path")
            if assertion.get("op") not in ("equals", "nonempty", "exists"):
                raise ValueError("Only equals, nonempty and exists assertions are supported; no eval")
            if assertion["op"] == "equals" and "value" not in assertion:
                raise ValueError("equals assertion requires its exact value")
        step["assertions"] = assertions
        if "project_result_path" in step:
            _path_selector(step["project_result_path"], "project_result_path")
        if "lease_owner" in step:
            _text(step["lease_owner"], "lease_owner")
        for field in ("idempotent", "retry_safe", "reviewed_repair"):
            if field in step and not isinstance(step[field], bool):
                raise ValueError("{} must be a boolean planning hint, never an authorization grant".format(field))
        if kind == "repair" and step.get("reviewed_repair") is not True:
            raise ValueError("A fixed typed repair must be explicitly marked for plan review")
        normalized.append(step)
    first = normalized[0]
    if first["kind"] != "preflight" or first["dcc_type"] != "unreal" or not first.get("project_result_path"):
        raise ValueError("First step must be a read-only Unreal project probe with project_result_path")
    if (first["tool_slug"].split(".")[2] != PROJECT_PROBE_NAME or first["project_result_path"] != PROJECT_RESULT_PATH
            or first["arguments"] != {} or first["input_schema"]["properties"] != {}):
        raise ValueError("First project probe must be the discovered unreal_pie__pie_get_status host capability with empty arguments")
    starts = [step for step in normalized if step["kind"] == "obs_start"]
    stops = [step for step in normalized if step["kind"] == "obs_stop"]
    if len(starts) > 1 or len(stops) > 1 or bool(starts) != bool(stops):
        raise ValueError("OBS requires exactly one paired start/stop, or neither")
    if starts:
        start, stop = starts[0], stops[0]
        if normalized.index(start) >= normalized.index(stop):
            raise ValueError("OBS stop must follow its owned start")
        guard = start.get("idle_guard")
        if not isinstance(guard, dict) or set(guard) != {"tool_slug", "recording_result_path"}:
            raise ValueError("OBS start requires a reviewed idle_guard")
        _path_selector(guard["recording_result_path"], "idle_guard.recording_result_path")
        guards = [step for step in normalized[:normalized.index(start)]
                  if step["tool_slug"] == guard["tool_slug"] and step["kind"] == "preflight" and step["dcc_type"] == "obs"]
        if len(guards) != 1:
            raise ValueError("Idle guard must identify a prior reviewed OBS read-only preflight step")
    if len([step for step in normalized if step["kind"] == "repair"]) > 1:
        raise ValueError("Only one fixed reviewed repair step is supported")
    digest, count = _source(root)
    plan = {"schema_version": 1, "kind": "spatiallabs_software_validation", "project_path": str(path),
            "project_root": str(root), "engine_association": association,
            "project_kind": "source" if source.is_dir() else "blueprint", "source_hash": digest, "source_file_count": count,
            "instance_id": instance_id, "instance_short": short, "steps": normalized, "max_attempts": max_attempts,
            "call_timeout_seconds": 30, "evidence_scope": EVIDENCE_ROOT + "/<plan_id>/**",
            "scope": "software_only; exact reviewed typed steps in the isolated project and named instances",
            "retry_policy": "Each action at most once; no automatic action retries or generated repairs",
            "resume_policy": "Existing unfinished journals permit status observations only; continuation needs a new reviewed plan",
            "vendor_terms": "No terms accepted, vendor installation, runtime changes or hardware acceptance authorized"}
    plan["plan_id"] = _hash(_json_bytes(plan))
    return plan


def _validate_plan(plan):
    plan = _bounded_json(plan, "software plan")
    payload = dict(plan)
    plan_id = payload.pop("plan_id", None)
    if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{64}", plan_id) or _hash(_json_bytes(payload)) != plan_id:
        raise ValueError("Software plan hash mismatch; prepare and review a new plan")
    rebuilt = prepare_software_plan(plan.get("project_path"), plan.get("instance_id"), plan.get("steps"),
                                    plan.get("max_attempts"), plan.get("instance_short"))
    changed = rebuilt["source_hash"] != plan["source_hash"] or rebuilt["source_file_count"] != plan["source_file_count"]
    for field in ("source_hash", "source_file_count", "plan_id"):
        rebuilt[field] = plan[field]
    if rebuilt != plan:
        raise ValueError("Project source lineage or reviewed software plan changed")
    return plan, changed


def _write(root, path, value):
    _inside(root, path)
    _inside(root, path.parent)
    payload = _json_bytes(value)
    descriptor, temporary = tempfile.mkstemp(prefix=".software-", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _inside(root, path)
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            _inside(root, temporary).unlink()


def _save(root, directory, journal):
    payload = dict(journal)
    payload.pop("journal_hash", None)
    journal["journal_hash"] = _hash(_json_bytes(payload))
    _bounded_json(journal, "journal", MAX_JOURNAL, 32)
    _write(root, directory / "journal.json", journal)


def _response(value):
    value = _bounded_json(value, "transport response")
    if not isinstance(value, dict) or value.get("status") not in ("completed", "pending", "failed"):
        raise ValueError("Transport must normalize a completed, pending or failed structured result")
    if "output" not in value:
        value["output"] = {}
    return value


def _assertions(step, output, project_path):
    if step["dcc_type"] == "unreal" and step["kind"] == "preflight" and step.get("project_result_path"):
        try:
            observed = _select(output, step.get("project_result_path", []))
        except (KeyError, IndexError, TypeError):
            return False, "Live project identity is absent from the declared result path"
        if not isinstance(observed, str) or os.path.normcase(os.path.abspath(observed)) != os.path.normcase(os.path.abspath(project_path)):
            return False, "Live Unreal project differs from the reviewed project"
    for assertion in step["assertions"]:
        try:
            value = _select(output, assertion["path"])
            exists = True
        except (KeyError, IndexError, TypeError):
            value, exists = None, False
        op = assertion["op"]
        passed = exists if op == "exists" else exists and value not in (None, "", [], {}) if op == "nonempty" else exists and _json_bytes(value) == _json_bytes(assertion["value"])
        if not passed:
            return False, "Business assertion failed at {} ({})".format(assertion["path"], op)
    return True, None


def _complete(step, entry, response, project_path, owned, can_own=False):
    entry["output"] = response["output"]
    if response["status"] == "failed":
        entry.update(call_state="failed", status="FAIL", reason="Typed tool reported failure; no blind retry")
        return
    if response["status"] == "pending":
        job_id = response.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            entry.update(call_state="uncertain", status="NOT_RUN", reason="Pending call omitted its durable job_id")
        else:
            entry.update(call_state="pending", job_id=_text(job_id, "job_id"), status="NOT_RUN", reason="Job pending")
        return
    if step["kind"] == "obs_start":
        recording_id = response.get("recording_id")
        if not isinstance(recording_id, str) or not recording_id.strip():
            entry.update(call_state="uncertain", status="NOT_RUN", reason="OBS start completed without an owned recording_id")
            return
        entry["recording_id"] = _text(recording_id, "recording_id")
        if can_own:
            owned["recording_id"] = recording_id
    if step["kind"] == "obs_stop":
        expected = owned.get("recording_id", entry.get("recording_id"))
        if expected is None or response.get("recording_id") != expected:
            entry.update(call_state="uncertain", status="NOT_RUN", reason="OBS stop did not confirm the exact owned recording_id")
            return
    passed, reason = _assertions(step, response["output"], project_path)
    has_assertions = bool(step["assertions"]) or bool(step.get("project_result_path"))
    entry.update(call_state="completed" if passed else "failed", status="PASS" if passed and has_assertions else "NOT_RUN" if passed else "FAIL",
                 reason=reason if not passed else None if has_assertions else "CALL_COMPLETED only; no business assertions supplied")
    if step["kind"] == "obs_stop" and passed:
        owned.clear()


def _status_observe(plan, step, entry, transport, journal, root, directory, owned, can_own=False):
    if not step.get("poll_tool_slug"):
        entry["reason"] = "Outcome needs observation but no reviewed status query exists; do not resend the action"
        return
    template = step["status_arguments_template"]
    job_id = entry.get("job_id")
    if job_id is None:
        if _tokens(template):
            entry["reason"] = "Lost acknowledgement has no bound job_id; status template cannot safely select a job"
            return
        # A generic read-only observation is evidence, never proof that an
        # unacknowledged mutation belongs to this plan or completed.
        try:
            _schema(step["status_schema"], template)
            journal["observations"].append({"step_id": step["id"], "state": "querying_unbound_status"})
            _save(root, directory, journal)
            observer = transport.call if can_own else getattr(transport, "observe", transport.call)
            observation = _response(observer(step["poll_tool_slug"], copy.deepcopy(template)))
            entry["unbound_status_observation"] = observation
        except Exception as exc:
            entry["observation_error"] = str(exc)[:1000]
        entry.update(call_state="uncertain", status="NOT_RUN", reason="Observed status cannot bind an unacknowledged action; no replay or cleanup")
        return
    if "$job_id" not in _tokens(template):
        entry.update(call_state="uncertain", status="NOT_RUN", reason="Status query does not explicitly bind the current job_id")
        return
    for _index in range(step["max_poll_count"]):
        try:
            arguments = _render(template, job_id=job_id, recording_id=entry.get("recording_id"))
            _paths(root, arguments)
            _schema(step["status_schema"], arguments)
            entry["polls"] += 1
            journal["observations"].append({"step_id": step["id"], "state": "querying", "job_id": job_id})
            _save(root, directory, journal)
            observer = transport.call if can_own else getattr(transport, "observe", transport.call)
            response = _response(observer(step["poll_tool_slug"], arguments))
            if response.get("job_id") != job_id:
                raise ValueError("Status response did not prove the exact current job_id")
        except Exception as exc:
            entry.update(call_state="uncertain", status="NOT_RUN", reason="Status observation failed: " + str(exc)[:1000])
            return
        _complete(step, entry, response, plan["project_path"], owned, can_own)
        _save(root, directory, journal)
        if entry["call_state"] != "pending":
            return
    entry["reason"] = "Bounded poll limit reached; resume may query status only"


def _execute(plan, step, entry, transport, journal, root, directory, owned):
    arguments = _render(step["arguments"], recording_id=owned.get("recording_id"))
    _paths(root, arguments)
    _schema(step["input_schema"], arguments)
    if step["kind"] == "obs_stop":
        expected = owned.get("recording_id")
        if expected is None or _select(arguments, step["recording_id_parameter"]) != expected:
            raise ValueError("OBS stop argument must bind the recording started by this invocation")
        entry["recording_id"] = expected
    entry.update(call_state="attempting", attempts=entry["attempts"] + 1, reason="Action may have been submitted")
    _save(root, directory, journal)  # Must be durable BEFORE submitting an action.
    try:
        response = _response(transport.call(step["tool_slug"], arguments))
    except Exception as exc:
        entry.update(call_state="uncertain", status="NOT_RUN", reason="Call outcome uncertain: " + str(exc)[:1000])
    else:
        _complete(step, entry, response, plan["project_path"], owned, can_own=True)
    _save(root, directory, journal)
    if entry["call_state"] in ("pending", "uncertain"):
        _status_observe(plan, step, entry, transport, journal, root, directory, owned, can_own=True)
        _save(root, directory, journal)


def _guard(step, plan, transport, journal, root, directory):
    guard = step["idle_guard"]
    guard_step = next(candidate for candidate in plan["steps"][:plan["steps"].index(step)]
                      if candidate["tool_slug"] == guard["tool_slug"] and candidate["kind"] == "preflight"
                      and candidate["dcc_type"] == "obs")
    journal["observations"].append({"step_id": step["id"], "state": "checking_obs_idle"})
    _save(root, directory, journal)
    try:
        response = _response(transport.call(guard_step["tool_slug"], copy.deepcopy(guard_step["arguments"])))
        return response["status"] == "completed" and _select(response["output"], guard["recording_result_path"]) is False
    except Exception:
        return False


def _report(plan, journal, directory):
    states = [entry["call_state"] for entry in journal["steps"]]
    if any(state in ("uncertain", "attempting") for state in states):
        status = "uncertain"
    elif "failed" in states:
        status = "repair_required"
    elif all(state in ("completed", "skipped") for state in states):
        status = "completed"
    else:
        status = "blocked"
    if journal.get("resume_only") and status == "completed":
        status = "blocked"
    return {"status": status, "scope": "software_only", "plan_id": plan["plan_id"], "skill_run_id": plan["plan_id"],
            "project_path": plan["project_path"], "source_hash": plan["source_hash"], "evidence_directory": str(directory),
            "steps": copy.deepcopy(journal["steps"]), "resume_only": journal.get("resume_only", False),
            "source_lineage_changed": journal.get("source_lineage_changed", False),
            "software_acceptance": "PASS" if status == "completed" and all(entry["status"] == "PASS" for entry in journal["steps"]) else "NOT_RUN",
            "hardware_acceptance": {key: "NOT_RUN" for key in ("stereo", "tracking", "comfort", "device_performance")},
            "limitations": ["Software call completion is not device, stereo, tracking, comfort or device performance acceptance.",
                            "No generated repairs or blind retries; failures need a reviewed continuation plan.",
                            "Existing unfinished journals permit status-only recovery, never new mutations or disk-only OBS cleanup.",
                            "The injected transport must enforce a per-call timeout of at most 30 seconds and fresh discovery/schema checks."]}


def run_software_plan(plan, transport, authority=None):
    """Execute exact reviewed steps once; persist uncertainty before recovery.

    ``authority.require(plan, 'software_validation')`` is an in-process grant,
    not a JSON flag. No authority means zero transport calls and project writes.
    ``transport.call(slug, arguments)`` returns normalized status plus original
    structured data in ``output``. Pending/status responses bind a durable
    ``job_id``; OBS start additionally binds a ``recording_id``.
    """
    plan, source_changed = _validate_plan(plan)
    root = Path(plan["project_root"])
    directory = _inside(root, root / EVIDENCE_ROOT / plan["plan_id"])
    if source_changed and not _inside(root, directory / "journal.json").is_file():
        raise ValueError("Project source lineage changed; a new action plan is required")
    if authority is None or isinstance(authority, dict) or not callable(getattr(authority, "require", None)):
        raise PermissionError("authorization_required: an exact in-process software-validation grant is required")
    if not callable(getattr(transport, "call", None)):
        raise ValueError("A bounded typed transport is required")
    if authority.require(plan, "software_validation") is False:
        raise PermissionError("Software authority refused this plan")
    directory.mkdir(parents=True, exist_ok=True)
    _inside(root, directory)
    lock_path = _inside(root, directory / "runner.lock")
    try:
        lock = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Software plan already has an execution lock; do not steal it")
    nonce = os.urandom(24).hex()
    owned = {}  # Never reconstructed from editable on-disk journal data.
    journal = None
    try:
        with os.fdopen(lock, "w") as stream:
            stream.write(nonce)
            stream.flush()
            os.fsync(stream.fileno())
        journal_path = _inside(root, directory / "journal.json")
        existing = journal_path.exists()
        if existing:
            if journal_path.stat().st_size > MAX_JOURNAL:
                raise ValueError("Software journal exceeds its 40 MiB recovery bound")
            journal = _bounded_json(json.loads(journal_path.read_text(encoding="utf-8")), "journal", MAX_JOURNAL, 32)
            content = dict(journal)
            checksum = content.pop("journal_hash", None)
            if checksum != _hash(_json_bytes(content)) or journal.get("plan_id") != plan["plan_id"]:
                raise ValueError("Software journal integrity/scope mismatch; no actions or cleanup")
            if [entry.get("id") for entry in journal.get("steps", [])] != [step["id"] for step in plan["steps"]]:
                raise ValueError("Journal step identity mismatch")
            journal["source_lineage_changed"] = source_changed
            if all(entry.get("call_state") in ("completed", "skipped") for entry in journal["steps"]):
                if source_changed:
                    journal["resume_only"] = True
                report = _report(plan, journal, directory)
                _write(root, directory / "report.json", report)
                return report
            journal["resume_only"] = True
            for step, entry in zip(plan["steps"], journal["steps"]):
                if entry["call_state"] in ("attempting", "pending", "uncertain"):
                    if entry["call_state"] == "attempting":
                        entry.update(call_state="uncertain", status="NOT_RUN", reason="Interrupted after journaled action attempt")
                    _status_observe(plan, step, entry, transport, journal, root, directory, owned, can_own=False)
            _save(root, directory, journal)
        else:
            journal = {"schema_version": 1, "plan_id": plan["plan_id"], "resume_only": False, "observations": [],
                       "steps": [{"id": step["id"], "kind": step["kind"], "call_state": "not_run", "status": "NOT_RUN",
                                  "attempts": 0, "polls": 0, "reason": "Not executed"} for step in plan["steps"]]}
            _write(root, directory / "plan.json", plan)
            _save(root, directory, journal)
            try:
                for step, entry in zip(plan["steps"], journal["steps"]):
                    if step["kind"] == "obs_stop" and not owned:
                        entry.update(call_state="skipped", reason="No recording was confirmed as started by this invocation")
                        _save(root, directory, journal)
                        continue
                    if step["kind"] == "obs_start" and not _guard(step, plan, transport, journal, root, directory):
                        entry["reason"] = "OBS is recording or idle state is unknown; no takeover"
                        _save(root, directory, journal)
                        break
                    _execute(plan, step, entry, transport, journal, root, directory, owned)
                    if entry["call_state"] != "completed":
                        break
            finally:
                if owned:
                    stop_index = next(index for index, step in enumerate(plan["steps"]) if step["kind"] == "obs_stop")
                    stop_entry = journal["steps"][stop_index]
                    if stop_entry["call_state"] == "not_run":
                        stop_entry["cleanup"] = True
                        _execute(plan, plan["steps"][stop_index], stop_entry, transport, journal, root, directory, owned)
        report = _report(plan, journal, directory)
        _write(root, directory / "report.json", report)
        return report
    finally:
        # Preserve a replaced/foreign lock. A nonce is coordination ownership,
        # never a grant to remove another writer's file or change its ACL.
        try:
            if lock_path.is_file() and not lock_path.is_symlink():
                _inside(root, lock_path)
                if lock_path.read_text() == nonce:
                    lock_path.unlink()
        except (OSError, ValueError):
            pass

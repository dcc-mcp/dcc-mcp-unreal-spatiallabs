"""Fake subprocess integration for CLI recording ownership; no CLI/DCC is run."""

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "skills/unreal-spatiallabs/scripts/software_runner.py"
UE_FULL = "unreal-full-owned-fixture"
UE_SHORT = "ue1234"
OBS_FULL = "obs-full-owned-fixture"
OBS_SHORT = "obs1234"
PROBE = "unreal.{}.unreal_pie__pie_get_status".format(UE_SHORT)
GUARD = "obs.{}.recording_status".format(OBS_SHORT)
START = "obs.{}.start_recording".format(OBS_SHORT)
POLL = "obs.{}.jobs_get_status".format(OBS_SHORT)
STOP = "obs.{}.stop_recording".format(OBS_SHORT)
RECORDING_ID = "owned-fixture-recording"
JOB_ID = "owned-fixture-start-job"


@pytest.fixture
def api():
    spec = importlib.util.spec_from_file_location("spatiallabs_cli_obs_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schema(properties=None, required=None):
    result = {"type": "object", "properties": properties or {}, "additionalProperties": False}
    if required:
        result["required"] = required
    return result


@pytest.fixture
def plan(tmp_path):
    root = tmp_path / "Isolated Project"
    root.mkdir()
    project_path = root / "Demo.uproject"
    project_path.write_text('{"EngineAssociation":"5.8"}', encoding="utf-8")
    obs_binding = {"dcc_type": "obs", "instance_id": OBS_FULL, "instance_short": OBS_SHORT}
    probe = {
        "id": "probe", "kind": "preflight", "tool_slug": PROBE,
        "input_schema": schema(), "arguments": {},
        "project_result_path": ["context", "perf", "project_name"],
    }
    guard = dict(
        obs_binding, id="obs_idle", kind="preflight", tool_slug=GUARD,
        input_schema=schema(), arguments={},
    )
    start = dict(
        obs_binding, id="record", kind="obs_start", tool_slug=START,
        input_schema=schema({"output_path": {"type": "string"}}, ["output_path"]),
        arguments={"output_path": str(root / "Saved/Owned.mkv")},
        poll_tool_slug=POLL,
        status_schema=schema({"job_id": {"type": "string"}}, ["job_id"]),
        status_arguments_template={"job_id": "$job_id"},
        idle_guard={"tool_slug": GUARD, "recording_result_path": ["context", "recording_active"]},
    )
    stop = dict(
        obs_binding, id="stop", kind="obs_stop", tool_slug=STOP,
        input_schema=schema({"recording_id": {"type": "string"}}, ["recording_id"]),
        arguments={"recording_id": "$recording_id"}, recording_id_parameter=["recording_id"],
    )
    return {
        "plan_id": "f" * 64, "project_root": str(root), "project_path": str(project_path),
        "instance_id": UE_FULL, "instance_short": UE_SHORT, "steps": [probe, guard, start, stop],
    }


class FakeCli:
    """The complete subprocess boundary is synthetic, including list/describe."""

    def __init__(self, plan, active=False):
        self.plan = plan
        self.active = active
        self.calls = []
        self.commands = []
        self.start_output_schema = schema(
            {"context": schema({"recording_id": {"type": "string"}}, ["recording_id"])}, ["context"]
        )
        self.readonly_overrides = {}
        self.stop_recording_id = RECORDING_ID
        self.definitions = {}
        for step in plan["steps"]:
            self.definitions[step["tool_slug"]] = (step["input_schema"], step["kind"] == "preflight")
            if step.get("poll_tool_slug"):
                self.definitions[step["poll_tool_slug"]] = (step["status_schema"], True)

    def __call__(self, command, **kwargs):
        assert command[0] == str(Path(sys.executable).resolve())
        assert command[1:5] == ["--no-update-maintenance", "--non-interactive", "--output", "json"]
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 30
        self.commands.append(list(command))
        args = command[5:]
        action = args[0]
        if action == "list":
            response = {
                "instances": [
                    {"dcc_type": "unreal", "instance_id": UE_FULL, "instance_short": UE_SHORT,
                     "direct_control": {"ready": True}},
                    {"dcc_type": "obs", "instance_id": OBS_FULL, "instance_short": OBS_SHORT,
                     "direct_control": {"ready": True}},
                ]
            }
        elif action == "describe":
            slug = args[1]
            input_schema, readonly = self.definitions[slug]
            readonly = self.readonly_overrides.get(slug, readonly)
            tool = {
                "name": slug.split(".", 2)[-1], "inputSchema": input_schema,
                "annotations": {"readOnlyHint": readonly, "destructiveHint": readonly is False},
            }
            if slug == START:
                tool["outputSchema"] = copy.deepcopy(self.start_output_schema)
            response = {
                "record": {"tool_slug": slug, "instance_id": UE_FULL if slug == PROBE else OBS_FULL},
                "tool": tool,
            }
        elif action == "call":
            slug = args[1]
            arguments = json.loads(kwargs["input"])
            self.calls.append((slug, arguments))
            response = self._call(slug, arguments)
        else:
            raise AssertionError("Unexpected subprocess action {}".format(action))
        return SimpleNamespace(returncode=0, stdout=json.dumps(response), stderr="")

    def _call(self, slug, arguments):
        if slug == PROBE:
            assert arguments == {}
            return {"output": {"success": True, "context": {"perf": {"project_name": self.plan["project_path"]}}}}
        if slug == GUARD:
            assert arguments == {}
            return {"output": {"success": True, "context": {"recording_active": self.active}}}
        if slug == START:
            assert not self.active, "The runner must never start over an existing recording"
            self.active = True
            return {"output": {"status": "pending", "job_id": JOB_ID}}
        if slug == POLL:
            assert arguments["job_id"] in (JOB_ID, "old-journal-job")
            return {
                "output": {
                    "status": "completed", "job_id": arguments["job_id"],
                    "result": {"success": True, "context": {"recording_id": RECORDING_ID}},
                }
            }
        if slug == STOP:
            assert arguments == {"recording_id": RECORDING_ID}
            self.active = False
            return {"output": {"success": True, "context": {"recording_id": self.stop_recording_id}}}
        raise AssertionError("Unreviewed fixture call {}".format(slug))


def transport_for(api, plan, fake):
    # sys.executable is only hashed; fake replaces every subprocess invocation.
    return api.CliTransport(plan, runner=fake, executable=sys.executable)


def test_pending_obs_start_poll_then_stop_preserves_exact_process_ownership(api, plan):
    fake = FakeCli(plan)
    transport = transport_for(api, plan, fake)
    transport.call(PROBE, {})
    started = transport.call(START, plan["steps"][2]["arguments"])
    assert started["status"] == "pending"
    assert started["job_id"] == JOB_ID
    assert transport.recordings == set()
    assert fake.active is True
    completed = transport.call(POLL, {"job_id": JOB_ID})
    assert completed["status"] == "completed"
    assert completed["recording_id"] == RECORDING_ID
    assert transport.recordings == {RECORDING_ID}
    stopped = transport.call(STOP, {"recording_id": RECORDING_ID})
    assert stopped["status"] == "completed"
    assert stopped["recording_id"] == RECORDING_ID
    assert transport.recordings == set()
    assert fake.calls[0] == (PROBE, {})
    assert [slug for slug, _args in fake.calls].count(GUARD) == 1
    assert [slug for slug, _args in fake.calls].count(STOP) == 1
    with pytest.raises(ValueError):
        transport.call(STOP, {"recording_id": RECORDING_ID})
    assert [slug for slug, _args in fake.calls].count(STOP) == 1


@pytest.mark.parametrize("active", [True, 0, None])
def test_existing_or_nonboolean_obs_state_never_starts_recording(api, plan, active):
    fake = FakeCli(plan, active=active)
    transport = transport_for(api, plan, fake)
    transport.call(PROBE, {})
    with pytest.raises(ValueError):
        transport.call(START, plan["steps"][2]["arguments"])
    assert not any(slug in (START, STOP) for slug, _args in fake.calls)
    assert transport.recordings == set()


@pytest.mark.parametrize(
    "output_schema",
    [
        {},
        schema({"recording_id": {"type": "string"}}),
        schema({"recording_id": {"type": "integer"}}, ["recording_id"]),
    ],
)
def test_obs_start_schema_must_guarantee_a_string_recording_id(api, plan, output_schema):
    fake = FakeCli(plan)
    fake.start_output_schema = output_schema
    transport = transport_for(api, plan, fake)
    with pytest.raises(ValueError):
        transport.call(START, plan["steps"][2]["arguments"])
    assert not any(slug == START for slug, _args in fake.calls)


def test_obs_idle_guard_requires_actual_readonly_boolean(api, plan):
    fake = FakeCli(plan)
    fake.readonly_overrides[GUARD] = "true"
    transport = transport_for(api, plan, fake)
    with pytest.raises(ValueError):
        transport.call(START, plan["steps"][2]["arguments"])
    assert not any(slug in (GUARD, START) for slug, _args in fake.calls)


def test_obs_stop_without_process_owned_recording_is_refused_before_call(api, plan):
    fake = FakeCli(plan)
    transport = transport_for(api, plan, fake)
    with pytest.raises(ValueError):
        transport.call(STOP, {"recording_id": RECORDING_ID})
    assert fake.calls == []


@pytest.mark.parametrize("confirmed_id", [None, "different-recording"])
def test_obs_stop_must_confirm_same_owned_id_without_replaying(api, plan, confirmed_id):
    fake = FakeCli(plan)
    transport = transport_for(api, plan, fake)
    transport.call(PROBE, {})
    transport.call(START, plan["steps"][2]["arguments"])
    transport.call(POLL, {"job_id": JOB_ID})
    fake.stop_recording_id = confirmed_id
    with pytest.raises(ValueError):
        transport.call(STOP, {"recording_id": RECORDING_ID})
    assert [slug for slug, _args in fake.calls].count(STOP) == 1
    assert transport.recordings == {RECORDING_ID}


def test_obs_logs_role_cannot_disguise_mutating_stop_tool(api, plan):
    plan["steps"][-1].update(kind="logs", arguments={"recording_id": RECORDING_ID})
    fake = FakeCli(plan)
    transport = transport_for(api, plan, fake)
    with pytest.raises(ValueError):
        transport.call(STOP, {"recording_id": RECORDING_ID})
    assert fake.calls == []


def test_observing_old_job_does_not_adopt_recording_or_mutation_ownership(api, plan):
    fake = FakeCli(plan, active=True)
    transport = transport_for(api, plan, fake)
    observed = transport.observe(POLL, {"job_id": "old-journal-job"})
    assert observed["status"] == "completed"
    assert observed["recording_id"] == RECORDING_ID
    assert transport.jobs == set()
    assert transport.recordings == set()
    with pytest.raises(ValueError):
        transport.call(STOP, {"recording_id": RECORDING_ID})
    assert fake.calls == [(POLL, {"job_id": "old-journal-job"})]


def test_constructor_does_not_select_cli_from_project_path_shadow(api, plan, monkeypatch):
    project_root = Path(plan["project_root"])
    shadow_name = "dcc-mcp-cli.exe" if api.os.name == "nt" else "dcc-mcp-cli"
    (project_root / shadow_name).write_bytes(b"synthetic project executable; must never run")
    monkeypatch.setattr(api.os, "get_exec_path", lambda: [str(project_root), "."])
    fake = FakeCli(plan)
    with pytest.raises(ValueError):
        api.CliTransport(plan, runner=fake)
    assert fake.commands == []


def test_project_path_link_cannot_resolve_to_an_external_executable(api, plan, monkeypatch):
    project_bin = Path(plan["project_root"]) / "bin"
    filename = "dcc-mcp-cli.exe" if api.os.name == "nt" else "dcc-mcp-cli"
    candidate = project_bin / filename
    original_resolve = Path.resolve

    def resolve_with_project_link(path, *args, **kwargs):
        if path == candidate:
            return original_resolve(Path(sys.executable))
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(api.os, "get_exec_path", lambda: [str(project_bin)])
    monkeypatch.setattr(Path, "resolve", resolve_with_project_link)
    fake = FakeCli(plan)
    with pytest.raises(ValueError, match="project-local shadows"):
        api.CliTransport(plan, runner=fake)
    assert fake.commands == []

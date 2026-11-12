"""Offline tests for the official CLI bridge; no registry or host is accessed."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "skills/unreal-spatiallabs/scripts/software_runner.py"


@pytest.fixture
def api():
    spec = importlib.util.spec_from_file_location("spatiallabs_cli_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plan(tmp_path):
    return {"plan_id": "f" * 64, "project_path": str(tmp_path / "Test.uproject"), "instance_id": "full-unreal-id",
            "steps": [{"id": "probe", "kind": "preflight", "tool_slug": "unreal.ue123456.unreal_pie__pie_get_status",
                       "input_schema": {"type": "object"}, "arguments": {},
                       "project_result_path": ["context", "perf", "project_name"]},
                      {"id": "build", "kind": "build", "tool_slug": "unreal.ue123456.build",
                       "input_schema": {"type": "object", "properties": {"target": {"type": "string"}}},
                       "arguments": {"target": "test"}}]}


class FakeCli:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []
        self.schema_drift = False
        self.foreign_project = False
        self.denied = False

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.denied:
            return SimpleNamespace(returncode=2, stdout="", stderr="registry denied")
        if "list" in command:
            payload = {"instances": [{"instance_id": "full-unreal-id", "instance_short": "ue123456",
                                      "dcc_type": "unreal", "direct_control": {"ready": True}}]}
        elif "describe" in command:
            slug = command[command.index("describe") + 1]
            step = next(s for s in self.plan["steps"] if s["tool_slug"] == slug)
            payload = {"record": {"tool_slug": slug, "instance_id": "full-unreal-id"},
                       "tool": {"name": slug.split(".", 2)[-1], "inputSchema": {} if self.schema_drift else step["input_schema"],
                                "annotations": {"readOnlyHint": step["kind"] == "preflight"}}}
        else:
            slug = command[command.index("call") + 1]
            context = {"perf": {"project_name": "C:/foreign.uproject" if self.foreign_project else self.plan["project_path"]}} if slug.endswith(".unreal_pie__pie_get_status") else {"artifact": "synthetic-only"}
            payload = {"output": {"success": True, "context": context}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")


def test_cli_uses_fixed_executable_json_stdin_and_disables_maintenance(api, plan):
    fake = FakeCli(plan)
    transport = api.CliTransport(plan, fake, executable=sys.executable)
    result = transport.call(plan["steps"][1]["tool_slug"], {"target": "test"})
    assert result["status"] == "completed"
    for command, kwargs in fake.calls:
        assert command[0] == str(Path(sys.executable).resolve())
        assert "--no-update-maintenance" in command and "--non-interactive" in command
        assert command[command.index("--output") + 1] == "json"
        assert kwargs["shell"] is False and kwargs["timeout"] == 30
    build = [(command, kwargs) for command, kwargs in fake.calls if "call" in command and command[command.index("call") + 1].endswith(".build")]
    assert len(build) == 1
    assert json.loads(build[0][1]["input"]) == {"target": "test"}


def test_cli_schema_drift_refuses_before_mutation(api, plan):
    fake = FakeCli(plan)
    fake.schema_drift = True
    with pytest.raises(ValueError, match="schema"):
        api.CliTransport(plan, fake, executable=sys.executable).call(plan["steps"][1]["tool_slug"], {"target": "test"})
    assert not any("call" in command for command, _ in fake.calls)


def test_cli_observes_project_identity_before_every_mutation(api, plan):
    fake = FakeCli(plan)
    fake.foreign_project = True
    with pytest.raises(ValueError, match="project differs"):
        api.CliTransport(plan, fake, executable=sys.executable).call(plan["steps"][1]["tool_slug"], {"target": "test"})
    assert not any("call" in command and command[command.index("call") + 1].endswith(".build") for command, _ in fake.calls)


def test_registry_denial_is_not_retried_or_bypassed(api, plan):
    fake = FakeCli(plan)
    fake.denied = True
    with pytest.raises(RuntimeError, match="no automatic retry"):
        api.CliTransport(plan, fake, executable=sys.executable).call(plan["steps"][1]["tool_slug"], {"target": "test"})
    assert len(fake.calls) == 1


def test_unknown_cli_envelope_does_not_become_pass(api):
    with pytest.raises(ValueError, match="Unrecognized"):
        api.normalize({"output": {"process_alive": True}})


def test_local_mcp_and_remote_output_envelopes_are_supported(api):
    payload = {"success": True, "context": {"recording_id": "owned-recording"}}
    local = {"result": {"isError": False, "content": [{"type": "text", "text": json.dumps(payload)}]}}
    assert api.normalize(local)["recording_id"] == "owned-recording"
    assert api.normalize({"output": {"status": "pending", "job_id": "j1"}})["job_id"] == "j1"
    assert api.normalize({"output": {"status": "completed", "result": {"success": False}}})["status"] == "failed"


def test_mcp_transport_error_never_becomes_completed(api):
    with pytest.raises(ValueError, match="error"):
        api.normalize({"result": {"isError": True, "content": []}})


def test_unreviewed_tool_is_never_invoked(api, plan):
    fake = FakeCli(plan)
    with pytest.raises(ValueError, match="reviewed"):
        api.CliTransport(plan, fake, executable=sys.executable).call("unreal.other.raw_exec", {})
    assert not fake.calls


def test_outer_error_cannot_be_hidden_by_successful_output(api):
    with pytest.raises(ValueError, match="error"):
        api.normalize({"isError": True, "output": {"success": True}})


def test_job_acknowledgment_is_pending_without_terminal_status(api):
    result = api.normalize({"output": {"success": True, "context": {"job_id": "j1"}}})
    assert result["status"] == "pending"


def test_terminal_job_preserves_final_business_payload_and_recording_id(api):
    payload = {"success": True, "context": {"recording_id": "r1", "artifact": "clip.mp4"}}
    result = api.normalize({"output": {"status": "completed", "job_id": "j1", "result": payload}})
    assert result["recording_id"] == "r1"
    assert result["job_id"] == "j1"
    assert result["output"] == payload


def test_nested_job_error_cannot_be_hidden_by_completed_wrapper(api):
    result = api.normalize({"output": {"status": "completed", "result": {"output": {"isError": True}}}})
    assert result["status"] == "failed"


@pytest.mark.parametrize("error", [{"success": False}, {"status": "failed"}])
def test_local_outer_error_cannot_be_hidden_by_structured_success(api, error):
    with pytest.raises(ValueError, match="error"):
        api.normalize({"result": dict(error, structuredContent={"success": True})})


def test_arguments_need_exact_review_binding_not_only_schema(api, plan):
    fake = FakeCli(plan)
    with pytest.raises(ValueError, match="arguments"):
        api.CliTransport(plan, fake, executable=sys.executable).call(plan["steps"][1]["tool_slug"], {"target": "other"})
    assert not fake.calls


def test_reused_slug_cannot_turn_project_observation_into_mutation(api, plan):
    plan["steps"].append(dict(plan["steps"][1], tool_slug=plan["steps"][0]["tool_slug"]))
    with pytest.raises(ValueError, match="observation and mutation"):
        api.CliTransport(plan, FakeCli(plan), executable=sys.executable)

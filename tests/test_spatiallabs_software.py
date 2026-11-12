"""Bounded fake-transport regressions; no DCC/OBS/vendor software is invoked."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "skills/unreal-spatiallabs/scripts"
UNREAL = "ue1234"
OBS = "obs1234"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("spatiallabs_software_under_test", SCRIPTS / "spatiallabs_software.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "Isolated Project"
    root.mkdir()
    (root / "Source").mkdir()
    (root / "Content").mkdir()
    (root / "Source" / "Demo.Build.cs").write_text("// synthetic source fixture only\n", encoding="utf-8")
    (root / "Demo.uproject").write_text(json.dumps({"EngineAssociation": "5.8", "Modules": [{"Name": "Demo"}]}), encoding="utf-8")
    return root


def schema(properties=None, required=None):
    result = {"type": "object", "properties": properties or {}, "additionalProperties": False}
    if required:
        result["required"] = required
    return result


def preflight(project):
    return {"id": "probe", "kind": "preflight", "tool_slug": "unreal." + UNREAL + ".unreal_pie__pie_get_status",
            "input_schema": schema(), "arguments": {},
            "project_result_path": ["context", "perf", "project_name"], "annotations": {"readOnlyHint": True}}


def build(project, pending=False):
    step = {"id": "build", "kind": "build", "tool_slug": "unreal." + UNREAL + ".build_project",
            "input_schema": schema({"project_path": {"type": "string"}}, ["project_path"]),
            "arguments": {"project_path": str(project / "Demo.uproject")},
            "assertions": [{"path": ["context", "exit_code"], "op": "equals", "value": 0}]}
    if pending:
        step.update(poll_tool_slug="unreal." + UNREAL + ".job_status",
                    status_schema=schema({"job_id": {"type": "string"}}, ["job_id"]),
                    status_arguments_template={"job_id": "$job_id"}, max_poll_count=2)
    return step


def completed(project=None, **context):
    if project is not None:
        context["perf"] = {"project_name": str(project / "Demo.uproject")}
    return {"status": "completed", "output": {"context": context}}


class Authority:
    def __init__(self, plan):
        self.plan_id = plan["plan_id"]
        self.calls = []

    def require(self, plan, action):
        self.calls.append((plan["plan_id"], action))
        if plan["plan_id"] != self.plan_id or action != "software_validation":
            raise PermissionError("wrong software scope")


class Transport:
    def __init__(self, responses, before_call=None):
        self.responses = list(responses)
        self.calls = []
        self.before_call = before_call

    def call(self, slug, arguments):
        self.calls.append((slug, copy.deepcopy(arguments)))
        if self.before_call:
            self.before_call(slug, arguments)
        if not self.responses:
            raise AssertionError("Unexpected extra external call")
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def plan_for(api, project, steps=None, **kwargs):
    return api.prepare_software_plan(str(project), UNREAL, steps or [preflight(project), build(project)], **kwargs)


def test_preparation_is_read_only_and_plan_binds_source_project_instances_and_exact_steps(api, project):
    before = snapshot(project)
    plan = plan_for(api, project)
    assert snapshot(project) == before
    assert plan["instance_short"] == UNREAL
    assert plan["project_path"] == str(project / "Demo.uproject")
    assert len(plan["source_hash"]) == 64
    assert plan["steps"][0]["project_result_path"] == ["context", "perf", "project_name"]
    assert plan["call_timeout_seconds"] == 30


@pytest.mark.parametrize("grant", [None, {}, {"approved": True}, True])
def test_missing_non_json_grant_means_zero_calls_and_zero_project_changes(api, project, grant):
    plan = plan_for(api, project)
    before = snapshot(project)
    transport = Transport([])
    with pytest.raises(PermissionError):
        api.run_software_plan(plan, transport, grant)
    assert transport.calls == []
    assert snapshot(project) == before


def test_denied_authority_has_no_calls_or_files(api, project):
    class Denied:
        def require(self, plan, action):
            return False
    plan = plan_for(api, project)
    before = snapshot(project)
    transport = Transport([])
    with pytest.raises(PermissionError):
        api.run_software_plan(plan, transport, Denied())
    assert snapshot(project) == before
    assert transport.calls == []


def test_journal_is_attempting_before_external_action_and_reports_only_software(api, project):
    plan = plan_for(api, project)
    directory = project / api.EVIDENCE_ROOT / plan["plan_id"]

    def inspect_journal(slug, arguments):
        journal = json.loads((directory / "journal.json").read_text())
        assert any(entry["call_state"] == "attempting" for entry in journal["steps"])

    transport = Transport([completed(project), completed(exit_code=0)], inspect_journal)
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "completed"
    assert report["software_acceptance"] == "PASS"
    assert all(status == "NOT_RUN" for status in report["hardware_acceptance"].values())
    assert (directory / "plan.json").is_file()
    assert (directory / "journal.json").is_file()
    assert (directory / "report.json").is_file()
    assert not (directory / "runner.lock").exists()


def test_successful_plan_is_idempotent_without_relaunching_or_rebuilding(api, project):
    plan = plan_for(api, project)
    transport = Transport([completed(project), completed(exit_code=0)])
    assert api.run_software_plan(plan, transport, Authority(plan))["status"] == "completed"
    second = Transport([])
    assert api.run_software_plan(plan, second, Authority(plan))["status"] == "completed"
    assert second.calls == []


def test_call_completion_without_business_assertions_is_not_behavior_pass(api, project):
    step = build(project)
    del step["assertions"]
    plan = plan_for(api, project, [preflight(project), step])
    report = api.run_software_plan(plan, Transport([completed(project), completed()]), Authority(plan))
    assert report["status"] == "completed"
    assert report["steps"][1]["call_state"] == "completed"
    assert report["steps"][1]["status"] == "NOT_RUN"
    assert report["software_acceptance"] == "NOT_RUN"


def test_wrong_live_project_stops_before_any_build_or_launch(api, project):
    plan = plan_for(api, project)
    transport = Transport([{"status": "completed", "output": {"context": {"project_path": "C:/foreign/Game.uproject"}}}])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "repair_required"
    assert len(transport.calls) == 1
    assert report["steps"][1]["status"] == "NOT_RUN"


def test_failed_business_assertion_is_preserved_and_not_retried(api, project):
    plan = plan_for(api, project, max_attempts=2)
    transport = Transport([completed(project), completed(exit_code=1)])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "repair_required"
    assert report["steps"][1]["status"] == "FAIL"
    assert report["steps"][1]["attempts"] == 1
    assert len(transport.calls) == 2


def test_pending_build_only_polls_the_returned_job_and_does_not_issue_second_build(api, project):
    plan = plan_for(api, project, [preflight(project), build(project, pending=True)])
    pending = {"status": "pending", "job_id": "job-1", "output": {}}
    done = dict(completed(exit_code=0), job_id="job-1")
    transport = Transport([completed(project), pending, pending, done])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "completed"
    assert [slug for slug, _arguments in transport.calls].count("unreal." + UNREAL + ".build_project") == 1
    assert [arguments for slug, arguments in transport.calls if slug.endswith(".job_status")] == [{"job_id": "job-1"}] * 2


def test_poll_limit_is_bounded_and_restart_recovery_is_status_only(api, project):
    steps = [preflight(project), build(project, pending=True),
             {"id": "launch", "kind": "launch", "tool_slug": "unreal." + UNREAL + ".launch_project",
              "input_schema": schema(), "arguments": {}, "assertions": []}]
    plan = plan_for(api, project, steps)
    pending = {"status": "pending", "job_id": "job-1", "output": {}}
    first = Transport([completed(project), pending, pending, pending])
    assert api.run_software_plan(plan, first, Authority(plan))["status"] == "blocked"
    assert len(first.calls) == 4
    resumed = Transport([dict(completed(exit_code=0), job_id="job-1")])
    report = api.run_software_plan(plan, resumed, Authority(plan))
    assert report["resume_only"] is True
    assert report["status"] == "blocked"
    assert resumed.calls == [("unreal." + UNREAL + ".job_status", {"job_id": "job-1"})]
    assert report["steps"][2]["status"] == "NOT_RUN"


def test_foreign_job_status_is_uncertain_and_never_continues(api, project):
    plan = plan_for(api, project, [preflight(project), build(project, pending=True)])
    transport = Transport([completed(project), {"status": "pending", "job_id": "job-1", "output": {}},
                           dict(completed(exit_code=0), job_id="other-job")])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "uncertain"
    assert report["steps"][1]["attempts"] == 1


def test_timeout_without_job_id_does_not_guess_a_job_or_replay_action(api, project):
    plan = plan_for(api, project, [preflight(project), build(project, pending=True)])
    transport = Transport([completed(project), TimeoutError("acknowledgement lost")])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "uncertain"
    assert len(transport.calls) == 2
    assert "no bound job_id" in report["steps"][1]["reason"]
    resumed = Transport([])
    assert api.run_software_plan(plan, resumed, Authority(plan))["status"] == "uncertain"
    assert resumed.calls == []


def test_timeout_can_observe_literal_status_but_cannot_infer_action_ownership(api, project):
    step = build(project)
    step.update(poll_tool_slug="unreal." + UNREAL + ".build_status", status_schema=schema(),
                status_arguments_template={})
    plan = plan_for(api, project, [preflight(project), step])
    transport = Transport([completed(project), TimeoutError("lost ack"), completed(exit_code=0)])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "uncertain"
    assert len(transport.calls) == 3
    assert report["steps"][1]["unbound_status_observation"]["status"] == "completed"


@pytest.mark.parametrize("response", [{"status": "pending"}, {"status": "made_up"}, {"success": True}])
def test_unrecognized_or_unbound_response_is_uncertain_not_a_pass(api, project, response):
    plan = plan_for(api, project)
    result = api.run_software_plan(plan, Transport([completed(project), response]), Authority(plan))
    assert result["status"] == "uncertain"
    assert result["steps"][1]["status"] == "NOT_RUN"


def obs_steps(project):
    binding = {"dcc_type": "obs", "instance_id": OBS, "instance_short": OBS}
    guard = dict(binding, id="obs_idle", kind="preflight", tool_slug="obs." + OBS + ".recording_status",
                 input_schema=schema(), arguments={})
    start = dict(binding, id="record", kind="obs_start", tool_slug="obs." + OBS + ".start_recording",
                 input_schema=schema({"output_path": {"type": "string"}}, ["output_path"]),
                 arguments={"output_path": str(project / "Saved" / "Owned.mkv")},
                 idle_guard={"tool_slug": guard["tool_slug"], "recording_result_path": ["context", "recording_active"]})
    stop = dict(binding, id="stop", kind="obs_stop", tool_slug="obs." + OBS + ".stop_recording",
                input_schema=schema({"recording_id": {"type": "string"}}, ["recording_id"]),
                arguments={"recording_id": "$recording_id"}, recording_id_parameter=["recording_id"])
    return [preflight(project), guard, start, build(project), stop]


def test_obs_cleanup_only_stops_the_confirmed_id_started_by_this_invocation(api, project):
    plan = plan_for(api, project, obs_steps(project))
    start = dict(completed(), recording_id="owned-recording")
    stop = dict(completed(), recording_id="owned-recording")
    transport = Transport([completed(project), completed(recording_active=False), completed(recording_active=False),
                           start, {"status": "failed", "output": {"error": "synthetic compiler failure"}}, stop])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "repair_required"
    assert transport.calls[-1] == ("obs." + OBS + ".stop_recording", {"recording_id": "owned-recording"})
    assert report["steps"][-1]["cleanup"] is True
    assert report["steps"][-1]["attempts"] == 1


@pytest.mark.parametrize("active", [True, None, 0])
def test_existing_or_unknown_obs_recording_is_never_taken_over(api, project, active):
    plan = plan_for(api, project, obs_steps(project))
    transport = Transport([completed(project), completed(recording_active=active), completed(recording_active=active)])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "blocked"
    assert not any(slug.endswith((".start_recording", ".stop_recording")) for slug, _arguments in transport.calls)


def test_uncertain_obs_start_never_blindly_stops_any_recording(api, project):
    steps = obs_steps(project)
    steps[2].update(poll_tool_slug="obs." + OBS + ".recording_status", status_schema=schema(), status_arguments_template={})
    plan = plan_for(api, project, steps)
    transport = Transport([completed(project), completed(recording_active=False), completed(recording_active=False),
                           TimeoutError("start ack lost"), completed(recording_active=True)])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "uncertain"
    assert not any(slug.endswith(".stop_recording") for slug, _arguments in transport.calls)
    assert report["steps"][2]["attempts"] == 1


def test_uncertain_obs_stop_is_not_reissued_in_finally_or_on_resume(api, project):
    plan = plan_for(api, project, obs_steps(project))
    transport = Transport([completed(project), completed(recording_active=False), completed(recording_active=False),
                           dict(completed(), recording_id="owned"), completed(exit_code=0), TimeoutError("stop ack lost")])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "uncertain"
    assert [slug for slug, _arguments in transport.calls].count("obs." + OBS + ".stop_recording") == 1
    resumed = Transport([])
    assert api.run_software_plan(plan, resumed, Authority(plan))["status"] == "uncertain"
    assert resumed.calls == []


def test_disk_only_recording_id_is_never_treated_as_current_invocation_ownership(api, project):
    plan = plan_for(api, project, obs_steps(project))
    transport = Transport([completed(project), completed(recording_active=False), completed(recording_active=False),
                           dict(completed(), recording_id="owned"), KeyboardInterrupt()])
    # finally owns this process's recording and attempts its exact paired stop;
    # the fake has no remaining response, leaving a durable uncertain stop.
    with pytest.raises(KeyboardInterrupt):
        api.run_software_plan(plan, transport, Authority(plan))
    resumed = Transport([])
    report = api.run_software_plan(plan, resumed, Authority(plan))
    assert report["status"] == "uncertain"
    assert resumed.calls == []


def test_plan_tampering_and_source_drift_refuse_before_calls_or_evidence(api, project):
    plan = plan_for(api, project)
    original = snapshot(project)
    bad = copy.deepcopy(plan)
    bad["steps"][1]["arguments"]["project_path"] = "C:/foreign/Other.uproject"
    with pytest.raises(ValueError, match="hash"):
        api.run_software_plan(bad, Transport([]), Authority(plan))
    assert snapshot(project) == original
    (project / "Source" / "Demo.Build.cs").write_text("// user edit\n", encoding="utf-8")
    changed = snapshot(project)
    with pytest.raises(ValueError, match="lineage"):
        api.run_software_plan(plan, Transport([]), Authority(plan))
    assert snapshot(project) == changed


@pytest.mark.parametrize("mutation", ["foreign_path", "schema_type", "raw_code", "external_ref", "foreign_slug", "foreign_poll", "template"])
def test_unsafe_step_inputs_fail_during_read_only_preparation(api, project, mutation):
    steps = [preflight(project), build(project, pending=True)]
    if mutation == "foreign_path":
        steps[1]["arguments"]["project_path"] = str(project.parent / "foreign.uproject")
    elif mutation == "schema_type":
        steps[1]["arguments"]["project_path"] = True
    elif mutation == "raw_code":
        steps[1]["input_schema"]["properties"]["code"] = {"type": "string"}
    elif mutation == "external_ref":
        steps[1]["input_schema"]["properties"]["project_path"] = {"$ref": "https://attacker.example/schema.json"}
    elif mutation == "foreign_slug":
        steps[1]["tool_slug"] = "unreal.other.build_project"
    elif mutation == "foreign_poll":
        steps[1]["poll_tool_slug"] = "unreal.other.job_status"
    else:
        steps[1]["status_arguments_template"] = {"job_id": "${eval(job_id)}"}
    before = snapshot(project)
    with pytest.raises(ValueError):
        plan_for(api, project, steps)
    assert snapshot(project) == before


@pytest.mark.parametrize("leaf", ["execute_python", "official_mcp_bridge", "install_plugin", "download_package", "run_script",
                                  "uninstall_plugin", "license_accept", "accept_license", "accept_vendor_terms", "update_driver", "set_runtime"])
def test_raw_harness_or_vendor_tools_are_not_a_software_validation_shortcut(api, project, leaf):
    step = build(project)
    step["tool_slug"] = "unreal." + UNREAL + "." + leaf
    with pytest.raises(ValueError):
        plan_for(api, project, [preflight(project), step])


def test_installer_disguised_as_logs_cannot_use_software_authority(api, project):
    step = {"id": "installer_disguised_as_logs", "kind": "logs", "tool_slug": "unreal." + UNREAL + ".spatiallabs_project__install_plan",
            "input_schema": schema(), "arguments": {}}
    before = snapshot(project)
    with pytest.raises(ValueError, match="vendor installation"):
        plan_for(api, project, [preflight(project), step])
    assert snapshot(project) == before


def test_full_instance_id_requires_explicit_inventory_short_token(api, project):
    full = "12345678-1234-1234-1234-123456789abc"
    with pytest.raises(ValueError, match="instance_short"):
        api.prepare_software_plan(str(project), full, [preflight(project)])
    plan = api.prepare_software_plan(str(project), full, [preflight(project)], instance_short=UNREAL)
    assert plan["instance_id"] == full
    assert plan["instance_short"] == UNREAL


@pytest.mark.parametrize("version", ["4.27", "6.0", "{custom-engine-guid}", None])
def test_other_or_unidentified_engine_is_not_promised_conversion(api, project, version):
    descriptor = {"EngineAssociation": version, "Modules": [{"Name": "Demo"}]}
    (project / "Demo.uproject").write_text(json.dumps(descriptor), encoding="utf-8")
    with pytest.raises(ValueError, match="UE 5"):
        plan_for(api, project)


def test_blueprint_project_is_allowed_but_module_project_without_source_is_not(api, project):
    (project / "Source" / "Demo.Build.cs").unlink()
    (project / "Source").rmdir()
    with pytest.raises(ValueError, match="Source"):
        plan_for(api, project)
    (project / "Demo.uproject").write_text(json.dumps({"EngineAssociation": "5.8"}), encoding="utf-8")
    assert plan_for(api, project)["project_kind"] == "blueprint"


@pytest.mark.parametrize("kwargs", [{"max_attempts": 0}, {"max_attempts": 3}, {"max_attempts": True}])
def test_attempt_bounds_cannot_be_unbounded_or_boolean(api, project, kwargs):
    with pytest.raises(ValueError):
        plan_for(api, project, **kwargs)


def test_step_poll_and_repair_bounds_are_explicit(api, project):
    steps = [preflight(project)] + [dict(build(project), id="build" + str(index)) for index in range(32)]
    with pytest.raises(ValueError, match="32"):
        plan_for(api, project, steps)
    step = build(project, pending=True)
    step["max_poll_count"] = 31
    with pytest.raises(ValueError, match="max_poll_count"):
        plan_for(api, project, [preflight(project), step])
    repair = dict(build(project), id="fixed_repair", kind="repair", tool_slug="unreal." + UNREAL + ".apply_project_config")
    with pytest.raises(ValueError, match="repair"):
        plan_for(api, project, [preflight(project), repair])


def test_reviewed_fixed_typed_repair_runs_once_without_generating_code(api, project):
    repair = {"id": "fixed_repair", "kind": "repair", "tool_slug": "unreal." + UNREAL + ".apply_project_config",
              "input_schema": schema({"settings": {"type": "object"}}, ["settings"]),
              "arguments": {"settings": {"r.ScreenPercentage": 100}}, "reviewed_repair": True,
              "assertions": [{"path": ["context", "applied"], "op": "equals", "value": True}]}
    plan = plan_for(api, project, [preflight(project), repair, build(project)])
    transport = Transport([completed(project), completed(applied=True), completed(exit_code=0)])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "completed"
    assert report["steps"][1]["attempts"] == 1


def test_obs_cannot_stop_literal_foreign_id_or_use_other_instance(api, project):
    steps = obs_steps(project)
    steps[-1]["arguments"] = {"recording_id": "someone-elses-recording"}
    with pytest.raises(ValueError, match="recording_id"):
        plan_for(api, project, steps)
    steps = obs_steps(project)
    steps[-1]["instance_id"] = "otherobs"
    steps[-1]["instance_short"] = "otherobs"
    steps[-1]["tool_slug"] = "obs.otherobs.stop_recording"
    with pytest.raises(ValueError, match="multiple OBS"):
        plan_for(api, project, steps)


def test_changed_journal_cannot_authorize_cleanup_or_action_replay(api, project):
    plan = plan_for(api, project)
    api.run_software_plan(plan, Transport([completed(project), TimeoutError("lost")]), Authority(plan))
    path = project / api.EVIDENCE_ROOT / plan["plan_id"] / "journal.json"
    data = json.loads(path.read_text())
    data["steps"][1]["call_state"] = "not_run"
    path.write_text(json.dumps(data), encoding="utf-8")
    transport = Transport([])
    with pytest.raises(ValueError, match="integrity"):
        api.run_software_plan(plan, transport, Authority(plan))
    assert transport.calls == []


def test_existing_execution_lock_is_preserved_not_stolen(api, project):
    plan = plan_for(api, project)
    directory = project / api.EVIDENCE_ROOT / plan["plan_id"]
    directory.mkdir(parents=True)
    lock = directory / "runner.lock"
    lock.write_text("another writer", encoding="utf-8")
    transport = Transport([])
    with pytest.raises(ValueError, match="execution lock"):
        api.run_software_plan(plan, transport, Authority(plan))
    assert lock.read_text() == "another writer"
    assert transport.calls == []


@pytest.mark.parametrize("change", ["echo_tool", "echo_argument", "result_path"])
def test_first_probe_cannot_be_a_filesystem_echo_of_supplied_project(api, project, change):
    step = preflight(project)
    if change == "echo_tool":
        step["tool_slug"] = "unreal." + UNREAL + ".inspect_project"
    elif change == "echo_argument":
        step["input_schema"] = schema({"project_path": {"type": "string"}})
        step["arguments"] = {"project_path": str(project / "Demo.uproject")}
    else:
        step["project_result_path"] = ["context", "project_path"]
    with pytest.raises(ValueError, match="host capability"):
        plan_for(api, project, [step, build(project)])


def test_typed_execute_action_is_allowed_without_raw_execution_parameters(api, project):
    step = {"id": "interact", "kind": "interaction", "tool_slug": "unreal." + UNREAL + ".playtest_execute_action",
            "input_schema": schema({"action": {"type": "string", "enum": ["jump"]}}, ["action"]),
            "arguments": {"action": "jump"}, "assertions": [{"path": ["context", "state"], "op": "equals", "value": "jumped"}]}
    plan = plan_for(api, project, [preflight(project), step])
    report = api.run_software_plan(plan, Transport([completed(project), completed(state="jumped")]), Authority(plan))
    assert report["steps"][1]["status"] == "PASS"


def test_obs_note_placeholder_does_not_bind_a_real_recording_parameter(api, project):
    steps = obs_steps(project)
    steps[-1]["input_schema"] = schema({"note": {"type": "string"}}, ["note"])
    steps[-1]["arguments"] = {"note": "$recording_id"}
    steps[-1]["recording_id_parameter"] = ["note"]
    with pytest.raises(ValueError, match="actual recording_id"):
        plan_for(api, project, steps)


@pytest.mark.parametrize("response", [completed(), dict(completed(), recording_id="foreign")])
def test_obs_stop_missing_or_wrong_returned_id_is_uncertain_without_replay(api, project, response):
    plan = plan_for(api, project, obs_steps(project))
    transport = Transport([completed(project), completed(recording_active=False), completed(recording_active=False),
                           dict(completed(), recording_id="owned"), completed(exit_code=0), response])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["status"] == "uncertain"
    assert [slug for slug, _arguments in transport.calls].count("obs." + OBS + ".stop_recording") == 1


def test_recovery_uses_observe_after_source_drift_and_never_dispatches_new_actions(api, project):
    plan = plan_for(api, project, [preflight(project), build(project, pending=True)])
    pending = {"status": "pending", "job_id": "job-1", "output": {}}
    assert api.run_software_plan(plan, Transport([completed(project), pending, pending, pending]), Authority(plan))["status"] == "blocked"
    (project / "Source" / "Demo.Build.cs").write_text("// authorized repair or user edit\n", encoding="utf-8")

    class ObserveOnly:
        def __init__(self):
            self.observations = []

        def call(self, slug, arguments):
            raise AssertionError("Mutation path must not be used on restart")

        def observe(self, slug, arguments):
            self.observations.append((slug, arguments))
            return dict(completed(exit_code=0), job_id="job-1")

    transport = ObserveOnly()
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["resume_only"] is True
    assert report["source_lineage_changed"] is True
    assert report["status"] == "blocked"
    assert transport.observations == [("unreal." + UNREAL + ".job_status", {"job_id": "job-1"})]


def test_completed_journal_after_source_change_remains_historical_and_never_mutates(api, project):
    plan = plan_for(api, project)
    assert api.run_software_plan(plan, Transport([completed(project), completed(exit_code=0)]), Authority(plan))["status"] == "completed"
    (project / "Source" / "Demo.Build.cs").write_text("// later source version\n", encoding="utf-8")
    transport = Transport([])
    report = api.run_software_plan(plan, transport, Authority(plan))
    assert report["source_lineage_changed"] is True
    assert report["status"] == "blocked"
    assert report["software_acceptance"] == "NOT_RUN"
    assert transport.calls == []


def test_total_journal_larger_than_one_response_bound_is_still_recoverable(api, project):
    log = {"id": "logs", "kind": "logs", "tool_slug": "unreal." + UNREAL + ".read_logs",
           "input_schema": schema(), "arguments": {}, "assertions": [{"path": ["context", "text"], "op": "nonempty"}]}
    plan = plan_for(api, project, [preflight(project), build(project), log])
    text = "synthetic log evidence " * 28000
    first = api.run_software_plan(plan, Transport([completed(project), completed(exit_code=0, text=text), completed(text=text)]), Authority(plan))
    assert first["status"] == "completed"
    journal = project / api.EVIDENCE_ROOT / plan["plan_id"] / "journal.json"
    assert api.MAX_JSON < journal.stat().st_size < api.MAX_JOURNAL
    transport = Transport([])
    assert api.run_software_plan(plan, transport, Authority(plan))["status"] == "completed"
    assert transport.calls == []


def test_lock_replaced_during_execution_is_preserved_for_the_other_writer(api, project):
    plan = plan_for(api, project)
    lock = project / api.EVIDENCE_ROOT / plan["plan_id"] / "runner.lock"

    def replace_lock(slug, arguments):
        if slug.endswith(".build_project"):
            lock.write_text("replacement-owner", encoding="utf-8")

    report = api.run_software_plan(plan, Transport([completed(project), completed(exit_code=0)], replace_lock), Authority(plan))
    assert report["status"] == "completed"
    assert lock.read_text() == "replacement-owner"

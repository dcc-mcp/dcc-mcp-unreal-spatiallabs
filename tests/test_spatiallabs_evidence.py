"""Public evidence entry-point checks without a live host or private game files."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError

SKILL = Path(__file__).parents[1] / "skills/unreal-spatiallabs"


def load(name, monkeypatch):
    monkeypatch.syspath_prepend(str(SKILL / "scripts"))
    spec = importlib.util.spec_from_file_location("evidence_entry_" + name, SKILL / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def test_public_entry_composes_real_file_evidence_without_mutating_or_granting_support(tmp_path, monkeypatch):
    project = tmp_path / "Review.uproject"
    project.write_text('{"FileVersion":3,"EngineAssociation":"5.8"}')
    engine = tmp_path / "Engine"
    (engine / "Build").mkdir(parents=True)
    (engine / "Build/Build.version").write_text(json.dumps({
        "MajorVersion": 5, "MinorVersion": 8, "PatchVersion": 1, "Changelist": 56057345,
    }))
    log = tmp_path / "run.log"
    log.write_text("LogInit: Engine Version: 5.8.0-55116800+++UE5+Release-5.8\n")
    before = snapshot(tmp_path)
    result = load("inspect_software_evidence", monkeypatch).inspect_software_evidence(
        project_path=str(project), engine_root=str(engine), run_log_path=str(log), cache_state="warm")
    assert result["success"] is True  # Analysis completed, not business acceptance.
    context = result["context"]
    assert context["runtime"]["engine_identity"]["status"] == "mismatch"
    assert context["run"]["scene"]["status"] == "NOT_RUN"
    assert context["project_to_run_binding"] == "not_verified"
    assert context["compatibility_status"] == "unknown"
    assert context["hardware_verified"] is False
    assert context["host_actions_executed"] is False
    assert context["installation_authorized"] is False
    assert snapshot(tmp_path) == before
    declaration = next(tool for tool in yaml.safe_load((SKILL / "tools.yaml").read_text())["tools"]
                       if tool["name"] == "inspect_software_evidence")
    Draft202012Validator(declaration["output_schema"]).validate(result)


def test_evidence_tool_has_no_mutation_or_visual_pass_override_arguments():
    declaration = next(tool for tool in yaml.safe_load((SKILL / "tools.yaml").read_text())["tools"]
                       if tool["name"] == "inspect_software_evidence")
    schema = declaration["input_schema"]
    args = {"project_path": "C:/review/Game.uproject", "engine_root": "C:/UE/Engine",
            "run_log_path": "C:/review/run.log"}
    Draft202012Validator(schema).validate(args)
    for extra in ({"approved": True}, {"scene_ready": True}, {"repair": "enable plugin"}, {"cache_state": "hot"}):
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(dict(args, **extra))


@pytest.mark.parametrize("kind", ["oversized_project", "deep_project", "deep_metadata", "deep_plugin"])
def test_public_entry_refuses_unbounded_or_deep_json_as_controlled_error(tmp_path, monkeypatch, kind):
    project = tmp_path / "Review.uproject"
    project.write_text('{"FileVersion":3}')
    engine = tmp_path / "Engine"
    (engine / "Build").mkdir(parents=True)
    metadata = engine / "Build/Build.version"
    metadata.write_text('{}')
    log = tmp_path / "run.log"
    log.write_text('LogInit: Engine Version: 5.8.0-55116800+++UE5+Release-5.8\n')
    deep = '{"unused":' + '[' * 2000 + '0' + ']' * 2000 + '}'
    if kind == "oversized_project":
        project.write_bytes(b' ' * (1024 * 1024 + 1))
    elif kind == "deep_project":
        project.write_text(deep)
    elif kind == "deep_metadata":
        metadata.write_text(deep)
    else:
        (tmp_path / "Config").mkdir()
        (tmp_path / "Config/DefaultGame.ini").write_text(
            '[/Script/Engine.AssetManagerSettings]\n'
            '+PrimaryAssetTypesToScan=(AssetBaseClass="/Script/GameFeatures.GameFeatureData")\n')
        plugin = engine / "Plugins/GameFeatures/GameFeatures.uplugin"
        plugin.parent.mkdir(parents=True)
        plugin.write_text(deep)
    result = load("inspect_software_evidence", monkeypatch).inspect_software_evidence(
        project_path=str(project), engine_root=str(engine), run_log_path=str(log))
    if kind == "deep_metadata":
        assert result["success"] is True  # Invalid metadata remains useful forensic evidence.
        assert result["context"]["runtime"]["engine_identity"]["status"] == "unknown"
        assert result["context"]["runtime"]["engine_identity"]["metadata"]["status"] == "invalid"
    else:
        assert result["success"] is False
        assert isinstance(result["error"], str)
    json.dumps(result, allow_nan=False)


def test_standalone_entry_emits_one_controlled_json_result(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(SKILL / "scripts/inspect_software_evidence.py")],
        input=json.dumps({"project_path": "relative", "engine_root": "relative", "run_log_path": "relative"}),
        text=True, capture_output=True, timeout=15, cwd=tmp_path,
    )
    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["success"] is False
    assert isinstance(result["error"], str)

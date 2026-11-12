"""Exercise the installable optional package through the real Core contracts."""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
SKILL = ROOT / "skills/unreal-spatiallabs"
SCRIPTS = SKILL / "scripts"


def load(name, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("spatiallabs_contract_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_core_validation_and_catalog_do_not_execute_scripts(monkeypatch):
    import dcc_mcp_core as core

    monkeypatch.setenv("DCC_MCP_DISABLE_DEFAULT_SKILL_PATHS", "1")
    report = core.validate_skill(str(SKILL))
    assert not report.issues
    registry = core.ToolRegistry()
    catalog = core.SkillCatalog(registry)
    catalog.set_in_process_executor(lambda *args, **kwargs: pytest.fail("Discovery must never execute code"))
    document = core.parse_skill_md(str(SKILL))
    catalog.load_skill_object(document)
    assert len(document.tools) == 8
    for tool in document.tools:
        action = registry.get_action("unreal_spatiallabs__" + tool.name)
        assert action["annotations"]["read_only_hint"] is True


def test_declared_schemas_are_read_only_and_do_not_offer_consent_flags():
    manifest = yaml.safe_load((SKILL / "tools.yaml").read_text())
    assert len(manifest["tools"]) == 8
    for tool in manifest["tools"]:
        Draft202012Validator.check_schema(tool["input_schema"])
        Draft202012Validator.check_schema(tool["output_schema"])
        assert tool["execution"] == "sync" and tool["affinity"] == "any"
        assert tool["annotations"]["read_only_hint"] is True
        assert tool["annotations"]["destructive_hint"] is False
        assert not {"authority", "approved", "confirmed", "accept_license"} & set(tool["input_schema"]["properties"])


def test_every_wrapper_loads_and_refuses_bad_input_with_core_envelope(monkeypatch):
    cases = {
        "inspect_stereo_pair": {"pair_path": "relative"},
        "inspect_software_evidence": {"project_path": "relative", "engine_root": "relative", "run_log_path": "relative"},
        "inspect_project": {"project_path": "relative"},
        "plan_install": {"project_path": "relative", "plugin_version": "2.1.9", "engine_version": "5.8", "source_url": "https://example.org"},
        "validate_archive": {"archive_path": "relative.zip", "plugin_version": "2.1.9", "engine_version": "5.8"},
        "analyze_performance": {"baseline": {}, "candidate": {}},
        "acceptance_report": {"evidence": {"layers": {"code": {"status": "PASS"}}}},
        "prepare_software_plan": {"project_path": "relative", "instance_id": "unbound", "steps": []},
    }
    for name, kwargs in cases.items():
        result = getattr(load(name, monkeypatch), name)(**kwargs)
        assert result["success"] is False, (name, result)
        assert result["error"]
        json.dumps(result, allow_nan=False)


def test_wrapper_inspection_success_remains_offline_and_hardware_unverified(tmp_path, monkeypatch):
    project = tmp_path / "Test.uproject"
    project.write_text('{"FileVersion":3,"EngineAssociation":"5.8"}')
    result = load("inspect_project", monkeypatch).inspect_project(project_path=str(project))
    assert result["success"] is True
    assert result["context"]["hardware_verified"] is False
    assert result["context"]["compatibility_status"] == "unknown"


def test_optional_package_retains_python37_syntax_and_no_vendor_artifacts():
    for path in SCRIPTS.glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 7))
    assert not list(SKILL.rglob("*.dll"))
    assert not list(SKILL.rglob("*.exe"))
    assert not list(SKILL.rglob("*.zip"))


def test_operator_rejects_piped_acceptance_before_any_download(tmp_path, monkeypatch):
    project = tmp_path / "Test.uproject"
    project.write_text('{"FileVersion":3,"EngineAssociation":"5.8"}')
    api = load("spatiallabs_project", monkeypatch)
    from datetime import datetime, timedelta, timezone

    evidence = {"status": "supported", "source_url": "https://spatiallabs.acer.com/developer/synthetic-test-only",
                "checked_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                "engine_version": "5.8", "plugin_version": "2.1.9", "runtime_version": "synthetic",
                "device_model": "synthetic-test-only"}
    import hashlib

    license_record = {"source_url": api.LICENSE_URL, "content_sha256": hashlib.sha256(b"SYNTHETIC LICENSE ONLY").hexdigest(),
                      "checked_at": evidence["checked_at"]}
    plan = api.plan_install(str(project), "2.1.9", "5.8", "https://spatiallabs.acer.com/synthetic-test-only.zip",
                            evidence, license_record)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan))
    completed = subprocess.run([sys.executable, str(SCRIPTS / "operator_install.py"), "install", str(plan_file)],
                               input="ACCEPT LICENSE AND INSTALL " + plan["plan_id"] + "\n", capture_output=True,
                               text=True, timeout=15)
    assert completed.returncode == 2
    assert "authorization_required" in completed.stderr
    assert not (tmp_path / "Plugins").exists()
    assert not (tmp_path / api.STATE_DIR).exists()


def test_catalog_draft_cannot_be_installed_or_misrepresent_a_published_revision():
    draft = json.loads((ROOT / "packaging/spatiallabs-catalog-draft.json").read_text())
    assert draft["installable"] is False
    assert draft["sourceRef"] is None
    assert draft["minCoreVersion"] is None
    assert draft["name"] == "dcc-mcp-unreal-spatiallabs"
    assert draft["skillRoots"] == ["skills/unreal-spatiallabs"]
    frontmatter = yaml.safe_load((SKILL / "SKILL.md").read_text().split("---", 2)[1])
    assert frontmatter["name"] == SKILL.name == "unreal-spatiallabs"

"""Offline counterexamples from Chumen findings; no private game data or host."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).parents[1] / "skills/unreal-spatiallabs/scripts"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("spatiallabs_runtime_under_test", SCRIPTS / "spatiallabs_runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixture(tmp_path):
    project, engine = tmp_path / "Project", tmp_path / "Engine"
    (project / "Config").mkdir(parents=True)
    (engine / "Build").mkdir(parents=True)
    (engine / "Build/Build.version").write_text(json.dumps({
        "MajorVersion": 5, "MinorVersion": 8, "PatchVersion": 1, "Changelist": 56057345,
    }))
    return project, engine


def require_gamefeatures(project):
    (project / "Config/DefaultGame.ini").write_text(
        '[/Script/Engine.AssetManagerSettings]\n'
        '+PrimaryAssetTypesToScan=(PrimaryAssetType="GameFeatureData",'
        'AssetBaseClass="/Script/GameFeatures.GameFeatureData")\n'
    )


def plugin(engine, name, references=None, default=False):
    path = engine / "Plugins" / name / (name + ".uplugin")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"EnabledByDefault": default, "Plugins": references or []}))
    return path


def chain(engine):
    plugin(engine, "AllToolsets", [{"Name": "GameFeaturesToolset", "Enabled": True}])
    plugin(engine, "GameFeaturesToolset", [{"Name": "GameFeatures", "Enabled": True}])
    plugin(engine, "GameFeatures")


def context(api, fixture, project_data=None, runtime=None):
    project, engine = fixture
    return api.inspect_runtime_context(project, project_data or {}, engine, runtime or {"status": "missing"})


def test_installation_metadata_cannot_silently_override_actual_runtime(api, fixture):
    result = context(api, fixture, runtime={"status": "observed", "version": "5.8.0", "changelist": 55116800})
    identity = result["engine_identity"]
    assert identity["status"] == "mismatch"
    assert identity["differing_fields"] == ["version", "changelist"]
    assert identity["metadata"]["version"] == "5.8.1"
    assert identity["runtime"]["version"] == "5.8.0"
    assert identity["official_support"] == "NOT_VERIFIED"
    assert identity["live_attestation"] is False


def test_matching_identity_does_not_become_official_support(api, fixture):
    identity = context(api, fixture, runtime={"status": "observed", "version": "5.8.1", "changelist": 56057345})["engine_identity"]
    assert identity["status"] == "match"
    assert identity["official_support"] == "NOT_VERIFIED"


@pytest.mark.parametrize("runtime", [
    {"status": "missing"}, {"status": "ambiguous", "version": "5.8.1", "changelist": 56057345},
    {"status": "observed", "version": "5.8", "changelist": 56057345},
    {"status": "observed", "version": "5.8.1", "changelist": True},
])
def test_incomplete_or_ambiguous_runtime_never_matches(api, fixture, runtime):
    assert context(api, fixture, runtime=runtime)["engine_identity"]["status"] == "unknown"


@pytest.mark.parametrize("raw", [b"{}", b"not-json", b'{"MajorVersion":true}', b'[]'])
def test_invalid_metadata_never_matches(api, fixture, raw):
    (fixture[1] / "Build/Build.version").write_bytes(raw)
    identity = context(api, fixture, runtime={"status": "observed", "version": "5.8.1", "changelist": 56057345})["engine_identity"]
    assert identity["status"] == "unknown"
    assert identity["metadata"]["status"] == "invalid"


def test_absent_metadata_stays_unknown(api, fixture):
    (fixture[1] / "Build/Build.version").unlink()
    assert context(api, fixture)["engine_identity"]["metadata"]["status"] == "missing"


def test_original_implicit_dependency_is_visible(api, fixture):
    require_gamefeatures(fixture[0])
    chain(fixture[1])
    data = {"Plugins": [{"Name": "AllToolsets", "Enabled": True}]}
    result = context(api, fixture, data)["runtime_dependencies"]
    assert result["status"] == "declared_implicit"
    assert result["declared_enabling_paths"] == [{"plugins": ["AllToolsets", "GameFeaturesToolset", "GameFeatures"], "conditional_edges": []}]
    assert result["runtime_loaded_state"] == "NOT_VERIFIED"


def test_disabling_control_root_exposes_lost_runtime_dependency(api, fixture):
    require_gamefeatures(fixture[0])
    chain(fixture[1])
    data = {"Plugins": [{"Name": "AllToolsets", "Enabled": False}]}
    result = context(api, fixture, data)["runtime_dependencies"]
    assert result["status"] == "potential_lost_implicit_dependency"
    assert result["declared_enabling_paths"] == []
    assert result["paths_from_disabled_roots"][0]["plugins"] == ["AllToolsets", "GameFeaturesToolset", "GameFeatures"]
    assert result["automatic_repair"] is False
    assert data["Plugins"][0]["Enabled"] is False


def test_explicit_gameplay_dependency_preserves_control_disable(api, fixture):
    require_gamefeatures(fixture[0])
    chain(fixture[1])
    data = {"Plugins": [{"Name": "AllToolsets", "Enabled": False}, {"Name": "GameFeatures", "Enabled": True}]}
    result = context(api, fixture, data)["runtime_dependencies"]
    assert result["status"] == "declared_explicit"
    assert result["declared_enabling_paths"] == [{"plugins": ["GameFeatures"], "conditional_edges": []}]
    assert result["runtime_loaded_state"] == "NOT_VERIFIED"


def test_default_conditional_path_is_not_runtime_loaded_proof(api, fixture):
    require_gamefeatures(fixture[0])
    plugin(fixture[1], "EditorOnly", [{"Name": "GameFeatures", "Enabled": True, "TargetAllowList": ["Editor"]}], default=True)
    plugin(fixture[1], "GameFeatures")
    result = context(api, fixture)["runtime_dependencies"]
    assert result["status"] == "declared_implicit"
    assert result["declared_enabling_paths"][0]["conditional_edges"][0]["conditions"] == ["TargetAllowList"]
    assert result["runtime_loaded_state"] == "NOT_VERIFIED"


def test_project_disabling_engine_defaults_removes_default_only_path(api, fixture):
    require_gamefeatures(fixture[0])
    plugin(fixture[1], "GameFeatures", default=True)
    assert context(api, fixture)["runtime_dependencies"]["status"] == "declared_implicit"
    result = context(api, fixture, {"DisableEnginePluginsByDefault": True})["runtime_dependencies"]
    assert result["status"] == "potential_missing_runtime_dependency"
    assert result["declared_enabling_paths"] == []
    assert result["disable_engine_plugins_by_default"] is True
    explicit = {"DisableEnginePluginsByDefault": True, "Plugins": [{"Name": "GameFeatures", "Enabled": True}]}
    assert context(api, fixture, explicit)["runtime_dependencies"]["status"] == "declared_explicit"


@pytest.mark.parametrize("flag", ["true", 1, None])
def test_disable_engine_defaults_flag_is_strict_boolean(api, fixture, flag):
    require_gamefeatures(fixture[0])
    with pytest.raises(ValueError, match="Malformed DisableEnginePluginsByDefault"):
        context(api, fixture, {"DisableEnginePluginsByDefault": flag})


def test_unquoted_gamefeature_class_at_end_is_detected(api, fixture):
    (fixture[0] / "Config/DefaultGame.ini").write_text(
        '[/Script/Engine.AssetManagerSettings]\n'
        '+PrimaryAssetTypesToScan=AssetBaseClass=/Script/GameFeatures.GameFeatureData\n'
    )
    plugin(fixture[1], "GameFeatures")
    assert context(api, fixture)["runtime_dependencies"]["status"] == "potential_missing_runtime_dependency"


@pytest.mark.parametrize("config", [
    '; /Script/GameFeatures.GameFeatureData\n',
    '[Unrelated]\n+PrimaryAssetTypesToScan=(AssetBaseClass="/Script/GameFeatures.GameFeatureData")\n',
    '[/Script/Engine.AssetManagerSettings]\n-PrimaryAssetTypesToScan=(AssetBaseClass="/Script/GameFeatures.GameFeatureData")\n',
    '[/Script/Engine.AssetManagerSettings]\n+PrimaryAssetTypesToScan=(AssetBaseClass="/Script/GameFeatures.GameFeatureData")\n!PrimaryAssetTypesToScan=ClearArray\n',
])
def test_no_runtime_requirement_does_not_scan_or_recommend_plugin(api, fixture, monkeypatch, config):
    (fixture[0] / "Config/DefaultGame.ini").write_text(config)
    monkeypatch.setattr(api, "_plugin_index", lambda root: pytest.fail("No irrelevant Engine plugin scan"))
    assert context(api, fixture)["runtime_dependencies"]["status"] == "not_detected"


def test_removed_exact_array_entry_does_not_leave_false_requirement(api, fixture):
    require_gamefeatures(fixture[0])
    path = fixture[0] / "Config/DefaultGame.ini"
    value = path.read_text().splitlines()[1][1:]
    path.write_text(path.read_text() + "-" + value + "\n")
    assert context(api, fixture)["runtime_dependencies"]["status"] == "not_detected"


def test_trailing_comma_is_normalized_in_memory_only(api, fixture):
    require_gamefeatures(fixture[0])
    path = plugin(fixture[1], "GameFeatures")
    path.write_bytes(b'{"EnabledByDefault":true,"Description":"comma, } inside string",}')
    before = path.read_bytes()
    assert context(api, fixture)["runtime_dependencies"]["status"] == "declared_implicit"
    assert path.read_bytes() == before


def test_cyclic_graph_is_bounded_and_reports_missing_path(api, fixture):
    require_gamefeatures(fixture[0])
    plugin(fixture[1], "Root", [{"Name": "Middle", "Enabled": True}], default=True)
    plugin(fixture[1], "Middle", [{"Name": "Root", "Enabled": True}])
    plugin(fixture[1], "GameFeatures")
    assert context(api, fixture)["runtime_dependencies"]["status"] == "potential_missing_runtime_dependency"


def test_rejects_malformed_dependency_instead_of_silently_skipping(api, fixture):
    require_gamefeatures(fixture[0])
    plugin(fixture[1], "GameFeatures", [{"Name": "Bad", "Enabled": "true"}])
    with pytest.raises(ValueError, match="Malformed plugin dependency"):
        context(api, fixture)


def test_inventory_and_document_bounds_fail_closed(api, fixture, monkeypatch):
    require_gamefeatures(fixture[0])
    plugin(fixture[1], "GameFeatures")
    monkeypatch.setattr(api, "MAX_PLUGIN_ENTRIES", 0)
    with pytest.raises(ValueError, match="bounded entry"):
        context(api, fixture)
    monkeypatch.setattr(api, "MAX_PLUGIN_ENTRIES", 20000)
    monkeypatch.setattr(api, "MAX_DOCUMENT_BYTES", 4)
    with pytest.raises(ValueError, match="bounded byte"):
        context(api, fixture)


def test_relative_paths_refused(api, fixture):
    with pytest.raises(ValueError, match="absolute"):
        api.inspect_runtime_context(Path("relative"), {}, fixture[1], {"status": "missing"})


def test_linked_engine_metadata_refused_before_read(api, fixture, tmp_path):
    metadata = fixture[1] / "Build/Build.version"
    target = tmp_path / "other.json"
    target.write_text(metadata.read_text())
    metadata.unlink()
    try:
        metadata.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError, match="Symlink/reparse"):
        context(api, fixture)


def test_windows_reparse_attribute_refused_without_creating_a_link(api, fixture, monkeypatch):
    metadata = fixture[1] / "Build/Build.version"
    original_lstat = Path.lstat

    def reparse_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == metadata:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse_lstat)
    with pytest.raises(ValueError, match="Symlink/reparse"):
        context(api, fixture)


@pytest.mark.parametrize("limit", ["MAX_PLUGIN_DESCRIPTORS", "MAX_PLUGIN_DEPTH"])
def test_remaining_inventory_bounds_refuse_incomplete_graph(api, fixture, monkeypatch, limit):
    require_gamefeatures(fixture[0])
    plugin(fixture[1], "GameFeatures")
    monkeypatch.setattr(api, limit, 0)
    with pytest.raises(ValueError, match="bounded"):
        context(api, fixture)


def test_duplicate_descriptor_names_cannot_resolve_arbitrarily(api, fixture):
    require_gamefeatures(fixture[0])
    original = plugin(fixture[1], "GameFeatures")
    duplicate = fixture[1] / "Plugins" / "Elsewhere" / "GameFeatures.uplugin"
    duplicate.parent.mkdir()
    duplicate.write_bytes(original.read_bytes())
    with pytest.raises(ValueError, match="Ambiguous duplicate"):
        context(api, fixture)


def test_dense_cyclic_default_graph_uses_single_reverse_traversal(api, fixture):
    require_gamefeatures(fixture[0])
    names = ["Node{}".format(number) for number in range(24)]
    plugin(fixture[1], "GameFeatures")
    for name in names:
        references = [{"Name": child, "Enabled": True} for child in names if child != name]
        references.append({"Name": "GameFeatures", "Enabled": True})
        plugin(fixture[1], name, references, default=True)
    result = context(api, fixture)["runtime_dependencies"]
    assert result["status"] == "declared_implicit"
    assert result["paths_truncated"] is True
    assert len(result["declared_enabling_paths"]) == api.MAX_PATHS
    # Independent of per-root BFS repetition: one index/reverse pass plus root lookups.
    assert result["graph_work"] < 1300


def test_graph_work_budget_refuses_instead_of_partial_success(api, fixture, monkeypatch):
    require_gamefeatures(fixture[0])
    chain(fixture[1])
    monkeypatch.setattr(api, "MAX_GRAPH_WORK", 2)
    with pytest.raises(ValueError, match="bounded graph work"):
        context(api, fixture, {"Plugins": [{"Name": "AllToolsets", "Enabled": True}]})


def test_project_root_conditions_are_kept_in_path_evidence(api, fixture):
    require_gamefeatures(fixture[0])
    chain(fixture[1])
    data = {"Plugins": [{"Name": "AllToolsets", "Enabled": True, "TargetAllowList": ["Editor"]}]}
    path = context(api, fixture, data)["runtime_dependencies"]["declared_enabling_paths"][0]
    assert path["conditional_edges"][0] == {
        "plugin": "<project>", "dependency": "AllToolsets", "conditions": ["TargetAllowList"],
    }


def test_json_depth_limit_is_independent_of_process_recursion_limit(api):
    # A permissive host recursion limit must not remove our input-complexity bound.
    previous_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(previous_limit, 20000))
    try:
        raw = b'{"nested":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}'
        with pytest.raises(ValueError, match="bounded JSON depth"):
            api._object(raw)
        with pytest.raises(ValueError, match="bounded JSON depth"):
            api._object(raw[:-1] + b',}', allow_trailing_comma=True)
    finally:
        sys.setrecursionlimit(previous_limit)


def test_json_depth_ignores_brackets_and_escaped_quotes_inside_strings(api):
    text = ('[{}]' * 2000) + ' escaped quote " then backslash \\ then brackets [{]}'
    raw = json.dumps({"description": text, "array": [{"value": "}\\\"[{"}]}).encode()
    assert api._object(raw)["description"] == text
    # Normalizing a descriptor's trailing comma still preserves string contents.
    assert api._object(raw[:-1] + b',}', allow_trailing_comma=True)["description"] == text


@pytest.mark.parametrize("raw", [
    b'{"x":"' + b'\\"' * 64,
    b'{"array":[1,2]',
    b'{"x":"' + b'\\"' * 64 + b'\\\n"}',
])
def test_incomplete_json_lexical_input_never_enters_regex_fallback(api, monkeypatch, raw):
    def forbidden(*args, **kwargs):
        pytest.fail("Incomplete JSON must be rejected before trailing-comma normalization")

    with monkeypatch.context() as context_patch:
        context_patch.setattr(api.re, "sub", forbidden)
        with pytest.raises(ValueError, match="Malformed runtime context JSON"):
            api._object(raw, allow_trailing_comma=True)

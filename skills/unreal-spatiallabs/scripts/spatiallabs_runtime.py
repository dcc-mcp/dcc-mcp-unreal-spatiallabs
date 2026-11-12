"""Bounded, read-only declared runtime context; never activates plugins or UE.

Installation metadata, a retained runtime log, and descriptor dependency paths
are different evidence. None of them attest live state or official support.
"""

import hashlib
import json
import os
import re
import stat
from collections import deque
from pathlib import Path

from spatiallabs_project import _inside, _no_links

MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_PLUGIN_ENTRIES = 20000
MAX_PLUGIN_DESCRIPTORS = 2000
MAX_PLUGIN_DEPTH = 12
MAX_DEPENDENCIES = 256
MAX_PATHS = 16
MAX_GRAPH_WORK = 50000
PRUNED_DIRECTORIES = frozenset(("content", "binaries", "source", "resources", "intermediate",
                                "saved", "deriveddatacache", ".git"))
DEPENDENCY_CONDITIONS = ("TargetAllowList", "TargetDenyList", "TargetConfigurationAllowList",
                         "TargetConfigurationDenyList", "PlatformAllowList", "PlatformDenyList",
                         "SupportedTargetPlatforms", "Optional")


def _read(path):
    path = _no_links(path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Runtime evidence must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("Runtime context document exceeds bounded byte limit")
    return raw


def _object(raw, allow_trailing_comma=False):
    text = raw.decode("utf-8-sig")
    depth, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            if ord(char) < 0x20:
                raise ValueError("Malformed runtime context JSON: raw control character in string")
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("Runtime context exceeds bounded JSON depth limit")
        elif char in "}]":
            depth -= 1
            if depth < 0:
                raise ValueError("Malformed runtime context JSON nesting")
    if in_string or depth != 0:
        # Reject incomplete lexical input before the trailing-comma regex. In
        # particular, a long unterminated escaped string must not trigger retry
        # matching at each quote inside that string.
        raise ValueError("Malformed runtime context JSON: unterminated string or container")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if not allow_trailing_comma:
            raise
        # Strings are consumed first, so commas inside JSON strings stay intact.
        text = re.sub(r'"(?:\\.|[^"\\])*"|,\s*(?=[}\]])',
                      lambda match: match[0] if match[0].startswith('"') else "", text)
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Runtime context JSON must contain an object")
    return data


def _metadata(engine_root):
    path = _inside(engine_root, engine_root / "Build" / "Build.version")
    result = {"path": str(path), "status": "missing"}
    if not path.exists():
        return result
    raw = _read(path)
    result["sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        value = _object(raw)
        numbers = [value.get(key) for key in ("MajorVersion", "MinorVersion", "PatchVersion", "Changelist")]
        if any(type(number) is not int or number < 0 for number in numbers) or numbers[0] < 1:
            raise ValueError("Incomplete engine metadata identity")
    except (ValueError, UnicodeError):
        result["status"] = "invalid"
        return result
    result.update(status="observed", version="{}.{}.{}".format(*numbers[:3]), changelist=numbers[3])
    return result


def _identity(engine_root, runtime_identity):
    if not isinstance(runtime_identity, dict):
        raise ValueError("runtime_identity must be an object")
    runtime = {"status": runtime_identity.get("status", "missing")}
    if runtime["status"] not in ("observed", "missing", "ambiguous"):
        raise ValueError("Unknown runtime identity status")
    if runtime["status"] == "observed":
        version, changelist = runtime_identity.get("version"), runtime_identity.get("changelist")
        if (not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
                or type(changelist) is not int or changelist < 0):
            runtime["status"] = "invalid"
        else:
            runtime.update(version=version, changelist=changelist)
    metadata = _metadata(engine_root)
    different = []
    status = "unknown"
    if metadata["status"] == runtime["status"] == "observed":
        different = [key for key in ("version", "changelist") if metadata[key] != runtime[key]]
        status = "mismatch" if different else "match"
    return {"status": status, "metadata": metadata, "runtime": runtime, "differing_fields": different,
            "official_support": "NOT_VERIFIED", "live_attestation": False,
            "meaning": "A metadata/log match is evidence consistency, not official compatibility or live engine attestation"}


def _gamefeature_requirement(project_root):
    path = _inside(project_root, project_root / "Config" / "DefaultGame.ini")
    if not path.exists():
        return {"detected": False, "config_path": str(path)}
    raw = _read(path)
    entries, section = {}, ""
    for number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].casefold()
            continue
        if section != "/script/engine.assetmanagersettings" or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key.lstrip("+-!").casefold() != "primaryassettypestoscan":
            continue
        if key.startswith("!"):
            entries.clear()
        elif key.startswith("-"):
            entries.pop(value, None)
        else:
            entries[value] = number
    lines = sorted(number for value, number in entries.items()
                   if re.search(r"/Script/GameFeatures\.GameFeatureData(?=[\"\s,)]|$)", value))
    return {"detected": bool(lines), "config_path": str(path), "line_numbers": lines,
            "config_sha256": hashlib.sha256(raw).hexdigest(),
            "scope": "Literal active DefaultGame.ini AssetManager PrimaryAssetTypesToScan entries; not merged runtime config"}


def _references(data):
    references = data.get("Plugins", [])
    if not isinstance(references, list) or len(references) > MAX_DEPENDENCIES:
        raise ValueError("Invalid or excessive plugin references")
    result, seen = [], set()
    for value in references:
        if (not isinstance(value, dict) or not isinstance(value.get("Name"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]+", value["Name"])
                or type(value.get("Enabled")) is not bool):
            raise ValueError("Malformed plugin dependency reference")
        name = value["Name"].casefold()
        if name in seen:
            raise ValueError("Duplicate plugin dependency reference")
        seen.add(name)
        conditions = []
        for key in DEPENDENCY_CONDITIONS:
            if key in value:
                if key == "Optional":
                    if type(value[key]) is not bool:
                        raise ValueError("Malformed optional plugin dependency")
                    if value[key]:
                        conditions.append(key)
                else:
                    if (not isinstance(value[key], list)
                            or any(not isinstance(item, str) for item in value[key])):
                        raise ValueError("Malformed conditional plugin dependency")
                    conditions.append(key)
        result.append({"name": value["Name"], "enabled": value["Enabled"], "conditions": conditions})
    return result


def _plugin_index(engine_root):
    plugins = _inside(engine_root, engine_root / "Plugins")
    if not plugins.is_dir():
        return {}, 0
    pending, index, entries_seen = [(plugins, 0)], {}, 0
    while pending:
        folder, depth = pending.pop()
        with os.scandir(str(_inside(engine_root, folder))) as entries:
            for entry in entries:
                entries_seen += 1
                if entries_seen > MAX_PLUGIN_ENTRIES:
                    raise ValueError("Plugin inventory exceeds bounded entry limit")
                if entry.name.casefold() in PRUNED_DIRECTORIES:
                    continue
                path = _inside(engine_root, Path(entry.path))
                mode = path.lstat().st_mode
                if stat.S_ISDIR(mode):
                    if depth >= MAX_PLUGIN_DEPTH:
                        raise ValueError("Plugin inventory exceeds bounded depth limit")
                    pending.append((path, depth + 1))
                elif stat.S_ISREG(mode) and path.suffix.casefold() == ".uplugin":
                    if len(index) >= MAX_PLUGIN_DESCRIPTORS:
                        raise ValueError("Plugin inventory exceeds bounded descriptor limit")
                    data = _object(_read(path), allow_trailing_comma=True)
                    if "EnabledByDefault" in data and type(data["EnabledByDefault"]) is not bool:
                        raise ValueError("Malformed plugin EnabledByDefault")
                    name = path.stem.casefold()
                    if name in index:
                        raise ValueError("Ambiguous duplicate plugin descriptor name")
                    index[name] = {"name": path.stem, "path": str(path),
                                   "enabled_by_default": data.get("EnabledByDefault", False),
                                   "references": _references(data)}
                elif not stat.S_ISREG(mode):
                    raise ValueError("Special files are not allowed in plugin inventory")
    return index, entries_seen


def _graph_step(work):
    work[0] += 1
    if work[0] > MAX_GRAPH_WORK:
        raise ValueError("Plugin dependency analysis exceeds bounded graph work limit")


def _edge_conditions(parent, edge):
    return ([{"plugin": parent, "dependency": edge["name"], "conditions": edge["conditions"]}]
            if edge["conditions"] else [])


def _shortest_paths(index, target, disabled, work):
    """One reverse BFS, not one traversal per enabled/default root."""
    incoming = {}
    for name, node in sorted(index.items()):
        _graph_step(work)
        for edge in sorted(node["references"], key=lambda item: item["name"].casefold()):
            _graph_step(work)
            child = edge["name"].casefold()
            if edge["enabled"] and name not in disabled and child not in disabled and child in index:
                incoming.setdefault(child, []).append((name, edge))
    if target not in index or target in disabled:
        return {}
    paths = {target: {"plugins": [index[target]["name"]], "conditional_edges": []}}
    pending = deque([target])
    while pending:
        child = pending.popleft()
        for parent, edge in incoming.get(child, []):
            _graph_step(work)
            if parent not in paths:  # Mark on enqueue; a cyclic/dense graph cannot duplicate queue entries.
                paths[parent] = {"plugins": [index[parent]["name"]] + paths[child]["plugins"],
                                 "conditional_edges": _edge_conditions(index[parent]["name"], edge)
                                 + paths[child]["conditional_edges"]}
                pending.append(parent)
    return paths


def _dependencies(project_root, project_data, engine_root):
    requirement = _gamefeature_requirement(project_root)
    result = {"status": "not_detected", "requirement": requirement, "required_plugin": "GameFeatures",
              "runtime_loaded_state": "NOT_VERIFIED",
              "scope": "Declared dependency paths only; target/platform conditions and UE runtime resolution may differ"}
    if not requirement["detected"]:
        return result
    disable_defaults = project_data.get("DisableEnginePluginsByDefault", False)
    if type(disable_defaults) is not bool:
        raise ValueError("Malformed DisableEnginePluginsByDefault")
    references = _references(project_data)
    explicit = {edge["name"].casefold(): edge for edge in references}
    disabled = {name for name, edge in explicit.items() if not edge["enabled"]}
    index, entries_seen = _plugin_index(engine_root)
    target = "gamefeatures"
    roots = {name for name, edge in explicit.items() if edge["enabled"]}
    if not disable_defaults:
        roots.update(name for name, node in index.items() if node["enabled_by_default"] and name not in explicit)
    work = [0]
    known = _shortest_paths(index, target, disabled, work)
    paths, lost = [], []
    for root in sorted(roots):
        _graph_step(work)
        if root in known:
            path = known[root]
            conditions = explicit.get(root, {}).get("conditions", [])
            if conditions:
                path = {"plugins": path["plugins"], "conditional_edges": [
                    {"plugin": "<project>", "dependency": index[root]["name"], "conditions": conditions}
                ] + path["conditional_edges"]}
            paths.append(path)
    for root in sorted(disabled):
        _graph_step(work)
        if root not in index:
            continue
        if root == target:
            lost.append({"plugins": [index[root]["name"]], "conditional_edges": []})
            continue
        candidates = []
        for edge in index[root]["references"]:
            _graph_step(work)
            child = edge["name"].casefold()
            if edge["enabled"] and child in known:
                candidates.append({"plugins": [index[root]["name"]] + known[child]["plugins"],
                                   "conditional_edges": _edge_conditions(index[root]["name"], edge)
                                   + known[child]["conditional_edges"]})
        if candidates:
            lost.append(min(candidates, key=lambda path: (len(path["plugins"]), path["plugins"])))
    if target not in index:
        status = "required_descriptor_missing"
    elif target in disabled:
        status = "declared_explicitly_disabled"
    elif target in explicit and explicit[target]["enabled"]:
        status = "declared_explicit"
    elif paths:
        status = "declared_implicit"
    elif lost:
        status = "potential_lost_implicit_dependency"
    else:
        status = "potential_missing_runtime_dependency"
    result.update(status=status, declared_enabling_paths=paths[:MAX_PATHS],
                  paths_from_disabled_roots=lost[:MAX_PATHS],
                  paths_truncated=len(paths) > MAX_PATHS or len(lost) > MAX_PATHS,
                  descriptors_indexed=len(index), inventory_entries_seen=entries_seen,
                  graph_work=work[0], graph_work_limit=MAX_GRAPH_WORK,
                  disable_engine_plugins_by_default=disable_defaults,
                  explicit_reference_conditions=explicit.get(target, {}).get("conditions", []),
                  automatic_repair=False,
                  next_step="Review the actual runtime dependency and logs; do not re-enable a control toolset or enable GameFeatures without project-specific evidence")
    return result


def inspect_runtime_context(project_root, project_data, engine_root, runtime_identity):
    """Inspect one explicit project/engine and an already-extracted log identity.

    Does not import unreal, execute code, write files, or grant installation/run
    authority. Runtime identity is retained log evidence, never live attestation.
    """
    project_root, engine_root = _no_links(Path(project_root)), _no_links(Path(engine_root))
    if not project_root.is_dir() or not engine_root.is_dir() or not isinstance(project_data, dict):
        raise ValueError("Existing absolute project/Engine directories and project data are required")
    return {"engine_identity": _identity(engine_root, runtime_identity),
            "runtime_dependencies": _dependencies(project_root, project_data, engine_root)}

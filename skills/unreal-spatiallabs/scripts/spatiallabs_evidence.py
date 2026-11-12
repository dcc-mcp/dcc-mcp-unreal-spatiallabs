"""Read-only software evidence checks; no launch, repair or vendor authority."""

from pathlib import Path

from spatiallabs_project import _no_links
from spatiallabs_run_evidence import _snapshot, inspect_run_evidence
from spatiallabs_runtime import _object, inspect_runtime_context

MAX_PROJECT_BYTES = 1024 * 1024


def inspect_software_evidence(project_path, engine_root, run_log_path, capture_path=None, cache_state="unknown"):
    descriptor = _no_links(Path(project_path))
    if descriptor.suffix.lower() != ".uproject":
        raise ValueError("The exact editable .uproject file is required; resolve delivery folders with inspect_project")
    descriptor, raw, fingerprint = _snapshot(descriptor, MAX_PROJECT_BYTES)
    data = _object(raw)
    root, descriptor_hash = descriptor.parent, fingerprint["sha256"]
    run = inspect_run_evidence(run_log_path, capture_path, cache_state)
    runtime = inspect_runtime_context(root, data, engine_root, run["runtime_identity"])
    if _snapshot(descriptor, MAX_PROJECT_BYTES)[2]["sha256"] != descriptor_hash:
        raise ValueError("Project descriptor changed during evidence inspection")
    return {
        "status": "analyzed",
        "project_path": str(descriptor),
        "project_descriptor_sha256": descriptor_hash,
        "runtime": runtime,
        "run": run,
        "project_to_run_binding": "not_verified",
        "compatibility_status": "unknown",
        "hardware_verified": False,
        "installation_authorized": False,
        "host_actions_executed": False,
        "limitations": [
            "This compares specified files, not live host or executable identity",
            "A log/map/PNG cannot independently prove the current project produced that run",
            "Declared plugin dependencies do not prove actual module or interpreter state",
            "A warm capture never clears an earlier cold-run failure",
            "Valid native capture requires visual review; scene readiness is not inferred from a delay or frame count",
            "Installation, support, build, interaction, SBS, OBS and physical-device acceptance are not granted",
        ],
    }

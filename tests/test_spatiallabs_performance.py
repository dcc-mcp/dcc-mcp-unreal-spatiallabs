"""Real regression tests for the optional offline performance/acceptance tools."""

import copy
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "skills/unreal-spatiallabs/scripts/spatiallabs_performance.py"
SPEC = importlib.util.spec_from_file_location("spatiallabs_performance", SCRIPT)
PERFORMANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PERFORMANCE)


def capture():
    return {
        "identity": {
            "project": "P:/isolated/Demo/Demo.uproject", "source_hash": "a" * 64,
            "scene": "/Game/Benchmark", "camera": "BenchmarkCamera", "resolution": [3840, 2160],
            "quality": {"preset": "Epic"}, "hardware": {"gpu": "test GPU", "cpu": "test CPU"},
            "driver": "fixture-driver", "engine": "5.8.1", "plugin": "fixture-plugin",
            "runtime": "fixture-runtime", "stereo": "stereo", "sample_window_seconds": 30,
            "warmup_seconds": 10, "capture_mode": "standalone, uncapped, AC power, fixed route",
        },
        "metrics": {
            "cpu_ms": {"samples": [10, 11, 12], "source": "synthetic regression fixture"},
            "gpu_ms": {"samples": [20, 21, 22], "source": "synthetic regression fixture"},
            "frame_ms": {"samples": [20, 21, 22], "source": "synthetic regression fixture"},
            "render_fps": {"samples": [50, 48, 46], "source": "synthetic regression fixture"},
            "display_fps": {"samples": [50, 48, 46], "source": "synthetic regression fixture"},
            "latency_ms": {"samples": None, "reason": "No latency instrument"},
        },
        "optimizations": {"fg": False},
    }


def test_frame_generation_display_fps_does_not_change_render_measurements():
    baseline = capture()
    candidate = copy.deepcopy(baseline)
    candidate["optimizations"]["fg"] = True
    candidate["metrics"]["display_fps"]["samples"] = [100, 96, 92]
    report = PERFORMANCE.analyze_performance(baseline, candidate)
    assert report["status"] == "comparable"
    assert report["comparison"]["display_fps"]["change_percent"] == 100
    assert report["comparison"]["display_fps"]["interpretation"] == "presentation_cadence_only"
    assert report["comparison"]["gpu_ms"]["delta"] == 0
    assert report["comparison"]["render_fps"]["delta"] == 0
    assert report["device_validation"] == "NOT_RUN"


@pytest.mark.parametrize("field,value", [("resolution", [1920, 1080]), ("camera", "OtherCamera"),
                                        ("sample_window_seconds", 45), ("warmup_seconds", 20),
                                        ("source_hash", "b" * 64), ("stereo", "mono")])
def test_changed_conditions_block_direct_comparison(field, value):
    baseline = capture()
    candidate = copy.deepcopy(baseline)
    candidate["identity"][field] = value
    result = PERFORMANCE.analyze_performance(baseline, candidate)
    assert result["status"] == "not_comparable"
    assert field in result["mismatched_conditions"]
    assert result["comparison"] == {}


def test_extra_condition_cannot_be_silently_ignored():
    baseline = capture()
    candidate = copy.deepcopy(baseline)
    candidate["identity"]["power_mode"] = "battery saver"
    assert PERFORMANCE.analyze_performance(baseline, candidate)["mismatched_conditions"] == ["power_mode"]


def test_boolean_and_number_are_distinct_quality_settings():
    baseline = capture()
    candidate = capture()
    baseline["identity"]["quality"] = {"motion_blur": False}
    candidate["identity"]["quality"] = {"motion_blur": 0}
    assert PERFORMANCE.analyze_performance(baseline, candidate)["mismatched_conditions"] == ["quality"]


@pytest.mark.parametrize("field", PERFORMANCE.IDENTITY_FIELDS)
def test_missing_identity_is_rejected(field):
    baseline = capture()
    del baseline["identity"][field]
    with pytest.raises(ValueError, match="identity missing"):
        PERFORMANCE.analyze_performance(baseline, capture())


@pytest.mark.parametrize("bad", [True, False, float("nan"), float("inf"), -1, 0, "16.6"])
def test_non_measurements_cannot_become_frame_times(bad):
    baseline = capture()
    baseline["metrics"]["gpu_ms"]["samples"] = [bad]
    with pytest.raises(ValueError):
        PERFORMANCE.analyze_performance(baseline, capture())


def test_missing_gpu_counter_stays_unavailable_with_reason():
    baseline = capture()
    baseline["metrics"]["gpu_ms"] = {"samples": None, "reason": "GPU timing unavailable on this RHI"}
    result = PERFORMANCE.analyze_performance(baseline, capture())
    assert result["baseline"]["metrics"]["gpu_ms"]["mean"] is None
    assert result["baseline"]["metrics"]["gpu_ms"]["reason"] == "GPU timing unavailable on this RHI"
    assert result["comparison"]["gpu_ms"]["delta"] is None


def test_missing_latency_does_not_fabricate_latency_improvement():
    result = PERFORMANCE.analyze_performance(capture(), capture())
    assert result["comparison"]["latency_ms"]["status"] == "unavailable"
    assert result["comparison"]["latency_ms"]["change_percent"] is None


def test_percentiles_and_measured_difference_are_from_samples():
    baseline = capture()
    candidate = copy.deepcopy(baseline)
    baseline["metrics"]["gpu_ms"]["samples"] = [10, 20, 30, 40, 50]
    candidate["metrics"]["gpu_ms"]["samples"] = [5, 10, 15, 20, 25]
    result = PERFORMANCE.analyze_performance(baseline, candidate)
    assert result["baseline"]["metrics"]["gpu_ms"]["p50"] == 30
    assert result["baseline"]["metrics"]["gpu_ms"]["p95"] == 48
    assert result["baseline"]["metrics"]["gpu_ms"]["p99"] == 49.6
    assert result["comparison"]["gpu_ms"]["change_percent"] == -50


def test_metric_requires_source_and_correct_unit():
    baseline = capture()
    baseline["metrics"]["gpu_ms"] = {"samples": [10], "source": "counter", "unit": "fps"}
    with pytest.raises(ValueError, match="unit"):
        PERFORMANCE.analyze_performance(baseline, capture())
    baseline["metrics"]["gpu_ms"] = {"samples": [10]}
    with pytest.raises(ValueError, match="source"):
        PERFORMANCE.analyze_performance(baseline, capture())


def test_empty_samples_require_explicit_unavailable_reason():
    baseline = capture()
    baseline["metrics"]["gpu_ms"] = {"samples": [], "source": "capture failed"}
    with pytest.raises(ValueError, match="samples"):
        PERFORMANCE.analyze_performance(baseline, capture())


def test_gpu_name_does_not_imply_dlss_support():
    run = capture()
    run["identity"]["hardware"]["gpu"] = "NVIDIA RTX 5090"
    result = PERFORMANCE.analyze_performance(run, run)
    assert all(item["status"] == "unknown" for item in result["baseline"]["dlss"].values())


def dlss_evidence(run):
    return {"status": "supported", "reason": "Synthetic reference validation fixture; no hardware claim",
            "source_url": "https://developer.nvidia.com/rtx/dlss",
            "checked_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "versions": {key: copy.deepcopy(run["identity"][key])
                         for key in ("engine", "plugin", "runtime", "hardware", "driver")},
            "stereo_compatible": True, "stereo_source_url": "https://spatiallabs.acer.com/developer/docs/test"}


@pytest.mark.parametrize("change", ["stereo_evidence", "version", "domain", "time"])
def test_incomplete_exact_combo_dlss_claim_is_unknown(change):
    run = capture()
    record = dlss_evidence(run)
    if change == "stereo_evidence":
        del record["stereo_source_url"]
    elif change == "version":
        record["versions"]["plugin"] = "different"
    elif change == "domain":
        record["source_url"] = "https://nvidia.com.attacker.example/dlss"
    else:
        record["checked_at"] = datetime.now(timezone.utc).date().isoformat()
    run["dlss"] = {"sr": record}
    result = PERFORMANCE.analyze_performance(run, run)
    assert result["baseline"]["dlss"]["sr"]["status"] == "unknown"


def test_dlss_features_are_independent_and_caller_evidence_is_labelled():
    run = capture()
    run["dlss"] = {"sr": dlss_evidence(run)}
    result = PERFORMANCE.analyze_performance(run, run)
    dlss = result["baseline"]["dlss"]
    assert dlss["sr"]["status"] == "supported"
    assert dlss["sr"]["evidence_origin"] == "caller_supplied_not_independently_verified"
    assert dlss["fg"]["status"] == "unknown"
    assert dlss["rr"]["status"] == "unknown"


@pytest.mark.parametrize("age_days", [-1, 8])
def test_future_or_stale_dlss_evidence_cannot_claim_support(age_days):
    run = capture()
    record = dlss_evidence(run)
    record["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    run["dlss"] = {"sr": record}
    assert PERFORMANCE.analyze_performance(run, run)["baseline"]["dlss"]["sr"]["status"] == "unknown"


def test_recent_non_utc_dlss_evidence_is_normalized_for_age_check():
    run = capture()
    record = dlss_evidence(run)
    record["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=6)).astimezone(
        timezone(timedelta(hours=8))).isoformat()
    run["dlss"] = {"sr": record}
    assert PERFORMANCE.analyze_performance(run, run)["baseline"]["dlss"]["sr"]["status"] == "supported"


@pytest.mark.parametrize("field", ["hardware", "driver"])
@pytest.mark.parametrize("change", ["missing", "different", "wrong_type"])
def test_dlss_evidence_requires_the_exact_hardware_and_driver(field, change):
    run = capture()
    record = dlss_evidence(run)
    if change == "missing":
        del record["versions"][field]
    elif change == "wrong_type":
        record["versions"][field] = 1
    else:
        record["versions"][field] = {"gpu": "different GPU", "cpu": "test CPU"} if field == "hardware" else "other driver"
    run["dlss"] = {"sr": record}
    assert PERFORMANCE.analyze_performance(run, run)["baseline"]["dlss"]["sr"]["status"] == "unknown"


def test_bad_official_url_port_is_unknown_instead_of_crashing_url_parser():
    run = capture()
    record = dlss_evidence(run)
    record["source_url"] = "https://developer.nvidia.com:invalid/dlss"
    run["dlss"] = {"sr": record}
    assert PERFORMANCE.analyze_performance(run, run)["baseline"]["dlss"]["sr"]["status"] == "unknown"


def test_extreme_percentage_remains_json_serializable_without_infinity():
    baseline = capture()
    candidate = capture()
    baseline["metrics"]["gpu_ms"]["samples"] = [1e-300]
    candidate["metrics"]["gpu_ms"]["samples"] = [1e300]
    result = PERFORMANCE.analyze_performance(baseline, candidate)
    assert result["comparison"]["gpu_ms"]["change_percent"] is None
    json.dumps(result, allow_nan=False)


def test_nan_optimization_settings_cannot_leak_into_output_json():
    run = capture()
    run["optimizations"] = {"resolution_scale": float("nan")}
    with pytest.raises(ValueError):
        PERFORMANCE.analyze_performance(run, run)


def test_no_device_forces_all_hardware_layers_not_run_despite_claimed_pass():
    layers = {key: {"status": "PASS", "evidence": "old-2d-video.mp4"} for key in PERFORMANCE.DEVICE_LAYERS}
    result = PERFORMANCE.acceptance_report({"layers": layers})
    assert result["status"] == "incomplete"
    for key in PERFORMANCE.DEVICE_LAYERS:
        assert result["layers"][key]["status"] == "NOT_RUN"
        assert result["layers"][key]["requested_status"] == "PASS"


def test_device_name_alone_is_not_physical_hardware_evidence():
    result = PERFORMANCE.acceptance_report({"device": {"present": True, "model": "SpatialLabs Pro"}})
    assert result["physical_device_evidence_supplied"] is False


def test_old_2d_or_mock_run_cannot_pass_new_editor_package_layers():
    result = PERFORMANCE.acceptance_report({"layers": {
        "editor": {"status": "PASS", "evidence": "mock stdout", "capture_kind": "synthetic"},
        "2d": {"status": "PASS", "evidence": "previous.mp4", "capture_kind": "previous_run"},
    }})
    assert result["layers"]["editor"]["status"] == "NOT_RUN"
    assert result["layers"]["2d"]["status"] == "NOT_RUN"


def test_each_device_layer_requires_matching_actual_device_capture():
    device = {"present": True, "kind": "physical", "family": "acer_spatiallabs",
              "device_id": "device-1", "model": "fixture SpatialLabs Pro",
              "evidence": "operator-device-check.json"}
    result = PERFORMANCE.acceptance_report({"device": device, "skill_run_id": "new-skill-run", "layers": {
        "stereo": {"status": "PASS", "evidence": "device-1-stereo.json", "capture_kind": "physical_device",
                   "device_id": "device-1", "skill_run_id": "new-skill-run"},
        "tracking": {"status": "PASS", "evidence": "other.json", "capture_kind": "physical_device",
                     "device_id": "device-2", "skill_run_id": "new-skill-run"},
    }})
    assert result["layers"]["stereo"]["status"] == "PASS"
    assert result["layers"]["tracking"]["status"] == "NOT_RUN"
    assert result["layers"]["comfort"]["status"] == "NOT_RUN"


@pytest.mark.parametrize("family", [None, "generic_monitor", "oculus"])
def test_other_or_unspecified_hardware_family_cannot_pass_spatiallabs_layers(family):
    device = {"present": True, "kind": "physical", "device_id": "device-1", "model": "physical display",
              "evidence": "operator-device-check.json"}
    if family is not None:
        device["family"] = family
    layers = {key: {"status": "PASS", "evidence": key + ".json", "capture_kind": "physical_device",
                    "device_id": "device-1", "skill_run_id": "new-run"} for key in PERFORMANCE.DEVICE_LAYERS}
    result = PERFORMANCE.acceptance_report({"device": device, "skill_run_id": "new-run", "layers": layers})
    assert result["physical_device_evidence_supplied"] is False
    assert all(result["layers"][key]["status"] == "NOT_RUN" for key in PERFORMANCE.DEVICE_LAYERS)


def test_actual_editor_capture_from_previous_run_cannot_pass_current_skill():
    report = PERFORMANCE.acceptance_report({"skill_run_id": "new-run", "layers": {
        "editor": {"status": "PASS", "evidence": "old-editor.log", "capture_kind": "actual_run",
                   "skill_run_id": "old-run"},
        "2d": {"status": "PASS", "evidence": "new-2d.log", "capture_kind": "actual_run",
               "skill_run_id": "new-run"},
    }})
    assert report["layers"]["editor"]["status"] == "NOT_RUN"
    assert report["layers"]["2d"]["status"] == "PASS"


def test_layer_failure_is_not_hidden_by_missing_device():
    result = PERFORMANCE.acceptance_report({"layers": {"code": {"status": "FAIL", "evidence": "pytest.log"}}})
    assert result["status"] == "failed"


@pytest.mark.parametrize("evidence", [{"device": {"present": "false"}},
                                       {"layers": {"code": {"status": "PASS"}}},
                                       {"layers": {"code": {"status": True}}}])
def test_invalid_acceptance_cannot_be_reported_passed(evidence):
    with pytest.raises(ValueError):
        PERFORMANCE.acceptance_report(evidence)

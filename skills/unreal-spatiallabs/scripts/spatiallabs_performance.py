"""Bounded, offline performance comparison and layered acceptance reporting.

All measurements and compatibility references are caller-supplied evidence.
This module never probes a device, downloads software, or changes a project.
It deliberately supports Python 3.7 syntax independently of the adapter.
"""

import math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

IDENTITY_FIELDS = (
    "project", "source_hash", "scene", "camera", "resolution", "quality",
    "hardware", "driver", "engine", "plugin", "runtime", "stereo",
    "sample_window_seconds", "warmup_seconds", "capture_mode",
)
METRICS = ("cpu_ms", "gpu_ms", "frame_ms", "render_fps", "display_fps", "latency_ms")
DLSS_FEATURES = ("sr", "dlaa", "rr", "fg")
LAYERS = ("code", "editor", "2d", "package", "stereo", "tracking", "comfort", "device_performance")
DEVICE_LAYERS = ("stereo", "tracking", "comfort", "device_performance")
MAX_SAMPLES = 100000


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError("{} must be a nonempty string of at most 4096 characters".format(label))
    return value


def _number(value, label, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{} must be a finite number".format(label))
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ValueError("{} must be a finite number".format(label))
    if not math.isfinite(result) or result < 0 or (result == 0 and not allow_zero):
        raise ValueError("{} must be {} and finite".format(label, "nonnegative" if allow_zero else "positive"))
    return result


def _condition(value, label, depth=0):
    """Reject missing, non-JSON, unbounded, or nonfinite identity components."""
    if depth > 8:
        raise ValueError("{} identity nesting exceeds eight levels".format(label))
    if isinstance(value, str):
        return _text(value, label)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        _number(value, label, allow_zero=True)
        return value
    if isinstance(value, list) and 0 < len(value) <= 64:
        return [_condition(item, label, depth + 1) for item in value]
    if isinstance(value, dict) and 0 < len(value) <= 64:
        return {_text(key, label): _condition(item, label, depth + 1) for key, item in value.items()}
    raise ValueError("{} must explicitly contain nonempty JSON identity data".format(label))


def _same_condition(left, right):
    # Python considers False == 0; those are different captured settings.
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (set(left) == set(right)
                and all(_same_condition(left[key], right[key]) for key in left))
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_condition(a, b) for a, b in zip(left, right))
    return left == right


def _identity(run, label):
    if not isinstance(run, dict) or not isinstance(run.get("identity"), dict):
        raise ValueError("{}.identity must be an object".format(label))
    identity = run["identity"]
    missing = [key for key in IDENTITY_FIELDS if key not in identity]
    if missing:
        raise ValueError("{}.identity missing: {}".format(label, ", ".join(missing)))
    result = {key: _condition(identity[key], "{}.identity.{}".format(label, key)) for key in IDENTITY_FIELDS}
    for key in ("project", "source_hash", "scene", "camera", "driver", "engine", "plugin", "runtime", "capture_mode"):
        _text(identity[key], "{}.identity.{}".format(label, key))
    resolution = identity["resolution"]
    if not isinstance(resolution, list) or len(resolution) != 2:
        raise ValueError("{}.identity.resolution must be [width, height]".format(label))
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in resolution):
        raise ValueError("{}.identity.resolution must contain positive integers".format(label))
    if identity["stereo"] not in ("mono", "stereo"):
        raise ValueError("{}.identity.stereo must be mono or stereo".format(label))
    result["sample_window_seconds"] = _number(identity["sample_window_seconds"], "sample_window_seconds")
    result["warmup_seconds"] = _number(identity["warmup_seconds"], "warmup_seconds", allow_zero=True)
    # Extra conditions (for example power mode or refresh rate) also participate.
    for key, value in identity.items():
        if key not in result:
            result[_text(key, "identity key")] = _condition(value, "{}.identity.{}".format(label, key))
    return result


def _percentile(ordered, fraction):
    position = (len(ordered) - 1) * fraction
    low = int(math.floor(position))
    high = int(math.ceil(position))
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _metric(record, metric):
    unit = "fps" if metric.endswith("fps") else "ms"
    if record is None:
        return {"status": "unavailable", "unit": unit, "samples": 0, "mean": None,
                "p50": None, "p95": None, "p99": None, "reason": "not_provided"}
    if not isinstance(record, dict):
        raise ValueError("metrics.{} must be an object or null".format(metric))
    if record.get("samples") is None:
        reason = _text(record.get("reason"), "metrics.{}.reason".format(metric))
        return {"status": "unavailable", "unit": unit, "samples": 0, "mean": None,
                "p50": None, "p95": None, "p99": None, "reason": reason}
    samples = record["samples"]
    if not isinstance(samples, list) or not 1 <= len(samples) <= MAX_SAMPLES:
        raise ValueError("metrics.{}.samples must contain 1 to {} values".format(metric, MAX_SAMPLES))
    source = _text(record.get("source"), "metrics.{}.source".format(metric))
    if record.get("unit", unit) != unit:
        raise ValueError("metrics.{} unit must be {}".format(metric, unit))
    ordered = sorted(_number(value, "metrics.{}.samples".format(metric)) for value in samples)
    # Divide before summing, so individually finite large values cannot overflow a mean.
    mean = math.fsum(value / len(ordered) for value in ordered)
    return {"status": "measured", "unit": unit, "samples": len(ordered), "source": source,
            "mean": mean, "p50": _percentile(ordered, 0.50), "p95": _percentile(ordered, 0.95),
            "p99": _percentile(ordered, 0.99), "reason": None}


def _official_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        return (parsed.scheme == "https" and not parsed.username and not parsed.password
                and parsed.port in (None, 443)
                and any(host == domain or host.endswith("." + domain)
                        for domain in ("acer.com", "nvidia.com", "epicgames.com")))
    except ValueError:
        return False


def _checked_time(value):
    if not isinstance(value, str):
        return False
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return False
        age = datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)
        return timedelta(0) <= age <= timedelta(days=7)
    except ValueError:
        return False


def _dlss(run, identity):
    provided = run.get("dlss", {})
    if not isinstance(provided, dict):
        raise ValueError("dlss must be an object")
    result = {}
    for feature in DLSS_FEATURES:
        record = provided.get(feature)
        if record is None:
            result[feature] = {"status": "unknown", "reason": "No feature-specific compatibility evidence supplied"}
            continue
        if not isinstance(record, dict) or record.get("status") not in ("supported", "unsupported", "unknown"):
            raise ValueError("dlss.{} needs supported, unsupported, or unknown status".format(feature))
        reason = _text(record.get("reason"), "dlss.{}.reason".format(feature))
        item = {"status": record["status"], "reason": reason,
                "evidence_origin": "caller_supplied_not_independently_verified"}
        if record["status"] != "unknown":
            versions = record.get("versions")
            exact_versions = (isinstance(versions, dict)
                              and all(_same_condition(versions.get(key), identity[key])
                                      for key in ("engine", "plugin", "runtime", "hardware", "driver")))
            evidence_complete = (_official_url(record.get("source_url")) and _checked_time(record.get("checked_at"))
                                 and exact_versions)
            if identity["stereo"] == "stereo" and record["status"] == "supported":
                evidence_complete = (evidence_complete and record.get("stereo_compatible") is True
                                     and _official_url(record.get("stereo_source_url")))
            if not evidence_complete:
                item["status"] = "unknown"
                item["reason"] = ("Exact-version, hardware, and driver evidence must be complete, "
                                  "no more than seven days old, and not future-dated; " + reason)
        for key in ("source_url", "checked_at", "stereo_source_url"):
            if key in record:
                item[key] = _text(record[key], "dlss.{}.{}".format(feature, key))
        if "versions" in record:
            item["versions"] = _condition(record["versions"], "dlss.{}.versions".format(feature))
        result[feature] = item
    return result


def _run_summary(run, identity):
    metrics = run.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be an object")
    optimizations = run.get("optimizations", {})
    if not isinstance(optimizations, dict):
        raise ValueError("optimizations must be an object")
    normalized = _condition(optimizations, "optimizations") if optimizations else {}
    return {"identity": identity, "metrics": {key: _metric(metrics.get(key), key) for key in METRICS},
            "optimizations": normalized, "dlss": _dlss(run, identity)}


def analyze_performance(baseline, candidate):
    """Compare explicit, matching capture conditions; never infer render time from FG FPS.

    Required ``identity`` keys are listed in ``IDENTITY_FIELDS``. Each metric
    is ``{samples: [...], source: '...'} precise`` or ``{samples: null, reason:
    '...'} unavailable. Missing metrics are reported as unavailable. Optimization
    settings live outside identity and may differ. The caller must still review
    stereo quality, UI, latency, and comfort before accepting an optimization.
    """
    before_identity = _identity(baseline, "baseline")
    after_identity = _identity(candidate, "candidate")
    before = _run_summary(baseline, before_identity)
    after = _run_summary(candidate, after_identity)
    keys = sorted(set(before_identity) | set(after_identity))
    mismatches = [key for key in keys if not _same_condition(before_identity.get(key), after_identity.get(key))]
    result = {"status": "not_comparable" if mismatches else "comparable", "mismatched_conditions": mismatches,
              "baseline": before, "candidate": after, "comparison": {},
              "evidence_origin": "caller_supplied_measurements_not_independently_captured",
              "device_validation": "NOT_RUN",
              "limitations": ["Observed differences do not establish statistical significance or hardware acceptance.",
                              "display_fps includes presentation or generated frames; it is not render_fps or GPU frame time.",
                              "Review both eyes, UI readability, latency, tracking, and comfort separately."]}
    if mismatches:
        result["reason"] = "Capture conditions differ; no direct performance deltas were calculated"
        return result
    for metric in METRICS:
        left = before["metrics"][metric]
        right = after["metrics"][metric]
        if left["mean"] is None or right["mean"] is None:
            result["comparison"][metric] = {"status": "unavailable", "delta": None, "change_percent": None,
                                             "reason": "Both captures require measured {}".format(metric)}
            continue
        delta = right["mean"] - left["mean"]
        change = delta / left["mean"] * 100
        percent_reason = None
        if not math.isfinite(change):
            change = None
            percent_reason = "Percentage exceeds finite numeric range; inspect the raw measurements"
        interpretation = "presentation_cadence_only" if metric == "display_fps" else "observed_measurement_difference"
        result["comparison"][metric] = {"status": "measured", "delta": delta, "change_percent": change,
                                         "direction": "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged",
                                         "interpretation": interpretation, "reason": percent_reason}
    result["reason"] = "Identical declared conditions; compare recorded metrics independently"
    return result


def acceptance_report(evidence):
    """Normalize independent acceptance layers, preserving missing-device NOT_RUN.

    An actual capture must match the top-level skill_run_id. A device record
    must explicitly identify physical hardware in the acer_spatiallabs family, a device_id,
    model, and evidence. A PASS in a device layer additionally needs matching
    device_id, capture_kind=physical_device, and its own evidence. These are
    caller-supplied records, not device detection or independent verification.
    """
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object")
    device = evidence.get("device", {})
    layers = evidence.get("layers", {})
    if not isinstance(device, dict) or not isinstance(layers, dict):
        raise ValueError("device and layers must be objects")
    if "present" in device and not isinstance(device["present"], bool):
        raise ValueError("device.present must be a boolean")
    run_id = evidence.get("skill_run_id")
    if run_id is not None:
        _text(run_id, "skill_run_id")
    physical = (device.get("present") is True and device.get("kind") == "physical"
                and device.get("family") == "acer_spatiallabs"
                and all(isinstance(device.get(key), str) and device[key].strip()
                        for key in ("device_id", "model", "evidence")))
    result = {"status": "incomplete", "physical_device_evidence_supplied": physical, "layers": {},
              "evidence_origin": "caller_supplied_not_independently_verified"}
    for layer in LAYERS:
        record = layers.get(layer, {"status": "NOT_RUN", "reason": "No layer-specific evidence supplied"})
        if not isinstance(record, dict) or record.get("status") not in ("PASS", "FAIL", "NOT_RUN"):
            raise ValueError("layers.{} status must be PASS, FAIL, or NOT_RUN".format(layer))
        status = record["status"]
        artifact = record.get("evidence")
        has_artifact = isinstance(artifact, str) and bool(artifact.strip())
        reason = record.get("reason")
        if layer in DEVICE_LAYERS and not physical:
            item = {"status": "NOT_RUN", "reason": "No physical Acer SpatialLabs family device evidence; hardware effect is unverified"}
            if status != "NOT_RUN":
                item["requested_status"] = status
        elif layer in DEVICE_LAYERS and status == "PASS" and (
                record.get("capture_kind") != "physical_device" or record.get("device_id") != device.get("device_id")
                or not has_artifact or run_id is None or record.get("skill_run_id") != run_id):
            item = {"status": "NOT_RUN", "requested_status": status,
                    "reason": "PASS requires this skill run's physical device and layer-specific capture evidence"}
        else:
            if status in ("PASS", "FAIL") and not has_artifact:
                raise ValueError("layers.{} {} requires evidence".format(layer, status))
            if status == "NOT_RUN":
                _text(reason, "layers.{}.reason".format(layer))
            if layer in ("editor", "2d", "package") and status == "PASS" and (
                    record.get("capture_kind") != "actual_run" or run_id is None or record.get("skill_run_id") != run_id):
                item = {"status": "NOT_RUN", "requested_status": status,
                        "reason": "An actual new-skill run is required; synthetic or previous 2D evidence is insufficient"}
            else:
                item = {"status": status, "evidence": artifact, "reason": reason}
        result["layers"][layer] = item
    statuses = [record["status"] for record in result["layers"].values()]
    result["status"] = "failed" if "FAIL" in statuses else "passed" if all(value == "PASS" for value in statuses) else "incomplete"
    return result

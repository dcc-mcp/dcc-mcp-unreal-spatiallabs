"""Bounded software SBS integrity checks; metadata does not attest a live device."""

import io
import math
from pathlib import Path

from spatiallabs_run_evidence import MAX_PNG_BYTES, _png, _snapshot
from spatiallabs_runtime import _object


def _numbers(value, count):
    if (not isinstance(value, list) or len(value) != count
            or any(isinstance(item, bool) or not isinstance(item, (int, float))
                   or not math.isfinite(item) for item in value)):
        raise ValueError("Camera values must be finite numeric arrays")
    return value


def inspect_stereo_pair(pair_path):
    pair_file, raw, fingerprint = _snapshot(pair_path, 64 * 1024)
    pair = _object(raw)
    if pair.get("schema") != 1 or isinstance(pair.get("schema"), bool):
        raise ValueError("Unsupported stereo evidence schema")
    if pair.get("label") != "SBS_SIMULATION_NOT_ACER" or pair.get("sbs_order") != "left|right":
        raise ValueError("Expected explicitly labelled software left|right SBS evidence")
    width, height = pair.get("eye_width"), pair.get("eye_height")
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (width, height)):
        raise ValueError("Eye dimensions must be positive integers")
    eyes = [pair.get("left"), pair.get("right")]
    if not all(isinstance(eye, dict) for eye in eyes):
        raise ValueError("Both eye records are required")
    positions = [_numbers(eye.get("position_cm"), 3) for eye in eyes]
    rotations = [_numbers(eye.get("quaternion_xyzw"), 4) for eye in eyes]
    if any(not math.isclose(sum(v * v for v in q), 1, abs_tol=1e-5) for q in rotations):
        raise ValueError("Eye rotations must be unit quaternions")
    projections = [_numbers(eye.get("projection_reference_matrix"), 16) for eye in eyes]
    views = [_numbers(eye.get("view_matrix"), 16) for eye in eyes]
    baseline = math.sqrt(sum((right - left) ** 2 for left, right in zip(*positions)))
    ipd = pair.get("ipd_cm")
    if (isinstance(ipd, bool) or not isinstance(ipd, (int, float)) or not math.isfinite(ipd)
            or ipd <= 0 or not math.isclose(baseline, ipd, rel_tol=1e-5, abs_tol=1e-4)):
        raise ValueError("Distinct camera positions must agree with the declared eye distance")
    for values in (rotations, projections):
        if not all(math.isclose(left, right, rel_tol=1e-7, abs_tol=1e-7) for left, right in zip(*values)):
            raise ValueError("This checker supports parallel, matching eye projections only")
    if views[0] == views[1]:
        raise ValueError("Eye view matrices must be distinct")

    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("Stereo pixel inspection requires Pillow; no dependency was installed") from exc

    images, provenance = [], []
    for index, name in enumerate(("left.png", "right.png", "SBS_SIMULATION_NOT_ACER.png")):
        eye = eyes[index] if index < 2 else None
        if eye is not None and eye.get("filename") != name:
            raise ValueError("Eye filenames must be exact local left.png and right.png names")
        path, content, record = _snapshot(pair_file.parent / name, MAX_PNG_BYTES)
        expected = eye.get("png_sha256") if eye is not None else pair.get("sbs_sha256")
        if record["sha256"] != expected:
            raise ValueError("Stereo image hash does not match the pair record")
        info = _png(content)
        size = (width * (2 if index == 2 else 1), height)
        if (info["width"], info["height"]) != size:
            raise ValueError("Stereo image dimensions do not match the pair record")
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            pixels = image.convert("RGBA")
        if pixels.getextrema()[3] != (255, 255):
            raise ValueError("Stereo pixels must be opaque")
        images.append(pixels)
        provenance.append(record)
    left, right, sbs = images
    if left.tobytes() == right.tobytes():
        raise ValueError("Duplicate eye pixels do not establish binocular content")
    if (sbs.crop((0, 0, width, height)).tobytes() != left.tobytes()
            or sbs.crop((width, 0, width * 2, height)).tobytes() != right.tobytes()):
        raise ValueError("SBS pixels are not exact rowwise left|right images")
    for record in [fingerprint] + provenance:
        if _snapshot(Path(record["path"]), MAX_PNG_BYTES)[2]["sha256"] != record["sha256"]:
            raise ValueError("Stereo evidence changed during inspection")
    return {
        "status": "integrity_pass_visual_review_required",
        "pair": fingerprint, "images": provenance,
        "eye_resolution": [width, height], "sbs_resolution": [width * 2, height],
        "reported_camera_baseline_cm": baseline,
        "rowwise_left_right_exact": True, "distinct_eye_pixels": True,
        "scene_acceptance": "NOT_RUN", "disparity_acceptance": "NOT_RUN",
        "hardware_verified": False, "host_actions_executed": False,
        "installation_authorized": False,
        "limitations": [
            "Pair metadata is supplied evidence, not independent frame/process ownership attestation",
            "Distinct pixels and camera metadata still require visible scene and horizontal-disparity review",
            "A software screenshot pair is not an interactive packaged game or SpatialLabs device acceptance",
        ],
    }

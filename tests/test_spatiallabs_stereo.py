"""Synthetic format checks do not claim a real scene or device result."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).parents[1] / "skills/unreal-spatiallabs/scripts"


def load(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("stereo_entry", SCRIPTS / "inspect_stereo_pair.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.inspect_stereo_pair


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def pair(tmp_path):
    left = Image.new("RGB", (8, 4), "red")
    right = Image.new("RGB", (8, 4), "blue")
    sbs = Image.new("RGB", (16, 4))
    sbs.paste(left, (0, 0))
    sbs.paste(right, (8, 0))
    matrix = [float(i % 5 == 0) for i in range(16)]
    view = list(matrix)
    view[12] = 6.4
    data = {"schema": 1, "label": "SBS_SIMULATION_NOT_ACER", "sbs_order": "left|right",
            "eye_width": 8, "eye_height": 4, "ipd_cm": 6.4}
    for name, image, position, eye_view in (
        ("left", left, [-3.2, 0, 0], matrix), ("right", right, [3.2, 0, 0], view)
    ):
        filename = name + ".png"
        image.save(tmp_path / filename)
        data[name] = {"filename": filename, "png_sha256": digest(tmp_path / filename),
                      "position_cm": position, "quaternion_xyzw": [0, 0, 0, 1],
                      "projection_reference_matrix": matrix, "view_matrix": eye_view}
    sbs.save(tmp_path / "SBS_SIMULATION_NOT_ACER.png")
    data["sbs_sha256"] = digest(tmp_path / "SBS_SIMULATION_NOT_ACER.png")
    path = tmp_path / "pair.json"
    path.write_text(json.dumps(data))
    return path, data


def test_valid_pair_is_read_only_and_does_not_pass_scene_or_device(pair, monkeypatch):
    path, _ = pair
    before = {p.name: digest(p) for p in path.parent.iterdir()}
    result = load(monkeypatch)(pair_path=str(path))
    assert result["success"] is True
    context = result["context"]
    assert context["rowwise_left_right_exact"] is True
    assert context["reported_camera_baseline_cm"] == pytest.approx(6.4)
    assert context["scene_acceptance"] == context["disparity_acceptance"] == "NOT_RUN"
    assert context["hardware_verified"] is context["installation_authorized"] is False
    assert {p.name: digest(p) for p in path.parent.iterdir()} == before


@pytest.mark.parametrize("change", ["hash", "swap", "duplicate", "baseline", "path", "quaternion", "nan"])
def test_invalid_pair_is_refused_even_with_changed_image_hashes(pair, monkeypatch, change):
    path, data = pair
    if change == "hash":
        data["left"]["png_sha256"] = "0" * 64
    elif change == "swap":
        sbs = Image.new("RGB", (16, 4))
        with Image.open(path.parent / "right.png") as right, Image.open(path.parent / "left.png") as left:
            sbs.paste(right, (0, 0))
            sbs.paste(left, (8, 0))
        sbs.save(path.parent / "SBS_SIMULATION_NOT_ACER.png")
        data["sbs_sha256"] = digest(path.parent / "SBS_SIMULATION_NOT_ACER.png")
    elif change == "duplicate":
        with Image.open(path.parent / "left.png") as left:
            left.save(path.parent / "right.png", compress_level=0)
        data["right"]["png_sha256"] = digest(path.parent / "right.png")
        assert data["right"]["png_sha256"] != data["left"]["png_sha256"]
    elif change == "baseline":
        data["ipd_cm"] = 64
    elif change == "path":
        data["left"]["filename"] = "../outside.png"
    elif change == "quaternion":
        data["left"]["quaternion_xyzw"] = [0, 0, 0, 0]
    else:
        data["left"]["position_cm"][0] = float("nan")
    path.write_text(json.dumps(data))
    result = load(monkeypatch)(pair_path=str(path))
    assert result["success"] is False
    assert isinstance(result["error"], str)

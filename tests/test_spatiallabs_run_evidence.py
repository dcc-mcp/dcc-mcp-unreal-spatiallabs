"""Native-log/PNG counterexamples derived from the real cold/warm failure.

All fixtures are tiny synthetic data. No game assets, user logs, UE process or
vendor binary is needed or committed.
"""

import hashlib
import importlib.util
import json
import struct
import zlib
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "skills/unreal-spatiallabs/scripts"
STAMP = "[2026.11.11-14.02.10:144][905]"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("run_evidence_under_test", SCRIPTS / "spatiallabs_run_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def png(width=2, height=2, pixels=None):
    # A solid color/sky-like image is fully valid and must never auto-pass a scene.
    pixels = b"\0\x80\xa0\xff\x80\xa0\xff" * height if pixels is None else pixels
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def native_log(capture, extra=""):
    return (
        "LogInit: Engine Version: 5.8.0-55116800+++UE5+Release-5.8\n"
        "LogInit: Compatible Engine Version: 5.7.0-123+++UE5\n"
        + STAMP + "LogRHI: RHI D3D12 with Feature Level SM6 is supported and will be used.\n"
        + STAMP + "LogLoad: LoadMap: /Game/Maps/RealMap?Name=Player\n"
        + STAMP + "LogWorld: Bringing World /Game/Maps/RealMap.RealMap up for play (max tick rate 0)\n"
        + STAMP + 'LogCore: Display: Tracing Screenshot "' + capture.stem + '" taken with size: 2 x 2\n'
        + STAMP + "LogClient: High resolution screenshot saved as " + str(capture) + "\n" + extra
    )


@pytest.fixture
def evidence(tmp_path):
    capture = tmp_path / "frame.png"
    capture.write_bytes(png())
    log = tmp_path / "run.log"
    log.write_text(native_log(capture), encoding="utf-8")
    return log, capture


def test_warm_native_frame_requires_semantic_review_and_never_passes(api, evidence):
    log, capture = evidence
    before = (log.read_bytes(), capture.read_bytes())
    result = api.inspect_run_evidence(str(log), str(capture), "warm")
    assert result["runtime_identity"] == {"status": "observed", "version": "5.8.0", "changelist": 55116800}
    assert result["world"]["status"] == "play_started"
    assert result["world"]["map_paths"] == ["/Game/Maps/RealMap"]
    assert result["world"]["project_binding"] == "NOT_VERIFIED"
    assert result["capture"]["status"] == "BOUND_TO_NATIVE_LOG"
    assert result["capture"]["sha256"] == hashlib.sha256(capture.read_bytes()).hexdigest()
    assert result["capture"]["native_frame"] == 905
    assert result["scene"]["status"] == "REVIEW_REQUIRED"
    assert result["scene"]["visual_review_required"] is True
    assert result["acceptance"]["scene"] == "NOT_RUN"
    assert result["cache_state_provenance"] == "caller_supplied_unverified"
    assert (log.read_bytes(), capture.read_bytes()) == before


def test_cold_stream_timeout_survives_exit_zero_and_later_warm_review(api, evidence, tmp_path):
    log, capture = evidence
    cold = tmp_path / "cold.log"
    cold.write_text(native_log(capture, STAMP + "LogBlueprintUserMessages: [BP_Room_C_3] "
                               "GAME STREAM ERROR: loading timed out; passage stays blocked\n"
                               + STAMP + "LogWindows: FPlatformMisc::RequestExitWithStatus(0, 0, FEngineLoop::Tick.Benchmarking)\n"))
    result = api.inspect_run_evidence(str(cold), str(capture), "cold")
    assert result["scene"]["status"] == "FAIL"
    assert "SCENE_LOADING_TIMEOUT" in result["scene"]["reason_codes"]
    assert api.inspect_run_evidence(str(log), str(capture), "warm")["scene"]["status"] == "REVIEW_REQUIRED"
    assert result["scene"]["status"] == "FAIL"  # independent results cannot erase the cold failure


def test_tdr_summary_is_not_a_loading_timeout(api, evidence):
    log, capture = evidence
    log.write_text(native_log(capture, STAMP + "LogRHI: Display: Timeout Detection and Recovery (TDR) summary:\n"))
    assert api.inspect_run_evidence(str(log), str(capture))["scene"]["status"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("change", ["orphan", "echo", "wrong_size", "wrong_stem", "duplicate"])
def test_native_capture_binding_cannot_come_from_echo_or_another_frame(api, evidence, change):
    log, capture = evidence
    text = native_log(capture)
    if change == "orphan":
        text = text.split("LogClient: High resolution screenshot saved as")[0]
    elif change == "echo":
        text = STAMP + 'LogCsvProfiler: Display: commandline="' + text.replace("\n", " ") + '"\n'
    elif change == "wrong_size":
        text = text.replace("size: 2 x 2", "size: 1280 x 720")
    elif change == "wrong_stem":
        text = text.replace('Screenshot "frame"', 'Screenshot "other"')
    else:
        text += STAMP + "LogClient: High resolution screenshot saved as " + str(capture) + "\n"
    log.write_text(text)
    result = api.inspect_run_evidence(str(log), str(capture))
    assert result["capture"]["status"] == "UNBOUND"
    assert result["scene"]["status"] == "NOT_RUN"


@pytest.mark.parametrize("contents", [b"not-png", png()[:-3], png()[:-12], png()[:40] + b"badcrc" + png()[46:],
                                      png(pixels=b"\0" * 100000), png(pixels=b"\x07" + b"\0" * 13)])
def test_corrupt_or_oversized_decoded_payload_is_not_a_capture(api, evidence, contents):
    log, capture = evidence
    capture.write_bytes(contents)
    result = api.inspect_run_evidence(str(log), str(capture))
    assert result["capture"]["status"] == "INVALID"
    assert result["scene"]["status"] == "FAIL"
    assert result["acceptance"]["scene"] == "NOT_RUN"


def test_duplicate_conflicting_runtime_identity_is_ambiguous(api, evidence):
    log, capture = evidence
    log.write_text(native_log(capture, "LogInit: Engine Version: 5.8.1-56057345+++UE5+Release-5.8\n"))
    result = api.inspect_run_evidence(str(log), str(capture))
    assert result["runtime_identity"] == {"status": "ambiguous", "distinct_identities": 2}


def test_missing_capture_world_rhi_and_null_rhi_do_not_pass(api, tmp_path):
    log = tmp_path / "run.log"
    log.write_text("LogRHI: Initializing NullRHI\n")
    result = api.inspect_run_evidence(str(log))
    assert result["rhi"]["status"] == "null"
    assert result["runtime_identity"]["status"] == "missing"
    assert result["scene"]["status"] == "NOT_RUN"
    assert result["capture"]["status"] == "NOT_RUN"


def test_stock_plugin_mount_and_disabled_interpreter_are_distinct(api, evidence):
    log, capture = evidence
    log.write_text(native_log(capture,
                             "LogPluginManager: Mounting Engine plugin PythonScriptPlugin\n"
                             "LogPluginManager: Mounting Engine plugin ModelingToolsEditorMode\n"
                             + STAMP + "LogPython: Python disabled via command-line flag '-DisablePython'\n"))
    result = api.inspect_run_evidence(str(log), str(capture))
    assert result["bootstrap"]["python_plugin_mounted"] is True
    assert result["bootstrap"]["modeling_plugin_mounted"] is True
    assert result["bootstrap"]["python_interpreter_status"] == "disabled"
    assert result["scene"]["status"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("record", ["LogPython: Using Python 3.11.8\n",
                                    "LogPluginManager: Mounting Engine plugin MCPClientToolset\n"])
def test_control_or_interpreter_bootstrap_remains_a_failure(api, evidence, record):
    log, capture = evidence
    log.write_text(native_log(capture, record))
    result = api.inspect_run_evidence(str(log), str(capture))
    assert result["scene"]["status"] == "FAIL"
    assert "CONTROL_BOOTSTRAP_OBSERVED" in result["scene"]["reason_codes"]


def test_secret_payloads_are_never_reemitted(api, evidence):
    log, capture = evidence
    log.write_text(native_log(capture, STAMP + "LogClass: Error: SecretToken=SHOULD_NOT_ESCAPE\n"
                             + STAMP + 'LogCsvProfiler: Display: commandline="password=ALSO_PRIVATE"\n'))
    output = json.dumps(api.inspect_run_evidence(str(log), str(capture)))
    assert "SHOULD_NOT_ESCAPE" not in output
    assert "ALSO_PRIVATE" not in output
    assert "ENGINE_LOG_ERROR" in output


@pytest.mark.parametrize("cache_state", ["Cold", True, [], ""])
def test_cache_labels_are_closed_and_not_inferred(api, evidence, cache_state):
    with pytest.raises(ValueError, match="cache_state"):
        api.inspect_run_evidence(str(evidence[0]), str(evidence[1]), cache_state)


def test_evidence_limits_and_paths_fail_closed(api, evidence, monkeypatch):
    log, capture = evidence
    with pytest.raises(ValueError, match="absolute"):
        api.inspect_run_evidence("relative.log")
    monkeypatch.setattr(api, "MAX_LOG_BYTES", 1)
    with pytest.raises(ValueError, match="bounded"):
        api.inspect_run_evidence(str(log), str(capture))


@pytest.mark.parametrize("separator", ["\r", "\u2028", "\x85"])
def test_non_lf_records_cannot_bypass_actual_line_budget(api, tmp_path, monkeypatch, separator):
    log = tmp_path / "many-records.log"
    log.write_bytes(separator.join([
        "LogInit: Engine Version: 5.8.0-55116800+++UE5+Release-5.8",
        "LogPluginManager: Mounting Engine plugin PythonScriptPlugin",
        "LogPython: Python disabled via command-line flag '-DisablePython'",
    ]).encode("utf-8"))
    monkeypatch.setattr(api, "MAX_LINES", 2)
    with pytest.raises(ValueError, match="line limit"):
        api.inspect_run_evidence(str(log))


def test_link_is_not_read(api, evidence, tmp_path):
    alias = tmp_path / "alias.log"
    try:
        alias.symlink_to(evidence[0])
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError, match="Symlink/reparse"):
        api.inspect_run_evidence(str(alias), str(evidence[1]))

"""Bounded, read-only native UE run evidence; never infer visible scene success.

Logs are untrusted observations, not instructions or process ownership receipts.
Only native category records are parsed. No host, shell, image model or decoder
dependency is started, and no cache or project is changed.
"""

import hashlib
import os
import re
import stat
import struct
import zlib
from pathlib import Path

from spatiallabs_project import _no_links

MAX_LOG_BYTES = 16 * 1024 * 1024
MAX_PNG_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 8 * 1024 * 1024
MAX_LINES = 100000
MAX_LINE = 32768
_RECORD = re.compile(
    r"^(?:\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3}\]"
    r"\[\s*(?P<frame>\d+)\])?(?P<category>Log[A-Za-z0-9_]+): (?P<message>.*)$"
)
_VERSION = re.compile(r"^Engine Version: (\d+\.\d+\.\d+)-(\d+)(?:[+\w.\-]*)$")
_RHI = re.compile(r"^(?:Display: )?RHI (\w+) with Feature Level (\w+) is supported and will be used\.$")
_TRACE = re.compile(r'^Display: Tracing Screenshot "([^"\r\n]+)" taken with size: (\d+) x (\d+)$')
_MOUNT = re.compile(r"^Mounting (?:Engine|Project) plugin ([A-Za-z][A-Za-z0-9_]*)$")
_CONTROL = frozenset(("MCPClientToolset", "ModelContextProtocol", "AllToolsets", "EditorToolset", "Terminal"))


def _snapshot(value, limit):
    path = _no_links(Path(value))
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError("Evidence must be a bounded regular file")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
        opened = os.fstat(stream.fileno())
    after = path.stat()
    def identity(item):
        return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns

    if len(data) > limit or identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("Evidence changed during inspection; retain the same operation and inspect after it settles")
    _no_links(path)
    return path, data, {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _png(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG_SIGNATURE")
    offset, count, header, ended = 8, 0, None, False
    compressed = bytearray()
    idat_ended = False
    while offset < len(data):
        count += 1
        if count > 10000 or offset + 12 > len(data):
            raise ValueError("PNG_CHUNK_BOUNDS")
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data) or not re.fullmatch(b"[A-Za-z]{4}", kind):
            raise ValueError("PNG_CHUNK_BOUNDS")
        payload = memoryview(data)[offset + 8:end - 4]
        crc = zlib.crc32(payload, zlib.crc32(kind)) & 0xFFFFFFFF
        if crc != struct.unpack_from(">I", data, end - 4)[0]:
            raise ValueError("PNG_CRC")
        if count == 1 and kind != b"IHDR":
            raise ValueError("PNG_HEADER")
        if kind == b"IHDR":
            if header is not None or length != 13:
                raise ValueError("PNG_HEADER")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if not (0 < width <= 8192 and 0 < height <= 8192 and width * height <= MAX_PIXELS):
                raise ValueError("PNG_DIMENSIONS")
            if (depth != 8 or color not in (2, 6) or compression or filtering or interlace):
                raise ValueError("PNG_UNSUPPORTED_FORMAT")
            header = (width, height, 3 if color == 2 else 4)
        elif kind == b"IDAT":
            if idat_ended:
                raise ValueError("PNG_IDAT_ORDER")
            compressed.extend(payload)
        elif kind == b"IEND":
            if length or end != len(data) or not compressed:
                raise ValueError("PNG_END")
            ended = True
        else:
            if compressed:
                idat_ended = True
            if kind[0] & 32 == 0 and kind != b"PLTE":
                raise ValueError("PNG_UNSUPPORTED_CHUNK")
        offset = end
    if not ended or header is None:
        raise ValueError("PNG_TRUNCATED")
    width, height, channels = header
    stride = width * channels + 1
    expected = stride * height
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error:
        raise ValueError("PNG_DEFLATE")
    if (len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
            or any(value > 4 for value in pixels[::stride])):
        raise ValueError("PNG_DECODE_BOUNDS")
    return {"width": width, "height": height, "format": "RGB8" if channels == 3 else "RGBA8",
            "container_and_scanlines_valid": True, "semantic_scene_validation": "NOT_RUN"}


def _path_key(value):
    # Normalize spelling only. Never follow a path discovered inside an untrusted log.
    return os.path.normcase(os.path.normpath(value))


def _map(value):
    return value.split("?", 1)[0].rsplit(".", 1)[0] if "." in value.rsplit("/", 1)[-1] else value.split("?", 1)[0]


def _records(text):
    if text.count("\n") > MAX_LINES:
        raise ValueError("Evidence log exceeds line limit")
    for line, raw in enumerate(text.splitlines(), 1):
        if line > MAX_LINES:
            raise ValueError("Evidence log exceeds line limit")
        if len(raw) > MAX_LINE:
            raise ValueError("Evidence log exceeds line-length limit")
        match = _RECORD.fullmatch(raw)
        if match:
            yield line, match["category"], match["message"], int(match["frame"]) if match["frame"] else None


def inspect_run_evidence(log_path, capture_path=None, cache_state="unknown"):
    """Inspect retained files, without certifying ownership, provenance or semantics.

    A valid native screenshot is only ready for visual review. Warm evidence never
    erases a different cold run's failure. Caller cache labels are unverified.
    """
    if cache_state not in ("cold", "warm", "unknown"):
        raise ValueError("cache_state must be cold, warm or unknown")
    _, data, log = _snapshot(log_path, MAX_LOG_BYTES)
    versions, loaded, playing, backends, mounts, controls = set(), set(), set(), set(), set(), set()
    traces, saves, issues = [], [], []
    python_disabled, python_initialized = False, False
    null_rhi = False
    for line, category, message, frame in _records(data.decode("utf-8-sig", errors="replace")):
        if category == "LogInit":
            match = _VERSION.fullmatch(message)
            if match:
                versions.add((match[1], int(match[2])))
        if category == "LogLoad" and message.startswith("LoadMap: /Game/"):
            loaded.add(_map(message[len("LoadMap: "):].split(" ", 1)[0]))
        if category == "LogWorld":
            match = re.match(r"^Bringing World (/Game/\S+) up for play(?: |$)", message)
            if match:
                playing.add(_map(match[1]))
        if category == "LogRHI":
            match = _RHI.fullmatch(message)
            if match:
                backends.add((match[1], match[2]))
            if re.search(r"\bNullRHI\b|\bNull RHI\b", message, re.IGNORECASE):
                null_rhi = True
        if category == "LogNullDrv":
            null_rhi = True
        if category == "LogPluginManager":
            match = _MOUNT.fullmatch(message)
            if match:
                mounts.add(match[1])
                if match[1] in _CONTROL:
                    controls.add(match[1])
        if category == "LogPython":
            if message == "Python disabled via command-line flag '-DisablePython'":
                python_disabled = True
            if re.search(r"\b(?:initializ(?:ed|ing)|Python [23]\.\d+|startup script)\b", message, re.IGNORECASE):
                python_initialized = True
        if category == "LogCore":
            match = _TRACE.fullmatch(message)
            if match and frame is not None:
                traces.append({"stem": match[1], "width": int(match[2]), "height": int(match[3]),
                               "frame": frame, "line": line})
        if category == "LogClient" and message.startswith("High resolution screenshot saved as "):
            saved_path = message[len("High resolution screenshot saved as "):].strip()
            if saved_path.startswith('"') and saved_path.endswith('"'):
                saved_path = saved_path[1:-1]
            saves.append((saved_path, line))
        # Match readiness errors in native message payloads, never the command-line echo.
        if category in ("LogBlueprintUserMessages", "LogStreaming", "LogLevelStreaming"):
            if re.search(r"(?:stream|loading|room|level).*\b(?:timed out|timeout)\b", message, re.IGNORECASE):
                issues.append({"code": "SCENE_LOADING_TIMEOUT", "line": line})
        if re.search(r"^(?:Error: |Fatal: )|^.*: (?:Error|Fatal): ", message) or message.startswith("Fatal error:"):
            issues.append({"code": "ENGINE_LOG_ERROR", "line": line})
    runtime = {"status": "missing"}
    if len(versions) == 1:
        version, changelist = next(iter(versions))
        runtime = {"status": "observed", "version": version, "changelist": changelist}
    elif versions:
        runtime = {"status": "ambiguous", "distinct_identities": len(versions)}
    rhi_status = "null" if null_rhi else "missing"
    if not null_rhi and backends:
        rhi_status = "usable" if len(backends) == 1 and next(iter(backends))[0] in (
            "D3D12", "D3D11", "Vulkan", "Metal", "OpenGL"
        ) else "ambiguous"
    capture = {"status": "NOT_RUN"}
    reason_codes = []
    if capture_path is not None:
        path, raw_png, provenance = _snapshot(capture_path, MAX_PNG_BYTES)
        capture = dict(provenance)
        try:
            capture.update(_png(raw_png))
        except ValueError as exc:
            capture.update(status="INVALID", error_code=str(exc))
            reason_codes.append("CAPTURE_INVALID")
        else:
            matching_saves = [line for name, line in saves if _path_key(name) == _path_key(str(path))]
            matching_traces = [item for item in traces
                               if item["stem"] == path.stem and item["width"] == capture["width"]
                               and item["height"] == capture["height"]
                               and any(0 < saved_line - item["line"] <= 10 for saved_line in matching_saves)]
            if len(matching_saves) == 1 and len(matching_traces) == 1:
                trace = matching_traces[0]
                capture.update(status="BOUND_TO_NATIVE_LOG", native_frame=trace["frame"],
                               trace_line=trace["line"], saved_line=matching_saves[0])
            else:
                capture.update(status="UNBOUND", reason="Exact native saved-path and unique matching trace required")
                reason_codes.append("CAPTURE_NATIVE_BINDING_MISSING_OR_AMBIGUOUS")
    else:
        reason_codes.append("CAPTURE_NOT_SUPPLIED")
    world_status = "play_started" if loaded & playing else "load_only" if loaded else "missing"
    if world_status != "play_started":
        reason_codes.append("WORLD_PLAY_NOT_OBSERVED")
    if rhi_status != "usable":
        reason_codes.append("USABLE_RHI_NOT_OBSERVED")
    if any(issue["code"] == "SCENE_LOADING_TIMEOUT" for issue in issues):
        reason_codes.append("SCENE_LOADING_TIMEOUT")
    if controls or python_initialized:
        reason_codes.append("CONTROL_BOOTSTRAP_OBSERVED")
    scene_status = "REVIEW_REQUIRED" if not reason_codes else "NOT_RUN"
    if any(code in reason_codes for code in ("SCENE_LOADING_TIMEOUT", "CAPTURE_INVALID", "CONTROL_BOOTSTRAP_OBSERVED")):
        scene_status = "FAIL"
    return {
        "log": log, "cache_state": cache_state, "cache_state_provenance": "caller_supplied_unverified",
        "runtime_identity": runtime,
        "world": {"status": world_status, "map_paths": sorted(loaded & playing),
                  "project_binding": "NOT_VERIFIED"},
        "rhi": {"status": rhi_status, "backends": [{"name": name, "feature_level": feature}
                                                    for name, feature in sorted(backends)]},
        "bootstrap": {"python_plugin_mounted": "PythonScriptPlugin" in mounts,
                      "modeling_plugin_mounted": "ModelingToolsEditorMode" in mounts,
                      "python_interpreter_status": "initialization_observed" if python_initialized else
                      "disabled" if python_disabled else "unknown", "control_plugin_mounts": sorted(controls),
                      "scope": "Bounded retained-log observation, not proof of every side effect"},
        "issues": issues, "capture": capture,
        "scene": {"status": scene_status, "visual_review_required": True, "reason_codes": reason_codes,
                  "note": "Native frame counts and valid PNGs do not prove room readiness; sky/black/loading frames require review"},
        "acceptance": {"scene": "NOT_RUN", "ownership_cleanup": "NOT_RUN", "interaction": "NOT_RUN",
                       "sbs": "NOT_RUN", "acer_output": "NOT_RUN", "hardware": "NOT_RUN"},
        "cross_run_limit": "This run cannot erase or establish another cold/warm run's result",
    }

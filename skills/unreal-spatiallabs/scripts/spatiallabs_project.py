"""Project-only SpatialLabs inspection and recoverable installation primitives.

No vendor code is imported or executed. Mutations require an in-process authority
capability; it is deliberately absent from MCP/JSON schemas. The operator console
is the only authority provider shipped with this experimental skill.
"""

import contextlib
import datetime
import hashlib
import json
import os
import re
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

LICENSE_URL = "https://spatiallabs.acer.com/developer/docs/3e97ce90-22b4-11ed-91b8-067bb43818a8/c2b1e1dc-806b-4361-b903-8697f0ea8686"
OFFICIAL_HOSTS = frozenset(("spatiallabs.acer.com", "global-download.acer.com", "static.acer.com"))
# Published by Acer's developer portal download metadata, checked 2026-11-11.
# This shared CDN is allowed only for the observed Unreal plugin namespace.
ACER_PLUGIN_CDN = "d20hwfev93w9j9.cloudfront.net"
ACER_PLUGIN_CDN_PATH = "/upload/file/startvr/"
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024
MAX_ENTRIES = 5000
STATE_DIR = ".spatiallabs-transactions"
BUNDLE_MAX_DEPTH = 4
BUNDLE_MAX_ENTRIES = 10000
BUNDLE_SKIP = frozenset((".git", ".venv", "node_modules", "saved", "intermediate", "binaries",
                         "deriveddatacache", "content", "plugins", STATE_DIR))


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _no_links(path):
    """Check original spelling before resolve(), including Windows junctions."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("An absolute path without parent traversal is required")
    for part in (path,) + tuple(path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Symlink/reparse paths are not allowed: {}".format(part))
    return path


def _inside(root, path):
    path = _no_links(path)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError("Path leaves the project")
    return path


def _project(project_path):
    path = _no_links(Path(project_path))
    if path.is_dir():
        projects = list(path.glob("*.uproject"))
        if len(projects) != 1:
            raise ValueError("Project directory must contain exactly one editable .uproject")
        path = _no_links(projects[0])
    if path.suffix.lower() != ".uproject" or not path.is_file():
        raise ValueError("An existing editable .uproject is required; packaged games are not supported")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Invalid .uproject object")
    return path.parent, path, data


def _inspection_project(project_path):
    """Resolve a delivery folder for observation only, never for mutation plans."""
    supplied = _no_links(Path(project_path))
    if not supplied.is_dir():
        root, path, data = _project(supplied)
        return root, path, data, {"input_path": str(supplied), "mode": "explicit_project"}

    pending = [(supplied, 0)]
    candidates = []
    entries_seen = 0
    packaged = False
    depth_limited = False
    while pending:
        folder, depth = pending.pop()
        children, projects = [], []
        # Count inside the iterator; a very large directory cannot first create
        # an unbounded list. Every path is checked before directory descent.
        with os.scandir(str(_inside(supplied, folder))) as entries:
            for entry in entries:
                entries_seen += 1
                if entries_seen > BUNDLE_MAX_ENTRIES:
                    raise ValueError("Delivery folder exceeds bounded entry limit; supply the exact .uproject path")
                if entry.name.casefold() in BUNDLE_SKIP:
                    continue  # Do not inspect generated links or enter asset/vendor trees.
                child = _inside(supplied, Path(entry.path))
                info = child.lstat()
                if stat.S_ISDIR(info.st_mode):
                    children.append(child)
                elif stat.S_ISREG(info.st_mode):
                    if child.suffix.casefold() == ".uproject":
                        projects.append(child)
                    elif child.suffix.casefold() in (".exe", ".pak", ".utoc", ".ucas"):
                        packaged = True
                else:
                    raise ValueError("Special files are not allowed in delivery inspection")
        if projects:
            candidates.extend(projects)
            # A selected project is inspected separately with full lineage.
            # Its content/vendor folders are not separate delivery projects.
            continue
        if depth < BUNDLE_MAX_DEPTH:
            pending.extend((child, depth + 1) for child in sorted(children, reverse=True))
        elif children:
            depth_limited = True

    if len(candidates) > 1:
        raise ValueError("Multiple editable .uproject candidates in delivery folder; supply the exact .uproject path")
    if not candidates:
        detail = (" Packaged-game markers are not editable source; obtain the original .uproject, Config and uncooked Content."
                  if packaged else " No supported engine or editable Unreal project has been established.")
        raise ValueError("No editable .uproject found within bounded delivery scan." + detail
                         + " Supply the exact .uproject path if it is outside the scan scope.")
    root, path, data = _project(candidates[0])
    return root, path, data, {
        "input_path": str(supplied),
        "mode": "project_directory" if root == supplied else "delivery_discovery",
        "candidate_count_in_scan": 1,
        "max_depth": BUNDLE_MAX_DEPTH, "max_entries": BUNDLE_MAX_ENTRIES,
        "entries_seen": entries_seen, "depth_limited": depth_limited,
        "scope": "Bounded scan; generated, asset and plugin folders and discovered project subtrees are pruned",
        "mutation_scope": "Review the resolved project_path; installation planning still requires an explicit project",
    }


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", value):
        raise ValueError("Version must be a numeric major.minor[.patch] string")
    return tuple(int(x) for x in value.split("."))


def _official_url(url):
    if not isinstance(url, str):
        raise ValueError("Official HTTPS URL required")
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != "https" or parts.username is not None or parts.password is not None
            or parts.port not in (None, 443) or parts.fragment):
        raise ValueError("Only allowlisted official Acer HTTPS sources are allowed")
    if parts.hostname in OFFICIAL_HOSTS:
        return url
    if parts.hostname == ACER_PLUGIN_CDN and not parts.query and parts.path.startswith(ACER_PLUGIN_CDN_PATH):
        decoded = urllib.parse.unquote(parts.path, errors="strict")
        filename = decoded[len(ACER_PLUGIN_CDN_PATH):]
        if (decoded.startswith(ACER_PLUGIN_CDN_PATH)
                and re.fullmatch(r"Acer SpatialLabs Unreal [0-9]+\.[0-9]+(?:\.[0-9]+)? Plugin_[0-9]+\.[0-9]+(?:\.[0-9]+)?\.zip", filename)):
            return url
    raise ValueError("Only allowlisted official Acer HTTPS sources and the reviewed Unreal plugin CDN path are allowed")


def _walk(root, exclude_generated=False):
    """Prune before descent, validate every directory before os.walk enters it."""
    _no_links(root)
    count = 0
    excluded = {".git", "Saved", "Intermediate", "Binaries", "DerivedDataCache", STATE_DIR}

    def fail(error):
        raise error

    for current, directories, filenames in os.walk(str(root), topdown=True, followlinks=False, onerror=fail):
        current = _inside(root, Path(current))
        retained = []
        for name in sorted(directories):
            path = current / name
            relative = path.relative_to(root).as_posix()
            if exclude_generated and (relative in excluded or relative == "Plugins/SpatialLabs"):
                continue
            _inside(root, path)
            count += 1
            if count > 100000:
                raise ValueError("Project inspection exceeds bounded entry limit")
            retained.append(name)
            yield path, True
        directories[:] = retained
        for name in sorted(filenames):
            path = current / name
            relative = path.relative_to(root).as_posix()
            if exclude_generated and (relative in excluded or relative == ".spatiallabs-install.lock"):
                continue
            _inside(root, path)
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError("Special files cannot be included in project lineage/inventory")
            count += 1
            if count > 100000:
                raise ValueError("Project inspection exceeds bounded entry limit")
            yield path, False


def _lineage(root):
    files = []
    total = 0
    # Deliberately excludes generated data and the installation target itself.
    for path, directory in _walk(root, exclude_generated=True):
        relative = path.relative_to(root)
        if not directory:
            total += path.stat().st_size
            if len(files) >= 100000 or total > 8 * 1024 ** 3:
                raise ValueError("Project lineage exceeds bounded inspection limits")
            files.append((relative.as_posix(), _file_hash(path)))
    files.sort()
    return _hash(_json_bytes(files)), files


def _support(evidence, engine_version, plugin_version):
    if evidence is None:
        return {"status": "unknown", "reason": "Current official engine/plugin/runtime/device matrix has not been reviewed"}
    if not isinstance(evidence, dict):
        raise ValueError("support_evidence must be an object")
    result = dict(evidence)
    if result.get("status") not in ("supported", "unsupported", "unknown"):
        raise ValueError("Invalid official support status")
    _official_url(result.get("source_url"))
    checked = result.get("checked_at", "")
    if not isinstance(checked, str):
        raise ValueError("Official support checked_at must be a timezone-aware string")
    try:
        timestamp = datetime.datetime.fromisoformat(checked.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("Official support evidence needs a timezone-aware checked_at")
    now = datetime.datetime.now(datetime.timezone.utc)
    if timestamp.tzinfo is None or timestamp > now or (now - timestamp).total_seconds() > 7 * 86400:
        raise ValueError("Official support evidence must be current (within seven days), never future-dated")
    if result.get("engine_version") != engine_version or result.get("plugin_version") != plugin_version:
        raise ValueError("Official support version mismatch")
    for key in ("runtime_version", "device_model"):
        if not isinstance(result.get(key), str) or not result[key].strip():
            raise ValueError("Official support evidence missing {}".format(key))
    return result


def inspect_project(project_path, environment=None):
    root, path, data, resolution = _inspection_project(project_path)
    lineage, files = _lineage(root)
    environment = dict(environment or {})
    descriptor = root / "Plugins" / "SpatialLabs" / "SpatialLabs.uplugin"
    _inside(root, descriptor)
    plugin = json.loads(descriptor.read_text(encoding="utf-8-sig")) if descriptor.is_file() else None
    if plugin is not None and not isinstance(plugin, dict):
        raise ValueError("Installed plugin descriptor must be an object")
    checks = {}
    for key in ("engine_version", "plugin_version", "runtime_version", "device_model", "gpu", "driver"):
        value = environment.get(key)
        checks[key] = {"value": value, "status": "reported" if value else "unknown", "verified": False}
    return {
        "status": "inspected", "project_path": str(path), "project_root": str(root),
        "input_resolution": resolution,
        "engine_association": data.get("EngineAssociation"), "source_hash": lineage, "source_file_count": len(files),
        "plugin": plugin, "plugin_version": plugin.get("VersionName") if plugin else None,
        "engine_version": environment.get("engine_version"), "environment": checks,
        "hardware_verified": False, "compatibility_status": "unknown",
        "limitations": ["Filesystem inspection does not prove runtime/driver/device compatibility",
                        "No plugin was loaded; stereo, tracking, comfort and device performance are NOT_RUN"],
    }


def _license_evidence(evidence):
    if evidence is None:
        return None
    if not isinstance(evidence, dict) or evidence.get("source_url") != LICENSE_URL:
        raise ValueError("License review must identify the exact official license URL")
    digest = evidence.get("content_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("License review needs the SHA-256 of the exact reviewed license content")
    checked = evidence.get("checked_at")
    if not isinstance(checked, str):
        raise ValueError("License checked_at must be a timezone-aware string")
    try:
        timestamp = datetime.datetime.fromisoformat(checked.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid license review timestamp")
    now = datetime.datetime.now(datetime.timezone.utc)
    if timestamp.tzinfo is None or timestamp > now or (now - timestamp).total_seconds() > 7 * 86400:
        raise ValueError("License content must be freshly reviewed (within seven days), never future-dated")
    return dict(evidence)


def plan_install(project_path, plugin_version, engine_version, source_url, support_evidence=None, license_evidence=None):
    root, path, data = _project(project_path)
    _version(plugin_version)
    engine = _version(engine_version)
    if engine[0] != 5:
        raise ValueError("This experimental skill only targets reviewed Unreal Engine 5 combinations")
    association = data.get("EngineAssociation", "")
    if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(association)) and _version(association)[:2] != engine[:2]:
        raise ValueError("Project engine association/version mismatch")
    _official_url(source_url)
    evidence = _support(support_evidence, engine_version, plugin_version)
    lineage, _files = _lineage(root)
    plan = {
        "schema_version": 1, "project_path": str(path), "project_root": str(root), "source_hash": lineage,
        "plugin_version": plugin_version, "engine_version": engine_version, "source_url": source_url,
        "license_url": LICENSE_URL, "support_evidence": evidence, "compatibility_status": evidence["status"],
        "license_evidence": _license_evidence(license_evidence),
        "files": ["Plugins/SpatialLabs/**", path.name, STATE_DIR + "/<plan_id>/**", ".spatiallabs-install.lock"],
        "integrity": "Local SHA-256 records identity only; no vendor-signed checksum is assumed",
        "activation": "Project descriptor only; no editor launch or system OpenXR change",
    }
    plan["plan_id"] = _hash(_json_bytes(plan))
    return plan


def _validate_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError("Plan must be an object")
    payload = dict(plan)
    plan_id = payload.pop("plan_id", None)
    if not isinstance(plan_id, str) or _hash(_json_bytes(payload)) != plan_id:
        raise ValueError("Plan hash mismatch; prepare and review a new plan")
    if plan.get("license_url") != LICENSE_URL:
        raise ValueError("License identity mismatch")
    _license_evidence(plan.get("license_evidence"))
    _official_url(plan.get("source_url"))
    _version(plan.get("plugin_version"))
    if _version(plan.get("engine_version"))[0] != 5:
        raise ValueError("This experimental skill only targets reviewed Unreal Engine 5 combinations")
    if plan.get("compatibility_status") != "unknown" or plan.get("support_evidence", {}).get("source_url"):
        _support(plan.get("support_evidence"), plan["engine_version"], plan["plugin_version"])
    root, path, _data = _project(plan["project_path"])
    if str(root) != plan.get("project_root"):
        raise ValueError("Project scope mismatch")
    expected_files = ["Plugins/SpatialLabs/**", path.name, STATE_DIR + "/<plan_id>/**", ".spatiallabs-install.lock"]
    if type(plan.get("schema_version")) is not int or plan["schema_version"] != 1 or plan.get("files") != expected_files:
        raise ValueError("Plan file scope/schema mismatch")
    if plan.get("activation") != "Project descriptor only; no editor launch or system OpenXR change":
        raise ValueError("Plan activation scope mismatch")
    association = _data.get("EngineAssociation", "")
    if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(association)) and _version(association)[:2] != _version(plan["engine_version"])[:2]:
        raise ValueError("Project engine association/version mismatch")
    return root, path


def validate_archive(archive_path, plugin_version, engine_version):
    archive = _no_links(Path(archive_path))
    _version(plugin_version)
    _version(engine_version)
    if not archive.is_file() or archive.stat().st_size > MAX_DOWNLOAD:
        raise ValueError("Archive missing or exceeds compressed size limit")
    inventory = []
    with zipfile.ZipFile(str(archive)) as package:
        infos = package.infolist()
        if not infos or len(infos) > MAX_ENTRIES:
            raise ValueError("Invalid archive entry count")
        names = set()
        expanded = 0
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name).parts
            if (not name or "\\" in name or name.startswith("/") or ":" in name or "\x00" in name
                    or any(p in ("", "..", ".") or p.rstrip(" .") != p for p in name.rstrip("/").split("/"))
                    or any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p) for p in parts)):
                raise ValueError("Unsafe archive path")
            canonical = name.rstrip("/").casefold()
            if canonical in names:
                raise ValueError("Duplicate/case-colliding archive path")
            names.add(canonical)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or (info.external_attr & 0x400) or info.flag_bits & 1:
                raise ValueError("Archive links/reparse/encrypted entries are not allowed")
            if mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("Archive special file is not allowed")
            expanded += info.file_size
            if expanded > MAX_EXPANDED or info.file_size > max(info.compress_size, 1) * 1000:
                raise ValueError("Archive expanded size/ratio limit exceeded")
        file_names = {i.filename.rstrip("/").casefold() for i in infos if not i.is_dir()}
        for info in infos:
            if any(parent.as_posix().casefold() in file_names for parent in PurePosixPath(info.filename).parents if str(parent) != "."):
                raise ValueError("Archive file/directory collision")
        descriptors = [i for i in infos if PurePosixPath(i.filename).name == "SpatialLabs.uplugin" and not i.is_dir()]
        if len(descriptors) != 1:
            raise ValueError("Expected exactly one SpatialLabs.uplugin descriptor")
        item = descriptors[0]
        if item.file_size > 1024 * 1024:
            raise ValueError("Plugin descriptor is too large")
        descriptor = json.loads(package.read(item).decode("utf-8-sig"))
        if not isinstance(descriptor, dict):
            raise ValueError("Plugin descriptor must be an object")
        if descriptor.get("VersionName") != plugin_version:
            raise ValueError("Plugin version mismatch")
        if _version(descriptor.get("EngineVersion"))[:2] != _version(engine_version)[:2]:
            raise ValueError("Engine version mismatch")
        platforms = descriptor.get("SupportedTargetPlatforms", [])
        if not isinstance(platforms, list) or any(not isinstance(p, str) for p in platforms) or "Win64" not in platforms:
            raise ValueError("Package does not declare Win64 support")
        prefix = item.filename[:-len("SpatialLabs.uplugin")]
        for info in infos:
            if not info.is_dir() and info.filename.startswith(prefix):
                relative = info.filename[len(prefix):]
                content = package.read(info)  # checks CRC; never executes vendor files
                inventory.append({"path": relative, "sha256": _hash(content), "size": len(content)})
        # Also validate CRC of non-plugin metadata rather than trusting an incomplete download.
        bad = package.testzip()
        if bad:
            raise ValueError("Archive CRC failure")
    return {"status": "validated", "plugin_version": plugin_version, "engine_version": engine_version,
            "archive_sha256": _file_hash(archive), "vendor_authenticity_verified": False,
            "prefix": prefix, "inventory": inventory}


class _OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_official(url, destination):
    _official_url(url)
    opener = urllib.request.build_opener(_OfficialRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "DCC-MCP-SpatialLabs-Experimental/0.1"})
    total = 0
    with opener.open(request, timeout=30) as response, Path(destination).open("xb") as output:
        final_url = _official_url(response.geturl())
        declared = response.headers.get("Content-Length")
        expected = None
        if declared is not None:
            try:
                expected = int(declared)
            except ValueError:
                raise ValueError("Invalid download Content-Length")
            if expected < 0 or expected > MAX_DOWNLOAD:
                raise ValueError("Download declared size exceeds bounded limit")
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            total += len(chunk)
            if total > MAX_DOWNLOAD:
                raise ValueError("Download exceeds bounded size limit")
            output.write(chunk)
        if expected is not None and total != expected:
            raise ValueError("Incomplete download: Content-Length mismatch")
    return {"source_url": url, "final_url": final_url, "download_bytes": total}


def _require(authority, scope, action):
    if authority is None or not callable(getattr(authority, "require", None)):
        raise PermissionError("authorization_required: use the local operator console; MCP has no mutation grant")
    if authority.require(scope, action) is False:
        raise PermissionError("Authorization provider refused this exact plan/action")


@contextlib.contextmanager
def _project_lock(root):
    lock = _inside(root, root / ".spatiallabs-install.lock")
    nonce = os.urandom(24).hex()
    fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(nonce)
        yield
    finally:
        if lock.is_file() and not lock.is_symlink() and lock.read_text() == nonce:
            lock.unlink()


def _inventory(root):
    result = []
    if not root.is_dir():
        raise ValueError("Installed plugin directory is missing")
    for path, directory in _walk(root):
        if not directory:
            result.append({"path": path.relative_to(root).as_posix(), "sha256": _file_hash(path), "size": path.stat().st_size})
    return sorted(result, key=lambda item: item["path"])


def _check_installed(root, path, receipt):
    target = _inside(root, root / "Plugins" / "SpatialLabs")
    if _file_hash(path) != receipt["after_sha256"] or _inventory(target) != receipt["inventory"]:
        raise ValueError("Post-install drift/conflict; preserve files and review before rollback")
    expected_dirs = set()
    for entry in receipt["inventory"]:
        expected_dirs.update(p.as_posix() for p in PurePosixPath(entry["path"]).parents if str(p) != ".")
    actual_dirs = {p.relative_to(target).as_posix() for p, directory in _walk(target) if directory}
    if expected_dirs != actual_dirs:
        raise ValueError("Post-install directory drift/conflict; preserve user directories")
    return target


def _write_json(path, value):
    temporary = _no_links(path.with_suffix(".json.tmp"))
    with temporary.open("wb") as output:
        output.write(_json_bytes(value) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(str(temporary), str(path))


def install_plan(plan, authority=None, downloader=None):
    _require(authority, plan, "install")  # before filesystem reads, staging or network
    root, path = _validate_plan(plan)
    if plan["compatibility_status"] != "supported" or plan["support_evidence"]["status"] != "supported":
        raise ValueError("Official compatibility unknown/unsupported; installation refused")
    if plan.get("license_evidence") is None:
        raise ValueError("Exact license content review is missing; no download or installation")
    txn = _inside(root, root / STATE_DIR / plan["plan_id"])
    receipt_path = _inside(root, txn / "receipt.json")
    target = _inside(root, root / "Plugins" / "SpatialLabs")
    with _project_lock(root):
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text())
            if receipt.get("plan") != plan or receipt.get("status") != "installed":
                raise ValueError("Existing transaction requires recovery/new plan, not a blind retry")
            _check_installed(root, path, receipt)
            return {"status": "already_installed", "plan_id": plan["plan_id"], "receipt_path": str(receipt_path)}
        if txn.exists() or target.exists():
            raise ValueError("Existing unowned plugin/transaction; preserve it and inspect manually")
        current, _ = _lineage(root)
        if current != plan["source_hash"]:
            raise ValueError("Project source changed since review; prepare a new plan")
        before = path.read_bytes()
        data = json.loads(before.decode("utf-8-sig"))
        plugins = data.setdefault("Plugins", [])
        if not isinstance(plugins, list) or any(not isinstance(p, dict) for p in plugins):
            raise ValueError("Invalid project Plugins array")
        matches = [p for p in plugins if isinstance(p.get("Name"), str) and p["Name"].casefold() == "spatiallabs"]
        if len(matches) > 1 or any(p["Name"] != "SpatialLabs" for p in matches):
            raise ValueError("Duplicate/case-variant SpatialLabs entries require manual review")
        if matches:
            matches[0]["Enabled"] = True
        else:
            plugins.append({"Name": "SpatialLabs", "Enabled": True})
        after = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
        with tempfile.TemporaryDirectory(prefix="spatiallabs-download-") as scratch:
            archive = Path(scratch) / "official.zip"
            download_record = (downloader or download_official)(plan["source_url"], archive)
            validation = validate_archive(str(archive), plan["plugin_version"], plan["engine_version"])
            # Recheck lineage after a potentially slow download and before committing.
            if _lineage(root)[0] != plan["source_hash"] or target.exists():
                raise ValueError("Project changed during download; nothing installed")
            _inside(root, txn)
            txn.mkdir(parents=True, exist_ok=False)
            (txn / "uproject.before").write_bytes(before)
            staged = txn / "plugin.stage"
            staged.mkdir()
            with zipfile.ZipFile(str(archive)) as package:
                for entry in validation["inventory"]:
                    destination = _inside(staged, staged / entry["path"])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(package.read(validation["prefix"] + entry["path"]))
            inventory = sorted(validation["inventory"], key=lambda x: x["path"])
            receipt = {"schema_version": 1, "status": "prepared", "plan": plan,
                       "before_sha256": _hash(before), "after_sha256": _hash(after), "inventory": inventory,
                       "archive_sha256": validation["archive_sha256"], "vendor_authenticity_verified": False}
            receipt["download"] = download_record or {"source_url": plan["source_url"], "final_url": None,
                                                       "reason": "Injected downloader did not provide transport evidence"}
            _write_json(receipt_path, receipt)
            moved = False
            try:
                _inside(root, target.parent).mkdir(parents=True, exist_ok=True)
                os.replace(str(staged), str(target))
                moved = True
                (txn / "uproject.after").write_bytes(after)
                if path.read_bytes() != before:
                    raise ValueError("Project descriptor changed during install")
                os.replace(str(txn / "uproject.after"), str(path))
                _check_installed(root, path, receipt)
                receipt["status"] = "installed"
                _write_json(receipt_path, receipt)
            except Exception:
                # Preserve any unexpected concurrent edits instead of deleting them.
                if path.read_bytes() == after:
                    (txn / "restore.tmp").write_bytes(before)
                    os.replace(str(txn / "restore.tmp"), str(path))
                if moved and _inventory(target) == inventory:
                    _inside(root, target)
                    os.replace(str(target), str(txn / "plugin.failed"))
                receipt["status"] = "failed_review_required"
                _write_json(receipt_path, receipt)
                raise
    return {"status": "installed", "plan_id": plan["plan_id"], "receipt_path": str(receipt_path),
            "archive_sha256": validation["archive_sha256"], "hardware_verified": False}


def rollback(project_path, plan_id, authority=None):
    _require(authority, {"project_path": project_path, "plan_id": plan_id}, "rollback")
    if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{64}", plan_id):
        raise ValueError("Invalid plan ID")
    root, path, _data = _project(project_path)
    txn = _inside(root, root / STATE_DIR / plan_id)
    receipt_path = _inside(root, txn / "receipt.json")
    with _project_lock(root):
        receipt = json.loads(receipt_path.read_text())
        plan = receipt["plan"]
        payload = dict(plan)
        payload.pop("plan_id", None)
        if _hash(_json_bytes(payload)) != plan_id or plan.get("project_path") != str(path):
            raise ValueError("Receipt scope/hash mismatch")
        before_path = _inside(root, txn / "uproject.before")
        before = before_path.read_bytes()
        if _hash(before) != receipt["before_sha256"]:
            raise ValueError("Backup integrity mismatch")
        target = _inside(root, root / "Plugins" / "SpatialLabs")
        if receipt["status"] == "rolled_back":
            if path.read_bytes() != before or target.exists():
                raise ValueError("Post-rollback drift/conflict")
            return {"status": "already_rolled_back", "plan_id": plan_id}
        if receipt["status"] not in ("installed", "rollback_prepared", "rollback_plugin_moved"):
            raise ValueError("Incomplete transaction requires manual recovery review")
        quarantined = _inside(root, txn / "plugin.rolled-back")
        if target.exists() and quarantined.exists():
            raise ValueError("Rollback conflict: both target and quarantine exist")
        if target.exists():
            _check_installed(root, path, receipt)
            receipt["status"] = "rollback_prepared"
            _write_json(receipt_path, receipt)
            os.replace(str(target), str(quarantined))
        elif not quarantined.exists() or _inventory(quarantined) != receipt["inventory"]:
            raise ValueError("Rollback quarantine missing or changed; preserve files for review")
        # Both crash windows (before/after rename and descriptor restore) are resumable.
        if _file_hash(path) not in (receipt["after_sha256"], receipt["before_sha256"]):
            raise ValueError("Project descriptor changed during rollback; preserve it")
        receipt["status"] = "rollback_plugin_moved"
        _write_json(receipt_path, receipt)
        if path.read_bytes() != before:
            (txn / "restore.tmp").write_bytes(before)
            os.replace(str(txn / "restore.tmp"), str(path))
        receipt["status"] = "rolled_back"
        _write_json(receipt_path, receipt)
    return {"status": "rolled_back", "plan_id": plan_id}

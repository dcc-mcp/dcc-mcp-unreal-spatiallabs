"""Synthetic SpatialLabs regressions; never download or execute vendor code."""

import hashlib
import importlib.util
import io
import json
import stat
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "skills/unreal-spatiallabs/scripts/spatiallabs_project.py"
SOURCE_URL = "https://spatiallabs.acer.com/developer/synthetic-test-plugin.zip"
SUPPORT_URL = (
    "https://spatiallabs.acer.com/developer/docs/dec752e4-1211-11ec-b734-061c90c28e02/"
    "12a0ce02-99da-48df-b2ce-e5f22a7ae1d8"
)
PUBLISHED_PLUGIN_URL = (
    "https://d20hwfev93w9j9.cloudfront.net/upload/file/startvr/"
    "Acer%20SpatialLabs%20Unreal%205.8%20Plugin_2.1.9.zip"
)


@pytest.fixture
def api():
    spec = importlib.util.spec_from_file_location("spatiallabs_project_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "Editable Project"
    root.mkdir()
    (root / "Content").mkdir()
    (root / "Content" / "Keep.txt").write_bytes(b"user-owned content\r\n")
    (root / "Test.uproject").write_bytes(
        b'{"FileVersion":3,"EngineAssociation":"5.8","Plugins":[{"Name":"Other","Enabled":true}]}\r\n'
    )
    return root


@pytest.fixture
def support_evidence():
    # Deliberately synthetic: this tests binding, not Acer compatibility.
    return {
        "status": "supported",
        "source_url": SUPPORT_URL,
        "checked_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "engine_version": "5.8",
        "plugin_version": "2.1.9",
        "runtime_version": "1.01.2059",
        "device_model": "SpatialLabs Pro",
    }


@pytest.fixture
def license_evidence(api):
    # This identity is only a fixture, never a statement about real Acer terms.
    return {
        "source_url": api.LICENSE_URL,
        "content_sha256": hashlib.sha256(b"SYNTHETIC LICENSE ONLY").hexdigest(),
        "checked_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    }


@pytest.fixture
def plan(api, project, support_evidence, license_evidence):
    return api.plan_install(
        str(project), "2.1.9", "5.8", SOURCE_URL,
        support_evidence=support_evidence, license_evidence=license_evidence,
    )


class Authority:
    """Test-only in-process capability; no user-consent boolean in production."""

    def __init__(self, plan_id, action="install"):
        self.plan_id = plan_id
        self.action = action
        self.calls = []

    def require(self, scope, action):
        self.calls.append((scope, action))
        if scope.get("plan_id") != self.plan_id or action != self.action:
            raise PermissionError("authorization scope mismatch")


def test_explicit_authority_denial_is_zero_network_and_zero_changes(api, project, plan):
    class Refused:
        def require(self, scope, action):
            return False

    before = snapshot(project)
    calls = []
    with pytest.raises(PermissionError, match="refused"):
        api.install_plan(plan, Refused(), lambda *args: calls.append(args))
    assert calls == []
    assert snapshot(project) == before


def test_rehashed_plan_cannot_bypass_unreal5_execution_scope(api, project, plan):
    project_file = Path(plan["project_path"])
    descriptor = json.loads(project_file.read_text())
    descriptor["EngineAssociation"] = "4.27"
    project_file.write_text(json.dumps(descriptor))
    plan["engine_version"] = "4.27"
    plan["support_evidence"]["engine_version"] = "4.27"
    plan["source_hash"] = api.inspect_project(str(project))["source_hash"]
    payload = dict(plan)
    payload.pop("plan_id")
    plan["plan_id"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()
    before = snapshot(project)
    calls = []
    with pytest.raises(ValueError, match="Unreal Engine 5"):
        api.install_plan(plan, Authority(plan["plan_id"]), lambda *args: calls.append(args))
    assert calls == []
    assert snapshot(project) == before


def snapshot(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def make_archive(path, extra=None, plugin_version="2.1.9", engine_version="5.8.0"):
    descriptor = {
        "FileVersion": 3,
        "VersionName": plugin_version,
        "EngineVersion": engine_version,
        "SupportedTargetPlatforms": ["Win64"],
        "Modules": [{"Name": "SpatialLabs", "Type": "Runtime"}],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("SpatialLabs/SpatialLabs.uplugin", json.dumps(descriptor))
        archive.writestr("SpatialLabs/Content/fixture.txt", b"SYNTHETIC_ONLY_FIXTURE_DATA")
        for name, data in extra or []:
            if name in archive.namelist():
                with pytest.warns(UserWarning, match="Duplicate name"):
                    archive.writestr(name, data)
            else:
                archive.writestr(name, data)
    return path


def downloader_for(archive_path, calls):
    def download(url, destination):
        calls.append(url)
        Path(destination).write_bytes(archive_path.read_bytes())

    return download


def test_inspection_is_read_only_and_hardware_remains_unverified(api, project):
    before = snapshot(project)
    result = api.inspect_project(str(project))
    assert snapshot(project) == before
    assert result["source_hash"]
    assert result["hardware_verified"] is False


def test_inspection_rejects_packaged_executable_and_relative_project(api, tmp_path):
    executable = tmp_path / "Packaged.exe"
    executable.write_bytes(b"not-an-editable-project")
    with pytest.raises((ValueError, OSError)):
        api.inspect_project(str(executable))
    with pytest.raises((ValueError, OSError)):
        api.inspect_project("relative-project")


def test_ambiguous_project_directory_fails_closed(api, project):
    (project / "Another.uproject").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        api.inspect_project(str(project))


def test_plan_is_read_only_and_binds_precise_scope(api, project, support_evidence, license_evidence):
    before = snapshot(project)
    plan = api.plan_install(
        str(project), "2.1.9", "5.8", SOURCE_URL,
        support_evidence=support_evidence, license_evidence=license_evidence,
    )
    assert snapshot(project) == before
    assert Path(plan["project_root"]).resolve() == project.resolve()
    assert Path(plan["project_path"]).resolve() == (project / "Test.uproject").resolve()
    assert plan["plugin_version"] == "2.1.9"
    assert plan["engine_version"] == "5.8"
    assert plan["source_url"] == SOURCE_URL
    assert plan["license_url"].startswith("https://spatiallabs.acer.com/developer/")
    assert plan["source_hash"]
    assert plan["plan_id"]
    assert plan["license_evidence"] == license_evidence


@pytest.mark.parametrize(
    "url",
    [
        "http://spatiallabs.acer.com/plugin.zip",
        "https://example.org/plugin.zip",
        "https://spatiallabs.acer.com.evil.invalid/plugin.zip",
        "https://spatiallabs.acer.com@evil.invalid/plugin.zip",
        "file:///C:/plugin.zip",
        "https://user:password@spatiallabs.acer.com/plugin.zip",
    ],
)
def test_download_plan_rejects_untrusted_sources(api, project, url):
    before = snapshot(project)
    with pytest.raises(ValueError):
        api.plan_install(str(project), "2.1.9", "5.8", url)
    assert snapshot(project) == before


def test_unknown_compatibility_never_downloads(api, project, license_evidence):
    plan = api.plan_install(str(project), "9.9.9", "5.8", SOURCE_URL, license_evidence=license_evidence)
    assert plan["compatibility_status"] == "unknown"
    before = snapshot(project)
    calls = []
    with pytest.raises(ValueError):
        api.install_plan(plan, Authority(plan["plan_id"]), lambda *args: calls.append(args))
    assert calls == []
    assert snapshot(project) == before


def test_missing_license_review_is_zero_network_and_zero_changes(api, project, support_evidence):
    plan = api.plan_install(str(project), "2.1.9", "5.8", SOURCE_URL, support_evidence=support_evidence)
    assert plan["license_evidence"] is None
    before = snapshot(project)
    calls = []
    with pytest.raises(ValueError):
        api.install_plan(plan, Authority(plan["plan_id"]), lambda *args: calls.append(args))
    assert calls == []
    assert snapshot(project) == before


@pytest.mark.parametrize("digest", [None, "not-a-digest", "a" * 63, "A" * 64])
def test_license_content_digest_format_rejected(api, project, support_evidence, license_evidence, digest):
    license_evidence["content_sha256"] = digest
    with pytest.raises(ValueError):
        api.plan_install(
            str(project), "2.1.9", "5.8", SOURCE_URL,
            support_evidence=support_evidence, license_evidence=license_evidence,
        )


def test_expired_license_review_rejected(api, project, support_evidence, license_evidence):
    license_evidence["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    with pytest.raises(ValueError):
        api.plan_install(
            str(project), "2.1.9", "5.8", SOURCE_URL,
            support_evidence=support_evidence, license_evidence=license_evidence,
        )


def test_license_identity_must_be_exact_official_document(api, project, support_evidence, license_evidence):
    license_evidence["source_url"] = SUPPORT_URL
    with pytest.raises(ValueError):
        api.plan_install(
            str(project), "2.1.9", "5.8", SOURCE_URL,
            support_evidence=support_evidence, license_evidence=license_evidence,
        )


@pytest.mark.parametrize(
    "field,replacement",
    [("files", ["Plugins/SpatialLabs/**", "../outside/**"]), ("activation", "Activate global OpenXR runtime")],
)
def test_rehashed_plan_cannot_expand_file_or_activation_scope(api, project, plan, field, replacement):
    plan[field] = replacement
    payload = {key: value for key, value in plan.items() if key != "plan_id"}
    plan["plan_id"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    before = snapshot(project)
    calls = []
    with pytest.raises(ValueError):
        api.install_plan(plan, Authority(plan["plan_id"]), lambda *args: calls.append(args))
    assert calls == []
    assert snapshot(project) == before


@pytest.mark.parametrize("name", ["spatiallabs", "SPATIALLABS"])
def test_case_variant_plugin_name_cannot_create_duplicate(api, project, support_evidence, license_evidence, name):
    descriptor = project / "Test.uproject"
    data = json.loads(descriptor.read_text(encoding="utf-8"))
    data["Plugins"].append({"Name": name, "Enabled": False})
    descriptor.write_text(json.dumps(data), encoding="utf-8")
    before = snapshot(project)
    calls = []
    with pytest.raises(ValueError):
        plan = api.plan_install(
            str(project), "2.1.9", "5.8", SOURCE_URL,
            support_evidence=support_evidence, license_evidence=license_evidence,
        )
        api.install_plan(plan, Authority(plan["plan_id"]), lambda *args: calls.append(args))
    assert calls == []
    assert snapshot(project) == before


def test_mismatched_support_record_rejected(api, project, support_evidence):
    support_evidence["engine_version"] = "5.7"
    with pytest.raises(ValueError):
        api.plan_install(str(project), "2.1.9", "5.8", SOURCE_URL, support_evidence=support_evidence)


@pytest.mark.parametrize("age", [timedelta(days=8), timedelta(minutes=-10)])
def test_stale_or_future_support_evidence_rejected(api, project, support_evidence, age):
    support_evidence["checked_at"] = (datetime.now(timezone.utc) - age).isoformat()
    with pytest.raises(ValueError):
        api.plan_install(str(project), "2.1.9", "5.8", SOURCE_URL, support_evidence=support_evidence)


@pytest.mark.parametrize("checked_at", [None, 42, False, []])
def test_non_string_support_timestamp_rejected(api, project, support_evidence, checked_at):
    support_evidence["checked_at"] = checked_at
    with pytest.raises(ValueError):
        api.plan_install(str(project), "2.1.9", "5.8", SOURCE_URL, support_evidence=support_evidence)


def test_missing_authority_is_zero_network_and_zero_file_changes(api, project, plan):
    before = snapshot(project)
    calls = []
    with pytest.raises(PermissionError):
        api.install_plan(plan, downloader=lambda *args: calls.append(args))
    assert calls == []
    assert snapshot(project) == before


def test_wrong_scope_authority_is_zero_network_and_zero_file_changes(api, project, plan):
    before = snapshot(project)
    calls = []
    with pytest.raises(PermissionError):
        api.install_plan(plan, Authority("another-plan"), lambda *args: calls.append(args))
    assert calls == []
    assert snapshot(project) == before


def test_json_approval_boolean_cannot_substitute_authority(api, project, plan):
    before = snapshot(project)
    with pytest.raises((PermissionError, TypeError)):
        api.install_plan(plan, {"approved": True})
    assert snapshot(project) == before


def test_valid_synthetic_archive_identity(api, tmp_path):
    archive = make_archive(tmp_path / "synthetic.zip")
    result = api.validate_archive(str(archive), "2.1.9", "5.8")
    assert result["plugin_version"] == "2.1.9"
    assert result["engine_version"].startswith("5.8")


class DownloadResponse(io.BytesIO):
    def __init__(self, body, declared_length, final_url=SOURCE_URL):
        super().__init__(body)
        self.headers = {"Content-Length": declared_length}
        self.final_url = final_url

    def geturl(self):
        return self.final_url


def mock_download_response(api, monkeypatch, body, declared_length, final_url=SOURCE_URL):
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == SOURCE_URL
            assert timeout == 30
            return DownloadResponse(body, declared_length, final_url)

    monkeypatch.setattr(api.urllib.request, "build_opener", lambda *args: Opener())


@pytest.mark.parametrize("declared,body", [("100", b"short"), ("invalid", b"body"), ("-1", b"")])
def test_official_download_rejects_incomplete_or_invalid_length(api, tmp_path, monkeypatch, declared, body):
    mock_download_response(api, monkeypatch, body, declared)
    with pytest.raises(ValueError):
        api.download_official(SOURCE_URL, tmp_path / "download.zip")


def test_official_download_records_actual_final_origin(api, tmp_path, monkeypatch):
    final_url = "https://global-download.acer.com/synthetic.zip"
    mock_download_response(api, monkeypatch, b"synthetic", "9", final_url)
    destination = tmp_path / "download.zip"
    result = api.download_official(SOURCE_URL, destination)
    assert destination.read_bytes() == b"synthetic"
    assert result == {"source_url": SOURCE_URL, "final_url": final_url, "download_bytes": 9}


def test_official_download_rejects_untrusted_final_origin(api, tmp_path, monkeypatch):
    mock_download_response(api, monkeypatch, b"synthetic", "9", "https://example.org/plugin.zip")
    with pytest.raises(ValueError):
        api.download_official(SOURCE_URL, tmp_path / "download.zip")


@pytest.mark.parametrize(
    "entry",
    [
        "../escape.txt",
        "SpatialLabs/../../escape.txt",
        "/absolute.txt",
        "C:/escape.txt",
        "C:escape.txt",
        "\\\\server\\share\\escape.txt",
        "SpatialLabs/..\\..\\escape.txt",
    ],
)
def test_archive_path_traversal_rejected_without_extraction(api, tmp_path, entry):
    archive = make_archive(tmp_path / "hostile.zip", [(entry, b"hostile")])
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        api.validate_archive(str(archive), "2.1.9", "5.8")
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "entry", ["SpatialLabs//Content/unsafe.txt", "SpatialLabs/Content", "SpatialLabs/Content/fixture.txt/"]
)
def test_archive_empty_component_or_file_directory_conflict_rejected(api, tmp_path, entry):
    archive = make_archive(tmp_path / "path-conflict.zip", [(entry, b"conflict")])
    with pytest.raises(ValueError):
        api.validate_archive(str(archive), "2.1.9", "5.8")


@pytest.mark.parametrize("entry", ["SpatialLabs/Content/FIXTURE.TXT", "SpatialLabs/Content/fixture.txt"])
def test_archive_duplicate_or_case_collision_rejected(api, tmp_path, entry):
    archive = make_archive(tmp_path / "collision.zip", [(entry, b"collision")])
    with pytest.raises(ValueError):
        api.validate_archive(str(archive), "2.1.9", "5.8")


def test_archive_symbolic_link_rejected(api, tmp_path):
    archive = make_archive(tmp_path / "symlink.zip")
    info = zipfile.ZipInfo("SpatialLabs/Content/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as container:
        container.writestr(info, "../../outside")
    with pytest.raises(ValueError):
        api.validate_archive(str(archive), "2.1.9", "5.8")


@pytest.mark.parametrize("plugin_version,engine_version", [("2.1.8", "5.8.0"), ("2.1.9", "5.7.0")])
def test_archive_descriptor_version_mismatch_rejected(api, tmp_path, plugin_version, engine_version):
    archive = make_archive(tmp_path / "mismatch.zip", plugin_version=plugin_version, engine_version=engine_version)
    with pytest.raises(ValueError):
        api.validate_archive(str(archive), "2.1.9", "5.8")


def test_archive_crc_corruption_rejected(api, tmp_path):
    archive = make_archive(tmp_path / "corrupt.zip")
    archive.write_bytes(archive.read_bytes().replace(b"SYNTHETIC_ONLY_FIXTURE_DATA", b"CORRUPTED_ONLY_FIXTURE_DAT!", 1))
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        api.validate_archive(str(archive), "2.1.9", "5.8")


def test_incomplete_archive_rejected(api, tmp_path):
    archive = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(archive, "w") as container:
        container.writestr("SpatialLabs/Content/readme.txt", b"descriptor missing")
    with pytest.raises(ValueError):
        api.validate_archive(str(archive), "2.1.9", "5.8")


@pytest.mark.parametrize(
    "descriptor",
    [
        [],
        None,
        {"VersionName": "2.1.9", "EngineVersion": "5.8.0", "SupportedTargetPlatforms": None},
        {"VersionName": "2.1.9", "EngineVersion": "5.8.0", "SupportedTargetPlatforms": "Win64"},
    ],
)
def test_malformed_archive_descriptor_shape_rejected(api, tmp_path, descriptor):
    archive = tmp_path / "malformed-descriptor.zip"
    with zipfile.ZipFile(archive, "w") as container:
        container.writestr("SpatialLabs/SpatialLabs.uplugin", json.dumps(descriptor))
    with pytest.raises(ValueError):
        api.validate_archive(str(archive), "2.1.9", "5.8")


def test_malformed_installed_descriptor_returns_validation_error(api, project):
    target = project / "Plugins/SpatialLabs"
    target.mkdir(parents=True)
    (target / "SpatialLabs.uplugin").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        api.inspect_project(str(project))


def test_extreme_compression_ratio_rejected(api, tmp_path):
    archive = make_archive(tmp_path / "compression-bomb.zip")
    with zipfile.ZipFile(archive, "a", compression=zipfile.ZIP_DEFLATED) as container:
        container.writestr("SpatialLabs/Content/huge-ratio.bin", b"0" * (2 * 1024 * 1024))
    with pytest.raises(ValueError):
        api.validate_archive(str(archive), "2.1.9", "5.8")


def test_project_symlink_rejected(api, project, tmp_path):
    link = tmp_path / "linked-project"
    try:
        link.symlink_to(project, target_is_directory=True)
    except OSError as exc:
        pytest.skip("Host does not grant symlink creation: {}".format(exc))
    with pytest.raises((ValueError, OSError)):
        api.inspect_project(str(link))


def test_install_then_rollback_preserves_original_project_bytes(api, project, plan, tmp_path):
    original = (project / "Test.uproject").read_bytes()
    original_content = (project / "Content" / "Keep.txt").read_bytes()
    archive = make_archive(tmp_path / "synthetic.zip")
    calls = []
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, calls))
    assert calls == [SOURCE_URL]
    assert (project / "Plugins/SpatialLabs/SpatialLabs.uplugin").is_file()
    descriptor = json.loads((project / "Test.uproject").read_text(encoding="utf-8"))
    assert {"Name": "Other", "Enabled": True} in descriptor["Plugins"]
    assert any(item["Name"] == "SpatialLabs" and item["Enabled"] for item in descriptor["Plugins"])
    assert (project / "Content" / "Keep.txt").read_bytes() == original_content
    api.rollback(str(project), plan["plan_id"], Authority(plan["plan_id"], "rollback"))
    assert (project / "Test.uproject").read_bytes() == original
    assert (project / "Content" / "Keep.txt").read_bytes() == original_content
    assert not (project / "Plugins/SpatialLabs").exists()


def test_install_is_idempotent_and_does_not_redownload(api, project, plan, tmp_path):
    archive = make_archive(tmp_path / "synthetic.zip")
    calls = []
    download = downloader_for(archive, calls)
    api.install_plan(plan, Authority(plan["plan_id"]), download)
    before = snapshot(project)
    api.install_plan(plan, Authority(plan["plan_id"]), download)
    assert calls == [SOURCE_URL]
    assert snapshot(project) == before


def test_mixed_case_file_inventory_installs_and_rolls_back_on_windows(api, project, plan, tmp_path):
    archive = make_archive(
        tmp_path / "mixed-case.zip",
        [("SpatialLabs/Content/B.txt", b"upper"), ("SpatialLabs/Content/a.txt", b"lower")],
    )
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    assert (project / "Plugins/SpatialLabs/Content/B.txt").read_bytes() == b"upper"
    assert (project / "Plugins/SpatialLabs/Content/a.txt").read_bytes() == b"lower"
    api.rollback(str(project), plan["plan_id"], Authority(plan["plan_id"], "rollback"))
    assert not (project / "Plugins/SpatialLabs").exists()


def test_download_failure_preserves_original_files(api, project, plan):
    original = (project / "Test.uproject").read_bytes()

    def failed_download(url, destination):
        Path(destination).write_bytes(b"partial-response")
        raise OSError("synthetic connection failure")

    with pytest.raises(OSError):
        api.install_plan(plan, Authority(plan["plan_id"]), failed_download)
    assert (project / "Test.uproject").read_bytes() == original
    assert (project / "Content/Keep.txt").read_bytes() == b"user-owned content\r\n"
    assert not (project / "Plugins/SpatialLabs").exists()


def test_invalid_download_does_not_enable_or_install_plugin(api, project, plan, tmp_path):
    original = (project / "Test.uproject").read_bytes()
    archive = make_archive(tmp_path / "wrong-version.zip", plugin_version="2.0.0")
    with pytest.raises(ValueError):
        api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    assert (project / "Test.uproject").read_bytes() == original
    assert not (project / "Plugins/SpatialLabs").exists()


def test_commit_failure_restores_original_and_requires_manual_recovery(api, project, plan, tmp_path, monkeypatch):
    original = (project / "Test.uproject").read_bytes()
    archive = make_archive(tmp_path / "synthetic.zip")
    calls = []
    real_replace = api.os.replace

    def fail_project_commit(source, destination):
        if Path(destination) == project / "Test.uproject":
            raise OSError("synthetic descriptor commit failure")
        return real_replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(api.os, "replace", fail_project_commit)
        with pytest.raises(OSError):
            api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, calls))
    assert (project / "Test.uproject").read_bytes() == original
    assert not (project / "Plugins/SpatialLabs").exists()
    receipt = project / ".spatiallabs-transactions" / plan["plan_id"] / "receipt.json"
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "failed_review_required"
    with pytest.raises(ValueError):
        api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, calls))
    assert calls == [SOURCE_URL]


def test_unmanaged_existing_plugin_never_overwritten(api, project, plan, tmp_path):
    existing = project / "Plugins/SpatialLabs"
    existing.mkdir(parents=True)
    (existing / "Keep.dll").write_bytes(b"user-owned binary")
    before = snapshot(project)
    archive = make_archive(tmp_path / "synthetic.zip")
    with pytest.raises((ValueError, FileExistsError)):
        api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    assert snapshot(project) == before


def test_project_changed_after_planning_is_rejected(api, project, plan, tmp_path):
    (project / "Test.uproject").write_text('{"EngineAssociation":"5.7"}', encoding="utf-8")
    before = snapshot(project)
    archive = make_archive(tmp_path / "synthetic.zip")
    calls = []
    with pytest.raises(ValueError):
        api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, calls))
    assert calls == []
    assert snapshot(project) == before


def test_project_change_during_download_aborts_before_install(api, project, plan, tmp_path):
    original = (project / "Test.uproject").read_bytes()
    archive = make_archive(tmp_path / "synthetic.zip")

    def download_and_edit(url, destination):
        Path(destination).write_bytes(archive.read_bytes())
        (project / "Content/Keep.txt").write_bytes(b"concurrent user edit")

    with pytest.raises(ValueError):
        api.install_plan(plan, Authority(plan["plan_id"]), download_and_edit)
    assert not (project / "Plugins/SpatialLabs").exists()
    assert (project / "Test.uproject").read_bytes() == original
    assert (project / "Content/Keep.txt").read_bytes() == b"concurrent user edit"


def test_existing_lock_never_stolen_or_deleted(api, project, plan):
    lock = project / ".spatiallabs-install.lock"
    lock.write_bytes(b"another writer's lock")
    before = snapshot(project)
    calls = []
    with pytest.raises(FileExistsError):
        api.install_plan(plan, Authority(plan["plan_id"]), lambda *args: calls.append(args))
    assert calls == []
    assert snapshot(project) == before


def test_rollback_without_authority_has_zero_changes(api, project, plan, tmp_path):
    archive = make_archive(tmp_path / "synthetic.zip")
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    before = snapshot(project)
    with pytest.raises(PermissionError):
        api.rollback(str(project), plan["plan_id"])
    assert snapshot(project) == before


def test_post_install_user_edit_blocks_rollback_without_overwriting(api, project, plan, tmp_path):
    archive = make_archive(tmp_path / "synthetic.zip")
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    installed_file = project / "Plugins/SpatialLabs/Content/fixture.txt"
    installed_file.write_bytes(b"user edit after installation")
    before = snapshot(project)
    with pytest.raises(ValueError):
        api.rollback(str(project), plan["plan_id"], Authority(plan["plan_id"], "rollback"))
    assert snapshot(project) == before


def test_added_user_file_inside_plugin_blocks_rollback(api, project, plan, tmp_path):
    archive = make_archive(tmp_path / "synthetic.zip")
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    (project / "Plugins/SpatialLabs/User.txt").write_bytes(b"new user file")
    before = snapshot(project)
    with pytest.raises(ValueError):
        api.rollback(str(project), plan["plan_id"], Authority(plan["plan_id"], "rollback"))
    assert snapshot(project) == before


def test_added_empty_user_directory_blocks_rollback(api, project, plan, tmp_path):
    archive = make_archive(tmp_path / "synthetic.zip")
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    user_directory = project / "Plugins/SpatialLabs/UserEmptyDirectory"
    user_directory.mkdir()
    before = snapshot(project)
    with pytest.raises(ValueError):
        api.rollback(str(project), plan["plan_id"], Authority(plan["plan_id"], "rollback"))
    assert user_directory.is_dir()
    assert snapshot(project) == before


def test_project_walk_permission_failure_propagates(api, project, monkeypatch):
    def failed_walk(*args, **kwargs):
        kwargs["onerror"](PermissionError("synthetic directory traversal refusal"))
        return iter(())

    monkeypatch.setattr(api.os, "walk", failed_walk)
    with pytest.raises(PermissionError, match="synthetic directory traversal refusal"):
        api.inspect_project(str(project))


def test_backup_corruption_blocks_rollback_and_preserves_install(api, project, plan, tmp_path):
    archive = make_archive(tmp_path / "synthetic.zip")
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    backup = project / ".spatiallabs-transactions" / plan["plan_id"] / "uproject.before"
    backup.write_bytes(b"corrupt backup")
    before = snapshot(project)
    with pytest.raises(ValueError):
        api.rollback(str(project), plan["plan_id"], Authority(plan["plan_id"], "rollback"))
    assert snapshot(project) == before


def test_project_descriptor_edit_blocks_rollback(api, project, plan, tmp_path):
    archive = make_archive(tmp_path / "synthetic.zip")
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    (project / "Test.uproject").write_text('{"UserEdit":true}', encoding="utf-8")
    before = snapshot(project)
    with pytest.raises(ValueError):
        api.rollback(str(project), plan["plan_id"], Authority(plan["plan_id"], "rollback"))
    assert snapshot(project) == before


def test_repeated_rollback_is_idempotent(api, project, plan, tmp_path):
    archive = make_archive(tmp_path / "synthetic.zip")
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    authority = Authority(plan["plan_id"], "rollback")
    api.rollback(str(project), plan["plan_id"], authority)
    before = snapshot(project)
    api.rollback(str(project), plan["plan_id"], authority)
    assert snapshot(project) == before


def test_rollback_journal_failure_after_plugin_move_can_resume(api, project, plan, tmp_path, monkeypatch):
    original = (project / "Test.uproject").read_bytes()
    archive = make_archive(tmp_path / "synthetic.zip")
    api.install_plan(plan, Authority(plan["plan_id"]), downloader_for(archive, []))
    real_write_json = api._write_json

    def failed_journal(path, value):
        if value.get("status") == "rollback_plugin_moved":
            raise OSError("synthetic journal failure after plugin rename")
        return real_write_json(path, value)

    authority = Authority(plan["plan_id"], "rollback")
    with monkeypatch.context() as patch:
        patch.setattr(api, "_write_json", failed_journal)
        with pytest.raises(OSError):
            api.rollback(str(project), plan["plan_id"], authority)
    quarantine = project / ".spatiallabs-transactions" / plan["plan_id"] / "plugin.rolled-back"
    assert not (project / "Plugins/SpatialLabs").exists()
    assert (quarantine / "SpatialLabs.uplugin").is_file()
    api.rollback(str(project), plan["plan_id"], authority)
    assert (project / "Test.uproject").read_bytes() == original
    assert not (project / "Plugins/SpatialLabs").exists()
    assert (quarantine / "SpatialLabs.uplugin").is_file()


@pytest.mark.parametrize("plan_id", ["../elsewhere", "C:/elsewhere", "..\\elsewhere"])
def test_rollback_transaction_path_cannot_escape_project(api, project, plan_id):
    before = snapshot(project)
    with pytest.raises(ValueError):
        api.rollback(str(project), plan_id, Authority(plan_id, "rollback"))
    assert snapshot(project) == before


def test_delivery_inspection_finds_nested_blueprint_project_without_expanding_install_scope(api, tmp_path):
    delivery = tmp_path / "Game delivery"
    source = delivery / "2.工程源文件"
    source.mkdir(parents=True)
    descriptor = source / "Game.uproject"
    descriptor.write_text('{"FileVersion":3,"EngineAssociation":"5.8"}', encoding="utf-8")
    (source / "Content").mkdir()
    (source / "Content/Map.umap").write_bytes(b"synthetic uncooked asset")
    before = snapshot(delivery)
    result = api.inspect_project(str(delivery))
    assert result["project_path"] == str(descriptor)
    assert result["project_root"] == str(source)
    assert result["input_resolution"]["mode"] == "delivery_discovery"
    assert result["hardware_verified"] is False
    assert result["compatibility_status"] == "unknown"
    assert snapshot(delivery) == before
    with pytest.raises(ValueError, match="exactly one editable"):
        api.plan_install(str(delivery), "2.1.9", "5.8", SOURCE_URL)


def test_delivery_inspection_never_chooses_between_two_projects(api, tmp_path):
    for name in ("Source A", "Source B"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "Game.uproject").write_text("{}", encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="Multiple editable"):
        api.inspect_project(str(tmp_path))
    assert snapshot(tmp_path) == before


def test_packaged_game_is_rejected_with_missing_editable_source_diagnostic(api, tmp_path):
    package = tmp_path / "02_Source files"
    package.mkdir()
    (package / "Game.exe").write_bytes(b"synthetic packaged executable; never executed")
    content = package / "Game/Content/Paks"
    content.mkdir(parents=True)
    (content / "Game.pak").write_bytes(b"synthetic cooked archive; never unpacked")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="Packaged-game markers are not editable source"):
        api.inspect_project(str(tmp_path))
    assert snapshot(tmp_path) == before


def test_delivery_without_ue_project_does_not_infer_an_engine(api, tmp_path):
    (tmp_path / "package.json").write_text('{"name":"unknown project"}', encoding="utf-8")
    with pytest.raises(ValueError, match="No supported engine.*established"):
        api.inspect_project(str(tmp_path))


def test_delivery_entry_bound_does_not_return_a_partial_candidate(api, tmp_path, monkeypatch):
    (tmp_path / "Game.uproject").write_text("{}", encoding="utf-8")
    (tmp_path / "other.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(api, "BUNDLE_MAX_ENTRIES", 1)
    with pytest.raises(ValueError, match="bounded entry limit"):
        api.inspect_project(str(tmp_path))


def test_delivery_depth_bound_requires_explicit_path_for_deep_project(api, tmp_path, monkeypatch):
    source = tmp_path / "one/two"
    source.mkdir(parents=True)
    descriptor = source / "Game.uproject"
    descriptor.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(api, "BUNDLE_MAX_DEPTH", 1)
    with pytest.raises(ValueError, match="outside the scan scope"):
        api.inspect_project(str(tmp_path))
    assert api.inspect_project(str(descriptor))["project_path"] == str(descriptor)


def test_delivery_scan_permission_failure_is_not_an_empty_result(api, tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("synthetic delivery scan refusal")

    monkeypatch.setattr(api.os, "scandir", denied)
    with pytest.raises(PermissionError, match="synthetic delivery scan refusal"):
        api.inspect_project(str(tmp_path))


def test_delivery_symlink_is_rejected_before_external_project_read(api, tmp_path, monkeypatch):
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    target = tmp_path / "outside.uproject"
    target.write_text("{}", encoding="utf-8")
    link = delivery / "Game.uproject"
    link.write_text("{}", encoding="utf-8")
    real_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        result = real_lstat(path, *args, **kwargs)
        if path == link:
            class Linked:
                st_mode = stat.S_IFLNK
                st_file_attributes = 0x400
            return Linked()
        return result

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="Symlink/reparse"):
        api.inspect_project(str(delivery))


def test_inspection_keeps_generated_directories_pruned_before_access(api, tmp_path, monkeypatch):
    descriptor = tmp_path / "Game.uproject"
    descriptor.write_text("{}", encoding="utf-8")
    generated = tmp_path / "Saved"
    generated.mkdir()
    real_lstat = Path.lstat

    def unavailable_generated(path, *args, **kwargs):
        if path == generated:
            raise PermissionError("Generated cache must not be inspected")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", unavailable_generated)
    assert api.inspect_project(str(tmp_path))["project_path"] == str(descriptor)


def test_published_acer_plugin_cdn_url_can_be_planned_without_install_authority(api, project):
    before = snapshot(project)
    result = api.plan_install(str(project), "2.1.9", "5.8", PUBLISHED_PLUGIN_URL)
    assert result["source_url"] == PUBLISHED_PLUGIN_URL
    assert result["compatibility_status"] == "unknown"
    assert result["license_evidence"] is None
    with pytest.raises(ValueError, match="compatibility|support"):
        api.install_plan(result, Authority(result["plan_id"]),
                         lambda *args: pytest.fail("Unknown compatibility must not download"))
    assert snapshot(project) == before


@pytest.mark.parametrize("url", [
    PUBLISHED_PLUGIN_URL.replace("https://", "http://"),
    PUBLISHED_PLUGIN_URL.replace("d20hwfev93w9j9.cloudfront.net", "other.cloudfront.net"),
    PUBLISHED_PLUGIN_URL.replace("cloudfront.net/", "cloudfront.net.evil.example/"),
    PUBLISHED_PLUGIN_URL.replace("/upload/file/startvr/", "/other/"),
    PUBLISHED_PLUGIN_URL.replace("/startvr/", "/startvr/../"),
    PUBLISHED_PLUGIN_URL.replace("/startvr/", "/startvr/%2e%2e/"),
    PUBLISHED_PLUGIN_URL.replace("/startvr/", "/startvr/%252e%252e%252f"),
    PUBLISHED_PLUGIN_URL.replace("Acer%20", "nested%2fAcer%20", 1),
    PUBLISHED_PLUGIN_URL.replace("Acer%20", "nested%5cAcer%20", 1),
    PUBLISHED_PLUGIN_URL.replace("Acer%20", "%00Acer%20", 1),
    PUBLISHED_PLUGIN_URL.replace(".zip", ".exe"),
    PUBLISHED_PLUGIN_URL.replace("Unreal", "Unity"),
    PUBLISHED_PLUGIN_URL.replace("Unreal%205.8", "Unreal%20%D9%A5.%D9%A8"),
    PUBLISHED_PLUGIN_URL + "?redirect=https://evil.example",
    PUBLISHED_PLUGIN_URL + "#fragment",
    PUBLISHED_PLUGIN_URL.replace("https://", "https://user:password@"),
    PUBLISHED_PLUGIN_URL.replace("https://", "https://@"),
    PUBLISHED_PLUGIN_URL.replace("https://", "https://:@"),
    "https://@spatiallabs.acer.com/developer/synthetic-test-plugin.zip",
])
def test_plugin_cdn_scope_does_not_allow_arbitrary_cloudfront_content(api, url):
    with pytest.raises(ValueError, match="official Acer"):
        api._official_url(url)

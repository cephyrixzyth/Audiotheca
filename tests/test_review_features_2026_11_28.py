"""Features from the 2026-11-28 review: reflink dedupe, schedules, notifications, Plugin Ledger,
license vault, DAW projects, recovery, naming templates, import pipeline, release monitor,
space map, UCS write-back and extensions."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import struct
import time
from datetime import datetime
from pathlib import Path

import pytest

from audiotheca import (
    daw_projects,
    extensions,
    import_pipeline,
    ledger_recovery,
    license_vault,
    naming_template,
    notify,
    plugin_ledger,
    reflink,
    release_monitor,
    run_items,
    scheduler,
    space_map,
    transaction_ledger,
    ucs_writeback,
)

STAMP = "20261128_0300"
PREV = "20261127_0300"
AUDIT_FIELDS = ["Section", "Item Name", "Current Path", "Vendor", "ID Method", "ID Confidence", "Fingerprint",
                "Version Key", "Size MB", "Status", "Investigation Bucket", "Planned Destination", "Flags"]


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Point every feature store at a temp folder."""
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(run_items, "reports_dir", lambda: reports)
    monkeypatch.setattr(notify, "CONFIG_PATH", reports / "notifications.json")
    monkeypatch.setattr(scheduler, "STORE_PATH", reports / "scan_schedules.json")
    monkeypatch.setattr(plugin_ledger, "STORE_PATH", reports / "plugin_ledger.json")
    monkeypatch.setattr(license_vault, "VAULT_PATH", reports / "license_vault.json")
    monkeypatch.setattr(daw_projects, "INDEX_PATH", reports / "daw_project_index.json")
    monkeypatch.setattr(naming_template, "CONFIG_PATH", reports / "naming_template.json")
    naming_template._cache["mtime"] = None
    monkeypatch.setattr(import_pipeline, "CONFIG_PATH", reports / "import_pipeline.json")
    monkeypatch.setattr(release_monitor, "STORE_PATH", reports / "release_monitor.json")
    monkeypatch.setattr(ucs_writeback, "BACKUP_ROOT", reports / "ucs_backups")
    monkeypatch.setattr(transaction_ledger, "LEDGER_PATH", reports / "transaction_ledger.jsonl")
    monkeypatch.delenv("AUDIOTHECA_AIR_GAP", raising=False)
    return reports


def write_audit(reports: Path, stamp: str, rows: list[dict]) -> None:
    with (reports / f"Scan_Audit_{stamp}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in AUDIT_FIELDS})


def write_dupes(reports: Path, stamp: str, groups: list[list[tuple[str, float]]]) -> None:
    with (reports / f"Duplicate_Review_{stamp}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Dedup Key", "Full Path", "Size MB", "Item Name"])
        writer.writeheader()
        for index, members in enumerate(groups):
            for path, size in members:
                writer.writerow({"Dedup Key": f"k{index}", "Full Path": path, "Size MB": size,
                                 "Item Name": Path(path).name})


# ── Reflink ─────────────────────────────────────────────────────────────────


def _fake_clone(src: Path, dst: Path) -> None:
    if os.path.lexists(dst):
        raise FileExistsError(dst)
    Path(dst).write_bytes(Path(src).read_bytes())


def test_reflink_apply_replaces_duplicate_with_independent_clone(tmp_path, monkeypatch):
    monkeypatch.setattr(reflink, "clone_file", _fake_clone)
    keeper = tmp_path / "keep.wav"
    dup = tmp_path / "dup.wav"
    keeper.write_bytes(b"same-bytes" * 100)
    dup.write_bytes(b"same-bytes" * 100)
    os.utime(dup, (1_600_000_000, 1_600_000_000))
    digest = hashlib.sha256(keeper.read_bytes()).hexdigest()
    reflink.apply(keeper, dup, digest)
    assert dup.read_bytes() == keeper.read_bytes()
    assert not os.path.samefile(keeper, dup)
    assert int(dup.stat().st_mtime) == 1_600_000_000
    # Writing one copy never changes the other (unlike a hardlink).
    dup.write_bytes(b"edited")
    assert keeper.read_bytes() == b"same-bytes" * 100
    assert not list(tmp_path.glob(".*reflink*"))


def test_reflink_apply_refuses_changed_files_and_hardlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(reflink, "clone_file", _fake_clone)
    keeper = tmp_path / "keep.bin"
    dup = tmp_path / "dup.bin"
    keeper.write_bytes(b"a" * 64)
    dup.write_bytes(b"b" * 64)
    digest = hashlib.sha256(b"a" * 64).hexdigest()
    with pytest.raises(ValueError, match="Duplicate changed"):
        reflink.apply(keeper, dup, digest)
    assert dup.read_bytes() == b"b" * 64
    linked = tmp_path / "linked.bin"
    os.link(keeper, linked)
    with pytest.raises(ValueError, match="same file"):
        reflink.apply(keeper, linked, digest)


def test_reflink_probe_reports_unsupported_filesystem(tmp_path, monkeypatch):
    def unsupported(_src, _dst):
        raise reflink.ReflinkUnsupported(95, "Operation not supported")

    monkeypatch.setattr(reflink, "clone_file", unsupported)
    result = reflink.probe(tmp_path)
    assert result["supported"] is False
    assert "not supported" in result["reason"]
    assert list(tmp_path.iterdir()) == []


def test_space_recovery_requires_opt_in_for_hardlinks(tmp_path, monkeypatch, capsys):
    import space_recovery

    monkeypatch.setattr("sys.argv", ["space_recovery.py", "--root", str(tmp_path), "--method", "hardlink"])
    assert space_recovery.main() == 2
    assert "--allow-hardlinks" in capsys.readouterr().out


def test_clone_scripts_quote_paths(tmp_path):
    import space_recovery

    row = {"keeper_path": "/lib/it's/keep.wav", "duplicate_path": "/lib/b/dup.wav", "sha256": "ab" * 32}
    ps1, sh = tmp_path / "c.ps1", tmp_path / "c.sh"
    space_recovery.write_clone_scripts(ps1, sh, [row], execute=True, stamp="x")
    assert "'/lib/it''s/keep.wav'" in ps1.read_text()
    assert "'/lib/it'\\''s/keep.wav'" in sh.read_text()
    assert "audiotheca.reflink" in sh.read_text()


# ── Scheduler ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("@nightly", datetime(2026, 11, 29, 2, 0)),
        ("*/15 * * * *", datetime(2026, 11, 28, 3, 15)),
        ("0 3 * * 0", datetime(2026, 11, 29, 3, 0)),   # 2026-11-28 is a Saturday
        ("0 0 * * 7", datetime(2026, 11, 29, 0, 0)),   # 7 is Sunday too
        ("30 1 1,15 * *", datetime(2026, 12, 1, 1, 30)),
        ("0 9 * * 1-5", datetime(2026, 11, 30, 9, 0)),
    ],
)
def test_next_run(expr, expected):
    assert scheduler.next_run(expr, datetime(2026, 11, 28, 3, 0)) == expected


@pytest.mark.parametrize("bad", ["", "* * *", "61 * * * *", "* 24 * * *", "*/0 * * * *", "a b c d e"])
def test_invalid_cron(bad):
    with pytest.raises(ValueError):
        scheduler.parse_cron(bad)


def test_schedule_store_forces_dry_run_safe_options(stores):
    schedule = scheduler.create_schedule({"name": "Nightly", "cron": "@nightly", "skip_phases": ["ai_lookup", "bogus"]})
    assert schedule["next_run"]
    assert set(schedule["skip_phases"]) == {"ai_lookup", "restructure_live"}
    assert scheduler.scan_options_for(schedule)["skip_phases"] == ["ai_lookup", "restructure_live"]
    due = scheduler.due_schedules(datetime(2026, 11, 28, 1, 59), datetime(2026, 11, 28, 2, 0))
    assert [s["id"] for s in due] == [schedule["id"]]
    assert scheduler.due_schedules(datetime(2026, 11, 28, 2, 0), datetime(2026, 11, 28, 2, 30)) == []
    scheduler.update_schedule(schedule["id"], {"enabled": False})
    assert scheduler.due_schedules(datetime(2026, 11, 28, 1, 59), datetime(2026, 11, 28, 2, 0)) == []
    assert scheduler.delete_schedule(schedule["id"])


def test_schedule_api_roundtrip(client, stores):
    res = client.post("/api/schedules", json={"name": "Weekly", "cron": "@weekly"})
    assert res.status_code == 200, res.text
    sid = res.json()["id"]
    assert client.post("/api/schedules", json={"cron": "nope"}).status_code == 400
    listing = client.get("/api/schedules").json()
    assert [s["id"] for s in listing["schedules"]] == [sid]
    preview = client.post("/api/schedules/preview", json={"cron": "0 * * * *"}).json()
    assert len(preview["next_runs"]) == 5
    assert client.delete(f"/api/schedules/{sid}").json() == {"ok": True}


def test_scheduled_run_skips_when_busy(stores, monkeypatch):
    import asyncio

    from api import schedule_runner
    from api.job_runner import job_manager

    async def busy(**_kwargs):
        raise RuntimeError("A scan is already running")

    monkeypatch.setattr(job_manager, "start", busy)
    schedule = scheduler.create_schedule({"name": "N", "cron": "@nightly"})
    result = asyncio.run(schedule_runner.run_schedule(schedule))
    assert result["outcome"] == "skipped"
    assert scheduler.list_schedules()[0]["last_run"]["outcome"] == "skipped"


# ── Notifications ───────────────────────────────────────────────────────────


def test_notify_url_validation_and_masking():
    assert notify.validate_url("ntfys://ntfy.sh/topic")
    with pytest.raises(ValueError):
        notify.validate_url("ftp://example.com/x")
    with pytest.raises(ValueError):
        notify.validate_url("http://example.com/hook")
    assert notify.mask_url("discord://123/secret-token") == "discord://…" or "secret" not in notify.mask_url(
        "discord://123/secret-token")
    assert "secret" not in notify.mask_url("gotifys://push.example.com/secret")


def test_notify_send_targets_and_digest(stores, monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "_post", lambda url, body, headers: calls.append((url, body, headers)) or 200)
    write_audit(stores, PREV, [{"Item Name": "A", "Vendor": "Acme", "Status": "ROUTED", "Size MB": "10"}])
    write_audit(stores, STAMP, [
        {"Item Name": "A", "Vendor": "Acme", "Status": "ROUTED", "Size MB": "10"},
        {"Item Name": "B", "Vendor": "", "Status": "NEEDS REVIEW", "Size MB": "5"},
    ])
    write_dupes(stores, STAMP, [[("/x/a", 2048.0), ("/y/a", 2048.0)]])
    notify.add_target("phone", "ntfys://ntfy.example.com/audiotheca")
    notify.add_target("discord", "discord://111/tok")
    result = notify.notify_run_finished(stamp=STAMP, status="done", scheduled=True, schedule_name="Nightly")
    assert result["sent"] == 2 and result["failed"] == 0
    urls = [c[0] for c in calls]
    assert urls[0] == "https://ntfy.example.com/audiotheca"
    assert urls[1] == "https://discord.com/api/webhooks/111/tok"
    body = calls[0][1].decode()
    assert "1 new duplicate group" in body and "1 new unknown vendor" in body and "2.0 GB recoverable" in body
    # Manual scans do not notify in the default "scheduled" mode.
    assert notify.notify_run_finished(stamp=STAMP, status="done", scheduled=False) is None
    # Air gap blocks sending.
    monkeypatch.setenv("AUDIOTHECA_AIR_GAP", "1")
    assert notify.send("t", "b")["skipped"] == "air_gap"


def test_notify_failure_is_reported_not_raised(stores, monkeypatch):
    def boom(*_args):
        raise OSError("connection refused")

    monkeypatch.setattr(notify, "_post", boom)
    notify.add_target("hook", "jsons://hooks.example.com/x")
    result = notify.send("t", "b")
    assert result["failed"] == 1 and "refused" in result["results"][0]["error"]


def test_notification_api_hides_urls(client, stores):
    res = client.post("/api/notifications/targets", json={"name": "n", "url": "gotifys://g.example.com/SECRET"})
    assert res.status_code == 200
    payload = client.get("/api/notifications").json()
    assert "SECRET" not in json.dumps(payload)
    assert payload["targets"][0]["url_masked"].startswith("gotifys://g.example.com")


# ── Plugin Ledger ───────────────────────────────────────────────────────────


def make_vst3(folder: Path, name: str, vendor: str, version: str) -> Path:
    bundle = folder / f"{name}.vst3"
    (bundle / "Contents" / "Resources").mkdir(parents=True)
    (bundle / "Contents" / "x86_64-win").mkdir()
    (bundle / "Contents" / "Resources" / "moduleinfo.json").write_text(json.dumps({
        "Name": name, "Version": version, "Factory Info": {"Vendor": vendor},
        "Classes": [{"Name": name, "Vendor": vendor, "Version": version}],
    }))
    return bundle


def make_au(folder: Path, name: str, vendor: str, version: str) -> Path:
    import plistlib

    bundle = folder / f"{name}.component"
    (bundle / "Contents").mkdir(parents=True)
    with (bundle / "Contents" / "Info.plist").open("wb") as handle:
        plistlib.dump({"CFBundleShortVersionString": version, "CFBundleIdentifier": f"com.{vendor.lower()}.{name}",
                       "AudioComponents": [{"name": f"{vendor}: {name}"}]}, handle)
    return bundle


def test_inspect_vst3_and_au(tmp_path):
    vst3 = plugin_ledger.inspect_plugin(make_vst3(tmp_path, "Pro-Q 3", "FabFilter", "3.21.0"), "VST3")
    assert (vst3["vendor"], vst3["product"], vst3["version"]) == ("FabFilter", "Pro-Q 3", "3.21")
    assert vst3["architectures"] == ["x64"]
    au = plugin_ledger.inspect_plugin(make_au(tmp_path, "Serum", "Xfer", "1.3.6"), "AU")
    assert (au["vendor"], au["product"], au["version"]) == ("Xfer", "Serum", "1.3.6")


def test_ledger_flags_gaps(stores, tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    make_vst3(plugins, "Pro-Q 3", "FabFilter", "3.2")
    make_vst3(plugins, "Pro-L 2", "FabFilter", "2.1")
    make_vst3(plugins, "Valhalla Room", "Valhalla DSP", "2.0")
    plugin_ledger.scan_installed(dirs=[("VST3", plugins)])
    write_audit(stores, STAMP, [
        {"Item Name": "FabFilter Pro-Q 3 v3.1 x64.exe", "Current Path": "/lib/a/FabFilter/proq3_31.exe",
         "Vendor": "FabFilter", "Status": "ROUTED", "Size MB": "40"},
        {"Item Name": "FabFilter Pro-L 2 v2.1.exe", "Current Path": "/lib/a/FabFilter/prol2.exe",
         "Vendor": "FabFilter", "Status": "ROUTED", "Size MB": "30"},
        {"Item Name": "FabFilter Pro-C 2 v2.0 Setup.exe", "Current Path": "/lib/a/FabFilter/proc2.exe",
         "Vendor": "FabFilter", "Status": "ROUTED", "Size MB": "30"},
    ])
    ledger = plugin_ledger.build_ledger(STAMP)
    by_product = {row["product"]: row for row in ledger["plugins"]}
    assert by_product["Pro-Q 3"]["status"] == "installer_older"
    assert "Installed v3.2, newest installer you hold is v3.1" == by_product["Pro-Q 3"]["note"]
    assert by_product["Pro-L 2"]["status"] == "covered"
    assert by_product["Valhalla Room"]["status"] == "no_installer"
    assert [o["installers"][0]["path"] for o in ledger["never_installed"]] == ["/lib/a/FabFilter/proc2.exe"]
    checklist = plugin_ledger.reinstall_checklist(STAMP)
    assert "## FabFilter" in checklist and "**no installer backed up**" in checklist
    assert "Pro-Q 3" in plugin_ledger.reinstall_checklist(STAMP, fmt="csv")


def test_inventory_export_import_roundtrip(stores, tmp_path):
    plugins = tmp_path / "p"
    plugins.mkdir()
    make_vst3(plugins, "Diva", "u-he", "1.4.7")
    plugin_ledger.scan_installed(dirs=[("VST3", plugins)])
    exported = plugin_ledger.export_inventory()
    plugin_ledger._save({"inventory": [], "extra_dirs": [], "scanned_at": None, "host": "", "ignored": []})
    assert plugin_ledger.import_inventory(exported)["count"] == 1
    with pytest.raises(ValueError):
        plugin_ledger.import_inventory({"kind": "other"})


# ── License vault ───────────────────────────────────────────────────────────


@pytest.mark.skipif(not license_vault.crypto_available(), reason="cryptography not installed")
def test_license_vault_encrypts_and_reveals(stores):
    license_vault.upsert_license("fabfilter:proq3", {"license_type": "serial", "secret": "ABCD-1234-SECRET",
                                                      "account": "me@example.com"})
    raw = license_vault.VAULT_PATH.read_text()
    assert "ABCD-1234-SECRET" not in raw
    listed = license_vault.list_licenses()
    assert listed[0]["has_secret"] is True and "secret" not in listed[0]
    assert license_vault.reveal("fabfilter:proq3") == "ABCD-1234-SECRET"
    if os.name != "nt":
        assert (license_vault._key_path().stat().st_mode & 0o777) == 0o600
    license_vault.upsert_license("fabfilter:proq3", {"secret": ""})
    assert license_vault.reveal("fabfilter:proq3") is None


@pytest.mark.skipif(not license_vault.crypto_available(), reason="cryptography not installed")
def test_license_api_never_lists_secret(client, stores):
    assert client.put("/api/licenses/xfer:serum", json={"license_type": "serial", "secret": "S3CR3T"}).status_code == 200
    assert "S3CR3T" not in client.get("/api/licenses").text
    assert client.post("/api/licenses/xfer:serum/reveal").json()["secret"] == "S3CR3T"
    assert client.put("/api/licenses/xfer:serum", json={"license_type": "bogus"}).status_code == 400


# ── DAW projects ────────────────────────────────────────────────────────────


ALS = """<?xml version="1.0" encoding="UTF-8"?>
<Ableton><LiveSet><Tracks><AudioTrack><DeviceChain>
<PluginDevice><PluginDesc><Vst3PluginInfo><Name Value="Pro-Q 3"/></Vst3PluginInfo></PluginDesc></PluginDevice>
<PluginDevice><PluginDesc><VstPluginInfo><PlugName Value="Serum"/></VstPluginInfo></PluginDesc></PluginDevice>
<PluginDevice><PluginDesc><AuPluginInfo><Name Value="Diva"/><Manufacturer Value="u-he"/></AuPluginInfo></PluginDesc></PluginDevice>
<SampleRef><FileRef><Path Value="/lib/samples/Kicks/kick01.wav"/></FileRef></SampleRef>
</DeviceChain></AudioTrack></Tracks></LiveSet></Ableton>"""

RPP = """<REAPER_PROJECT 0.1 "7.0"
  <TRACK
    <FXCHAIN
      <VST "VST3: Pro-Q 3 (FabFilter)" "FabFilter Pro-Q 3.vst3" 0 ""
      >
      <CLAP "CLAP: Surge XT (Surge Synth Team)" org.surge-synth-team.surge-xt
      >
    >
    <ITEM
      <SOURCE WAVE
        FILE "/lib/samples/Snares/snare02.wav"
      >
    >
  >
>"""


def test_daw_project_index_and_usage(stores, tmp_path):
    projects = tmp_path / "projects"
    (projects / "Song A Project").mkdir(parents=True)
    (projects / "Song A Project" / "Song A.als").write_bytes(gzip.compress(ALS.encode()))
    (projects / "song b").mkdir()
    (projects / "song b" / "Song B.rpp").write_text(RPP)
    (projects / "Song A Project" / "Backup").mkdir()
    (projects / "Song A Project" / "Backup" / "old.als").write_bytes(gzip.compress(ALS.encode()))
    summary = daw_projects.index_projects([str(projects)])
    assert summary["project_count"] == 2
    assert {p["name"] for p in summary["top_plugins"]} >= {"Pro-Q 3", "Serum", "Diva", "Surge XT"}
    assert len(daw_projects.projects_using_plugin("Pro-Q 3")) == 2
    assert daw_projects.plugin_usage_counts()["proq3"] == 2
    assert [p["name"] for p in daw_projects.projects_using_path("/lib/samples/Kicks")] == ["Song A"]
    rpp = daw_projects.parse_reaper(projects / "song b" / "Song B.rpp")
    assert {"format": "VST3", "name": "Pro-Q 3", "vendor": "FabFilter"} in rpp["plugins"]
    assert {"format": "CLAP", "name": "Surge XT", "vendor": "Surge Synth Team"} in rpp["plugins"]


# ── Recovery ────────────────────────────────────────────────────────────────


def _pending(src: Path, dst: Path) -> str:
    from audiotheca.cross_volume import object_id
    from audiotheca.file_integrity import content_identity

    return transaction_ledger.log_move(batch_id="b1", src=src, dst=dst,
                                       meta={"identity": content_identity(src), "object_id": object_id(src)})


def test_recovery_dismisses_move_that_never_started(stores, tmp_path):
    src = tmp_path / "lib" / "a.wav"
    src.parent.mkdir()
    src.write_bytes(b"x")
    entry = _pending(src, tmp_path / "lib" / "dest" / "a.wav")
    items = ledger_recovery.scan()["items"]
    assert items[0]["state"] == "not_moved" and "dismiss" in items[0]["actions"]
    ledger_recovery.resolve(entry, "dismiss")
    assert ledger_recovery.scan()["count"] == 0
    assert src.read_bytes() == b"x"


def test_recovery_finishes_or_restores_completed_move(stores, tmp_path):
    src = tmp_path / "lib" / "b.wav"
    dst = tmp_path / "lib" / "dest" / "b.wav"
    src.parent.mkdir()
    src.write_bytes(b"payload")
    entry = _pending(src, dst)
    dst.parent.mkdir()
    os.rename(src, dst)  # crash after the rename, before commit
    item = ledger_recovery.scan()["items"][0]
    assert item["state"] == "moved"
    with pytest.raises(ValueError):
        ledger_recovery.resolve(entry, "dismiss")
    result = ledger_recovery.resolve(entry, "restore")
    assert result["ok"], result
    assert src.read_bytes() == b"payload" and not dst.exists()
    assert ledger_recovery.scan()["count"] == 0


def test_recovery_api_requires_confirmation(client, stores, tmp_path):
    src = tmp_path / "c.wav"
    src.write_bytes(b"c")
    dst = tmp_path / "d" / "c.wav"
    entry = _pending(src, dst)
    dst.parent.mkdir()
    os.rename(src, dst)
    assert client.get("/api/recovery").json()["count"] == 1
    assert client.post(f"/api/recovery/{entry}", json={"action": "finish"}).status_code == 400
    res = client.post(f"/api/recovery/{entry}", json={"action": "finish", "confirm_live": True})
    assert res.status_code == 200 and res.json()["ok"]
    assert client.get("/api/recovery").json()["count"] == 0
    assert dst.exists()


# ── Naming templates ────────────────────────────────────────────────────────


def test_naming_template_render_and_validation():
    fields = naming_template.fields_for(name="Serum v1.3.6 x64 VST3.zip", vendor="Xfer Records", bin_name="a")
    assert fields["version"] == "1.3.6" and fields["format"] == "VST3" and fields["product"] == "Serum"
    assert naming_template.render("{bin}/{vendor}/{product}[ v{version}]", fields) == "a/Xfer Records/Serum v1.3.6"
    no_version = naming_template.fields_for(name="Serum", vendor="Xfer", bin_name="a")
    assert naming_template.render("{bin}/{vendor}/{product}[ v{version}]", no_version) == "a/Xfer/Serum"
    assert naming_template.render("{bin}/{vendor}/{name}", {"bin": "a", "vendor": "Acme", "name": "Acme"}) == "a/Acme"
    assert naming_template.render("{vendor}/{name}", {"vendor": 'Bad:Name?', "name": "x"}) == "BadName/x"
    for bad in ["/abs/{name}", "{bin}/../{name}", "{bin}/{vendor}", "{bin}/{nope}/{name}", "{bin}/[{name}"]:
        with pytest.raises(ValueError):
            naming_template.validate(bad)


def test_naming_template_drives_engine_routing(stores, tmp_path):
    from audiotheca.routing import RoutingMixin

    naming_template.save_config(template="{bin}/{vendor}/{product}[ v{version}]", enabled=True)

    class Router(RoutingMixin):
        root_dir = tmp_path
        investigate_dir = tmp_path / "_requiresinvestigation"
        tonex_dir = tmp_path / "_tonex"
        investigation_store = None

        def _needs_investigation(self, item):
            return False

        def _apply_platform_lane(self, item, dest_path, relative_dest):
            return dest_path, relative_dest

    import audiotheca.routing as routing_module

    original = routing_module.apply_hints_to_item
    routing_module.apply_hints_to_item = lambda item, store: item
    try:
        item = {"company": "Xfer Records", "original_name": "Serum_v1.3.6_x64", "source_bin": "a",
                "is_tonex": False, "version_key": ""}
        dest, relative, status, _bucket = Router().compute_destination(item)
    finally:
        routing_module.apply_hints_to_item = original
    assert status == "READY"
    assert relative == "a/Xfer Records/Serum v1.3.6"
    assert dest == tmp_path / "a" / "Xfer Records" / "Serum v1.3.6"


def test_naming_preview_api(client, stores):
    write_audit(stores, STAMP, [
        {"Section": "a", "Item Name": "Pro-Q 3 v3.1", "Vendor": "FabFilter", "Status": "ROUTED"},
        {"Section": "a", "Item Name": "Pro-Q 3 v3.1", "Vendor": "FabFilter", "Status": "ROUTED"},
        {"Section": "b", "Item Name": "Mystery", "Vendor": "", "Status": "NEEDS REVIEW"},
    ])
    res = client.post("/api/naming-template/preview", json={"template": "{bin}/{vendor}/{product}[ v{version}]"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["routed_items"] == 2 and data["collisions"] == 2
    assert data["rows"][0]["template_destination"] == "a/FabFilter/Pro-Q 3 v3.1"
    assert client.put("/api/naming-template", json={"template": "{bin}/{vendor}", "enabled": True}).status_code == 400


# ── Import pipeline ─────────────────────────────────────────────────────────


def _age(path: Path) -> None:
    old = time.time() - 3600
    os.utime(path, (old, old))


def test_import_pipeline_proposes_and_files(stores, tmp_path, monkeypatch, client):
    lib = tmp_path / "lib"
    incoming = lib / "_incoming"
    incoming.mkdir(parents=True)
    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(lib))
    write_audit(stores, STAMP, [
        {"Section": "b", "Item Name": "Kontakt 7.1", "Current Path": str(lib / "b/Native Instruments/Kontakt 7.1"),
         "Vendor": "Native Instruments", "Version Key": "7.1", "Status": "ROUTED"},
    ])
    newer = incoming / "Native Instruments Kontakt 7.10.zip"
    newer.write_bytes(b"zip")
    same = incoming / "Native Instruments Kontakt 7.1.zip"
    same.write_bytes(b"zip")
    partial = incoming / "Serum.zip.part"
    partial.write_bytes(b"...")
    fresh = incoming / "Native Instruments Massive X.zip"
    fresh.write_bytes(b"zip")
    for path in (newer, same, partial):
        _age(path)

    res = client.put("/api/import/settings", json={"incoming": str(incoming), "library_root": str(lib)})
    assert res.status_code == 200, res.text
    listing = client.get("/api/import").json()
    by_name = {i["name"]: i for i in listing["items"]}
    assert set(by_name) == {newer.name, same.name}
    assert listing["waiting"] == [fresh.name]
    assert by_name[newer.name]["library_status"] == "newer_version"
    assert by_name[newer.name]["vendor"] == "Native Instruments"
    assert by_name[newer.name]["destination"] == "b/Native Instruments/Native Instruments Kontakt 7.10.zip"
    assert by_name[same.name]["library_status"] == "duplicate"
    assert by_name[same.name]["recommended"] == "skip"

    # Live apply needs confirm_live.
    body = {"items": [{"path": str(newer), "action": "apply"}], "dry_run": False}
    assert client.post("/api/import/apply", json=body).status_code == 400
    res = client.post("/api/import/apply", json={**body, "confirm_live": True})
    assert res.status_code == 200, res.text
    result = res.json()["results"][0]
    assert result["ok"], result
    assert (lib / "b" / "Native Instruments" / newer.name).read_bytes() == b"zip"
    assert not newer.exists()
    skip = client.post("/api/import/apply", json={"items": [{"path": str(same), "action": "skip"}],
                                                  "dry_run": False, "confirm_live": True})
    assert skip.json()["results"][0]["ok"]
    assert [i["name"] for i in client.get("/api/import").json()["items"]] == []
    # The move is in the ledger and can be undone.
    batch = res.json()["batch_id"]
    assert transaction_ledger.rollback_batch(batch)["ok"]
    assert newer.exists()


def test_import_refuses_paths_outside_incoming(stores, tmp_path):
    incoming = tmp_path / "in"
    incoming.mkdir()
    import_pipeline.save_settings(incoming=str(incoming))
    other = tmp_path / "elsewhere.zip"
    other.write_bytes(b"x")
    with pytest.raises(ValueError, match="Incoming"):
        import_pipeline.apply(str(other), "as_is", library_root=tmp_path, dry_run=False)


def test_import_settings_reject_incoming_outside_library(client, stores, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(tmp_path / "lib"))
    res = client.put("/api/import/settings", json={"incoming": "/etc"})
    assert res.status_code in {400, 403}


# ── Release monitor ─────────────────────────────────────────────────────────


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>FabFilter news</title>
<item><title>FabFilter releases Pro-Q 4</title><link>https://example.com/proq4</link></item>
<item><title>Pro-L 2 version 2.2 now available</title><link>https://example.com/prol22</link></item>
<item><title>Pro-L 2 version 2.1 update</title><link>https://example.com/prol21</link></item>
</channel></rss>"""


def test_release_monitor_wanted_list(stores, tmp_path):
    write_audit(stores, STAMP, [
        {"Item Name": "FabFilter Pro-L 2 v2.1", "Vendor": "FabFilter", "Status": "ROUTED"},
    ])
    feed = release_monitor.add_feed("FabFilter", "https://example.com/feed.xml")
    result = release_monitor.check_feeds(fetch=lambda url: RSS)
    assert result == {"checked": 1, "new_entries": 3, "errors": []}
    wanted = release_monitor.wanted_list()
    kinds = {e["title"]: e["kind"] for e in wanted["entries"]}
    assert kinds == {"FabFilter releases Pro-Q 4": "not_owned", "Pro-L 2 version 2.2 now available": "update"}
    update = next(e for e in wanted["entries"] if e["kind"] == "update")
    assert update["owned_version"] == "2.1" and update["version"] == "2.2"
    assert release_monitor.mark(update["id"], "dismissed")
    assert len(release_monitor.wanted_list()["entries"]) == 1
    release_monitor.check_feeds(fetch=lambda url: RSS)  # marks survive a recheck
    assert len(release_monitor.wanted_list()["entries"]) == 1
    assert release_monitor.remove_feed(feed["id"])


def test_release_monitor_rejects_entities_and_http():
    with pytest.raises(ValueError):
        release_monitor.parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><rss></rss>')
    with pytest.raises(ValueError):
        release_monitor.add_feed("V", "http://example.com/feed")


# ── Space map ───────────────────────────────────────────────────────────────


def test_space_map(stores, client):
    write_audit(stores, STAMP, [
        {"Section": "a", "Item Name": "X", "Current Path": "/l/a/X", "Vendor": "Acme", "Size MB": "100"},
        {"Section": "a", "Item Name": "X copy", "Current Path": "/l/a/X copy", "Vendor": "Acme", "Size MB": "100"},
        {"Section": "b", "Item Name": "Y", "Current Path": "/l/b/Y", "Vendor": "", "Size MB": "50"},
    ])
    write_dupes(stores, STAMP, [[("/l/a/X", 100.0), ("/l/a/X copy", 100.0)]])
    tree = space_map.build_space_map(STAMP)
    assert tree["total_mb"] == 250 and tree["duplicate_mb"] == 100
    assert tree["children"][0]["name"] == "a"
    assert tree["children"][1]["children"][0]["name"] == "Unknown vendor"
    assert client.get(f"/api/runs/{STAMP}/space-map").json()["total_mb"] == 250


# ── UCS write-back ──────────────────────────────────────────────────────────


def make_wav(path: Path, frames: bytes = b"\x01\x02" * 100) -> None:
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(frames)) + frames
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def test_ucs_plan_and_rename(stores, tmp_path):
    a = tmp_path / "creaky door open.wav"
    b = tmp_path / "creaky_door_close.wav"
    make_wav(a)
    make_wav(b)
    planned = ucs_writeback.plan([str(a), str(b)], cat_id="DOORWood", creator_id="JD", source_id="Backyard")
    names = [r["new_name"] for r in planned["rows"]]
    assert names == ["DOORWood_Creaky Door Open_JD_Backyard.wav", "DOORWood_Creaky Door Close_JD_Backyard.wav"]
    result = ucs_writeback.apply_renames(planned)
    assert result["renamed"] == 2
    assert (tmp_path / names[0]).exists() and not a.exists()
    assert transaction_ledger.rollback_batch(result["batch_id"])["ok"]
    assert a.exists()
    with pytest.raises(ValueError):
        ucs_writeback.ucs_name(cat_id="door", fx_name="x", creator_id="a", source_id="b")


def test_ucs_ixml_write_preserves_audio_and_undoes(stores, tmp_path):
    wav = tmp_path / "hit.wav"
    make_wav(wav)
    original = wav.read_bytes()
    audio_before = ucs_writeback._audio_digest(wav)
    result = ucs_writeback.apply_metadata([str(wav)], cat_id="IMPTMetal", creator_id="JD", source_id="Lib",
                                          fx_names={str(wav): "Metal Hit <Big>"})
    assert result["written"] == 1, result
    data = wav.read_bytes()
    assert b"iXML" in data and b"<CATID>IMPTMetal</CATID>" in data and b"Metal Hit &lt;Big&gt;" in data
    assert struct.unpack("<I", data[4:8])[0] == len(data) - 8
    assert ucs_writeback._audio_digest(wav) == audio_before
    # Writing again replaces the chunk instead of stacking a second one.
    ucs_writeback.apply_metadata([str(wav)], cat_id="IMPTMetal", creator_id="JD", source_id="Lib")
    assert wav.read_bytes().count(b"iXML") == 1
    batches = ucs_writeback.list_metadata_batches()
    oldest = batches[-1]["batch"]
    assert ucs_writeback.undo_metadata(oldest)["restored"] == 1
    assert wav.read_bytes() == original


# ── Extensions ──────────────────────────────────────────────────────────────


def test_extensions_are_opt_in(tmp_path, monkeypatch):
    folder = tmp_path / "ext"
    folder.mkdir()
    (folder / "studio_rules.py").write_text(
        "NAME = 'Studio rules'\n"
        "VENDOR_RULES = {'Acme Audio': ['acmesynth']}\n"
        "SENT = []\n"
        "def notify(title, body):\n    SENT.append(title)\n"
        "def export_run(stamp, items):\n    return ('acme.txt', f'{stamp}:{len(items)}')\n"
    )
    (folder / "broken.py").write_text("raise RuntimeError('nope')\n")
    monkeypatch.setenv("AUDIOTHECA_EXTENSIONS_DIR", str(folder))
    monkeypatch.delenv("AUDIOTHECA_EXTENSIONS", raising=False)
    assert extensions.vendor_rows() == []
    monkeypatch.setenv("AUDIOTHECA_EXTENSIONS", "1")
    extensions._loaded["key"] = None
    info = extensions.describe()
    assert info["extensions"][0]["vendor_rules"] == 1 and info["extensions"][0]["exporter"]
    assert info["errors"][0]["file"] == "broken.py"
    assert extensions.vendor_rows()[0].company == "Acme Audio"
    from audiotheca.vendor_overrides import compile_user_routes

    assert any(vendor == "Acme Audio" for vendor, _pattern, _strong in compile_user_routes())
    assert extensions.run_notifiers("hello", "body")[0]["ok"]
    assert extensions.run_export("studio_rules", STAMP)[0] == "acme.txt"

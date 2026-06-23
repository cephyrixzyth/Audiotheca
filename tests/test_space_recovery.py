"""Tests for space_recovery — hardlink dedup planning and bloat classification."""

from pathlib import Path

from space_recovery import (
    build_link_plan,
    classify_bloat,
    full_sha256,
    is_link_candidate,
)

MB = 1024 * 1024


class TestClassifyBloat:
    def test_directx_installer(self):
        verdict, label, embedded = classify_bloat("DXSETUP.exe", "Product/Redist/DirectX/DXSETUP.exe")
        assert verdict == "REDIST_INSTALLER"
        assert label == "DirectX"
        assert embedded is True

    def test_vc_redist_embedded_in_installer_data(self):
        verdict, _label, embedded = classify_bloat(
            "vc_redist.x64.exe",
            "Steinberg/Activation/Installer Data/vc_redist.x64.exe",
        )
        assert verdict == "REDIST_INSTALLER"
        assert embedded is True

    def test_vc_redist_loose_not_embedded(self):
        verdict, _label, embedded = classify_bloat("vcredist_x86.exe", "SomeProduct/vcredist_x86.exe")
        assert verdict == "REDIST_INSTALLER"
        assert embedded is False

    def test_promo_url_shortcut(self):
        verdict, label, _ = classify_bloat("Visit Our Site.url", "Product/Visit Our Site.url")
        assert verdict == "PROMO_FILE"
        assert label == "Internet shortcut"

    def test_promo_html_with_keyword(self):
        verdict, _label, _ = classify_bloat("More Products Here.html", "Product/More Products Here.html")
        assert verdict == "PROMO_FILE"

    def test_plain_html_documentation_not_flagged(self):
        assert classify_bloat("index.html", "Product/Documentation/index.html") is None

    def test_torrent_note(self):
        verdict, _label, _ = classify_bloat(
            "Torrent downloaded from demonoid.txt", "Product/Torrent downloaded from demonoid.txt"
        )
        assert verdict == "PROMO_FILE"

    def test_os_junk(self):
        assert classify_bloat("Thumbs.db", "x/Thumbs.db")[0] == "OS_JUNK"
        assert classify_bloat(".DS_Store", "x/.DS_Store")[0] == "OS_JUNK"
        assert classify_bloat("._resource", "x/._resource")[0] == "OS_JUNK"

    def test_product_setup_never_flagged(self):
        assert classify_bloat("Setup Serum v1.35.exe", "Xfer/Setup Serum v1.35.exe") is None

    def test_nfo_never_flagged(self):
        assert classify_bloat("release.nfo", "Product/release.nfo") is None


class TestLinkCandidates:
    def test_large_wav_is_candidate(self):
        assert is_link_candidate("samples.wav", 100 * MB) is True

    def test_small_file_is_not(self):
        assert is_link_candidate("samples.wav", 1 * MB) is False

    def test_small_pdf_manual_is_candidate(self):
        assert is_link_candidate("Manual.pdf", 1 * MB) is True

    def test_tiny_pdf_is_not(self):
        assert is_link_candidate("Manual.pdf", 100 * 1024) is False


class TestBuildLinkPlan:
    def test_identical_files_grouped_different_excluded(self, tmp_path: Path):
        lib_a = tmp_path / "LibA"
        lib_b = tmp_path / "LibB"
        lib_a.mkdir()
        lib_b.mkdir()
        payload = b"x" * 4096
        (lib_a / "kick.wav").write_bytes(payload)
        (lib_b / "kick.wav").write_bytes(payload)
        (lib_b / "snare.wav").write_bytes(b"y" * 4096)  # same size, different bytes

        size_index = {
            4096: [
                (lib_a / "kick.wav", "a"),
                (lib_b / "kick.wav", "b"),
                (lib_b / "snare.wav", "b"),
            ]
        }
        rows = build_link_plan(size_index, progress=False)
        assert len(rows) == 1
        assert rows[0]["duplicate_path"].endswith("kick.wav")
        assert rows[0]["sha256"] == full_sha256(lib_a / "kick.wav")

    def test_keeper_is_shortest_path(self, tmp_path: Path):
        shallow = tmp_path / "a.bin"
        deep = tmp_path / "deeply" / "nested"
        deep.mkdir(parents=True)
        deep_file = deep / "a.bin"
        shallow.write_bytes(b"z" * 2048)
        deep_file.write_bytes(b"z" * 2048)

        rows = build_link_plan({2048: [(deep_file, "x"), (shallow, "x")]}, progress=False)
        assert len(rows) == 1
        assert rows[0]["keeper_path"] == str(shallow)
        assert rows[0]["duplicate_path"] == str(deep_file)

    def test_unique_sizes_skipped_without_hashing(self, tmp_path: Path):
        only = tmp_path / "solo.bin"
        only.write_bytes(b"q" * 1024)
        rows = build_link_plan({1024: [(only, "x")]}, progress=False)
        assert rows == []

from __future__ import annotations

from pathlib import Path

from api.duplicate_execute import infer_library_root
from api.path_logic import is_logical_path_under, logical_path_parts


class TestLogicalPathUnder:
    def test_windows_paths_without_filesystem(self):
        assert is_logical_path_under(
            r"Z:\test\a\Product",
            r"Z:\test",
        )


class TestLogicalPathParts:
    def test_windows_path_on_posix(self):
        parts = logical_path_parts(r"Z:\_software\_audio\a\Native Instruments\Serum")
        assert parts == ["Z:", "_software", "_audio", "a", "Native Instruments", "Serum"]

    def test_posix_path(self):
        parts = logical_path_parts("/library/a/Vendor/Product")
        assert parts == ["", "library", "a", "Vendor", "Product"]


class TestInferLibraryRoot:
    def test_first_section_bin_under_wrappers(self):
        path = Path(r"Z:\_software\_audio\a\Native Instruments\Serum")
        assert infer_library_root(path) == Path(r"Z:\_software\_audio")

    def test_ignores_nested_single_letter_folder(self):
        path = Path(
            r"Z:\_software\_audio\a\Native Instruments\Kontakt\Library\a\Samples\file.wav"
        )
        assert infer_library_root(path) == Path(r"Z:\_software\_audio")

    def test_investigation_path(self):
        path = Path(
            r"Z:\_software\_audio\_requiresinvestigation\_unknown_vendor\Noire Library"
        )
        assert infer_library_root(path) == Path(r"Z:\_software\_audio")

    def test_simple_section_layout(self):
        path = Path(r"D:\AudioLib\z\Xfer Records\Serum")
        assert infer_library_root(path) == Path(r"D:\AudioLib")

    def test_equals_section_bin(self):
        path = Path(r"Z:\_software\_audio\=\287901\product")
        assert infer_library_root(path) == Path(r"Z:\_software\_audio")

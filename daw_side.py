"""DAW-SIDE: DAW helper plugin manifest and JUCE project scaffold."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

PLUGIN_VERSION = "0.1.0"
REPO_TEMPLATE = Path(__file__).resolve().parent / "plugins" / "daw_side" / "template"


def plugin_manifest(
    *,
    formats: tuple[str, ...] = ("vst3", "au"),
    api_base: str | None = None,
) -> dict[str, Any]:
    base = (api_base or os.environ.get("AUDIOTHECA_API_BASE") or "http://127.0.0.1:8787").rstrip("/")
    if not base.endswith("/api"):
        # Accept host-only or full /api base from desktop discovery.
        if "://" in base and not base.rstrip("/").endswith("/api"):
            base = f"{base.rstrip('/')}"
    return {
        "name": "AudiothecaSidecar",
        "vendor": "Audiotheca",
        "version": PLUGIN_VERSION,
        "formats": list(formats),
        "built": False,
        "features": ["drag_from_library", "cue_markers", "tempo_sync"],
        "api_base": base if base.endswith("/api") else f"{base}/api",
        "juce_minimum": "7.0.9",
    }


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_blueprint(
    *,
    home: str | Path | None = None,
    api_base: str | None = None,
) -> dict[str, Any]:
    root = Path(home or os.environ.get("AUDIOTHECA_HOME", Path.home() / ".audiotheca"))
    plugin_dir = root / "plugins" / "daw_side"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest = plugin_manifest(api_base=api_base)
    manifest_path = plugin_dir / "plugin_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Copy template tree when present; otherwise emit inline scaffold.
    if REPO_TEMPLATE.is_dir():
        for src in REPO_TEMPLATE.rglob("*"):
            if src.is_file():
                rel = src.relative_to(REPO_TEMPLATE)
                dest = plugin_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
    else:
        _emit_inline_scaffold(plugin_dir)

    build_script = plugin_dir / ("build.ps1" if os.name == "nt" else "build.sh")
    if not build_script.is_file():
        _write_file(
            build_script,
            _build_script_content(plugin_dir),
        )
        if os.name != "nt":
            build_script.chmod(0o755)

    return {
        "manifest_path": str(manifest_path),
        "plugin_dir": str(plugin_dir),
        "cmake": str(plugin_dir / "CMakeLists.txt"),
        "build_script": str(build_script),
        "built": False,
        "ok": True,
        "install_instructions": _install_instructions(plugin_dir),
    }


def _emit_inline_scaffold(plugin_dir: Path) -> None:
    _write_file(
        plugin_dir / "CMakeLists.txt",
        """cmake_minimum_required(VERSION 3.22)
project(AudiothecaSidecar VERSION 0.1.0)

# Fetch JUCE — set JUCE_PATH env or clone alongside this project.
if(DEFINED ENV{JUCE_PATH})
  add_subdirectory($ENV{JUCE_PATH} juce)
else()
  include(FetchContent)
  FetchContent_Declare(juce
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG        7.0.9)
  FetchContent_MakeAvailable(juce)
endif()

juce_add_plugin(AudiothecaSidecar
  COMPANY_NAME "Audiotheca"
  PLUGIN_MANUFACTURER_CODE Atca
  PLUGIN_CODE Atsc
  FORMATS VST3 AU
  PRODUCT_NAME "Audiotheca Sidecar")

target_sources(AudiothecaSidecar PRIVATE
  Source/PluginProcessor.cpp
  Source/PluginProcessor.h
  Source/PluginEditor.cpp
  Source/PluginEditor.h)

target_compile_definitions(AudiothecaSidecar
  PUBLIC JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0)

target_link_libraries(AudiothecaSidecar
  PRIVATE juce::juce_audio_utils
  PUBLIC juce::juce_recommended_config_flags
         juce::juce_recommended_lto_flags
         juce::juce_recommended_warning_flags)
""",
    )
    _write_file(
        plugin_dir / "Source" / "PluginProcessor.h",
        """#pragma once
#include <JuceHeader.h>

class AudiothecaSidecarProcessor : public juce::AudioProcessor {
public:
  AudiothecaSidecarProcessor();
  ~AudiothecaSidecarProcessor() override = default;
  void prepareToPlay(double, int) override {}
  void releaseResources() override {}
  void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override {}
  juce::AudioProcessorEditor* createEditor() override;
  bool hasEditor() const override { return true; }
  const juce::String getName() const override { return "Audiotheca Sidecar"; }
  bool acceptsMidi() const override { return false; }
  bool producesMidi() const override { return false; }
  double getTailLengthSeconds() const override { return 0.0; }
  int getNumPrograms() override { return 1; }
  int getCurrentProgram() override { return 0; }
  void setCurrentProgram(int) override {}
  const juce::String getProgramName(int) override { return {}; }
  void changeProgramName(int, const juce::String&) override {}
  void getStateInformation(juce::MemoryBlock&) override {}
  void setStateInformation(const void*, int) override {}
  static juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter();
};
""",
    )
    _write_file(
        plugin_dir / "Source" / "PluginProcessor.cpp",
        """#include "PluginProcessor.h"
#include "PluginEditor.h"

AudiothecaSidecarProcessor::AudiothecaSidecarProcessor()
  : juce::AudioProcessor(BusesProperties().withOutput("Output", juce::AudioChannelSet::stereo(), true)) {}

juce::AudioProcessorEditor* AudiothecaSidecarProcessor::createEditor() {
  return new AudiothecaSidecarEditor(*this);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() {
  return new AudiothecaSidecarProcessor();
}
""",
    )
    _write_file(
        plugin_dir / "Source" / "PluginEditor.h",
        """#pragma once
#include <JuceHeader.h>
#include "PluginProcessor.h"

class AudiothecaSidecarEditor : public juce::AudioProcessorEditor {
public:
  explicit AudiothecaSidecarEditor(AudiothecaSidecarProcessor&);
  void paint(juce::Graphics&) override;
  void resized() override;
private:
  AudiothecaSidecarProcessor& processor;
  juce::Label statusLabel;
};
""",
    )
    _write_file(
        plugin_dir / "Source" / "PluginEditor.cpp",
        """#include "PluginEditor.h"

AudiothecaSidecarEditor::AudiothecaSidecarEditor(AudiothecaSidecarProcessor& p)
  : juce::AudioProcessorEditor(&p), processor(p) {
  setSize(420, 120);
  statusLabel.setText("Audiotheca Sidecar — connect to http://127.0.0.1:8787", juce::dontSendNotification);
  statusLabel.setJustificationType(juce::Justification::centred);
  addAndMakeVisible(statusLabel);
}

void AudiothecaSidecarEditor::paint(juce::Graphics& g) {
  g.fillAll(juce::Colour(0xff1a1a2e));
}

void AudiothecaSidecarEditor::resized() {
  statusLabel.setBounds(getLocalBounds().reduced(12));
}
""",
    )


def _build_script_content(plugin_dir: Path) -> str:
    if os.name == "nt":
        return f"""# AudiothecaSidecar VST3/AU build (Windows)
$ErrorActionPreference = "Stop"
$Root = "{plugin_dir.as_posix()}"
Set-Location $Root
if (-not (Test-Path build)) {{ New-Item -ItemType Directory -Path build | Out-Null }}
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
Write-Host "Artifacts under build/AudiothecaSidecar_artefacts/"
"""
    return f"""#!/usr/bin/env bash
set -euo pipefail
cd "{plugin_dir.as_posix()}"
mkdir -p build
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
echo "Artifacts under build/AudiothecaSidecar_artefacts/"
"""


def _install_instructions(plugin_dir: Path) -> list[str]:
    return [
        "Prerequisites: CMake 3.22+, C++17 compiler, JUCE 7.0.9 (set JUCE_PATH or auto-fetch).",
        f"1. Blueprint exported to: {plugin_dir}",
        f"2. Run build script: {plugin_dir / ('build.ps1' if os.name == 'nt' else 'build.sh')}",
        "   Repo template (no export): scripts/build_daw_sidecar.ps1 (Windows) or scripts/build_daw_sidecar.sh",
        "3. Copy VST3 from build/AudiothecaSidecar_artefacts/VST3/ to your DAW plugin folder.",
        "   Windows: %COMMONPROGRAMFILES%/VST3/  ·  macOS: ~/Library/Audio/Plug-Ins/VST3/",
        "4. Rescan plugins in your DAW; sidecar connects to Audiotheca API on port 8787.",
    ]


BUILD_TIMEOUT_SEC = 45 * 60


def install_daw_sidecar(
    *,
    home: str | Path | None = None,
    dry_run: bool = True,
    copy_to_system: bool = True,
    api_base: str | None = None,
    timeout_sec: int = BUILD_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Export blueprint (if needed) and run CMake build for the DAW sidecar plugin."""
    import subprocess

    blueprint = write_blueprint(home=home, api_base=api_base)
    plugin_dir = Path(blueprint["plugin_dir"])
    build_script = Path(blueprint["build_script"])
    log: list[str] = []

    if not shutil.which("cmake"):
        return {
            **blueprint,
            "ok": False,
            "built": False,
            "error": "cmake not found on PATH — install CMake 3.22+",
            "log": log,
        }

    if dry_run:
        log.append(f"Would run: {build_script} (timeout {timeout_sec}s)")
        if copy_to_system:
            log.append("Would copy VST3 (and AU on macOS) to system plugin folders after build")
        return {**blueprint, "ok": True, "built": False, "dry_run": True, "log": log}

    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(build_script)],
                cwd=str(plugin_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_sec,
            )
        else:
            proc = subprocess.run(
                [str(build_script)],
                cwd=str(plugin_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_sec,
            )
        if proc.stdout:
            log.extend(proc.stdout.splitlines())
        if proc.stderr:
            log.extend(proc.stderr.splitlines())
        if proc.returncode != 0:
            return {
                **blueprint,
                "ok": False,
                "built": False,
                "error": f"build failed (exit {proc.returncode})",
                "log": log,
            }
    except subprocess.TimeoutExpired:
        return {
            **blueprint,
            "ok": False,
            "built": False,
            "error": f"build timed out after {timeout_sec}s",
            "log": log,
        }
    except OSError as exc:
        return {**blueprint, "ok": False, "built": False, "error": str(exc), "log": log}

    artefacts = plugin_dir / "build" / "AudiothecaSidecar_artefacts"
    vst3_src = artefacts / "VST3"
    au_src = artefacts / "AU"
    installed_to = ""
    installed_au = ""
    if copy_to_system and vst3_src.is_dir():
        if os.name == "nt":
            common = os.environ.get("COMMONPROGRAMFILES", r"C:\Program Files\Common Files")
            dest_root = Path(common) / "VST3"
        else:
            dest_root = Path.home() / "Library" / "Audio" / "Plug-Ins" / "VST3"
        dest_root.mkdir(parents=True, exist_ok=True)
        for bundle in vst3_src.glob("*.vst3"):
            target = dest_root / bundle.name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(bundle, target)
            installed_to = str(target)
            log.append(f"Installed {bundle.name} -> {target}")

    if copy_to_system and sys.platform == "darwin" and au_src.is_dir():
        au_dest = Path.home() / "Library" / "Audio" / "Plug-Ins" / "Components"
        au_dest.mkdir(parents=True, exist_ok=True)
        for bundle in list(au_src.glob("*.component")) + list(au_src.glob("*.au")):
            target = au_dest / bundle.name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(bundle, target)
            installed_au = str(target)
            log.append(f"Installed AU {bundle.name} -> {target}")

    manifest = plugin_manifest(api_base=api_base)
    manifest["built"] = True
    manifest_path = plugin_dir / "plugin_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        **blueprint,
        "ok": True,
        "built": True,
        "artefacts_dir": str(artefacts),
        "installed_vst3": installed_to,
        "installed_au": installed_au,
        "log": log,
    }

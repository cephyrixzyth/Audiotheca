cmake_minimum_required(VERSION 3.22)
project(AudiothecaSidecar VERSION 0.1.0)

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

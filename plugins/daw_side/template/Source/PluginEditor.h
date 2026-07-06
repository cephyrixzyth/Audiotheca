#pragma once
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

#include "PluginEditor.h"

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

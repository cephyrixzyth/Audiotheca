#include "PluginProcessor.h"
#include "PluginEditor.h"

AudiothecaSidecarProcessor::AudiothecaSidecarProcessor()
  : juce::AudioProcessor(BusesProperties().withOutput("Output", juce::AudioChannelSet::stereo(), true)) {}

juce::AudioProcessorEditor* AudiothecaSidecarProcessor::createEditor() {
  return new AudiothecaSidecarEditor(*this);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() {
  return new AudiothecaSidecarProcessor();
}

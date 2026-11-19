export function waveformPeaks(
  audio: AudioBuffer,
  count: number,
  start = 0,
  end = audio.duration,
) {
  const samples = audio
    .getChannelData(0)
    .subarray(
      Math.floor(start * audio.sampleRate),
      Math.ceil(end * audio.sampleRate),
    );
  const bins = Math.min(count, samples.length);
  const width = samples.length / bins;
  const peaks = new Float32Array(bins);
  for (let i = 0; i < bins; i++) {
    const begin = Math.floor(i * width),
      end = Math.min(samples.length, Math.floor((i + 1) * width));
    for (let j = begin; j < end; j += Math.max(1, Math.floor(width / 48))) {
      peaks[i] = Math.max(peaks[i], Math.abs(samples[j]));
    }
  }
  return peaks;
}

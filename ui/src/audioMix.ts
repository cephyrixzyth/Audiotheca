export type MixChannel = "stereo" | "mono" | "left" | "right";

/** Gains ordered as left→left, right→left, left→right, right→right. */
export function channelMixGains(channel: MixChannel): readonly [number, number, number, number] {
  switch (channel) {
    case "mono":
      return [0.5, 0.5, 0.5, 0.5];
    case "left":
      return [1, 0, 1, 0];
    case "right":
      return [0, 1, 0, 1];
    default:
      return [1, 0, 0, 1];
  }
}

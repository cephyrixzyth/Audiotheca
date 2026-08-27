export type NearLane = "acoustic" | "fuzzy";

export function nearLaneTitle(lane: NearLane): string {
  switch (lane) {
    case "acoustic":
      return "Acoustic near-duplicates";
    case "fuzzy":
      return "Fuzzy pack near-duplicates";
    default: {
      const _exhaustive: never = lane;
      return _exhaustive;
    }
  }
}

export function nearLaneHint(lane: NearLane): string {
  switch (lane) {
    case "acoustic":
      return "Chromaprint exact/near matches across formats (Sononym-style lane). Heuristic fallback when fpcalc is unavailable.";
    case "fuzzy":
      return "ssdeep/TLSH/rolling fuzzy similarity for installer and pack files.";
    default: {
      const _exhaustive: never = lane;
      return _exhaustive;
    }
  }
}

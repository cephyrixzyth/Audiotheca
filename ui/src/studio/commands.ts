import { editTrack } from "./session";
import type { Project, Track } from "./session";
export type Edit =
  | "mute"
  | "solo"
  | "gainDown"
  | "gainUp"
  | "inBack"
  | "inForward"
  | "outBack"
  | "outForward"
  | "earlier"
  | "later";
export type Command =
  | Edit
  | "play"
  | "rewind"
  | "previous"
  | "next"
  | "undo"
  | "redo"
  | "export"
  | "exit"
  | "saveProject"
  | "findAudio"
  | "prevFile"
  | "nextFile"
  | "addFile";
export function adjust(project: Project, track: Track, edit: Edit): Project {
  const changes: Record<Edit, Partial<Track>> = {
    mute: { mute: !track.mute },
    solo: { solo: !track.solo },
    gainDown: { volume: track.volume - 0.05 },
    gainUp: { volume: track.volume + 0.05 },
    inBack: { start: track.start - 0.125 },
    inForward: { start: track.start + 0.125 },
    outBack: { end: track.end - 0.125 },
    outForward: { end: track.end + 0.125 },
    earlier: { offset: track.offset - 0.125 },
    later: { offset: track.offset + 0.125 },
  };
  return editTrack(project, track.id, changes[edit]);
}

import type { Project } from "./session";

type SavedProject = { revision: number; project: Project };
export class StudioStore {
  revision = 0;
  private queue: Promise<unknown> = Promise.resolve();
  private constructor(private db: IDBDatabase) {}

  static async open(): Promise<StudioStore> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("audiotheca.spatial-studio", 1);
      request.onupgradeneeded = () => {
        request.result.createObjectStore("sessions");
        request.result.createObjectStore("audio");
      };
      request.onsuccess = () => resolve(new StudioStore(request.result));
      request.onerror = () => reject(request.error);
    });
  }

  async read(): Promise<{ project?: Project; assets: Map<string, Blob> }> {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction(["sessions", "audio"]);
      const read = transaction.objectStore("sessions").get("current");
      const assets = new Map<string, Blob>();
      let saved: SavedProject | undefined;
      let error: Error | undefined;
      read.onsuccess = () => {
        saved = read.result;
        if (!saved) return;
        if (saved.project.version !== 1) {
          error = new Error("This session needs a newer Audiotheca.");
          transaction.abort();
          return;
        }
        this.revision = saved.revision;
        for (const t of saved.project.tracks) {
          if (t.voice) continue;
          const asset = transaction.objectStore("audio").get(t.id);
          asset.onsuccess = () => {
            if (asset.result instanceof Blob) assets.set(t.id, asset.result);
            else {
              error = new Error("Saved audio is missing for " + t.name);
              transaction.abort();
            }
          };
        }
      };
      transaction.oncomplete = () =>
        resolve({ project: saved?.project, assets });
      transaction.onabort = () => reject(error ?? transaction.error);
    });
  }

  save(project: Project, assets: Map<string, Blob>) {
    const persist = () =>
      new Promise<void>((resolve, reject) => {
        const transaction = this.db.transaction(
          ["sessions", "audio"],
          "readwrite",
        );
        const sessions = transaction.objectStore("sessions");
        const audio = transaction.objectStore("audio");
        const current = sessions.get("current");
        const nextRevision = this.revision + 1;
        let error: Error | undefined;
        current.onsuccess = () => {
          const previous = current.result as SavedProject | undefined;
          if ((previous?.revision ?? 0) !== this.revision) {
            error = new Error(
              "Another window changed this session. Reopen the studio before saving again.",
            );
            transaction.abort();
            return;
          }
          const previousIds = new Set(
            previous?.project.tracks.map((t) => t.id),
          );
          for (const t of project.tracks) {
            if (t.voice || previousIds.has(t.id)) continue;
            const blob = assets.get(t.id);
            if (!blob) {
              error = new Error("Missing source for " + t.name);
              transaction.abort();
              return;
            }
            audio.put(blob, t.id);
          }
          for (const id of previousIds)
            if (!project.tracks.some((t) => t.id === id)) audio.delete(id);
          sessions.put({ revision: nextRevision, project }, "current");
        };
        transaction.oncomplete = () => {
          this.revision = nextRevision;
          resolve();
        };
        transaction.onabort = () =>
          reject(
            error ??
              transaction.error ??
              new Error("Could not save this session."),
          );
      });
    const pending = this.queue.then(persist, persist);
    this.queue = pending;
    return pending;
  }

  close() {
    void this.queue.catch(() => undefined).then(() => this.db.close());
  }
}

import { createReadStream, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

const assets = join(dirname(fileURLToPath(import.meta.url)), "../docs/assets");
const formats = {
  screenshots: [".png", "image/png"],
  gifs: [".gif", "image/gif"],
  videos: [".mp4", "video/mp4"],
};

function inventory() {
  const files = new Map<string, { path: string; mime: string }>();
  for (const [folder, [extension, mime]] of Object.entries(formats)) {
    for (const name of readdirSync(join(assets, folder))) {
      if (name.endsWith(extension))
        files.set(name, { path: join(assets, folder, name), mime });
    }
  }
  return files;
}

/** The help reader, desktop bundle and documentation all use the same media bytes. */
export function helpMedia(): Plugin {
  return {
    name: "audiotheca-help-media",
    configureServer(server) {
      server.middlewares.use("/help", (req, res, next) => {
        const name = req.url?.slice(1).split("?")[0];
        const file = name && inventory().get(name);
        if (!file || (req.method !== "GET" && req.method !== "HEAD"))
          return next();
        const size = statSync(file.path).size;
        let start = 0,
          end = size - 1;
        res.setHeader("Content-Type", file.mime);
        res.setHeader("Accept-Ranges", "bytes");
        res.setHeader("Cache-Control", "no-cache");
        if (req.headers.range) {
          const request = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
          if (request && (request[1] || request[2])) {
            start = request[1]
              ? Number(request[1])
              : Math.max(0, size - Number(request[2]));
            end =
              request[1] && request[2]
                ? Math.min(end, Number(request[2]))
                : end;
          }
          if (
            !request ||
            (!request[1] && !request[2]) ||
            start > end ||
            start >= size
          ) {
            res.writeHead(416, { "Content-Range": `bytes */${size}` });
            res.end();
            return;
          }
          res.statusCode = 206;
          res.setHeader("Content-Range", `bytes ${start}-${end}/${size}`);
        }
        res.setHeader("Content-Length", end - start + 1);
        if (req.method === "HEAD" || size === 0) res.end();
        else
          createReadStream(file.path, { start, end })
            .on("error", next)
            .pipe(res);
      });
    },
    generateBundle() {
      for (const [name, { path }] of inventory()) {
        this.emitFile({
          type: "asset",
          fileName: "help/" + name,
          source: readFileSync(path),
        });
      }
    },
  };
}

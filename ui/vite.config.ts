import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { helpMedia } from "./helpMedia";

const host = process.env.TAURI_DEV_HOST;

const apiPort = process.env.VITE_API_PORT || "8787";
const apiTarget = `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  plugins: [react(), helpMedia()],
  clearScreen: false,
  cacheDir: process.env.AUDIOTHECA_VITE_CACHE,
  envPrefix: ["VITE_", "TAURI_"],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
  server: {
    port: 5173,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    target: process.env.TAURI_PLATFORM === "windows" ? "chrome105" : "safari13",
    // Vite 8 minifies with oxc (Rust) by default; "esbuild" is no longer bundled
    minify: !process.env.TAURI_DEBUG,
    sourcemap: !!process.env.TAURI_DEBUG,
    // The Spatial Studio room (three.js) is already a lazy chunk loaded only when
    // the Studio opens; allow it without a warning on every build.
    chunkSizeWarningLimit: 600,
  },
});

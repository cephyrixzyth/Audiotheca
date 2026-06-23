import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  envPrefix: ["VITE_", "TAURI_"],
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
        target: "http://127.0.0.1:8787",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    target: process.env.TAURI_PLATFORM === "windows" ? "chrome105" : "safari13",
    minify: process.env.TAURI_DEBUG ? false : "esbuild",
    sourcemap: !!process.env.TAURI_DEBUG,
  },
});

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Everything is bundled and served by nginx from the same origin: the strict CSP
// (default-src 'self') means no CDN, no inline script, no remote font.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    assetsDir: "assets",
    modulePreload: { polyfill: false },
  },
  server: {
    // `npm run dev` against a local `docker compose up` (nginx on port 80).
    proxy: { "/api": "http://localhost", "/media": "http://localhost" },
  },
});

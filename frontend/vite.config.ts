import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend is served by the app itself (frontend/dist under FastAPI's `/`).
// No dev-server proxy needed for the build; `npm run dev` proxies /api to
// the app running on 8816 so `npm run dev` works standalone too.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8816",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});

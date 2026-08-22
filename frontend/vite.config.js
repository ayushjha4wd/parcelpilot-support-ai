import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes straight into the backend's static dir so FastAPI serves it.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../backend/app/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});

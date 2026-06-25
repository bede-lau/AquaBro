import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api → backend so dev uses same-origin (SSE + MJPEG just work).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});

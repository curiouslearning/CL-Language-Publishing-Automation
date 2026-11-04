import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev`: the page on http://localhost:5173 with live reload; the API is ../server.py on :8080.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://localhost:8080" },
  },
  build: { outDir: "dist", emptyOutDir: true },
});

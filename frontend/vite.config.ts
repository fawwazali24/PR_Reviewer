import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend already allows http://localhost:5173 via CORS_ORIGINS, so the
// dashboard talks to it directly. Override the target with VITE_API_BASE.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
  },
});

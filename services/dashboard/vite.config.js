import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server is bound to 0.0.0.0:5173 so it works both locally and inside the Docker container.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
  },
});

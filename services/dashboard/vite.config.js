import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server is bound to 0.0.0.0:5173 so it works both locally and inside the Docker container.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    // Docker bind-mounts on Windows/macOS don't deliver inotify events, so poll for changes.
    // This lets edits to src/ hot-reload in the container without an image rebuild.
    watch: { usePolling: true, interval: 300 },
  },
});

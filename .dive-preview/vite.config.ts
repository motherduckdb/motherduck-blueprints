import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Production Dives load d3, lucide-react, recharts, and React at the versions pinned in
      // package.json; Dives import nothing else.
      "@motherduck/react-sql-query": path.resolve(__dirname, "src/md-sdk.tsx"),
      "d3": path.resolve(__dirname, "node_modules/d3"),
      "recharts": path.resolve(__dirname, "node_modules/recharts"),
      "lucide-react": path.resolve(__dirname, "node_modules/lucide-react"),
      "react": path.resolve(__dirname, "node_modules/react"),
      "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
    },
  },
  server: {
    // Production Dives are not cross-origin isolated, so the preview sends no COOP/COEP headers.
    fs: {
      allow: [path.resolve(__dirname, "..")],
    },
  },
});

import { defineConfig } from "vite";
import type { Plugin } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Packages that back the SDK runtime but that production Dives cannot import.
const RUNTIME_ONLY = ["@tanstack/query-core"];
const SDK_RUNTIME = path.resolve(import.meta.dirname, "src/md-sdk-runtime.tsx");

function runtimeOnlyImports(): Plugin {
  return {
    name: "md-runtime-only-imports",
    enforce: "pre",
    resolveId(source, importer) {
      const runtimeOnly = RUNTIME_ONLY.some((name) => source === name || source.startsWith(`${name}/`));
      if (runtimeOnly && importer && path.resolve(importer.split("?")[0]) !== SDK_RUNTIME) {
        this.error(
          `Dives cannot import "${source}". Production Dives load only @motherduck/react-sql-query, ` +
            "React, d3, lucide-react, and recharts.",
        );
      }
      return null;
    },
  };
}

export default defineConfig({
  plugins: [runtimeOnlyImports(), react()],
  resolve: {
    alias: {
      // Production Dives load d3, lucide-react, recharts, and React at the versions pinned in
      // package.json; Dives import nothing else.
      "@motherduck/react-sql-query": path.resolve(import.meta.dirname, "src/md-sdk.tsx"),
      "d3": path.resolve(import.meta.dirname, "node_modules/d3"),
      "recharts": path.resolve(import.meta.dirname, "node_modules/recharts"),
      "lucide-react": path.resolve(import.meta.dirname, "node_modules/lucide-react"),
      "react": path.resolve(import.meta.dirname, "node_modules/react"),
      "react-dom": path.resolve(import.meta.dirname, "node_modules/react-dom"),
    },
  },
  server: {
    // Production Dives are not cross-origin isolated, so the preview sends no COOP/COEP headers.
    fs: {
      allow: [path.resolve(import.meta.dirname, "..")],
    },
  },
});

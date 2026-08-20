import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "../../frontend/node_modules/vite/dist/node/index.js";
// @ts-expect-error The harness intentionally loads the frontend's pinned plugin runtime.
import react from "../../frontend/node_modules/@vitejs/plugin-react-swc/index.mjs";
import tailwindcss from "../../frontend/node_modules/@tailwindcss/vite/dist/index.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const workspace = path.resolve(here, "../..");
const frontend = path.join(workspace, "frontend");
const frontendModules = path.join(frontend, "node_modules");

export default defineConfig({
  root: here,
  publicDir: path.join(frontend, "public"),
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: "@", replacement: path.join(frontend, "src") },
      { find: "react", replacement: path.join(frontendModules, "react") },
      { find: "react-dom", replacement: path.join(frontendModules, "react-dom") },
    ],
  },
  server: {
    host: "127.0.0.1",
    port: 4179,
    strictPort: true,
    fs: {
      allow: [workspace],
    },
  },
});

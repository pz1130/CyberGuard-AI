import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  root: path.resolve(__dirname, "renderer"),
  plugins: [react()],
  server: {
    // 必须显式绑 IPv4：electron/main.cjs 与 index.html 的 CSP 都写死
    // http://127.0.0.1:5173，而 vite 默认按 localhost 解析——这台机器上
    // 先解析到 ::1，于是壳去连 127.0.0.1 直接 ERR_CONNECTION_REFUSED。
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: path.resolve(__dirname, "dist-renderer"),
    emptyOutDir: true,
  },
});

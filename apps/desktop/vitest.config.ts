import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    root: path.resolve(__dirname),
    environment: "jsdom",
    include: ["renderer/__tests__/**/*.test.{ts,tsx}"],
    setupFiles: ["renderer/__tests__/setup.ts"],
    css: false,
  },
});

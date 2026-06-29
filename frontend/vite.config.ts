import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/** 统一后端（8391）：学伴系统 + LangGraph AI */
const API_TARGET = "http://127.0.0.1:8391";

/** AI 路由在合并后端上不带 /api 前缀，需 rewrite */
const eduRewriteProxy = {
  target: API_TARGET,
  changeOrigin: true,
  rewrite: (path: string) => path.replace(/^\/api/, ""),
  timeout: 30 * 60 * 1000,
  proxyTimeout: 30 * 60 * 1000,
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api/edu-health": {
        ...eduRewriteProxy,
        rewrite: () => "/health",
      },
      "/api/analyze": eduRewriteProxy,
      "/api/group-evaluation": eduRewriteProxy,
      "/api/section-evaluation": eduRewriteProxy,
      "/api/sessions": eduRewriteProxy,
      "/api/sessions/": eduRewriteProxy,
      "/api/section-graphrag": eduRewriteProxy,
      "/uploads": {
        target: API_TARGET,
        changeOrigin: true,
      },
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
});

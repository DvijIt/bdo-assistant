import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Статика в out/, яку роздає FastAPI; серверних можливостей Next немає.
  output: "export",
  // /inventory → out/inventory/index.html, щоб StaticFiles(html=True) знаходив сторінки.
  trailingSlash: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;

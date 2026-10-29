import type { NextConfig } from "next";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const nextConfig: NextConfig = {
  output: "standalone",
  // без этого Turbopack может взять корнем каталог выше (чужой package-lock) и собрать пустой app
  turbopack: { root: dirname(fileURLToPath(import.meta.url)) },
  // вкладка не должна сидеть на старой сборке после деплоя (BUG-004): документы
  // всегда переспрашиваются у сервера, хешированная статика — бессрочный кэш
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [{ key: "Cache-Control", value: "no-cache" }],
      },
      {
        source: "/_next/static/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
    ];
  },
};

export default nextConfig;

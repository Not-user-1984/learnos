import type { NextConfig } from "next";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const nextConfig: NextConfig = {
  output: "standalone",
  // без этого Turbopack может взять корнем каталог выше (чужой package-lock) и собрать пустой app
  turbopack: { root: dirname(fileURLToPath(import.meta.url)) },
  // вкладка не должна сидеть на старой сборке после деплоя (BUG-004): документы
  // всегда переспрашиваются у сервера; хешированная статика — бессрочный кэш,
  // но только в проде: в dev свой Cache-Control для статики, кастомный его ломает
  // (варнинг «Custom Cache-Control headers detected», ревью B-011)
  async headers() {
    const headers = [
      {
        source: "/:path*",
        headers: [{ key: "Cache-Control", value: "no-cache" }],
      },
    ];
    if (process.env.NODE_ENV === "production") {
      headers.push({
        source: "/_next/static/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      });
    }
    return headers;
  },
};

export default nextConfig;

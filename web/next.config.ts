import type { NextConfig } from "next";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const nextConfig: NextConfig = {
  output: "standalone",
  // без этого Turbopack может взять корнем каталог выше (чужой package-lock) и собрать пустой app
  turbopack: { root: dirname(fileURLToPath(import.meta.url)) },
};

export default nextConfig;

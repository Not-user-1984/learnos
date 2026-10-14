import type { MetadataRoute } from "next";

/** Web App Manifest: установка как приложение + share_target («Поделиться» с телефона). */

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "LearnOS — персональная система обучения",
    short_name: "LearnOS",
    description: "Сессии с агентом, база знаний, библиотека и курсы",
    start_url: "/chat",
    display: "standalone",
    background_color: "#09090b",
    theme_color: "#09090b",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    share_target: {
      action: "/share",
      method: "GET",
      params: { title: "title", text: "text", url: "url" },
    },
  };
}

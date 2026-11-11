/** YouTube-хелперы (B-009: единая точка вместо трёх копий в UI). */

/** Это ссылка YouTube? (watch / youtu.be / shorts / live) */
export function isYoutubeUrl(url: string): boolean {
  return /youtu\.?be/i.test(url);
}

/** Заголовок видео через oembed (null — сервис не ответил). */
export async function fetchYoutubeTitle(url: string): Promise<string | null> {
  try {
    const resp = await fetch(
      `https://www.youtube.com/oembed?url=${encodeURIComponent(url)}&format=json`,
    );
    if (!resp.ok) return null;
    const data = (await resp.json()) as { title?: string };
    return data.title ?? null;
  } catch {
    return null;
  }
}

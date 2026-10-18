"use client";

/** SSE-клиент чата: fetch + ReadableStream (EventSource не умеет POST). */

import type { SseEvent } from "@/lib/types";

/** Прочитать SSE-поток ответа агента; onEvent вызывается на каждое событие.
 *  research=true — сообщение запускает ресёрч-цикл (директива уйдёт агенту, в чате видна только тема). */
export async function streamChat(
  conversationUid: string,
  content: string,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal,
  research = false,
): Promise<void> {
  // относительный путь: Next проксирует /api на ядро
  const res = await fetch(`/api/conversations/${conversationUid}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, research }),
    signal,
  });
  if (!res.ok || !res.body) {
    onEvent({ event: "error", data: { error: "http", message: `HTTP ${res.status}` } });
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    // события разделены \n\n; парсим event:/data: пары
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const lines = chunk.split("\n");
      const ev: { event: string; data: string } = { event: "message", data: "" };
      for (const line of lines) {
        if (line.startsWith("event: ")) ev.event = line.slice(7).trim();
        else if (line.startsWith("data: ")) ev.data += line.slice(6);
      }
      if (ev.data) {
        try {
          onEvent({ event: ev.event, data: JSON.parse(ev.data) } as SseEvent);
        } catch {
          // незавершённый JSON — пропускаем
        }
      }
    }
  }
}

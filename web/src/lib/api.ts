/** API-клиент LearnOS: все запросы к ядру идут через этот модуль. */

export const API_URL = process.env.LEARNOS_API_URL ?? "http://localhost:8765";

/** В браузере — относительный путь (Next проксирует /api на ядро), на сервере — прямой URL. */
const base = (): string => (typeof window === "undefined" ? API_URL : "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
  }
}

/** GET-запрос, возвращает JSON (серверные компоненты — no-store). */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base()}/api${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    try {
      const body = (await res.json()) as { message?: string; error?: string };
      throw new ApiError(res.status, body.message ?? `${res.status} ${res.statusText}`, body.error);
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw new ApiError(res.status, `${res.status} ${res.statusText}: ${path}`);
    }
  }
  return (await res.json()) as T;
}

/** POST с JSON-телом. */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

/** PATCH с JSON-телом. */
export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

/** DELETE. */
export async function apiDelete<T>(path: string): Promise<T> {
  return api<T>(path, { method: "DELETE" });
}

/** Загрузка файла (multipart). */
export async function apiUpload<T>(path: string, file: File, extra?: Record<string, string>): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  if (extra?.title) form.append("title", extra.title);
  const res = await fetch(`${base()}/api${path}`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, `upload failed: ${res.status}`);
  return (await res.json()) as T;
}

export const apiUrl = API_URL;

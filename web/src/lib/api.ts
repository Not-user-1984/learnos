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

/** Заголовки серверных запросов: bearer-токен из env (в браузере его нет — там прокси). */
const authHeaders = (): Record<string, string> => {
  const token = typeof window === "undefined" ? process.env.LEARNOS_API_TOKEN : "";
  return token ? { authorization: `Bearer ${token}` } : {};
};

/** GET-запрос, возвращает JSON (серверные компоненты — no-store). */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base()}/api${path}`, {
    cache: "no-store",
    ...init,
    headers: { ...authHeaders(), ...(init?.headers ?? {}) },
  });
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
  const res = await fetch(`${base()}/api${path}`, {
    method: "POST",
    body: form,
    headers: authHeaders(),
  });
  if (!res.ok) {
    // текст ошибки сервера раньше терялся (R-25)
    let message = `upload failed: ${res.status}`;
    try {
      const body = (await res.json()) as { message?: string };
      if (body.message) message = body.message;
    } catch {
      /* тело не JSON — оставляем статус */
    }
    throw new ApiError(res.status, message);
  }
  return (await res.json()) as T;
}


/** Добавить материал по ссылке одним действием (R-25: единая точка, не 4 копии):
 *  сервер сам определяет тип (видео/PDF/статья), качает и ставит job обработки. */
export async function addSourceFromUrl(url: string): Promise<{ uid: string; kind: string; title: string; job_id: number | null }> {
  return apiPost("/sources/from-url", { url });
}

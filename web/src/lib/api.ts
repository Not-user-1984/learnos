const API = process.env.LEARNOS_API_URL ?? "http://localhost:8765";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}: ${path}`);
  return (await res.json()) as T;
}

export const apiUrl = API;

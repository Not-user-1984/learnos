/** Runtime-прокси /api/* → ядро LearnOS (SSE стримится как есть). */

const BACKEND = () => process.env.LEARNOS_API_URL ?? "http://localhost:8765";

async function proxy(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const target = `${BACKEND()}/api/${url.pathname.replace(/^\/api\//, "")}${url.search}`;
  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");
  // R-07: токен живёт на сервере (env), браузер его не видит
  const token = process.env.LEARNOS_API_TOKEN;
  if (token) headers.set("authorization", `Bearer ${token}`);
  const init: RequestInit = {
    method: req.method,
    headers,
    redirect: "manual",
  };
  if (!["GET", "HEAD"].includes(req.method)) {
    init.body = await req.arrayBuffer();
  }
  const res = await fetch(target, init);
  const outHeaders = new Headers(res.headers);
  outHeaders.delete("content-encoding");
  outHeaders.delete("transfer-encoding");
  return new Response(res.body, { status: res.status, headers: outHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;

export const dynamic = "force-dynamic";

import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

const API = process.env.API_URL ?? "http://127.0.0.1:8000";

const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
  "content-length", "content-encoding",
]);

async function forward(req: NextRequest, path: string[]): Promise<Response> {
  const url = new URL(req.url);
  const target = `${API}/api/${path.join("/")}${url.search}`;
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!["host", "connection", "content-length"].includes(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  headers.set("accept-encoding", "identity");

  let body: ArrayBuffer | undefined;
  if (!["GET", "HEAD"].includes(req.method)) {
    body = await req.arrayBuffer();
  }

  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
    });
    const out = new Headers();
    upstream.headers.forEach((value, key) => {
      if (!HOP_BY_HOP.has(key.toLowerCase())) out.set(key, value);
    });
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch (error) {
    return Response.json(
      { detail: `Engine gateway unreachable: ${(error as Error).message}` },
      { status: 502 },
    );
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}

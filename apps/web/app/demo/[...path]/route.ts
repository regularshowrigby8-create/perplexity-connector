import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const API = process.env.API_URL ?? "http://127.0.0.1:8000";

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const upstream = await fetch(`${API}/demo/${path.join("/")}`, { cache: "no-store" });
  const headers = new Headers();
  const type = upstream.headers.get("content-type");
  if (type) headers.set("content-type", type);
  return new Response(upstream.body, { status: upstream.status, headers });
}

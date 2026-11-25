import { readFile } from "node:fs/promises";
import path from "node:path";
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Serves the repository's single-file launcher (index.html) from the web app,
 * so the page is reachable both statically and at /launch.
 */
export async function GET(request: NextRequest): Promise<Response> {
  const candidates = [
    path.join(process.cwd(), "index.html"),
    path.join(process.cwd(), "..", "..", "index.html"),
    path.join(process.cwd(), "public", "index.html"),
  ];
  for (const candidate of candidates) {
    try {
      const html = await readFile(candidate, "utf8");
      const download = request.nextUrl.searchParams.has("download");
      const headers: Record<string, string> = {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
      };
      if (download) {
        headers["content-disposition"] = 'attachment; filename="nighthawk-index.html"';
      }
      return new Response(html, { headers });
    } catch {
      continue;
    }
  }
  return new Response(
    "<!doctype html><meta charset=utf-8><title>Launcher missing</title>" +
      "<body style='font-family:system-ui;background:#06070a;color:#e9eef6;padding:40px'>" +
      "<h1>index.html not found</h1><p>Run <code>./run.sh</code> from the repository root, " +
      "or open <code>index.html</code> directly.</p>",
    { status: 404, headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

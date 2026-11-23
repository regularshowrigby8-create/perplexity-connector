import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/nav";

export const metadata: Metadata = {
  title: "Nighthawk — buried files & opportunities engine",
  description:
    "A fusion crawler with 60+ remote engines, an 86-engine crawl arsenal and a local vault. Finds the files, calls and portals mainstream search never shows.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Nav />
        {children}
        <footer className="footer">
          <div className="wrap footer-in">
            <span className="mono">NIGHTHAWK v1.0</span>
            <span className="dim">·</span>
            <span>{66} remote engines · {86} arsenal engines · {54} portals</span>
            <span className="dim">·</span>
            <a href="/api/docs" target="_blank" rel="noreferrer">API</a>
            <a href="/arsenal">Engine status</a>
            <span style={{ marginLeft: "auto" }} className="mono">
              crawl responsibly — you own the targets you point it at
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}

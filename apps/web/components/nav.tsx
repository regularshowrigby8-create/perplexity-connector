"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const LINKS = [
  { href: "/", label: "Hunt" },
  { href: "/crawl", label: "Crawl" },
  { href: "/arsenal", label: "Arsenal" },
  { href: "/vault", label: "Vault" },
  { href: "/hunts", label: "Watchers" },
];

export function Nav() {
  const path = usePathname();
  const [counts, setCounts] = useState({ remote: 66, arsenal: 86 });

  useEffect(() => {
    fetch("/api/v1/health")
      .then((r) => r.json())
      .then((d) =>
        setCounts({
          remote: (d.engines_remote ?? 66) + 1,
          arsenal: d.engines_arsenal ?? 86,
        }),
      )
      .catch(() => undefined);
  }, []);

  return (
    <header className="nav">
      <div className="wrap nav-in">
        <Link href="/" className="brand">
          <span className="brand-mark">N</span>
          <span>
            Nighthawk
            <small>buried web engine</small>
          </span>
        </Link>
        <nav className="nav-links">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              data-active={path === link.href || (link.href !== "/" && path.startsWith(link.href))}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="nav-right">
          <span className="count-chip">
            <b>{counts.remote}</b> remote · <b>{counts.arsenal}</b> arsenal
          </span>
        </div>
      </div>
    </header>
  );
}

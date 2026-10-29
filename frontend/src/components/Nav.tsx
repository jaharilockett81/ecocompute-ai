"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApi } from "@/lib/useApi";
import Logo from "./Logo";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/challenge", label: "Challenge" },
  { href: "/playground", label: "Playground" },
  { href: "/router", label: "Router" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/impact", label: "Impact" },
  { href: "/history", label: "History" },
  { href: "/methodology", label: "Methodology" },
];

export default function Nav() {
  const path = usePathname();
  const { data, error } = useApi<any>("/health", { poll: true, intervalMs: 30000 });
  const status = error ? "offline" : data ? (data.sample_data ? "mock" : "live") : "…";
  const dot = error ? "var(--bad)" : data?.sample_data ? "var(--warn)" : data ? "var(--accent)" : "var(--muted)";
  const active = (href: string) => (href === "/" ? path === "/" : path?.startsWith(href));

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-[rgba(5,12,8,0.72)] backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 md:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-2">
          <Logo />
          <span className="text-lg font-medium tracking-tight">
            Eco<span className="text-accent">Compute</span>
          </span>
        </Link>
        <nav className="hidden flex-1 items-center gap-1 lg:flex">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded-full px-3 py-1.5 text-sm transition-colors ${active(l.href) ? "bg-accent-soft text-accent" : "text-muted hover:text-fg"}`}
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <span className="hidden items-center gap-2 rounded-full border border-border px-3 py-1 text-xs text-muted sm:flex" title="Backend provider status">
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: dot, boxShadow: `0 0 8px ${dot}` }} />
            {status === "live" ? "Nebius live" : `backend ${status}`}
          </span>
          <Link href="/settings" className={`rounded-full px-3 py-1.5 text-sm ${active("/settings") ? "text-accent" : "text-muted hover:text-fg"}`}>
            Settings
          </Link>
        </div>
      </div>
      <nav className="flex gap-1 overflow-x-auto px-4 pb-2 lg:hidden">
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`whitespace-nowrap rounded-full px-3 py-1 text-sm ${active(l.href) ? "bg-accent-soft text-accent" : "text-muted"}`}
          >
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

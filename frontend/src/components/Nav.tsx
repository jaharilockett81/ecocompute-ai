"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApi } from "@/lib/useApi";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/challenge", label: "The Challenge" },
  { href: "/playground", label: "Playground" },
  { href: "/router", label: "Router" },
  { href: "/benchmarks", label: "Benchmark Lab" },
  { href: "/impact", label: "Impact" },
  { href: "/history", label: "History" },
  { href: "/methodology", label: "Methodology" },
  { href: "/settings", label: "Settings" },
];

export default function Nav() {
  const path = usePathname();
  const { data, error } = useApi<any>("/health", { poll: true, intervalMs: 30000 });
  const status = error ? "offline" : data ? (data.sample_data ? "mock" : "nebius") : "…";
  const dot = error ? "var(--bad)" : data?.sample_data ? "var(--warn)" : data ? "var(--accent)" : "var(--muted)";
  return (
    <aside className="border-b border-border bg-panel md:fixed md:inset-y-0 md:left-0 md:w-56 md:border-b-0 md:border-r">
      <div className="flex items-center justify-between px-4 py-4 md:block">
        <Link href="/" className="block">
          <div className="text-lg font-semibold tracking-tight">
            <span className="text-accent">Eco</span>Compute AI
          </div>
          <div className="text-xs text-muted">Quality-aware Nemotron routing</div>
        </Link>
        <div className="flex items-center gap-1.5 text-xs text-muted md:mt-3" title="Backend provider status">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: dot }} />
          backend: {status}
        </div>
      </div>
      <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
        {LINKS.map((l) => {
          const active = l.href === "/" ? path === "/" : path?.startsWith(l.href);
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${active ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-panel-2 hover:text-fg"}`}
            >
              {l.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

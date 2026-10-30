"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/useApi";
import Icon from "./Icon";
import Logo from "./Logo";

const LINKS = [
  { href: "/", label: "Overview", icon: "home" },
  { href: "/optimize", label: "Optimize", icon: "bolt" },
  { href: "/challenge", label: "Challenge", icon: "flag" },
  { href: "/playground", label: "Playground", icon: "play" },
  { href: "/router", label: "Model Router", icon: "router" },
  { href: "/benchmarks", label: "Benchmarks", icon: "bars" },
  { href: "/impact", label: "Impact", icon: "leaf" },
  { href: "/history", label: "History", icon: "clock" },
  { href: "/methodology", label: "Methodology", icon: "doc" },
  { href: "/settings", label: "Settings", icon: "gear" },
];

const THEME_KEY = "ecocompute.theme";

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    let t: string | null = null;
    try {
      t = localStorage.getItem(THEME_KEY);
    } catch {
      /* storage unavailable */
    }
    setTheme(t === "dark" || (!t && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light");
  }, []);
  function pick(t: "light" | "dark") {
    setTheme(t);
    document.documentElement.dataset.theme = t;
    try {
      localStorage.setItem(THEME_KEY, t);
    } catch {
      /* storage unavailable */
    }
  }
  return (
    <div className="seg w-full">
      {(["light", "dark"] as const).map((t) => (
        <button key={t} aria-pressed={theme === t} onClick={() => pick(t)} className="flex flex-1 items-center justify-center gap-1.5">
          <Icon name={t === "light" ? "sun" : "moon"} size={14} />
          {t === "light" ? "Light" : "Dark"}
        </button>
      ))}
    </div>
  );
}

export function useProviderStatus() {
  const { data, error } = useApi<any>("/health", { poll: true, intervalMs: 30000 });
  if (error) return { tone: "var(--bad)", title: "Backend offline", sub: "Check Settings" };
  if (!data) return { tone: "var(--muted)", title: "Connecting…", sub: "" };
  if (data.sample_data) return { tone: "var(--warn)", title: "Mock provider", sub: "Sample data only" };
  return { tone: "var(--accent)", title: "Nebius Connected", sub: "NVIDIA Nemotron via Token Factory" };
}

export default function Nav() {
  const path = usePathname();
  const st = useProviderStatus();
  const active = (href: string) => (href === "/" ? path === "/" : path?.startsWith(href));

  return (
    <>
      {/* desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-border bg-sidebar md:flex">
        <Link href="/" className="flex items-center gap-2.5 px-6 pb-6 pt-7">
          <Logo size={28} />
          <span className="display text-[22px]">EcoCompute</span>
        </Link>
        <nav className="flex-1 space-y-1 px-3">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={active(l.href) ? "page" : undefined}
              className={`flex items-center gap-3 rounded-full px-4 py-2 text-[14.5px] transition-colors ${active(l.href) ? "bg-accent-soft font-medium text-accent-strong" : "text-fg/75 hover:bg-panel-2 hover:text-fg"}`}
            >
              <Icon name={l.icon} className={active(l.href) ? "text-accent" : "text-muted"} />
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="space-y-3 px-4 py-5">
          <Link href="/settings" className="card flex gap-3 rounded-2xl px-4 py-3 hover:border-border-strong" aria-label={`Provider status: ${st.title}. Open settings`}>
            <span className="relative mt-1 inline-flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full rounded-full opacity-30" style={{ background: st.tone, transform: "scale(1.9)" }} />
              <span className="relative inline-block h-2.5 w-2.5 rounded-full" style={{ background: st.tone }} />
            </span>
            <div className="min-w-0 text-sm leading-snug">
              <div className="font-medium">{st.title}</div>
              <div className="text-xs text-muted">{st.sub}</div>
            </div>
          </Link>
          <ThemeToggle />
        </div>
      </aside>

      {/* mobile top bar */}
      <header className="sticky top-0 z-30 border-b border-border bg-sidebar md:hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <Link href="/" className="flex items-center gap-2">
            <Logo size={24} />
            <span className="font-semibold">EcoCompute</span>
          </Link>
          <span className="flex items-center gap-1.5 text-xs text-muted">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: st.tone }} />
            {st.title}
          </span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-2">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${active(l.href) ? "bg-accent-soft font-medium text-accent-strong" : "text-muted"}`}
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </header>
    </>
  );
}

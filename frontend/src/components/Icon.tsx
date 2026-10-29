/** Small stroke icon set (24px grid, currentColor). */
const PATHS: Record<string, string> = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  flag: "M5 21V4m0 0h11l-2 4 2 4H5",
  play: "M7 4.5v15l12-7.5z",
  router: "M12 3v6m0 0-6 6m6-6 6 6M6 15a2 2 0 1 0 0 4 2 2 0 0 0 0-4m12 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4M12 1.5a1.5 1.5 0 1 0 0 3",
  bars: "M5 20V11m7 9V5m7 15v-6",
  leaf: "M5 19c0-9 6-14 15-14-1 9-6 15-14 15m-1-1 8-8",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18m0-14v5l3 2",
  doc: "M7 3h7l4 4v14H7zm7 0v4h4M10 12h5m-5 4h5",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6m7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2l.4 2.6h5l.4-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2",
  check: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18m-4-9 3 3 5-6",
  dollar: "M12 2v20m5-16H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10M12 1v2m0 18v2M4.2 4.2l1.4 1.4m12.8 12.8 1.4 1.4M1 12h2m18 0h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8",
  arrowRight: "M5 12h14m-6-6 6 6-6 6",
  arrowUp: "M12 19V5m-6 6 6-6 6 6",
  arrowDown: "M12 5v14m6-6-6 6-6-6",
  drop: "M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11",
  cloud: "M7 18h10a4 4 0 0 0 .5-8 6 6 0 0 0-11.4 1.5A3.3 3.3 0 0 0 7 18",
  bolt: "M13 2 4 14h7l-1 8 9-12h-7z",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18m0-5v-5m0-3h.01",
  chevron: "m9 6 6 6-6 6",
  menu: "M4 6h16M4 12h16M4 18h16",
};

export default function Icon({ name, size = 18, className = "" }: { name: keyof typeof PATHS | string; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={PATHS[name] || PATHS.info} />
    </svg>
  );
}

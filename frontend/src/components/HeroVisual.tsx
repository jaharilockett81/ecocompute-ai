/** Decorative hero: a glowing orb with the Nano → Super → Ultra escalation ladder orbiting it. */
export default function HeroVisual() {
  const nodes = [
    { x: 300, y: 92, label: "Ultra", sub: "55B active", c: "var(--t-large)" },
    { x: 384, y: 236, label: "Super", sub: "12B active", c: "var(--t-medium)" },
    { x: 262, y: 344, label: "Nano", sub: "3B active", c: "var(--t-small)" },
  ];
  return (
    <svg viewBox="0 0 500 440" className="h-auto w-full max-w-[520px]" aria-hidden="true">
      <defs>
        <radialGradient id="orb" cx="40%" cy="35%" r="70%">
          <stop offset="0%" stopColor="#7dffb3" stopOpacity="0.9" />
          <stop offset="35%" stopColor="#1fbf66" stopOpacity="0.55" />
          <stop offset="75%" stopColor="#0a3d22" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#04130b" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="halo" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#2fe07a" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#2fe07a" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="leaf" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor="#1fbf66" />
          <stop offset="100%" stopColor="#9dffc6" />
        </linearGradient>
      </defs>

      <circle cx="220" cy="220" r="210" fill="url(#halo)" />
      {[150, 185].map((r) => (
        <circle key={r} cx="220" cy="220" r={r} fill="none" stroke="var(--accent)" strokeOpacity={r === 150 ? 0.18 : 0.08} strokeDasharray={r === 150 ? "2 6" : undefined} />
      ))}
      <circle cx="220" cy="220" r="118" fill="url(#orb)" />
      <circle cx="220" cy="220" r="118" fill="none" stroke="#9dffc6" strokeOpacity="0.25" />

      {/* circuit traces */}
      <g stroke="#9dffc6" strokeOpacity="0.35" strokeWidth="1" fill="none">
        <path d="M150 250h40l14-14h30" />
        <path d="M160 190h28l12 12h40" />
        <path d="M205 290v-24l10-10" />
      </g>
      <g fill="#c9ffe0" fillOpacity="0.8">
        <circle cx="150" cy="250" r="2.5" />
        <circle cx="160" cy="190" r="2.5" />
        <circle cx="205" cy="290" r="2.5" />
      </g>
      {/* leaf */}
      <path d="M196 262c-6-52 26-88 84-92-2 58-34 92-84 92z" fill="url(#leaf)" fillOpacity="0.92" />
      <path d="M198 260c18-26 38-46 70-76" stroke="#04210f" strokeWidth="2" strokeLinecap="round" fill="none" />

      {/* escalation ladder */}
      <path d="M262 344 Q 360 320 384 236 Q 392 150 300 92" fill="none" stroke="var(--accent)" strokeOpacity="0.5" strokeWidth="1.5" strokeDasharray="4 5" />
      {nodes.map((n) => (
        <g key={n.label}>
          <circle cx={n.x} cy={n.y} r="22" fill="rgba(5,12,8,0.85)" stroke={n.c} strokeWidth="1.5" />
          <circle cx={n.x} cy={n.y} r="5" fill={n.c} />
          <text x={n.x + 30} y={n.y - 2} fill="var(--fg)" fontSize="14" fontWeight="500">
            {n.label}
          </text>
          <text x={n.x + 30} y={n.y + 15} fill="var(--muted)" fontSize="11">
            {n.sub}
          </text>
        </g>
      ))}
      <text x="40" y="420" fill="var(--muted)" fontSize="11" letterSpacing="2">
        START SMALL · ESCALATE ONLY ON FAILURE
      </text>
    </svg>
  );
}

/** Leaf-on-circuit mark. */
export default function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="15" fill="none" stroke="var(--accent)" strokeOpacity="0.35" />
      <path d="M9 22c0-8 6-13 15-13-1 9-6 14-13 14" fill="var(--accent)" fillOpacity="0.9" />
      <path d="M9 23l8-8" stroke="var(--accent-ink)" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="6" cy="26" r="1.6" fill="var(--accent)" />
      <path d="M6 26h3" stroke="var(--accent)" strokeWidth="1.2" />
    </svg>
  );
}

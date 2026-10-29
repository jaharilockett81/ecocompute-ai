/** Leaf mark. */
export default function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <path d="M5 27C5 14 13 5 28 4c-1 15-9 23-22 23" fill="var(--accent-strong)" />
      <path d="M6 26 18 14" stroke="var(--panel)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

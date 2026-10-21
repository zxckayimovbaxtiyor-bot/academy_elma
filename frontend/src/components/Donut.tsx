/** Score ring (SVG): mockup 4. */
export function Donut({ value, tone, label, sub }: { value: number; tone: "success" | "danger"; label: string; sub: string }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const filled = (Math.max(0, Math.min(100, value)) / 100) * c;
  return (
    <div className={`donut donut-${tone}`}>
      <svg viewBox="0 0 120 120" width="200" height="200" aria-hidden="true">
        <circle cx="60" cy="60" r={r} className="donut-track" />
        <circle
          cx="60"
          cy="60"
          r={r}
          className="donut-fill"
          strokeDasharray={`${filled} ${c - filled}`}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="donut-label">
        <strong>{label}</strong>
        <span>{sub}</span>
      </div>
    </div>
  );
}

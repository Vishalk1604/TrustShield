import React, { useEffect, useState } from "react";
import { color as C, hexA } from "../../theme.js";

// Neon trust gauge (0–100). Animated sweep on mount/value-change + soft glow in the action color.
// `size` controls the diameter. The arc color is the recommended-action color passed in.
export default function Gauge({ value = 0, accent = C.accent, size = 168, label = "trust" }) {
  const [shown, setShown] = useState(0);
  const v = Math.max(0, Math.min(100, value ?? 0));

  // animate from 0 → value
  useEffect(() => {
    let raf;
    const start = performance.now();
    const dur = 900;
    const from = 0;
    const tick = (t) => {
      const k = Math.min(1, (t - start) / dur);
      const eased = 1 - Math.pow(1 - k, 3); // easeOutCubic
      setShown(from + (v - from) * eased);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [v]);

  const stroke = Math.round(size * 0.075);
  const r = (size - stroke * 2) / 2 - 2;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * r;
  const pct = shown / 100;
  const gid = `gauge-grad-${Math.round(size)}-${accent.replace("#", "")}`;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block" }}>
      <defs>
        <linearGradient id={gid} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={accent} />
          <stop offset="100%" stopColor={hexA(accent, 0.55)} />
        </linearGradient>
        <filter id={`${gid}-glow`} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {/* track */}
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(148,163,184,0.12)" strokeWidth={stroke} />
      {/* value arc */}
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke={`url(#${gid})`}
        strokeWidth={stroke}
        strokeDasharray={circ}
        strokeDashoffset={circ * (1 - pct)}
        strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`}
        filter={`url(#${gid}-glow)`}
      />
      <text x={cx} y={cy - size * 0.02} textAnchor="middle" fontSize={size * 0.27} fontWeight="800" fill="#f4f8ff" letterSpacing="-1">
        {Math.round(shown)}
      </text>
      <text x={cx} y={cy + size * 0.16} textAnchor="middle" fontSize={size * 0.085} fill={C.textDim} letterSpacing="0.5">
        / 100 {label}
      </text>
    </svg>
  );
}

import React, { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { color, font, maxWidth } from "../theme.js";
import { ShieldIcon, HomeIcon, ScanIcon, GalleryIcon } from "./Icons.jsx";
import LocalFirstBadge from "./LocalFirstBadge.jsx";

const NAV = [
  { to: "/", label: "Home", icon: HomeIcon, end: true },
  { to: "/investigator", label: "Investigator", icon: ScanIcon },
  { to: "/examples", label: "Examples", icon: GalleryIcon },
];

function navLinkStyle({ isActive }) {
  return {
    display: "flex",
    alignItems: "center",
    gap: 7,
    textDecoration: "none",
    fontSize: 14,
    fontWeight: 600,
    padding: "8px 12px",
    borderRadius: 8,
    color: isActive ? "#04131c" : color.textDim,
    background: isActive ? color.accent : "transparent",
    whiteSpace: "nowrap",
  };
}

export default function Shell() {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", fontFamily: font.sans }}>
      <header
        style={{
          position: "sticky", top: 0, zIndex: 20,
          background: "rgba(6,8,15,0.72)",
          backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)",
          borderBottom: `1px solid ${color.border}`,
          boxShadow: "0 1px 0 rgba(56,189,248,0.08)",
        }}
      >
        <div
          style={{
            maxWidth, margin: "0 auto", padding: "12px 24px",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap",
          }}
        >
          <NavLink to="/" style={{ display: "flex", alignItems: "center", gap: 9, textDecoration: "none", color: color.text }}>
            <span style={{ display: "inline-flex", filter: `drop-shadow(0 0 6px ${color.accent}66)` }}>
              <ShieldIcon width={24} height={24} stroke={color.accent} />
            </span>
            <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: -0.3 }}>TrustShield</span>
          </NavLink>

          <nav style={{ display: "flex", alignItems: "center", gap: 4, flex: 1, justifyContent: "center" }} className="ts-nav">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} style={navLinkStyle}>
                <Icon width={15} height={15} />
                {label}
              </NavLink>
            ))}
          </nav>

          <LocalFirstBadge style={{ display: "none" }} className="ts-badge-desktop" />
          <button
            aria-label="Toggle navigation"
            onClick={() => setNavOpen((v) => !v)}
            className="ts-nav-toggle"
            style={{ display: "none", background: "none", border: `1px solid ${color.border}`, borderRadius: 8, color: color.text, padding: "6px 10px", cursor: "pointer" }}
          >
            ☰
          </button>
        </div>
        {navOpen && (
          <div className="ts-nav-mobile" style={{ borderTop: `1px solid ${color.border}`, padding: "8px 16px", display: "flex", flexDirection: "column", gap: 4 }}>
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} onClick={() => setNavOpen(false)} style={navLinkStyle}>
                <Icon width={15} height={15} />
                {label}
              </NavLink>
            ))}
          </div>
        )}
      </header>

      <main style={{ flex: 1 }}>
        <Outlet />
      </main>

      <footer style={{ borderTop: `1px solid ${color.border}`, marginTop: 48, background: "rgba(255,255,255,0.012)" }}>
        <div style={{ maxWidth, margin: "0 auto", padding: "22px 24px", display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", fontSize: 12, color: color.textFaint }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <ShieldIcon width={14} height={14} stroke={color.accent} />
            TrustShield — synthetic data, zero PII, 100% on-device. Every score carries a full evidence chain.
          </span>
          <span>React + Vite · FastAPI forensics (:8001) · FastAPI risk (:8002)</span>
        </div>
      </footer>

      <style>{`
        @media (max-width: 860px) {
          .ts-nav { display: none !important; }
          .ts-nav-toggle { display: inline-flex !important; }
        }
        @media (min-width: 861px) {
          .ts-nav-mobile { display: none !important; }
        }
        @media (min-width: 640px) {
          .ts-badge-desktop { display: inline-flex !important; }
        }
      `}</style>
    </div>
  );
}

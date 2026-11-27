import React, { useLayoutEffect, useRef, useState } from "react";
import {
  AbsoluteFill,
  Composition,
  Easing,
  interpolate,
  useCurrentFrame,
} from "remotion";
import assets from "./assets.json";

// High-DPI, zero-grain README hero GIF for mintchip ("One command. Every surface.")
// Native 1280x720 @ 15 fps, 330 frames (22.0 s).
// Optimized for 256-color FASTOCTREE + dither=NONE GIF encoding:
// - Pure solid #0B1020 dark studio backdrop (no radial gradients, no blurred drop shadows)
// - Native 1:1 CSS pixels (zero fractional CSS transform scaling on text or SVGs)
// - 100% real mintchip outputs (ANSI, Markdown, currentColor HTML, CSS, and stderr warnings)

export const WIDTH = 1280;
export const HEIGHT = 720;
export const FPS = 15;
export const DURATION = 330; // 22.0 s

const C = {
  bg: "#0B1020",
  panel: "#11192E",
  term: "#0D1426",
  termBar: "#131D35",
  line: "#263659",
  ink: "#F1F5FC",
  muted: "#9AA8C4",
  dim: "#6B7C9D",
  mint: "#34D8A0",
  mintDark: "#149E70",
  blue: "#7FB2FF",
  amber: "#F6B941",
  red: "#FF5D6C",
  // Light document surface (matches mc.css [data-mc-scheme=light])
  page: "#FFFFFF",
  pageInk: "#1A1D21",
  pageMuted: "#5B6570",
  pageLine: "#E2E7EE",
  bubble: "#EEF1F5",
  // Dark document surface (matches mc.css [data-mc-scheme=dark])
  darkPage: "#14181F",
  darkInk: "#E6E9EE",
  darkMuted: "#97A3B6",
  darkLine: "#2A3241",
  darkBar: "#1B212C",
};

const SANS =
  '-apple-system, "SF Pro Display", "Helvetica Neue", Helvetica, Arial, sans-serif';
const UI = 'system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif';
const MONO = '"SF Mono", Menlo, "JetBrains Mono", Consolas, monospace';

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.33, 0, 0.2, 1);
const ramp = (f: number, a: number, b: number) =>
  interpolate(f, [a, b], [0, 1], { ...clamp, easing: ease });
const within = (f: number, [a, b]: readonly [number, number]) => f >= a && f < b;

// Beat timeline (330 frames @ 15 fps = 22.0 s)
const B = {
  wall: [0, 60] as const, // 0.0 - 4.0 s
  term: [60, 140] as const, // 4.0 - 9.33 s
  html: [140, 232] as const, // 9.33 - 15.47 s
  distort: [232, 300] as const, // 15.47 - 20.0 s (4.53 s so both cards & stderr read comfortably)
  end: [300, 330] as const, // 20.0 - 22.0 s (+ hold_end_ms on last frame)
};

// Beat 3 internal milestones
const POP_MOVE_START = 148;
const POP_CLICK = 162;
const POP_OPEN = 163;
const POP_CLOSE = 194;
const WIPE_START = 198;
const WIPE_END = 220;

// Right stage window (native 1:1 pixels inside 1280x720)
const WIN = { x: 454, y: 22, w: 794, h: 676, bar: 36 };

type AnsiSpan = { t: string; c: string | null; dim: boolean; b: boolean };
type Pt = { x: number; y: number; w: number; h: number };

const ANSI_COLORS: Record<string, string> = {
  green: C.mint,
  red: C.red,
  amber: C.amber,
  blue: C.blue,
  cyan: "#5EEAD4",
};

const AnsiSpans: React.FC<{
  spans: AnsiSpan[];
  markZeroCol?: boolean;
  zeroRef?: React.RefObject<HTMLSpanElement | null>;
}> = ({ spans, markZeroCol, zeroRef }) => (
  <>
    {spans.map((s, i) => {
      const color = s.c
        ? ANSI_COLORS[s.c] ?? C.ink
        : s.dim
          ? "#7B8CA8"
          : C.ink;
      if (markZeroCol && s.t.includes("│")) {
        const idx = s.t.indexOf("│");
        const before = s.t.slice(0, idx);
        const after = s.t.slice(idx + 1);
        return (
          <span key={i} style={{ color, fontWeight: s.b ? 700 : 400 }}>
            {before}
            <span ref={zeroRef} data-zero-bar="1">
              │
            </span>
            {after}
          </span>
        );
      }
      return (
        <span key={i} style={{ color, fontWeight: s.b ? 700 : 400 }}>
          {s.t}
        </span>
      );
    })}
  </>
);

const Html: React.FC<{
  html: string;
  style?: React.CSSProperties;
  className?: string;
}> = React.memo(({ html, style, className }) => (
  <div
    className={className}
    style={style}
    dangerouslySetInnerHTML={{ __html: html }}
  />
));

const CursorIcon: React.FC<{ x: number; y: number; press: number }> = ({
  x,
  y,
  press,
}) => (
  <svg
    width={24}
    height={28}
    viewBox="0 0 22 26"
    style={{
      position: "absolute",
      left: x - 3,
      top: y - 2,
      zIndex: 40,
      transform: `scale(${1 - press * 0.14})`,
      transformOrigin: "3px 2px",
    }}
  >
    <path
      d="M3 2 L3 21 L8 16.5 L11.5 24 L14.6 22.6 L11.2 15.3 L18 15.3 Z"
      fill="#111827"
      stroke="#FFFFFF"
      strokeWidth={1.8}
      strokeLinejoin="round"
    />
  </svg>
);

const relPos = (el: Element, root: HTMLElement): Pt => {
  const o = root.getBoundingClientRect();
  const s = o.width / root.offsetWidth || 1;
  const b = el.getBoundingClientRect();
  return {
    x: (b.left - o.left) / s,
    y: (b.top - o.top) / s,
    w: b.width / s,
    h: b.height / s,
  };
};

// ============================================================================
// Left Rail Sidebar (Beats 1 - 4a)
// ============================================================================

const SIDEBAR_STEPS = [
  { id: 0, pill: "1 Wall", accent: C.amber },
  { id: 1, pill: "2 Terminal", accent: C.mint },
  { id: 2, pill: "3 HTML", accent: C.mint },
  { id: 3, pill: "4 Honest", accent: C.amber },
] as const;

function getCaption(frame: number) {
  if (frame < B.term[0]) {
    return {
      stepId: 0,
      at: B.wall,
      eyebrow: "Before · Wall of numbers",
      accent: C.amber,
      title: `${assets.numbers_before} numbers in one PR report.`,
      body: "Your coding agent ran CI and the parser benchmark, then buried every signal in prose.",
    };
  }
  if (frame < B.html[0]) {
    return {
      stepId: 1,
      at: B.term,
      eyebrow: "Terminal · ANSI + Markdown",
      accent: C.mint,
      title: "One command. Every surface.",
      body: "Inline chips and a shared-scale forest plot straight from stdout — or --format md for GitHub PRs.",
    };
  }
  if (frame < WIPE_START - 2) {
    return {
      stepId: 2,
      at: [B.html[0], WIPE_START - 2] as const,
      eyebrow: "HTML · Zero-JS popover",
      accent: C.mint,
      title: "Same data, live HTML chips.",
      body: "Click any chip for exact n, IQR, and clipped outlier notes — built on native HTML Popover with zero JS.",
    };
  }
  if (frame < B.distort[0]) {
    return {
      stepId: 2,
      at: [WIPE_START - 2, B.html[1]] as const,
      eyebrow: "currentColor · Auto theme",
      accent: C.blue,
      title: "Light & dark automatically.",
      body: "Every inline SVG inherits currentColor — drop into any doc, chat, or dark UI with zero config.",
    };
  }
  return {
    stepId: 3,
    at: B.distort,
    eyebrow: "Honest by default",
    accent: C.amber,
    title: "Distortions are announced.",
    body: "Clipped outliers never vanish silently — marked →240 in text, a chevron in SVG, and a warning on stderr.",
  };
}

const Sidebar: React.FC<{ frame: number }> = ({ frame }) => {
  const cap = getCaption(frame);
  const [a, b] = cap.at;
  const inP = cap.stepId === 0 ? 1 : ramp(frame, a, a + 6);
  const outP = 1 - ramp(frame, b - 5, b);

  // Beat 1 left-rail command card slides in at frame 28
  const cmdCardIn =
    frame < B.term[0]
      ? ramp(frame, 28, 36) * (1 - ramp(frame, B.wall[1] - 5, B.wall[1]))
      : 0;

  return (
    <div
      style={{
        position: "absolute",
        left: 36,
        top: 0,
        width: 390,
        height: HEIGHT,
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "36px 0 34px",
        boxSizing: "border-box",
        fontFamily: SANS,
      }}
    >
      {/* Top brand + zero-deps badge */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 13,
            height: 13,
            borderRadius: 4,
            background: C.mint,
          }}
        />
        <span
          style={{
            fontFamily: MONO,
            fontSize: 17,
            fontWeight: 700,
            color: C.ink,
            letterSpacing: 0.3,
          }}
        >
          mintchip
        </span>
        <span
          style={{
            marginLeft: 4,
            padding: "3px 9px",
            borderRadius: 999,
            background: C.panel,
            border: `1px solid ${C.line}`,
            fontFamily: MONO,
            fontSize: 12,
            fontWeight: 600,
            color: C.mint,
          }}
        >
          0 deps · 12 ms
        </span>
      </div>

      {/* Main narrative caption + Beat 1 command preview */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div
          style={{
            opacity: inP * outP,
            transform: `translateY(${(1 - inP) * 12}px)`,
          }}
        >
          <div
            style={{
              display: "inline-block",
              padding: "5px 12px",
              borderRadius: 999,
              background: C.panel,
              border: `1.5px solid ${cap.accent}`,
              color: cap.accent,
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: 1.3,
              textTransform: "uppercase",
              fontFamily: MONO,
            }}
          >
            {cap.eyebrow}
          </div>
          <div
            style={{
              color: C.ink,
              fontSize: 38,
              fontWeight: 780,
              lineHeight: 1.09,
              letterSpacing: -0.9,
              marginTop: 16,
            }}
          >
            {cap.title}
          </div>
          <div
            style={{
              color: C.muted,
              fontSize: 18.5,
              lineHeight: 1.45,
              marginTop: 14,
            }}
          >
            {cap.body}
          </div>
        </div>

        {/* Beat 1: One shell command rail preview */}
        {cmdCardIn > 0.01 && (
          <div
            style={{
              opacity: cmdCardIn,
              transform: `translateY(${(1 - cmdCardIn) * 10}px)`,
              background: C.term,
              border: `1.5px solid ${C.mint}`,
              borderRadius: 10,
              padding: "12px 14px",
              fontFamily: MONO,
              fontSize: 13,
              lineHeight: 1.6,
              color: C.ink,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 6,
                fontSize: 11.5,
                color: C.mint,
                fontWeight: 700,
                letterSpacing: 0.6,
                textTransform: "uppercase",
              }}
            >
              <span>Replace with two commands</span>
              <span>stdlib only</span>
            </div>
            <div>
              <span style={{ color: C.mint, fontWeight: 700 }}>$ </span>
              mintchip render report.txt
            </div>
            <div>
              <span style={{ color: C.mint, fontWeight: 700 }}>$ </span>
              mintchip table bench.json \
            </div>
            <div style={{ color: C.muted, paddingLeft: 16 }}>
              --col change:ci
            </div>
          </div>
        )}
      </div>

      {/* Step pills */}
      <div style={{ display: "flex", gap: 8, flexWrap: "nowrap" }}>
        {SIDEBAR_STEPS.map((step) => {
          const isCur = step.id === cap.stepId;
          const done = step.id < cap.stepId;
          const borderColor = isCur ? cap.accent : done ? "#2B4A4A" : C.line;
          const bgColor = isCur ? "#15233D" : C.bg;
          const txtColor = isCur ? cap.accent : done ? "#7CA89C" : "#6B7894";
          return (
            <div
              key={step.id}
              style={{
                padding: "5px 10px",
                borderRadius: 8,
                border: `1.5px solid ${borderColor}`,
                background: bgColor,
                color: txtColor,
                fontFamily: MONO,
                fontSize: 12.5,
                fontWeight: isCur ? 700 : 500,
                whiteSpace: "nowrap",
              }}
            >
              {step.pill}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ============================================================================
// Beat 1: Wall of numbers (PR / Coding-Agent benchmark summary)
// ============================================================================

const WallOfNumbersCard: React.FC<{ frame: number }> = ({ frame }) => {
  const out = 1 - ramp(frame, B.wall[1] - 5, B.wall[1]);
  const text = assets.before_text;
  const shown = Math.floor(interpolate(frame, [2, 22], [0, text.length], clamp));
  const parts = text.split(/([-+−]?\d+(?:\.\d+)?)/);

  let pos = 0;
  let numIdx = 0;
  const nodes: React.ReactNode[] = [];

  parts.forEach((p, i) => {
    const start = pos;
    pos += p.length;
    if (start >= shown) return;
    const vis = p.slice(0, Math.max(0, shown - start));
    if (i % 2) {
      const lit = frame >= 24 + numIdx * 0.55;
      numIdx += 1;
      nodes.push(
        <span
          key={i}
          style={{
            background: lit ? "#FDE68A" : "transparent",
            borderRadius: 3,
            padding: lit ? "0 2px" : 0,
            color: C.pageInk,
            fontWeight: lit ? 650 : 400,
          }}
        >
          {vis}
        </span>,
      );
    } else {
      nodes.push(<span key={i}>{vis}</span>);
    }
  });

  const diagIn = ramp(frame, 36, 44);

  return (
    <div
      style={{
        position: "absolute",
        left: WIN.x,
        top: WIN.y,
        width: WIN.w,
        height: WIN.h,
        background: C.page,
        borderRadius: 14,
        border: `1.5px solid ${C.line}`,
        overflow: "hidden",
        color: C.pageInk,
        fontFamily: UI,
        boxSizing: "border-box",
        opacity: out,
      }}
    >
      {/* Window title bar */}
      <div
        style={{
          height: WIN.bar,
          borderBottom: `1px solid ${C.pageLine}`,
          display: "flex",
          alignItems: "center",
          padding: "0 14px",
          gap: 8,
          background: "#F6F8FA",
        }}
      >
        {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
          <span
            key={c}
            style={{
              width: 11,
              height: 11,
              borderRadius: 6,
              background: c,
              display: "inline-block",
            }}
          />
        ))}
        <span
          style={{
            flex: 1,
            textAlign: "center",
            fontSize: 13,
            fontWeight: 500,
            color: C.pageMuted,
            marginRight: 48,
          }}
        >
          coding-agent · parser-bench · PR #418
        </span>
      </div>

      {/* Chat content */}
      <div style={{ padding: "24px 36px", display: "flex", flexDirection: "column", gap: 20 }}>
        {/* User prompt bubble */}
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <div
            style={{
              background: C.bubble,
              borderRadius: 16,
              padding: "9px 16px",
              fontSize: 15.5,
              color: C.pageInk,
            }}
          >
            How did CI and the parser benchmark go?
          </div>
        </div>

        {/* Agent wall-of-text reply */}
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 13.5,
              fontWeight: 700,
              color: C.pageMuted,
              marginBottom: 10,
            }}
          >
            <span
              style={{
                width: 18,
                height: 18,
                borderRadius: 5,
                background: "#D97706",
                display: "inline-block",
              }}
            />
            Coding Agent · raw prose
          </div>
          <p
            style={{
              margin: 0,
              fontSize: 16,
              lineHeight: 1.7,
              color: C.pageInk,
            }}
          >
            {nodes}
          </p>
        </div>

        {/* Bottom pain-point strip */}
        <div
          style={{
            marginTop: 18,
            opacity: diagIn,
            transform: `translateY(${(1 - diagIn) * 8}px)`,
            display: "flex",
            gap: 10,
            flexWrap: "wrap",
          }}
        >
          {[
            `${assets.numbers_before} buried numbers`,
            "5 intervals with no shared zero line",
            "1 outlier (240 ms) lost in prose",
          ].map((label) => (
            <span
              key={label}
              style={{
                padding: "6px 12px",
                borderRadius: 8,
                background: "#FEF3C7",
                border: "1px solid #F59E0B",
                color: "#92400E",
                fontFamily: MONO,
                fontSize: 12.5,
                fontWeight: 600,
              }}
            >
              {label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// Beat 2: Terminal ANSI + Shared-Scale Forest Plot + Markdown PR Preview
// ============================================================================

const TerminalBeat: React.FC<{ frame: number }> = ({ frame }) => {
  const f = frame - B.term[0];
  const dur = B.term[1] - B.term[0];
  const fadeIn = ramp(f, 0, 5);
  const fadeOut = 1 - ramp(f, dur - 5, dur);

  const tableBoxRef = useRef<HTMLDivElement>(null);
  const zeroBarRef = useRef<HTMLSpanElement>(null);
  const [zeroPos, setZeroPos] = useState<{ x: number; w: number } | null>(null);

  useLayoutEffect(() => {
    if (!tableBoxRef.current || !zeroBarRef.current) return;
    const p = relPos(zeroBarRef.current, tableBoxRef.current);
    setZeroPos({ x: p.x, w: p.w });
  }, []);

  const cmd1 = "mintchip render report.txt --compact --format ansi";
  const typed1 = Math.round(interpolate(f, [1, 10], [0, cmd1.length], clamp));
  const proseIn = ramp(f, 10, 14);

  const cmd2In = ramp(f, 15, 19);
  const tableLines = assets.table.ansi_lines as AnsiSpan[][];

  // Subtle mint vertical scan-line along the aligned │ zero line
  const scanIn = ramp(f, 25, 31) * (1 - ramp(f, 52, 57));
  const scanProgress = ramp(f, 26, 40);
  const regHi = ramp(f, 34, 40) * (1 - ramp(f, 54, 58));

  // Quick --format md GitHub PR preview card
  const mdIn = ramp(f, 45, 52);

  return (
    <div
      style={{
        position: "absolute",
        left: WIN.x,
        top: WIN.y,
        width: WIN.w,
        height: WIN.h,
        background: C.term,
        borderRadius: 14,
        border: `1.5px solid ${C.line}`,
        overflow: "hidden",
        color: C.ink,
        fontFamily: MONO,
        boxSizing: "border-box",
        opacity: fadeIn * fadeOut,
      }}
    >
      {/* Terminal title bar */}
      <div
        style={{
          height: WIN.bar,
          borderBottom: `1px solid ${C.line}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 14px",
          background: C.termBar,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
            <span
              key={c}
              style={{
                width: 11,
                height: 11,
                borderRadius: 6,
                background: c,
                display: "inline-block",
              }}
            />
          ))}
          <span
            style={{
              marginLeft: 8,
              fontFamily: SANS,
              fontSize: 13,
              fontWeight: 500,
              color: C.muted,
            }}
          >
            zsh — parser-bench
          </span>
        </div>
        <span
          style={{
            padding: "2px 9px",
            borderRadius: 999,
            background: "#122624",
            border: `1px solid ${C.mint}`,
            color: C.mint,
            fontSize: 11.5,
            fontWeight: 700,
          }}
        >
          --format ansi
        </span>
      </div>

      {/* Terminal body */}
      <div style={{ padding: "16px 24px 18px", fontSize: 13.5, lineHeight: 1.54 }}>
        {/* Command 1 */}
        <div>
          <span style={{ color: C.mint, fontWeight: 700 }}>$ </span>
          <span style={{ color: C.ink }}>{cmd1.slice(0, typed1)}</span>
          {typed1 < cmd1.length && (
            <span style={{ background: C.ink, color: C.ink }}>▌</span>
          )}
        </div>

        {/* Real ANSI prose output */}
        <div
          style={{
            marginTop: 6,
            opacity: proseIn,
            color: C.ink,
            whiteSpace: "pre-wrap",
          }}
        >
          <AnsiSpans spans={assets.prose.ansi_spans as AnsiSpan[]} />
        </div>

        {/* Command 2 */}
        <div style={{ marginTop: 14, opacity: cmd2In }}>
          <span style={{ color: C.mint, fontWeight: 700 }}>$ </span>
          <span>
            mintchip table bench.json --col input --col main:num --col new:num \
          </span>
          <div style={{ paddingLeft: 18, color: C.muted }}>
            --col &apos;change:ci:change, 95% CI&apos; --format ansi
          </div>
        </div>

        {/* Real 5-row shared-scale CI forest plot table */}
        <div
          ref={tableBoxRef}
          style={{
            position: "relative",
            marginTop: 10,
            padding: "8px 12px",
            borderRadius: 8,
            background: "#0A101E",
            border: `1px solid ${scanIn > 0.1 ? "#1E4D45" : "#1A2540"}`,
            fontSize: 14.5,
            lineHeight: 1.52,
            whiteSpace: "pre",
          }}
        >
          {/* Floating badge for aligned zero line */}
          {scanIn > 0.02 && (
            <div
              style={{
                position: "absolute",
                top: -11,
                right: 12,
                padding: "1px 9px",
                borderRadius: 999,
                background: C.mint,
                color: C.bg,
                fontSize: 11,
                fontWeight: 800,
                opacity: scanIn,
              }}
            >
              aligned │ zero line · shared scale (−38% to +9.3%)
            </div>
          )}

          {/* Mint vertical scan-line on the exact │ column */}
          {zeroPos && scanIn > 0.02 && (
            <>
              <div
                style={{
                  position: "absolute",
                  left: zeroPos.x - 4,
                  top: 74,
                  width: zeroPos.w + 8,
                  height: 114 * scanProgress,
                  background: "rgba(52, 216, 160, 0.16)",
                  borderRadius: 3,
                  opacity: scanIn,
                  pointerEvents: "none",
                }}
              />
              <div
                style={{
                  position: "absolute",
                  left: zeroPos.x + zeroPos.w / 2 - 1,
                  top: 74,
                  width: 2,
                  height: 114 * scanProgress,
                  background: C.mint,
                  opacity: scanIn,
                  pointerEvents: "none",
                }}
              />
            </>
          )}

          {tableLines.map((lineSpans, idx) => {
            const lineIn = ramp(f, 18 + idx * 1.1, 21 + idx * 1.1);
            const isHeader = idx < 3;
            const isRegression = idx === 6; // nested.json (+5%)
            return (
              <div
                key={idx}
                style={{
                  opacity: lineIn,
                  position: "relative",
                  zIndex: 2,
                  color: isHeader ? C.muted : C.ink,
                  background:
                    isRegression && regHi > 0.05
                      ? `rgba(246, 185, 65, ${0.14 * regHi})`
                      : "transparent",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <span>
                  <AnsiSpans
                    spans={lineSpans}
                    markZeroCol={idx === 3}
                    zeroRef={idx === 3 ? zeroBarRef : undefined}
                  />
                </span>
                {isRegression && regHi > 0.05 && (
                  <span
                    style={{
                      opacity: regHi,
                      color: C.amber,
                      fontSize: 11,
                      fontWeight: 700,
                      paddingRight: 4,
                    }}
                  >
                    ← right of 0%
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Quick --format md GitHub PR preview card */}
        <div
          style={{
            marginTop: 14,
            opacity: mdIn,
            transform: `translateY(${(1 - mdIn) * 10}px)`,
            background: C.panel,
            border: `1.5px solid ${C.line}`,
            borderRadius: 10,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "6px 12px",
              background: "#16213B",
              borderBottom: `1px solid ${C.line}`,
              fontSize: 11.5,
            }}
          >
            <span style={{ color: C.ink, fontWeight: 700 }}>
              $ mintchip table bench.json … --format md
            </span>
            <span
              style={{
                padding: "1px 8px",
                borderRadius: 999,
                background: "#1A2B4C",
                border: `1px solid ${C.blue}`,
                color: C.blue,
                fontSize: 11,
                fontWeight: 700,
              }}
            >
              GitHub PR Markdown
            </span>
          </div>
          <div
            style={{
              padding: "8px 12px",
              fontSize: 11.5,
              lineHeight: 1.46,
              color: "#CBD5E1",
              whiteSpace: "pre",
              overflow: "hidden",
            }}
          >
            {(assets.table.md_lines as string[]).slice(0, 6).join("\n")}
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// Beat 3: Same data -> --format html (Zero-JS Popover + Light <-> Dark wipe)
// ============================================================================

const HtmlDocumentInner: React.FC<{
  scheme: "light" | "dark";
  proseRef?: React.RefObject<HTMLDivElement | null>;
}> = ({ scheme, proseRef }) => {
  const isDark = scheme === "dark";
  return (
    <div
      className="mc-page"
      data-mc-scheme={scheme}
      style={{
        position: "absolute",
        inset: 0,
        background: isDark ? C.darkPage : C.page,
        color: isDark ? C.darkInk : C.pageInk,
        fontFamily: UI,
        padding: "22px 34px 24px",
        boxSizing: "border-box",
      }}
    >
      {/* Document header */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          paddingBottom: 12,
          marginBottom: 16,
          borderBottom: `1px solid ${isDark ? C.darkLine : C.pageLine}`,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 19,
              fontWeight: 700,
              letterSpacing: -0.3,
              color: isDark ? C.darkInk : C.pageInk,
            }}
          >
            Parser benchmark &amp; CI summary
          </div>
          <div
            style={{
              fontSize: 13,
              color: isDark ? C.darkMuted : C.pageMuted,
              marginTop: 2,
            }}
          >
            PR #418 · 18 runs per input · generated with{" "}
            <span style={{ fontFamily: MONO }}>mintchip --format html</span>
          </div>
        </div>
        <span
          style={{
            fontFamily: MONO,
            fontSize: 12,
            color: isDark ? C.darkMuted : C.pageMuted,
          }}
        >
          currentColor SVGs
        </span>
      </div>

      {/* Real mintchip HTML prose */}
      <div ref={proseRef}>
        <Html
          html={`<p style="margin:0;font-size:16px;line-height:1.72">${assets.prose.html}</p>`}
        />
      </div>

      {/* Real mintchip HTML table */}
      <div
        className="mc-demo-table"
        style={{
          marginTop: 24,
          padding: "16px 20px",
          borderRadius: 10,
          background: isDark ? "#191F29" : "#F8FAFC",
          border: `1px solid ${isDark ? C.darkLine : C.pageLine}`,
        }}
      >
        <Html html={assets.table.html} />
      </div>

      {/* Subtle footer note */}
      <div
        style={{
          marginTop: 18,
          display: "flex",
          justifyContent: "space-between",
          fontFamily: MONO,
          fontSize: 12,
          color: isDark ? C.darkMuted : C.pageMuted,
        }}
      >
        <span>mc.format_prose(..., format=&quot;html&quot;) + table.html()</span>
        <span>0 KB JavaScript</span>
      </div>
    </div>
  );
};

const HtmlBeat: React.FC<{ frame: number }> = ({ frame }) => {
  const f = frame - B.html[0];
  const dur = B.html[1] - B.html[0];
  const fadeIn = ramp(f, 0, 5);
  const fadeOut = 1 - ramp(f, dur - 5, dur);

  const stageRef = useRef<HTMLDivElement>(null);
  const proseRef = useRef<HTMLDivElement>(null);
  const [pts, setPts] = useState<{ chip?: Pt; pop?: string }>({});

  useLayoutEffect(() => {
    if (!stageRef.current || !proseRef.current) return;
    const distOpen = proseRef.current.querySelector(".mc-dist .mc-open");
    const distPop = proseRef.current.querySelector(".mc-dist .mc-pop");
    setPts({
      chip: distOpen ? relPos(distOpen, stageRef.current) : undefined,
      pop: distPop?.innerHTML,
    });
  }, []);

  // Dotted underline + focus tint on the dist chip while hovered/clicked
  useLayoutEffect(() => {
    const distOpen = proseRef.current?.querySelector<HTMLElement>(".mc-dist .mc-open");
    if (!distOpen) return;
    const active = frame >= POP_CLICK - 3 && frame < POP_CLOSE;
    distOpen.style.textDecoration = active ? "underline dotted 1.5px" : "none";
    distOpen.style.textUnderlineOffset = ".22em";
    distOpen.style.background = active ? "#E8F4FD" : "transparent";
    distOpen.style.borderRadius = "4px";
    distOpen.style.padding = active ? "1px 3px" : "0";
  }, [frame]);

  // Cursor glides onto the dist chip, clicks, then exits before the dark wipe
  const showCursor = pts.chip && within(frame, [POP_MOVE_START, POP_CLOSE + 1]);
  const cursorP = ramp(frame, POP_MOVE_START, POP_CLICK - 2);
  const press = interpolate(
    frame,
    [POP_CLICK - 2, POP_CLICK, POP_CLICK + 3],
    [0, 1, 0],
    clamp,
  );
  const curX = pts.chip
    ? interpolate(cursorP, [0, 1], [pts.chip.x + pts.chip.w + 130, pts.chip.x + pts.chip.w * 0.62])
    : 0;
  const curY = pts.chip
    ? interpolate(cursorP, [0, 1], [pts.chip.y + 110, pts.chip.y + pts.chip.h * 0.55])
    : 0;

  // Popover visibility
  const popVisible = pts.chip && pts.pop && within(frame, [POP_OPEN, POP_CLOSE]);
  const popOpacity =
    ramp(frame, POP_OPEN, POP_OPEN + 3) * (1 - ramp(frame, POP_CLOSE - 3, POP_CLOSE));

  // Crisp Light -> Dark wipe
  const wipe = ramp(frame, WIPE_START, WIPE_END);
  const isWiping = wipe > 0.005 && wipe < 0.995;
  const isFullDark = wipe >= 0.995;

  return (
    <div
      style={{
        position: "absolute",
        left: WIN.x,
        top: WIN.y,
        width: WIN.w,
        height: WIN.h,
        background: isFullDark ? C.darkPage : C.page,
        borderRadius: 14,
        border: `1.5px solid ${C.line}`,
        overflow: "hidden",
        boxSizing: "border-box",
        opacity: fadeIn * fadeOut,
      }}
    >
      <style>
        {assets.css}
        {`
          .mc-demo-table table.mc-table { width: 100%; font-size: 16px; }
          .mc-demo-table table.mc-table th,
          .mc-demo-table table.mc-table td { padding: 0.42em 0 0.42em 1.25em; }
          .mc-demo-table table.mc-table :is(th, td):first-child { padding-left: 0; }
        `}
      </style>

      {/* Window title bar */}
      <div
        style={{
          height: WIN.bar,
          borderBottom: `1px solid ${isFullDark ? C.darkLine : C.pageLine}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 14px",
          background: isFullDark ? C.darkBar : "#F6F8FA",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
            <span
              key={c}
              style={{
                width: 11,
                height: 11,
                borderRadius: 6,
                background: c,
                display: "inline-block",
              }}
            />
          ))}
          <span
            style={{
              marginLeft: 8,
              fontFamily: UI,
              fontSize: 13,
              fontWeight: 500,
              color: isFullDark ? C.darkMuted : C.pageMuted,
            }}
          >
            mintchip --format html · parser-bench.html
          </span>
        </div>
        <span
          style={{
            padding: "2px 9px",
            borderRadius: 999,
            background: isFullDark ? "#132925" : "#ECFDF5",
            border: `1px solid ${isFullDark ? C.mint : C.mintDark}`,
            color: isFullDark ? C.mint : C.mintDark,
            fontFamily: MONO,
            fontSize: 11.5,
            fontWeight: 700,
          }}
        >
          {isFullDark ? "dark mode" : isWiping ? "light ↔ dark" : "light mode"}
        </span>
      </div>

      {/* Main HTML stage with dual light/dark layers */}
      <div
        ref={stageRef}
        style={{
          position: "relative",
          width: "100%",
          height: WIN.h - WIN.bar,
          overflow: "hidden",
        }}
      >
        {/* Bottom: Light layer */}
        <HtmlDocumentInner scheme="light" proseRef={proseRef} />

        {/* Top: Dark layer revealed cleanly across the wipe */}
        {wipe > 0.001 && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              clipPath: `inset(0 ${(1 - wipe) * 100}% 0 0)`,
              zIndex: 10,
            }}
          >
            <HtmlDocumentInner scheme="dark" />
          </div>
        )}

        {/* Crisp mint vertical wipe divider */}
        {isWiping && (
          <div
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: `${wipe * 100}%`,
              width: 3,
              marginLeft: -1.5,
              background: C.mint,
              zIndex: 25,
            }}
          >
            <div
              style={{
                position: "absolute",
                bottom: 54,
                left: "50%",
                transform: "translateX(-50%)",
                padding: "4px 12px",
                borderRadius: 999,
                background: C.mint,
                color: C.bg,
                fontFamily: MONO,
                fontSize: 11.5,
                fontWeight: 800,
                whiteSpace: "nowrap",
              }}
            >
              DARK │ LIGHT
            </div>
          </div>
        )}

        {/* Real Zero-JS Popover for the dist chip */}
        {popVisible && pts.chip && pts.pop && (
          <div
            style={{
              position: "absolute",
              left: Math.max(24, Math.min(pts.chip.x - 10, WIN.w - 390)),
              top: pts.chip.y + pts.chip.h + 8,
              width: 356,
              padding: "10px 14px",
              border: `2px solid ${C.mintDark}`,
              borderRadius: 8,
              background: "#FFFFFF",
              color: C.pageInk,
              fontFamily: UI,
              fontSize: 13.5,
              lineHeight: 1.48,
              zIndex: 30,
              opacity: popOpacity,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 6,
                paddingBottom: 5,
                borderBottom: `1px solid ${C.pageLine}`,
              }}
            >
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: 11,
                  fontWeight: 700,
                  color: C.mintDark,
                  textTransform: "uppercase",
                  letterSpacing: 0.6,
                }}
              >
                Zero-JS HTML Popover
              </span>
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: 11,
                  color: C.pageMuted,
                }}
              >
                &lt;span popover&gt;
              </span>
            </div>
            <div
              className="mc-pop-preview"
              dangerouslySetInnerHTML={{ __html: pts.pop }}
            />
          </div>
        )}

        {showCursor && <CursorIcon x={curX} y={curY} press={press} />}
      </div>
    </div>
  );
};

// ============================================================================
// Beat 4a: Distortions Announced (stderr warning + →240 + SVG chevron)
// ============================================================================

const DistortionBeat: React.FC<{ frame: number }> = ({ frame }) => {
  const f = frame - B.distort[0];
  const dur = B.distort[1] - B.distort[0];
  const fadeIn = ramp(f, 0, 5);
  const fadeOut = 1 - ramp(f, dur - 5, dur);

  const chipText = assets.distortion.dist_compact_text;
  const arrowIdx = chipText.indexOf("→240");
  const chipMain = arrowIdx >= 0 ? chipText.slice(0, arrowIdx) : chipText;
  const chipTail = arrowIdx >= 0 ? chipText.slice(arrowIdx) : "→240";

  const warningText = assets.distortion.stderr_warning;
  const keyPhrase = "1 sample(s) (240) beyond 3×IQR clipped";
  const kpIdx = warningText.indexOf(keyPhrase);

  const badgeIn = ramp(f, 5, 11);
  const stderrIn = ramp(f, 9, 15);

  return (
    <div
      style={{
        position: "absolute",
        left: WIN.x,
        top: WIN.y,
        width: WIN.w,
        height: WIN.h,
        display: "flex",
        flexDirection: "column",
        gap: 18,
        opacity: fadeIn * fadeOut,
        fontFamily: SANS,
      }}
    >
      {/* Top card: Marked in every surface */}
      <div
        style={{
          background: C.panel,
          border: `1.5px solid ${C.line}`,
          borderRadius: 14,
          padding: "22px 26px",
          display: "flex",
          flexDirection: "column",
          gap: 18,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span
            style={{
              fontFamily: MONO,
              fontSize: 13,
              fontWeight: 700,
              color: C.amber,
              textTransform: "uppercase",
              letterSpacing: 1.1,
            }}
          >
            1 · Marked inside the chip
          </span>
          <span
            style={{
              fontFamily: MONO,
              fontSize: 12,
              color: C.muted,
            }}
          >
            rule #8: distortions are announced
          </span>
        </div>

        {/* Text surface callout */}
        <div
          style={{
            background: C.term,
            border: `1px solid ${C.line}`,
            borderRadius: 10,
            padding: "16px 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div
              style={{
                fontFamily: MONO,
                fontSize: 11.5,
                color: C.muted,
                marginBottom: 6,
                textTransform: "uppercase",
                letterSpacing: 0.8,
              }}
            >
              Plain text / ANSI / Markdown
            </div>
            <div style={{ fontFamily: MONO, fontSize: 22, color: C.ink }}>
              <span>{chipMain}</span>
              <span
                style={{
                  background: "#3B2A0F",
                  border: `2px solid ${C.amber}`,
                  color: C.amber,
                  fontWeight: 800,
                  borderRadius: 6,
                  padding: "1px 7px",
                  marginLeft: 2,
                }}
              >
                {chipTail}
              </span>
            </div>
          </div>
          <div
            style={{
              opacity: badgeIn,
              padding: "6px 11px",
              borderRadius: 8,
              background: "#261E14",
              border: `1px solid ${C.amber}`,
              color: C.amber,
              fontFamily: MONO,
              fontSize: 12,
              fontWeight: 700,
              textAlign: "right",
            }}
          >
            value printed
            <br />
            past brackets
          </div>
        </div>

        {/* SVG surface callout (exact 2x integer sizing: 32px fontSize -> 144x32 SVG) */}
        <div
          className="mc-page"
          data-mc-scheme="dark"
          style={{
            background: C.darkPage,
            border: `1px solid ${C.line}`,
            borderRadius: 10,
            padding: "18px 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <style>{assets.css}</style>
          <div>
            <div
              style={{
                fontFamily: MONO,
                fontSize: 11.5,
                color: C.muted,
                marginBottom: 8,
                textTransform: "uppercase",
                letterSpacing: 0.8,
              }}
            >
              HTML / SVG (currentColor)
            </div>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 12,
                fontSize: 32,
                color: C.darkInk,
                fontFamily: UI,
                fontVariantNumeric: "tabular-nums",
                position: "relative",
              }}
            >
              <span>med 151.0 ms</span>
              <span style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
                <Html html={assets.distortion.dist_svg} />
                {/* Crisp amber ring around the right-edge chevron */}
                <span
                  style={{
                    position: "absolute",
                    right: -4,
                    top: -2,
                    width: 24,
                    height: 36,
                    borderRadius: 6,
                    border: `2.5px solid ${C.amber}`,
                    opacity: badgeIn,
                  }}
                />
              </span>
            </div>
          </div>
          <div
            style={{
              opacity: badgeIn,
              padding: "6px 11px",
              borderRadius: 8,
              background: "#261E14",
              border: `1px solid ${C.amber}`,
              color: C.amber,
              fontFamily: MONO,
              fontSize: 12,
              fontWeight: 700,
              textAlign: "right",
            }}
          >
            edge chevron
            <br />
            marks clip
          </div>
        </div>
      </div>

      {/* Bottom card: Real stderr warning */}
      <div
        style={{
          flex: 1,
          background: C.term,
          border: `1.5px solid ${C.amber}`,
          borderRadius: 14,
          overflow: "hidden",
          opacity: stderrIn,
          transform: `translateY(${(1 - stderrIn) * 10}px)`,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            padding: "10px 18px",
            background: "#1B1A1F",
            borderBottom: `1px solid #3A3222`,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontFamily: MONO,
          }}
        >
          <span style={{ color: C.amber, fontSize: 13, fontWeight: 700 }}>
            2 · Named on stderr
          </span>
          <span
            style={{
              padding: "2px 9px",
              borderRadius: 999,
              background: "#2B1920",
              border: `1px solid ${C.red}`,
              color: C.red,
              fontSize: 11.5,
              fontWeight: 700,
            }}
          >
            --strict exits 1
          </span>
        </div>
        <div
          style={{
            padding: "18px 22px",
            fontFamily: MONO,
            fontSize: 14.5,
            lineHeight: 1.62,
            color: C.ink,
            whiteSpace: "pre-wrap",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            flex: 1,
          }}
        >
          <div>
            {kpIdx >= 0 ? (
              <>
                <span style={{ color: C.amber, fontWeight: 700 }}>
                  {warningText.slice(0, 18)}
                </span>
                <span style={{ color: C.muted }}>
                  {warningText.slice(18, kpIdx)}
                </span>
                <span
                  style={{
                    background: "#3B2A0F",
                    color: "#FDE68A",
                    fontWeight: 700,
                    padding: "1px 5px",
                    borderRadius: 4,
                  }}
                >
                  {keyPhrase}
                </span>
                <span style={{ color: C.ink }}>
                  {warningText.slice(kpIdx + keyPhrase.length)}
                </span>
              </>
            ) : (
              warningText
            )}
          </div>
          <div
            style={{
              paddingTop: 14,
              borderTop: `1px solid #1E293B`,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 13,
              color: C.muted,
            }}
          >
            <span>
              <span style={{ color: C.mint, fontWeight: 700 }}>$ </span>
              mintchip render report.txt --strict
            </span>
            <span style={{ color: C.red, fontWeight: 700 }}>
              stdout clean · warning on stderr · exit 1
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// Beat 4b: Crisp Closing End Card Lockup
// ============================================================================

const EndCard: React.FC<{ frame: number }> = ({ frame }) => {
  const f = frame - B.end[0];
  const fadeIn = ramp(f, 0, 7);
  const chipsIn = ramp(f, 4, 11);
  const ctaIn = ramp(f, 8, 15);

  const endChips = assets.end_chips as {
    kind: string;
    label: string;
    svg: string;
  }[];

  return (
    <AbsoluteFill
      style={{
        background: C.bg,
        alignItems: "center",
        justifyContent: "center",
        padding: "40px 64px",
        fontFamily: SANS,
        opacity: fadeIn,
      }}
    >
      <style>{assets.css}</style>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 24,
          maxWidth: 1180,
          width: "100%",
        }}
      >
        {/* Wordmark */}
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              background: C.mint,
            }}
          />
          <span
            style={{
              fontFamily: MONO,
              fontSize: 64,
              fontWeight: 800,
              color: C.ink,
              letterSpacing: -1.5,
              lineHeight: 1,
            }}
          >
            mintchip
          </span>
        </div>

        {/* Tagline */}
        <div
          style={{
            fontSize: 32,
            fontWeight: 750,
            color: C.mint,
            letterSpacing: -0.5,
          }}
        >
          One command. Every surface.
        </div>

        {/* Spec line */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            justifyContent: "center",
            fontFamily: MONO,
            fontSize: 17,
            color: C.muted,
          }}
        >
          <span>14 word-sized chips + shared-scale tables</span>
          <span style={{ color: C.line }}>·</span>
          <span style={{ color: C.ink, fontWeight: 600 }}>stdlib only</span>
          <span style={{ color: C.line }}>·</span>
          <span>text · ansi · md · html · svg</span>
        </div>

        {/* Live 4-chip dark-mode showcase strip */}
        <div
          className="mc-page"
          data-mc-scheme="dark"
          style={{
            display: "flex",
            gap: 12,
            justifyContent: "center",
            background: "transparent",
            opacity: chipsIn,
            transform: `translateY(${(1 - chipsIn) * 10}px)`,
            marginTop: 6,
          }}
        >
          {endChips.map((chip) => (
            <div
              key={chip.kind}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                padding: "11px 15px",
                borderRadius: 10,
                background: C.darkPage,
                border: `1.5px solid ${C.line}`,
                color: C.darkInk,
                fontFamily: UI,
                fontSize: 15.5,
                fontVariantNumeric: "tabular-nums",
                whiteSpace: "nowrap",
              }}
            >
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: 11.5,
                  fontWeight: 700,
                  color: C.mint,
                  background: "#132925",
                  padding: "2px 7px",
                  borderRadius: 5,
                }}
              >
                {chip.kind}
              </span>
              <span style={{ fontWeight: 600 }}>
                {chip.kind === "ci" ? "−29%" : chip.label}
              </span>
              <Html html={chip.svg} />
            </div>
          ))}
        </div>

        {/* CTA command box */}
        <div
          style={{
            marginTop: 10,
            opacity: ctaIn,
            transform: `translateY(${(1 - ctaIn) * 8}px)`,
            background: C.term,
            border: `2px solid ${C.mint}`,
            borderRadius: 12,
            padding: "14px 32px",
            fontFamily: MONO,
            fontSize: 24,
            fontWeight: 700,
            color: C.ink,
          }}
        >
          <span style={{ color: C.mint }}>$ </span>uvx mintchip guide
        </div>

        {/* Subtle footer */}
        <div
          style={{
            marginTop: 6,
            opacity: ctaIn,
            fontSize: 16.5,
            color: C.dim,
            fontWeight: 500,
          }}
        >
          Need full charts? Pairs with{" "}
          <span style={{ fontFamily: MONO, color: C.muted, fontWeight: 700 }}>
            mintfig
          </span>
          .
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ============================================================================
// Root Composition
// ============================================================================

export const MintchipOpener: React.FC = () => {
  const frame = useCurrentFrame();
  const isEnd = frame >= B.end[0];

  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {!isEnd && <Sidebar frame={frame} />}
      {within(frame, B.wall) && <WallOfNumbersCard frame={frame} />}
      {within(frame, B.term) && <TerminalBeat frame={frame} />}
      {within(frame, B.html) && <HtmlBeat frame={frame} />}
      {within(frame, B.distort) && <DistortionBeat frame={frame} />}
      {isEnd && <EndCard frame={frame} />}
    </AbsoluteFill>
  );
};

export const MintchipOpenerRoot: React.FC = () => (
  <Composition
    id="MintchipOpener"
    component={MintchipOpener}
    width={WIDTH}
    height={HEIGHT}
    fps={FPS}
    durationInFrames={DURATION}
  />
);

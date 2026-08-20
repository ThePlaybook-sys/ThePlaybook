/**
 * Structural, non-dismissible Demo Mode label (Mac's explicit
 * requirement) -- rendered once, here, by `app/demo/layout.tsx`, so every
 * page under `/demo` gets it automatically. No individual page ever
 * renders its own copy; that's exactly the bug this component exists to
 * make impossible.
 */
export function DemoModeBanner() {
  return (
    <div
      style={{
        background: "#7c2d12",
        color: "#fff7ed",
        padding: "0.5rem 1rem",
        fontFamily: "system-ui, sans-serif",
        fontSize: "0.85rem",
        fontWeight: 600,
        letterSpacing: "0.02em",
        textAlign: "center",
        position: "sticky",
        top: 0,
        zIndex: 1000,
      }}
    >
      DEMO MODE — SIMULATED DATA — NOT LIVE BETTING DATA
    </div>
  );
}

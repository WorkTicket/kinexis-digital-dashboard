import Link from "next/link";

export default function NotFound() {
  return (
    <html>
      <body
        style={{
          background: "#08090c",
          color: "#edeef2",
          fontFamily: "system-ui, sans-serif",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          margin: 0,
        }}
      >
        <div style={{ textAlign: "center" }}>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>
            Page not found
          </h1>
          <p style={{ color: "#6b7080", fontSize: "0.875rem", margin: "12px 0 0" }}>
            The page you&apos;re looking for doesn&apos;t exist.
          </p>
          <Link
            href="/"
            style={{
              display: "inline-block",
              marginTop: 20,
              color: "#c8cdd4",
              fontSize: "0.875rem",
              fontWeight: 500,
              textDecoration: "none",
            }}
          >
            Back to dashboard
          </Link>
        </div>
      </body>
    </html>
  );
}

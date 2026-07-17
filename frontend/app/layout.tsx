import type { Metadata, Viewport } from "next";
import { Plus_Jakarta_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import Script from "next/script";
import { AppProviders } from "@/components/AppProviders";
import { THEME_COLOR_DARK, THEME_COLOR_LIGHT } from "@/lib/brandColors";

const jakarta = Plus_Jakarta_Sans({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-ui",
  display: "swap",
});

const jakartaDisplay = Plus_Jakarta_Sans({
  weight: ["600", "700"],
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  weight: ["400", "500"],
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kinexis — Client Success Command",
  description: "Diagnose, fix, and grow client SEO & conversion performance",
  appleWebApp: {
    title: "Kinexis",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: THEME_COLOR_DARK },
    { media: "(prefers-color-scheme: light)", color: THEME_COLOR_LIGHT },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={cn(jakarta.variable, jakartaDisplay.variable, plexMono.variable, "font-sans")}
      suppressHydrationWarning
    >
      <head>
        <link rel="icon" type="image/svg+xml" href="/logo.svg" />
        <Script
          id="theme-initializer"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("kinexis-theme");if(t==="light")document.documentElement.setAttribute("data-theme","light")}catch(e){}})()`,
          }}
        />
      </head>
      <body className="font-ui antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}

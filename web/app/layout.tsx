import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Event Scraper — Speakhyve",
  description: "Discover and score speaker-booking events",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto max-w-6xl px-6 py-8">
          <header className="mb-8 flex items-baseline justify-between">
            <a href="/" className="text-xl font-semibold tracking-tight">
              Event Scraper
            </a>
            <span className="text-xs text-zinc-500">Speakhyve</span>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}

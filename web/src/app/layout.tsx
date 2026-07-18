import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aircraft Tracker",
  description: "Country-centric military aircraft fleet & procurement tracker",
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/countries", label: "Countries" },
  { href: "/aircraft", label: "Aircraft" },
  { href: "/weekly", label: "Weekly report" },
  { href: "/admin/review", label: "Review" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-200 antialiased">
        <nav className="border-b border-slate-800 bg-slate-950/80">
          <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
            <Link href="/" className="text-sm font-bold tracking-wide text-cyan-400">
              ✈ AIRCRAFT TRACKER
            </Link>
            <div className="flex gap-4">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href}
                      className="text-sm text-slate-400 hover:text-slate-100">
                  {n.label}
                </Link>
              ))}
            </div>
          </div>
        </nav>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-700">
          OSINT-based tracker — data extracted automatically from public news, verify before use.
        </footer>
      </body>
    </html>
  );
}

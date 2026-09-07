import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { DemoBanner } from "@/components/DemoBanner";

export const metadata: Metadata = {
  title: "BuildGate",
  description: "AI governance layer for engineering requests",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <DemoBanner />
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-semibold text-slate-900">
              BuildGate
            </Link>
            <nav className="flex gap-4 text-sm text-slate-600">
              <Link href="/requests" className="hover:text-slate-900">
                Requests
              </Link>
              <Link
                href="/requests/new"
                className="rounded-md bg-slate-900 px-3 py-1.5 text-white hover:bg-slate-700"
              >
                New Request
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}

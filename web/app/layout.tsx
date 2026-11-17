import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { NavLinks } from "@/components/NavLinks";
import { ThemeToggle } from "@/components/ThemeToggle";
import { REPO_URL, meta } from "@/lib/data";
import { THEME_SCRIPT } from "@/lib/theme";
import "./globals.css";

const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Baggage assistant evals",
  description: "A RAG assistant for Wizz Air baggage rules, and how it was measured: 325 questions, 3 answers each, every answer graded.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // The head script sets data-theme before React hydrates, hence the warning suppressed on <html>.
    // Font variables on <html>: --font-sans resolves there (:root), so on <body> they come too late.
    <html lang="en" className={`${geist.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="antialiased">
        <header className="sticky top-0 z-10 flex min-h-16 items-center border-b border-line bg-paper">
          <nav aria-label="Main" className="mx-auto flex w-full max-w-page flex-wrap items-center gap-x-6 gap-y-2 px-6 py-2">
            <Link href="/" className="mr-auto flex items-center gap-3 font-semibold text-ink hover:text-ink">
              <svg aria-hidden="true" width="28" height="28" viewBox="0 0 28 28" fill="none">
                {/* Whole-pixel geometry: 2px strokes centred on whole coordinates, 2px bars 2px apart. */}
                <path d="M11 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" className="stroke-accent" strokeWidth="2" strokeLinecap="round" />
                <rect x="4" y="8" width="20" height="16" rx="5" className="fill-accent-soft stroke-accent" strokeWidth="2" />
                <rect x="9" y="12" width="2" height="8" rx="1" className="fill-correct" />
                <rect x="13" y="12" width="2" height="8" rx="1" className="fill-correct" />
                <rect x="17" y="12" width="2" height="8" rx="1" className="fill-wrong" />
              </svg>
              Baggage assistant evals
            </Link>
            <NavLinks repoUrl={REPO_URL} />
            <ThemeToggle />
          </nav>
        </header>
        <main className="mx-auto max-w-page px-6 pt-16 pb-24">{children}</main>
        <footer className="border-t border-line text-sm text-muted">
          <div className="mx-auto flex max-w-page flex-wrap justify-between gap-x-6 gap-y-2 px-6 py-8">
            <p className="max-w-measure">
              A personal project, not affiliated with Wizz Air. Answers come from Wizz Air documents saved on{" "}
              {meta.snapshot} and are not official advice.
            </p>
            <p className="font-mono text-xs/5">Static results · no model calls</p>
          </div>
        </footer>
      </body>
    </html>
  );
}

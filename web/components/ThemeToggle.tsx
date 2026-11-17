"use client";

import { THEME_KEY } from "@/lib/theme";

function toggle() {
  const root = document.documentElement;
  const next = root.dataset.theme === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch {
    // Storage blocked (private window): the switch still works for this page view.
  }
}

/** The label names the theme a click switches to; CSS picks it, so server HTML needs no theme. */
export function ThemeToggle() {
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Switch between light and dark theme"
      className="flex min-h-11 cursor-pointer items-center gap-2 rounded-full border border-line-strong bg-surface px-4 text-sm font-medium text-ink"
    >
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" />
      </svg>
      <span className="dark:hidden">Dark</span>
      <span className="hidden dark:inline">Light</span>
    </button>
  );
}

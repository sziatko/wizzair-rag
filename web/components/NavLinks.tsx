"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINK = "flex min-h-11 items-center gap-1 rounded-md px-3 text-sm font-medium";
const ON = "bg-accent-soft text-accent hover:text-accent";
const OFF = "text-muted hover:text-ink";

export function NavLinks({ repoUrl }: { repoUrl: string }) {
  const path = usePathname();
  const links = [
    { href: "/", label: "Overview", current: path === "/" },
    { href: "/questions", label: "All questions", current: path !== "/" },
  ];
  return (
    <ul className="flex flex-wrap gap-1">
      {links.map((l) => (
        <li key={l.href}>
          <Link href={l.href} aria-current={l.current ? "page" : undefined} className={`${LINK} ${l.current ? ON : OFF}`}>
            {l.label}
          </Link>
        </li>
      ))}
      <li>
        <a href={repoUrl} className={`${LINK} ${OFF}`}>
          Code
          <svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 2h6v6M10 2 3 9" />
          </svg>
        </a>
      </li>
    </ul>
  );
}

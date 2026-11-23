"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { Logo } from "./Logo";

const NAV = [
  { href: "/", label: "Meetings" },
  { href: "/tasks", label: "Action items" },
  { href: "/assistant", label: "Assistant" },
  { href: "/search", label: "Search" },
  { href: "/extension", label: "Chrome extension" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { email, signOut } = useAuth();
  const active = (href: string) => (href === "/" ? pathname === "/" || pathname.startsWith("/meetings") : pathname.startsWith(href));

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[232px_1fr]">
      <aside className="border-b border-line bg-surface md:sticky md:top-0 md:flex md:h-dvh md:flex-col md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-5 py-4 md:py-5">
          <Link href="/" className="flex items-center gap-2 text-[17px] font-semibold tracking-tight">
            <Logo /> Minutes
          </Link>
          <Link href="/meetings/new" className="btn-primary md:hidden">New</Link>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:px-3 md:pb-0" aria-label="Main">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${active(n.href) ? "bg-canvas font-medium text-ink" : "text-muted hover:text-ink"}`}>
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="hidden px-3 pt-4 md:block">
          <Link href="/meetings/new" className="btn-primary w-full">New meeting</Link>
        </div>
        <div className="mt-auto hidden border-t border-line px-5 py-4 text-xs text-muted md:block">
          <p className="truncate" title={email ?? ""}>{email}</p>
          {email !== "local mode" && <button onClick={signOut} className="mt-1 underline underline-offset-2 hover:text-ink">Sign out</button>}
        </div>
      </aside>
      <main className="mx-auto w-full max-w-5xl px-4 py-6 md:px-10 md:py-10">{children}</main>
    </div>
  );
}

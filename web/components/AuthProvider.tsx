"use client";

import type { Session } from "@supabase/supabase-js";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { authEnabled, supabase } from "@/lib/supabase";

type AuthState = { ready: boolean; email: string | null; signOut: () => Promise<void> };
const AuthContext = createContext<AuthState>({ ready: false, email: null, signOut: async () => {} });
export const useAuth = () => useContext(AuthContext);

const PUBLIC_PATHS = ["/login", "/auth/callback"];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(!authEnabled);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setReady(true); });
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  useEffect(() => {
    if (!authEnabled || !ready) return;
    if (!session && !isPublic) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    if (session && pathname === "/login") router.replace("/");
  }, [ready, session, isPublic, pathname, router]);

  const value: AuthState = {
    ready,
    email: authEnabled ? session?.user.email ?? null : "local mode",
    signOut: async () => { await supabase?.auth.signOut(); router.replace("/login"); },
  };

  if (authEnabled && (!ready || (!session && !isPublic))) {
    return <div className="grid min-h-dvh place-items-center text-sm text-muted">Loading…</div>;
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

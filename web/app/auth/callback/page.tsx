"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { supabase } from "@/lib/supabase";

/** Supabase returns here after Google sign-in or email confirmation. */
export default function AuthCallback() {
  const router = useRouter();
  useEffect(() => {
    const next = new URLSearchParams(location.search).get("next") || "/";
    const code = new URLSearchParams(location.search).get("code");
    const done = () => router.replace(next.startsWith("/") ? next : "/");
    if (supabase && code) supabase.auth.exchangeCodeForSession(code).finally(done);
    else setTimeout(done, 300);
  }, [router]);
  return <div className="grid min-h-dvh place-items-center text-sm text-muted">Signing you in…</div>;
}

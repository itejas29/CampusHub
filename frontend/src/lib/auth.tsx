import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from "react";
import { api, tokenStore } from "@/lib/api";
import type {
  AuthResponse, CoordinationDomain, CurrentUser, Role,
} from "@/types";

interface AuthValue {
  user: CurrentUser | null;
  status: "loading" | "authenticated" | "anonymous";
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  refresh: () => Promise<void>;
  /** Mirrors the backend permission matrix served by /auth/me. */
  can: (permission: string) => boolean;
  hasRole: (...roles: Role[]) => boolean;
  /** True when this faculty actually mentors students on that internship type. */
  mentorsProgram: (type: string) => boolean;
  /** True when they coordinate the domain (any department). */
  coordinates: (domain: CoordinationDomain) => boolean;
  isStaff: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

const ADMIN_ROLES: Role[] = [
  "SUPER_ADMIN", "DEPARTMENT_ADMIN", "INTERNSHIP_COORDINATOR", "CLUB_ADMIN",
];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [status, setStatus] = useState<AuthValue["status"]>("loading");

  const load = useCallback(async () => {
    if (!tokenStore.access()) {
      setUser(null);
      setStatus("anonymous");
      return;
    }
    try {
      const me = await api.get<CurrentUser>("/auth/me");
      setUser(me);
      setStatus("authenticated");
    } catch {
      tokenStore.clear();
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // The api client fires this when a refresh attempt finally fails.
  useEffect(() => {
    function onSignedOut() {
      setUser(null);
      setStatus("anonymous");
    }
    window.addEventListener("campushub:signed-out", onSignedOut);
    return () => window.removeEventListener("campushub:signed-out", onSignedOut);
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const response = await api.post<AuthResponse>("/auth/login", { email, password });
    tokenStore.set(response.tokens.access_token, response.tokens.refresh_token);
    setUser(response.user);
    setStatus("authenticated");
  }, []);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthValue>(() => {
    const permissions = new Set(user?.permissions ?? []);
    const roles = new Set(user?.roles ?? []);
    const mentored = new Set(user?.faculty?.mentors_programs ?? []);
    const coordinated = new Set(
      (user?.faculty?.coordinations ?? []).map((c) => c.domain),
    );
    return {
      user,
      status,
      signIn,
      signOut,
      refresh: load,
      can: (permission) => permissions.has("*") || permissions.has(permission),
      hasRole: (...list) => list.some((role) => roles.has(role)),
      mentorsProgram: (type) => mentored.has(type),
      coordinates: (domain) => coordinated.has(domain),
      isStaff: Boolean(user && !(roles.size === 1 && roles.has("STUDENT"))),
      isAdmin: ADMIN_ROLES.some((role) => roles.has(role)),
    };
  }, [user, status, signIn, signOut, load]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

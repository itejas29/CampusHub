import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, tokenStore } from "@/lib/api";
import type {
  AuthResponse, CoordinationDomain, CurrentUser, Role,
} from "@/types";

interface AuthValue {
  user: CurrentUser | null;
  status: "loading" | "authenticated" | "anonymous";
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  /**
   * Who the last session belonged to, and whether it ended by signing out.
   * The sign-in page returns someone to the page they were on only when it
   * was their own session that lapsed — never the next person at the desk.
   */
  lastSession: () => { userId: number | null; signedOut: boolean };
  refresh: () => Promise<void>;
  /** Sets a new password. Every other session ends; this one carries on with
   *  the fresh tokens the server returns. Throws ApiError on refusal. */
  changePassword: (current: string, next: string) => Promise<void>;
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
  // Cached server data belongs to whoever fetched it. Left in place, the next
  // person signing in on this browser was briefly shown the last account's
  // lists and figures until each query refreshed.
  const queryClient = useQueryClient();
  const lastSessionRef = useRef<{ userId: number | null; signedOut: boolean }>(
    { userId: null, signedOut: false });

  const load = useCallback(async () => {
    if (!tokenStore.access()) {
      setUser(null);
      setStatus("anonymous");
      return;
    }
    try {
      const me = await api.get<CurrentUser>("/auth/me");
      lastSessionRef.current = { userId: me.id, signedOut: false };
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
    queryClient.clear();
    lastSessionRef.current = { userId: response.user.id, signedOut: false };
    setUser(response.user);
    setStatus("authenticated");
  }, [queryClient]);

  const changePassword = useCallback(async (current: string, next: string) => {
    const response = await api.post<{ tokens: AuthResponse["tokens"] }>(
      "/auth/change-password", { current_password: current, new_password: next });
    tokenStore.rotate(response.tokens.access_token, response.tokens.refresh_token);
    await load();
  }, [load]);

  const signOut = useCallback(() => {
    // A deliberate sign-out leaves nothing to return to: whoever signs in next
    // starts on their own dashboard, not the page the last person had open.
    lastSessionRef.current = { userId: null, signedOut: true };
    tokenStore.clear();
    queryClient.clear();
    setUser(null);
    setStatus("anonymous");
  }, [queryClient]);

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
      lastSession: () => lastSessionRef.current,
      refresh: load,
      changePassword,
      can: (permission) => permissions.has("*") || permissions.has(permission),
      hasRole: (...list) => list.some((role) => roles.has(role)),
      mentorsProgram: (type) => mentored.has(type),
      coordinates: (domain) => coordinated.has(domain),
      isStaff: Boolean(user && !(roles.size === 1 && roles.has("STUDENT"))),
      isAdmin: ADMIN_ROLES.some((role) => roles.has(role)),
    };
  }, [user, status, signIn, signOut, load, changePassword]);


  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import * as api from "@/lib/api/endpoints";
import { setCsrfToken, setUnauthorizedHandler } from "@/lib/api/client";
import type { MeResponse } from "@/lib/api/types";

interface AuthState {
  user: MeResponse | null;
  status: "loading" | "authenticated" | "anonymous";
  isAdmin: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const queryClient = useQueryClient();

  const clearLocalSession = useCallback(() => {
    setUser(null);
    setCsrfToken(null);
    setStatus("anonymous");
    // Drop every cached server value so no protected data survives sign-out.
    void queryClient.cancelQueries();
    queryClient.clear();
  }, [queryClient]);

  const refresh = useCallback(async () => {
    try {
      const me = await api.getMe();
      setCsrfToken(me.csrf_token);
      setUser(me);
      setStatus("authenticated");
    } catch {
      setUser(null);
      setCsrfToken(null);
      setStatus("anonymous");
    }
  }, []);

  // Bootstrap once on mount only — no interval refetch, so an idle session is
  // never kept alive by the frontend.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setUnauthorizedHandler(() => clearLocalSession());
    return () => setUnauthorizedHandler(null);
  }, [clearLocalSession]);

  const signIn = useCallback(async (username: string, password: string) => {
    const result = await api.login(username, password);
    setCsrfToken(result.csrf_token);
    setUser({ ...result });
    setStatus("authenticated");
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      clearLocalSession();
    }
  }, [clearLocalSession]);

  const value = useMemo<AuthState>(
    () => ({ user, status, isAdmin: user?.role === "admin", signIn, signOut, refresh }),
    [user, status, signIn, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

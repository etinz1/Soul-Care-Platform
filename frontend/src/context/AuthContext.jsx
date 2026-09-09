import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authApi, clearTokens, getStoredTokens, providersApi, storeTokens } from "../api/client.js";

const AuthContext = createContext(null);

/** Decodes the JWT payload for UI purposes only (role, sub) — never trust
 * this for authorization; the backend re-checks role on every request. */
function decodeJwtPayload(token) {
  try {
    const [, payload] = token.split(".");
    return JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [accessToken, setAccessToken] = useState(() => getStoredTokens().accessToken);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    // Tokens are read synchronously above; this just marks the initial
    // "do we have a session" check as done so routes can render.
    setInitializing(false);
  }, []);

  const user = useMemo(() => {
    if (!accessToken) return null;
    const claims = decodeJwtPayload(accessToken);
    if (!claims) return null;
    return { id: claims.sub, role: claims.role };
  }, [accessToken]);

  const login = useCallback(async (email, password) => {
    const tokens = await authApi.login(email, password);
    storeTokens(tokens);
    setAccessToken(tokens.access_token);
    return tokens;
  }, []);

  const register = useCallback(async (email, password) => {
    const tokens = await authApi.register(email, password);
    storeTokens(tokens);
    setAccessToken(tokens.access_token);
    return tokens;
  }, []);

  // Provider self-onboarding (POST /providers/onboard) returns its tokens
  // nested under `tokens` rather than at the top level like login/register —
  // see ProviderOnboardResponse in backend/app/schemas.py — so this can't
  // just reuse `register` above.
  const onboardProvider = useCallback(async (payload) => {
    const result = await providersApi.onboard(payload);
    storeTokens(result.tokens);
    setAccessToken(result.tokens.access_token);
    return result;
  }, []);

  const logout = useCallback(async () => {
    const { refreshToken } = getStoredTokens();
    if (refreshToken) await authApi.logout(refreshToken);
    clearTokens();
    setAccessToken(null);
  }, []);

  // If the API client had to clear tokens after a failed refresh, the next
  // render should reflect "logged out" — cheap poll on focus is enough for
  // this app's needs rather than wiring a pub/sub for one edge case.
  useEffect(() => {
    function syncFromStorage() {
      const current = getStoredTokens().accessToken;
      setAccessToken((prev) => (prev !== current ? current : prev));
    }
    window.addEventListener("storage", syncFromStorage);
    window.addEventListener("focus", syncFromStorage);
    return () => {
      window.removeEventListener("storage", syncFromStorage);
      window.removeEventListener("focus", syncFromStorage);
    };
  }, []);

  const value = { user, initializing, login, register, onboardProvider, logout, isAuthenticated: Boolean(user) };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

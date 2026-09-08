/**
 * Thin fetch wrapper for the Soul Care Platform API.
 *
 * Tokens live in localStorage (`sc_access_token` / `sc_refresh_token`) so a
 * page reload doesn't lose the session — this is a real browser app, not
 * an inline preview, so localStorage is the right place for it (see
 * AuthContext for the load/clear lifecycle).
 *
 * On a 401 from an authenticated request, this makes ONE attempt to
 * refresh the access token via POST /auth/refresh and retries the original
 * request once. If the refresh itself fails, it clears stored tokens and
 * raises an ApiError with status 401 so the caller (AuthContext) can route
 * back to /login. This module never redirects itself — it has no
 * knowledge of routing.
 */

const ACCESS_TOKEN_KEY = "sc_access_token";
const REFRESH_TOKEN_KEY = "sc_refresh_token";

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function getStoredTokens() {
  return {
    accessToken: localStorage.getItem(ACCESS_TOKEN_KEY),
    refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY),
  };
}

export function storeTokens({ access_token, refresh_token }) {
  if (access_token) localStorage.setItem(ACCESS_TOKEN_KEY, access_token);
  if (refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

function getApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
}

async function doFetch(path, { method = "GET", body, auth = true, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  const accessToken = token ?? getStoredTokens().accessToken;
  if (auth && accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 204) return null;

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json().catch(() => null) : null;

  if (!response.ok) {
    throw new ApiError(payload?.detail || `Request failed (${response.status})`, response.status, payload);
  }
  return payload;
}

async function refreshAccessToken() {
  const { refreshToken } = getStoredTokens();
  if (!refreshToken) throw new ApiError("No refresh token available", 401);

  const tokens = await doFetch("/api/v1/auth/refresh", {
    method: "POST",
    body: { refresh_token: refreshToken },
    auth: false,
  });
  storeTokens(tokens);
  return tokens;
}

/**
 * Authenticated request with one automatic refresh-and-retry on 401.
 * Use this for everything except register/login/refresh themselves.
 */
export async function apiRequest(path, options = {}) {
  try {
    return await doFetch(path, options);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401 && options.auth !== false) {
      try {
        const { access_token } = await refreshAccessToken();
        return await doFetch(path, { ...options, token: access_token });
      } catch (refreshErr) {
        clearTokens();
        throw refreshErr;
      }
    }
    throw err;
  }
}

// --- Auth ---
export const authApi = {
  register: (email, password) => doFetch("/api/v1/auth/register", { method: "POST", body: { email, password }, auth: false }),
  login: (email, password) => doFetch("/api/v1/auth/login", { method: "POST", body: { email, password }, auth: false }),
  logout: (refreshToken) =>
    doFetch("/api/v1/auth/logout", { method: "POST", body: { refresh_token: refreshToken } }).catch(() => null),
};

// --- Clients ---
export const clientsApi = {
  getMe: () => apiRequest("/api/v1/clients/me"),
  updateMe: (patch) => apiRequest("/api/v1/clients/me", { method: "PATCH", body: patch }),
};

// --- Intake ---
export const intakeApi = {
  createDraft: (clientId) => apiRequest("/api/v1/intake", { method: "POST", body: { client_id: clientId } }),
  get: (intakeId) => apiRequest(`/api/v1/intake/${intakeId}`),
  submit: (intakeId, payload) => apiRequest(`/api/v1/intake/${intakeId}/submit`, { method: "POST", body: payload }),
};

// --- Scheduling / prayer / CRM reads (dashboard summary tiles) ---
export const schedulingApi = {
  listSessions: () => apiRequest("/api/v1/scheduling/sessions"),
  listPrayerRequests: () => apiRequest("/api/v1/scheduling/prayer-requests"),
};

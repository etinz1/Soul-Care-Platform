import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";

/** Builds a syntactically-valid (unsigned) JWT shape so AuthContext's
 * client-side decode (used only for UI role display, never for auth) can
 * read a `role` claim out of it. */
function fakeAccessToken(role) {
  const header = btoa(JSON.stringify({ alg: "none", typ: "JWT" }));
  const payload = btoa(JSON.stringify({ sub: "11111111-1111-1111-1111-111111111111", role }));
  return `${header}.${payload}.fake-signature`;
}

function jsonResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  });
}

describe("App — login flow", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("redirects an unauthenticated visitor to /login", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });

  it("logs in and reaches the client dashboard", async () => {
    const user = userEvent.setup();
    const tokens = { access_token: fakeAccessToken("client"), refresh_token: "refresh-abc", token_type: "bearer" };

    vi.spyOn(global, "fetch").mockImplementation((url) => {
      const path = String(url);
      if (path.endsWith("/api/v1/auth/login")) return jsonResponse(tokens);
      if (path.endsWith("/api/v1/clients/me")) {
        return jsonResponse({
          client_id: "22222222-2222-2222-2222-222222222222",
          user_id: "11111111-1111-1111-1111-111111111111",
          coach_id: null,
          church_sponsor_id: null,
          date_of_birth: null,
          emergency_contact: null,
          created_at: "2026-01-01T00:00:00",
        });
      }
      if (path.endsWith("/api/v1/scheduling/sessions")) return jsonResponse([]);
      if (path.endsWith("/api/v1/scheduling/prayer-requests")) return jsonResponse([]);
      return jsonResponse({ detail: `unhandled path in test: ${path}` }, 404);
    });

    render(<App />);

    await user.type(screen.getByLabelText(/email/i), "client@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "correcthorsebattery");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText(/your profile/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /start intake/i })).toBeInTheDocument();
  });
});

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
      if (path.endsWith("/api/v1/referrals")) return jsonResponse([]);
      if (path.endsWith("/api/v1/scripture/deliveries")) return jsonResponse([]);
      if (path.endsWith("/api/v1/providers/directory")) return jsonResponse([]);
      return jsonResponse({ detail: `unhandled path in test: ${path}` }, 404);
    });

    render(<App />);

    await user.type(screen.getByLabelText(/email/i), "client@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "correcthorsebattery");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText(/your profile/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /start intake/i })).toBeInTheDocument();
    expect(screen.getByText(/scripture for you/i)).toBeInTheDocument();
    expect(screen.getByText(/request a clinical referral/i)).toBeInTheDocument();
  });

  it("logs in as a coach and reaches the coach dashboard", async () => {
    const user = userEvent.setup();
    const tokens = { access_token: fakeAccessToken("coach"), refresh_token: "refresh-coach", token_type: "bearer" };

    vi.spyOn(global, "fetch").mockImplementation((url) => {
      const path = String(url);
      if (path.endsWith("/api/v1/auth/login")) return jsonResponse(tokens);
      if (path.endsWith("/api/v1/crm/clients")) {
        return jsonResponse([
          {
            client_id: "33333333-3333-3333-3333-333333333333",
            email: "client-a@example.com",
            coach_id: "44444444-4444-4444-4444-444444444444",
            church_sponsor_id: null,
            created_at: "2026-01-01T00:00:00",
          },
        ]);
      }
      if (path.endsWith("/api/v1/scheduling/sessions")) return jsonResponse([]);
      if (path.endsWith("/api/v1/scheduling/prayer-requests")) return jsonResponse([]);
      return jsonResponse({ detail: `unhandled path in test: ${path}` }, 404);
    });

    render(<App />);
    await user.type(screen.getByLabelText(/email/i), "coach@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "correcthorsebattery");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText(/your caseload/i)).toBeInTheDocument());
    // The client's email appears both in the roster row and the "schedule a
    // session" dropdown, so assert presence rather than a single match.
    expect(screen.getAllByText(/client-a@example.com/i).length).toBeGreaterThan(0);
  });

  it("logs in as a provider and reaches the provider dashboard", async () => {
    const user = userEvent.setup();
    const tokens = { access_token: fakeAccessToken("provider"), refresh_token: "refresh-provider", token_type: "bearer" };

    vi.spyOn(global, "fetch").mockImplementation((url) => {
      const path = String(url);
      if (path.endsWith("/api/v1/auth/login")) return jsonResponse(tokens);
      if (path.endsWith("/api/v1/providers/me")) {
        return jsonResponse({
          provider_id: "55555555-5555-5555-5555-555555555555",
          email: "provider@example.com",
          provider_type: "psychiatrist",
          license_state: "OK",
          vetting_status: "approved",
          accepting_referrals: true,
        });
      }
      if (path.endsWith("/api/v1/referrals")) return jsonResponse([]);
      if (path.endsWith("/api/v1/scheduling/sessions")) return jsonResponse([]);
      return jsonResponse({ detail: `unhandled path in test: ${path}` }, 404);
    });

    render(<App />);
    await user.type(screen.getByLabelText(/email/i), "provider@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "correcthorsebattery");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText(/your provider profile/i)).toBeInTheDocument());
    expect(screen.getByText(/psychiatrist/i)).toBeInTheDocument();
  });

  it("logs in as a platform admin and reaches the admin dashboard", async () => {
    const user = userEvent.setup();
    const tokens = { access_token: fakeAccessToken("platform_admin"), refresh_token: "refresh-admin", token_type: "bearer" };

    vi.spyOn(global, "fetch").mockImplementation((url) => {
      const path = String(url);
      if (path.endsWith("/api/v1/auth/login")) return jsonResponse(tokens);
      if (path.endsWith("/api/v1/providers")) return jsonResponse([]);
      if (path.endsWith("/api/v1/coaches")) return jsonResponse([]);
      if (path.endsWith("/api/v1/church")) return jsonResponse([]);
      if (path.endsWith("/api/v1/crm/clients")) return jsonResponse([]);
      if (path.endsWith("/api/v1/church/invoices")) return jsonResponse([]);
      return jsonResponse({ detail: `unhandled path in test: ${path}` }, 404);
    });

    render(<App />);
    await user.type(screen.getByLabelText(/email/i), "admin@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "correcthorsebattery");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText(/provider vetting/i)).toBeInTheDocument());
    expect(screen.getByText(/^coaches$/i)).toBeInTheDocument();
    expect(screen.getByText(/^churches$/i)).toBeInTheDocument();
  });

  it("logs in as a church admin and reaches the church dashboard", async () => {
    const user = userEvent.setup();
    const tokens = { access_token: fakeAccessToken("church_admin"), refresh_token: "refresh-church", token_type: "bearer" };

    vi.spyOn(global, "fetch").mockImplementation((url) => {
      const path = String(url);
      if (path.endsWith("/api/v1/auth/login")) return jsonResponse(tokens);
      if (path.endsWith("/api/v1/church/me")) {
        return jsonResponse({
          church_id: "66666666-6666-6666-6666-666666666666",
          name: "Grace Fellowship",
          billing_email: "billing@gracefellowship.example",
          primary_contact_user_id: "11111111-1111-1111-1111-111111111111",
          created_at: "2026-01-01T00:00:00",
        });
      }
      if (path.endsWith("/api/v1/church/sponsorships")) return jsonResponse([]);
      if (path.endsWith("/api/v1/church/invoices")) return jsonResponse([]);
      return jsonResponse({ detail: `unhandled path in test: ${path}` }, 404);
    });

    render(<App />);
    await user.type(screen.getByLabelText(/email/i), "church-admin@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "correcthorsebattery");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText(/grace fellowship/i)).toBeInTheDocument());
    expect(screen.getByText(/no active sponsorships yet/i)).toBeInTheDocument();
  });
});

describe("App — provider self-onboarding", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submits the onboarding form and reaches the provider dashboard", async () => {
    const user = userEvent.setup();
    const tokens = { access_token: fakeAccessToken("provider"), refresh_token: "refresh-onboard", token_type: "bearer" };

    vi.spyOn(global, "fetch").mockImplementation((url, options = {}) => {
      const path = String(url);
      if (path.endsWith("/api/v1/providers/onboard")) {
        expect(JSON.parse(options.body)).toMatchObject({
          email: "new-provider@example.com",
          provider_type: "psychiatrist",
          license_number: "OK-9999",
          license_state: "OK",
        });
        return jsonResponse({
          provider_id: "77777777-7777-7777-7777-777777777777",
          vetting_status: "pending",
          accepting_referrals: false,
          tokens,
        }, 201);
      }
      if (path.endsWith("/api/v1/providers/me")) {
        return jsonResponse({
          provider_id: "77777777-7777-7777-7777-777777777777",
          email: "new-provider@example.com",
          provider_type: "psychiatrist",
          license_state: "OK",
          vetting_status: "pending",
          accepting_referrals: false,
        });
      }
      if (path.endsWith("/api/v1/referrals")) return jsonResponse([]);
      if (path.endsWith("/api/v1/scheduling/sessions")) return jsonResponse([]);
      return jsonResponse({ detail: `unhandled path in test: ${path}` }, 404);
    });

    render(<App />);
    await user.click(screen.getByRole("link", { name: /apply here/i }));

    await user.type(screen.getByLabelText(/^email$/i), "new-provider@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "correcthorsebattery");
    await user.type(screen.getByLabelText(/license number/i), "OK-9999");
    await user.type(screen.getByLabelText(/^state$/i), "ok");
    await user.click(screen.getByRole("button", { name: /submit for review/i }));

    await waitFor(() => expect(screen.getByText(/your provider profile/i)).toBeInTheDocument());
    expect(screen.getByText(/you can't accept referrals until/i)).toBeInTheDocument();
  });
});

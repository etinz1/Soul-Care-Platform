import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

/**
 * Bold "entry point" treatment (deep purple/burgundy, crisp white/black,
 * a heavy display serif for the headline) — see RegisterPage.jsx for the
 * matching sibling and NavBar.jsx for the same palette carried into the
 * portal masthead. Dashboards intentionally stay on the plain slate/white
 * utility styling; this bold identity is scoped to login/register/masthead
 * only, by design.
 */
export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Could not sign in. Please check your email and password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <div className="relative overflow-hidden bg-gradient-to-br from-brand-purple via-brand-purpledark to-brand-ink text-white flex items-center justify-center px-8 py-16 md:w-1/2 md:min-h-screen">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rotate-12 bg-brand-crimson/30 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-32 -left-16 h-80 w-80 -rotate-12 bg-brand-burgundy/40 blur-3xl"
        />
        <div className="relative max-w-md">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-white/70">Soul Care Platform</p>
          <h1 className="mt-4 font-display text-4xl md:text-5xl font-black leading-[1.05] tracking-tight">
            You don't carry this alone.
          </h1>
          <p className="mt-5 text-white/80 text-base leading-relaxed">
            Coaching, clinical referrals, prayer, and church support — one platform built for Christian mental
            health care, without compromising either half of that word.
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center bg-white px-4 py-16">
        <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-crimson">Welcome back</p>
            <h2 className="mt-1 font-display text-3xl font-bold text-black">Sign in</h2>
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-crimson focus:border-brand-crimson"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-crimson focus:border-brand-crimson"
            />
          </div>

          {error && (
            <div role="alert" className="rounded-md bg-red-50 border border-red-300 text-red-800 p-3 text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-brand-ink text-white py-3 font-semibold tracking-wide hover:bg-brand-crimson transition-colors disabled:opacity-50"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>

          <p className="text-sm text-center text-slate-500">
            New here?{" "}
            <Link to="/register" className="font-medium text-brand-crimson hover:text-brand-burgundy">
              Create an account
            </Link>
          </p>
          <p className="text-xs text-center text-slate-400">
            Clinical provider?{" "}
            <Link to="/provider-onboarding" className="underline hover:text-slate-600">
              Apply here
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

/**
 * Public self-registration is client-only (see backend/app/api/v1/auth.py's
 * docstring) — coaches, providers, and admins are provisioned separately.
 *
 * Bold "entry point" treatment matching LoginPage.jsx — see that file's
 * comment for the design scope (login/register/masthead only).
 */
export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }

    setSubmitting(true);
    try {
      await register(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Could not create your account. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <div className="relative overflow-hidden bg-gradient-to-br from-brand-burgundy via-brand-purpledark to-brand-ink text-white flex items-center justify-center px-8 py-16 md:w-1/2 md:min-h-screen">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-20 -top-28 h-72 w-72 rotate-12 bg-brand-purple/40 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 -right-16 h-80 w-80 -rotate-12 bg-brand-crimson/30 blur-3xl"
        />
        <div className="relative max-w-md">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-white/70">Soul Care Platform</p>
          <h1 className="mt-4 font-display text-4xl md:text-5xl font-black leading-[1.05] tracking-tight">
            Start where you are.
          </h1>
          <p className="mt-5 text-white/80 text-base leading-relaxed">
            A short intake, a coach who's paying attention, and a clear path to clinical care if you need it —
            all in one account.
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center bg-white px-4 py-16">
        <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-crimson">Get started</p>
            <h2 className="mt-1 font-display text-3xl font-bold text-black">Create your account</h2>
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
              minLength={12}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-crimson focus:border-brand-crimson"
            />
            <p className="text-xs text-slate-500 mt-1">At least 12 characters.</p>
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
            {submitting ? "Creating account…" : "Create account"}
          </button>

          <p className="text-sm text-center text-slate-500">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-brand-crimson hover:text-brand-burgundy">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}

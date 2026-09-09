import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

const PROVIDER_TYPES = [
  { value: "psychiatrist", label: "Psychiatrist" },
  { value: "licensed_counselor", label: "Licensed counselor" },
  { value: "addiction_specialist", label: "Addiction specialist" },
];

/**
 * Public self-onboarding for clinical providers (POST /providers/onboard).
 * Unlike client registration, this does NOT grant network membership —
 * it creates the account plus a `pending` provider row; a platform admin
 * still has to approve it (AdminDashboardPage's vetting queue) before the
 * provider can receive referrals. See backend/app/api/v1/providers.py.
 */
export default function ProviderOnboardingPage() {
  const { onboardProvider } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [providerType, setProviderType] = useState("psychiatrist");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [licenseState, setLicenseState] = useState("");
  const [npiNumber, setNpiNumber] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }
    if (licenseState.trim().length !== 2) {
      setError("License state must be a 2-letter abbreviation (e.g. OK).");
      return;
    }

    setSubmitting(true);
    try {
      await onboardProvider({
        email,
        password,
        provider_type: providerType,
        license_number: licenseNumber.trim(),
        license_state: licenseState.trim(),
        npi_number: npiNumber.trim() || undefined,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Could not create your provider account. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4 py-16">
      <div className="w-full max-w-md space-y-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">Soul Care Platform</p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">Join as a clinical provider</h1>
          <p className="mt-2 text-sm text-slate-600">
            Creating an account starts the vetting process — you won't be visible to clients or able to accept
            referrals until a platform admin reviews and approves your credentials.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white border border-slate-200 rounded-lg p-6 space-y-4">
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
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
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
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
            <p className="text-xs text-slate-500 mt-1">At least 12 characters.</p>
          </div>

          <div>
            <label htmlFor="providerType" className="block text-sm font-medium text-slate-700 mb-1">
              Provider type
            </label>
            <select
              id="providerType"
              value={providerType}
              onChange={(e) => setProviderType(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {PROVIDER_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label htmlFor="licenseNumber" className="block text-sm font-medium text-slate-700 mb-1">
                License number
              </label>
              <input
                id="licenseNumber"
                type="text"
                required
                value={licenseNumber}
                onChange={(e) => setLicenseNumber(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <div className="w-24">
              <label htmlFor="licenseState" className="block text-sm font-medium text-slate-700 mb-1">
                State
              </label>
              <input
                id="licenseState"
                type="text"
                required
                maxLength={2}
                placeholder="OK"
                value={licenseState}
                onChange={(e) => setLicenseState(e.target.value.toUpperCase())}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm uppercase"
              />
            </div>
          </div>

          <div>
            <label htmlFor="npi" className="block text-sm font-medium text-slate-700 mb-1">
              NPI number <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              id="npi"
              type="text"
              value={npiNumber}
              onChange={(e) => setNpiNumber(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
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
            className="w-full rounded-md bg-slate-900 text-white py-2.5 font-medium disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit for review"}
          </button>

          <p className="text-sm text-center text-slate-500">
            Not a provider?{" "}
            <Link to="/register" className="font-medium text-slate-700 underline">
              Create a client account
            </Link>{" "}
            or{" "}
            <Link to="/login" className="font-medium text-slate-700 underline">
              sign in
            </Link>
            .
          </p>
        </form>
      </div>
    </div>
  );
}

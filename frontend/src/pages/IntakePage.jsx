import { useEffect, useState } from "react";
import { clientsApi, intakeApi, getStoredTokens } from "../api/client.js";
import IntakeForm from "../components/IntakeForm.jsx";

/**
 * Wires the standalone IntakeForm (see its own docstring) to a real
 * client_id and a freshly-created draft intake_id. IntakeForm keeps its
 * own simple fetch-with-authToken interface rather than going through
 * api/client.js's refresh-and-retry logic — a 15-minute access token is
 * expected to outlive filling out this one form.
 */
export default function IntakePage() {
  const [clientId, setClientId] = useState(null);
  const [intakeId, setIntakeId] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const profile = await clientsApi.getMe();
        if (cancelled) return;
        setClientId(profile.client_id);

        const draft = await intakeApi.createDraft(profile.client_id);
        if (cancelled) return;
        setIntakeId(draft.intake_id);
      } catch (err) {
        if (!cancelled) setError(err.message || "Could not start your intake. Please try again.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
  const { accessToken } = getStoredTokens();

  if (error) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <div role="alert" className="rounded-md bg-red-50 border border-red-300 text-red-800 p-3 text-sm">
          {error}
        </div>
      </div>
    );
  }

  if (!clientId || !intakeId) {
    return <div className="max-w-2xl mx-auto p-6 text-slate-500">Preparing your intake…</div>;
  }

  return <IntakeForm clientId={clientId} intakeId={intakeId} apiBaseUrl={apiBaseUrl} authToken={accessToken} />;
}

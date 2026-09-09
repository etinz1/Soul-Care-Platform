import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { clientsApi, consentsApi, providersApi, referralsApi, schedulingApi, scriptureApi, ApiError } from "../api/client.js";

function ProfileForm({ profile, onSaved }) {
  const [dateOfBirth, setDateOfBirth] = useState(profile.date_of_birth || "");
  const [emergencyContact, setEmergencyContact] = useState(profile.emergency_contact || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      const patch = {};
      if (dateOfBirth) patch.date_of_birth = dateOfBirth;
      if (emergencyContact) patch.emergency_contact = emergencyContact;
      const updated = await clientsApi.updateMe(patch);
      onSaved(updated);
      setSaved(true);
    } catch (err) {
      setError(err.message || "Could not save your profile.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label htmlFor="dob" className="block text-sm font-medium text-slate-700 mb-1">
          Date of birth
        </label>
        <input
          id="dob"
          type="text"
          placeholder="YYYY-MM-DD"
          value={dateOfBirth}
          onChange={(e) => setDateOfBirth(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
      <div>
        <label htmlFor="emergency" className="block text-sm font-medium text-slate-700 mb-1">
          Emergency contact
        </label>
        <input
          id="emergency"
          type="text"
          placeholder="Name, phone number"
          value={emergencyContact}
          onChange={(e) => setEmergencyContact(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {saved && <p className="text-sm text-emerald-700">Saved.</p>}
      <button
        type="submit"
        disabled={saving}
        className="rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save profile"}
      </button>
    </form>
  );
}

function NewPrayerRequestForm({ clientId, onSubmitted }) {
  const [requestText, setRequestText] = useState("");
  const [urgency, setUrgency] = useState("routine");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!requestText.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await schedulingApi.createPrayerRequest({
        client_id: clientId,
        request_text: requestText.trim(),
        urgency,
      });
      setRequestText("");
      setUrgency("routine");
      onSubmitted();
    } catch (err) {
      setError(err.message || "Could not submit your prayer request.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 mb-4">
      <textarea
        value={requestText}
        onChange={(e) => setRequestText(e.target.value)}
        placeholder="Share what you'd like prayer for…"
        rows={2}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
      />
      <div className="flex items-center gap-2">
        <select
          value={urgency}
          onChange={(e) => setUrgency(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-xs"
        >
          <option value="routine">Routine</option>
          <option value="urgent">Urgent</option>
          <option value="immediate">Immediate</option>
        </select>
        <button
          type="submit"
          disabled={saving || !requestText.trim()}
          className="rounded-md bg-slate-900 text-white px-3 py-1.5 text-xs font-medium disabled:opacity-50"
        >
          {saving ? "Submitting…" : "Submit prayer request"}
        </button>
      </div>
      {error && <p className="text-xs text-red-700">{error}</p>}
    </form>
  );
}

function ScriptureSection() {
  const [deliveries, setDeliveries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    scriptureApi
      .listDeliveries()
      .then((data) => {
        if (!cancelled) setDeliveries(data || []);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return null;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="font-semibold text-lg mb-2">Scripture for you</h2>
      {deliveries.length === 0 ? (
        <p className="text-sm text-slate-500">
          Nothing here yet — scripture reflections are shared with you after you complete an intake.
        </p>
      ) : (
        <ul className="space-y-3">
          {deliveries.map((d) => (
            <li key={d.delivery_id} className="border-l-2 border-slate-200 pl-3">
              <p className="text-sm font-medium text-slate-900">
                {d.reference} <span className="text-xs font-normal text-slate-400">({d.translation})</span>
              </p>
              <p className="text-sm text-slate-700 italic">"{d.verse_text}"</p>
              {d.reflection_text && <p className="text-xs text-slate-500 mt-1">{d.reflection_text}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RequestReferralPanel({ clientId, referrals, onChanged }) {
  const [providers, setProviders] = useState([]);
  const [providerId, setProviderId] = useState("");
  const [signatureName, setSignatureName] = useState("");
  const [shareClinicalSummary, setShareClinicalSummary] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [loadingProviders, setLoadingProviders] = useState(true);

  useEffect(() => {
    let cancelled = false;
    providersApi
      .directory()
      .then((data) => {
        if (!cancelled) setProviders(data || []);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoadingProviders(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!providerId || !signatureName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      // Step 1: sign a release-of-information consent scoped to this
      // provider — a referral cannot exist without one (see
      // backend/app/api/v1/referrals.py).
      const consent = await consentsApi.create({
        client_id: clientId,
        discloses_to_provider_id: providerId,
        scope: { clinical_summary: shareClinicalSummary },
        typed_signature_name: signatureName.trim(),
        expires_in_days: 90,
      });
      // Step 2: request the referral itself, referencing that consent.
      await referralsApi.create({
        client_id: clientId,
        provider_id: providerId,
        consent_id: consent.consent_id,
        referral_type: "standard",
      });
      setProviderId("");
      setSignatureName("");
      onChanged();
    } catch (err) {
      setError(err.message || "Could not submit your referral request.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
      <div>
        <h2 className="font-semibold text-lg mb-1">Request a clinical referral</h2>
        <p className="text-sm text-slate-600">
          Browse licensed providers currently accepting new clients, sign a release of information, and request a
          referral. This is separate from any crisis routing, which happens automatically during intake.
        </p>
      </div>

      {referrals.length > 0 && (
        <ul className="text-sm divide-y divide-slate-100">
          {referrals.map((r) => (
            <li key={r.referral_id} className="py-2">
              {r.referral_type} referral — {r.status}
            </li>
          ))}
        </ul>
      )}

      {loadingProviders ? (
        <p className="text-sm text-slate-500">Loading providers…</p>
      ) : providers.length === 0 ? (
        <p className="text-sm text-slate-500">No providers are currently accepting referrals.</p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label htmlFor="provider" className="block text-sm font-medium text-slate-700 mb-1">
              Provider
            </label>
            <select
              id="provider"
              value={providerId}
              onChange={(e) => setProviderId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Select a provider…</option>
              {providers.map((p) => (
                <option key={p.provider_id} value={p.provider_id}>
                  {p.provider_type.replace(/_/g, " ")} — {p.license_state}
                </option>
              ))}
            </select>
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={shareClinicalSummary}
              onChange={(e) => setShareClinicalSummary(e.target.checked)}
            />
            Share my clinical intake summary with this provider
          </label>

          <div>
            <label htmlFor="signature" className="block text-sm font-medium text-slate-700 mb-1">
              Type your full legal name to sign this release of information
            </label>
            <input
              id="signature"
              type="text"
              value={signatureName}
              onChange={(e) => setSignatureName(e.target.value)}
              placeholder="Full legal name"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>

          {error && <p className="text-sm text-red-700">{error}</p>}

          <button
            type="submit"
            disabled={saving || !providerId || !signatureName.trim()}
            className="rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {saving ? "Submitting…" : "Sign consent & request referral"}
          </button>
        </form>
      )}
    </div>
  );
}

export default function ClientDashboardPage() {
  const [profile, setProfile] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [prayerRequests, setPrayerRequests] = useState([]);
  const [referrals, setReferrals] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadAll() {
    try {
      const [profileData, sessionsData, prayerData, referralsData] = await Promise.all([
        clientsApi.getMe(),
        schedulingApi.listSessions().catch(() => []),
        schedulingApi.listPrayerRequests().catch(() => []),
        referralsApi.list().catch(() => []),
      ]);
      setProfile(profileData);
      setSessions(sessionsData || []);
      setPrayerRequests(prayerData || []);
      setReferrals(referralsData || []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your dashboard.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) return <div className="max-w-2xl mx-auto p-6 text-slate-500">Loading…</div>;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      {error && (
        <div role="alert" className="rounded-md bg-red-50 border border-red-300 text-red-800 p-3 text-sm">
          {error}
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-3">Your profile</h2>
        {profile && <ProfileForm profile={profile} onSaved={setProfile} />}
        {profile && !profile.coach_id && (
          <p className="text-sm text-slate-500 mt-3">
            You haven't been matched with a coach yet — this happens once your care team reviews your intake.
          </p>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-2">Get started</h2>
        <p className="text-sm text-slate-600 mb-3">
          Complete your intake so your coach and, if needed, a licensed clinical partner can best support you.
        </p>
        <Link
          to="/intake"
          className="inline-block rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-medium"
        >
          Start intake
        </Link>
      </div>

      <ScriptureSection />

      {profile && <RequestReferralPanel clientId={profile.client_id} referrals={referrals} onChanged={loadAll} />}

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-2">Sessions</h2>
        {sessions.length === 0 ? (
          <p className="text-sm text-slate-500">No sessions scheduled yet.</p>
        ) : (
          <ul className="text-sm text-slate-700 space-y-1">
            {sessions.map((s) => (
              <li key={s.session_id}>
                {s.session_type} — {new Date(s.scheduled_at).toLocaleString()} ({s.status})
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-2">Prayer requests</h2>
        {profile && <NewPrayerRequestForm clientId={profile.client_id} onSubmitted={loadAll} />}
        {prayerRequests.length === 0 ? (
          <p className="text-sm text-slate-500">You haven't submitted a prayer request yet.</p>
        ) : (
          <ul className="text-sm text-slate-700 space-y-1">
            {prayerRequests.map((p) => (
              <li key={p.prayer_request_id}>
                {p.request_text} — {p.status}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

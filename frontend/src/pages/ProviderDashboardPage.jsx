import { useEffect, useState } from "react";
import { providersApi, referralsApi, schedulingApi, ApiError } from "../api/client.js";

function AddSessionNoteForm({ sessionId, onAdded }) {
  const [noteType, setNoteType] = useState("progress");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!content.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await schedulingApi.createSessionNote(sessionId, { note_type: noteType, content: content.trim() });
      setContent("");
      onAdded();
    } catch (err) {
      setError(err.message || "Could not save the note.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-2 flex gap-2 flex-wrap">
      <select
        value={noteType}
        onChange={(e) => setNoteType(e.target.value)}
        className="rounded-md border border-slate-300 px-2 py-1 text-xs"
      >
        <option value="progress">Progress note</option>
        <option value="clinical">Clinical note</option>
        <option value="spiritual_action_plan">Spiritual action plan</option>
      </select>
      <input
        type="text"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Note content…"
        className="flex-1 min-w-[200px] rounded-md border border-slate-300 px-2 py-1 text-xs"
      />
      <button
        type="submit"
        disabled={saving}
        className="rounded-md bg-slate-900 text-white px-3 py-1 text-xs font-medium disabled:opacity-50"
      >
        Add note
      </button>
      {error && <p className="text-xs text-red-700 w-full">{error}</p>}
    </form>
  );
}

function NewClinicalSessionForm({ acceptedReferrals, onCreated }) {
  const [clientId, setClientId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!clientId || !scheduledAt) return;
    setSaving(true);
    setError(null);
    try {
      await schedulingApi.createSession({
        client_id: clientId,
        session_type: "clinical",
        scheduled_at: new Date(scheduledAt).toISOString(),
      });
      setScheduledAt("");
      onCreated();
    } catch (err) {
      setError(err.message || "Could not schedule the session.");
    } finally {
      setSaving(false);
    }
  }

  if (acceptedReferrals.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        You'll be able to schedule a clinical session once you've accepted a referral.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="flex gap-2 flex-wrap">
        <select
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-2 text-sm"
        >
          <option value="">Select a client…</option>
          {acceptedReferrals.map((r) => (
            <option key={r.referral_id} value={r.client_id}>
              Client {r.client_id.slice(0, 8)}… ({r.referral_type})
            </option>
          ))}
        </select>
        <input
          type="datetime-local"
          value={scheduledAt}
          onChange={(e) => setScheduledAt(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-slate-900 text-white px-3 py-2 text-sm font-medium disabled:opacity-50"
        >
          Schedule
        </button>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
    </form>
  );
}

export default function ProviderDashboardPage() {
  const [profile, setProfile] = useState(null);
  const [referrals, setReferrals] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [expandedSessionId, setExpandedSessionId] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadAll() {
    try {
      const [profileData, referralsData, sessionsData] = await Promise.all([
        providersApi.getMe(),
        referralsApi.list().catch(() => []),
        schedulingApi.listSessions().catch(() => []),
      ]);
      setProfile(profileData);
      setReferrals(referralsData || []);
      setSessions(sessionsData || []);
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

  async function handleRespond(referralId, decision) {
    try {
      await referralsApi.respond(referralId, decision);
      await loadAll();
    } catch (err) {
      setError(err.message || "Could not respond to the referral.");
    }
  }

  if (loading) return <div className="max-w-4xl mx-auto p-6 text-slate-500">Loading…</div>;

  const acceptedReferrals = referrals.filter((r) => r.status === "accepted");

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {error && (
        <div role="alert" className="rounded-md bg-red-50 border border-red-300 text-red-800 p-3 text-sm">
          {error}
        </div>
      )}

      {profile && (
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="font-semibold text-lg mb-2">Your provider profile</h2>
          <p className="text-sm text-slate-700">
            {profile.provider_type} · {profile.license_state} · vetting status:{" "}
            <span className="font-medium">{profile.vetting_status}</span>
          </p>
          {profile.vetting_status !== "approved" && (
            <p className="text-sm text-slate-500 mt-2">
              You can't accept referrals until a platform admin approves your credentials.
            </p>
          )}
          {profile.vetting_status === "approved" && !profile.accepting_referrals && (
            <p className="text-sm text-slate-500 mt-2">
              You're approved but not currently marked as accepting referrals — an admin can turn this on.
            </p>
          )}
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-3">Referrals</h2>
        {referrals.length === 0 ? (
          <p className="text-sm text-slate-500">No referrals routed to you yet.</p>
        ) : (
          <ul className="text-sm divide-y divide-slate-100">
            {referrals.map((r) => (
              <li key={r.referral_id} className="py-2 flex items-center justify-between">
                <span>
                  {r.referral_type} — client {r.client_id.slice(0, 8)}… ({r.status})
                </span>
                {r.status === "pending" && (
                  <span className="flex gap-2">
                    <button
                      onClick={() => handleRespond(r.referral_id, "accepted")}
                      className="text-xs rounded-md bg-emerald-700 text-white px-2 py-1"
                    >
                      Accept
                    </button>
                    <button
                      onClick={() => handleRespond(r.referral_id, "declined")}
                      className="text-xs rounded-md bg-slate-200 text-slate-800 px-2 py-1"
                    >
                      Decline
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-3">
        <h2 className="font-semibold text-lg">Schedule a clinical session</h2>
        <NewClinicalSessionForm acceptedReferrals={acceptedReferrals} onCreated={loadAll} />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-2">Your sessions</h2>
        {sessions.length === 0 ? (
          <p className="text-sm text-slate-500">No sessions scheduled yet.</p>
        ) : (
          <ul className="text-sm text-slate-700 divide-y divide-slate-100">
            {sessions.map((s) => (
              <li key={s.session_id} className="py-2">
                <div className="flex items-center justify-between">
                  <span>
                    {s.session_type} — {new Date(s.scheduled_at).toLocaleString()} ({s.status})
                  </span>
                  <button
                    onClick={() => setExpandedSessionId(expandedSessionId === s.session_id ? null : s.session_id)}
                    className="text-xs text-slate-500 underline"
                  >
                    {expandedSessionId === s.session_id ? "Hide notes" : "Add note"}
                  </button>
                </div>
                {expandedSessionId === s.session_id && (
                  <AddSessionNoteForm sessionId={s.session_id} onAdded={() => setExpandedSessionId(null)} />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

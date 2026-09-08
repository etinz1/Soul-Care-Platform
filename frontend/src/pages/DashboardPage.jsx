import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { clientsApi, schedulingApi, ApiError } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";

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

export default function DashboardPage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [prayerRequests, setPrayerRequests] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (user?.role !== "client") {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [profileData, sessionsData, prayerData] = await Promise.all([
          clientsApi.getMe(),
          schedulingApi.listSessions().catch(() => []),
          schedulingApi.listPrayerRequests().catch(() => []),
        ]);
        if (cancelled) return;
        setProfile(profileData);
        setSessions(sessionsData || []);
        setPrayerRequests(prayerData || []);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load your dashboard.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user?.role]);

  if (user?.role !== "client") {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <p className="font-medium text-slate-900">Signed in as {user?.role}.</p>
          <p className="text-sm text-slate-600 mt-1">
            A dedicated {user?.role} dashboard isn't built yet — this frontend milestone covers the client
            experience end to end (register, profile, intake). The API for other roles is live and testable via{" "}
            <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">/docs</code> in the meantime.
          </p>
        </div>
      </div>
    );
  }

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

import { useEffect, useState } from "react";
import { crmApi, schedulingApi, ApiError } from "../api/client.js";

function ClientDetailPanel({ clientId, onClose }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [noteText, setNoteText] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  async function loadSummary() {
    setLoading(true);
    setError(null);
    try {
      const data = await crmApi.getClientSummary(clientId);
      setSummary(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this client's summary.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await crmApi.getClientSummary(clientId);
        if (!cancelled) setSummary(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load this client's summary.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  async function handleAddNote(e) {
    e.preventDefault();
    if (!noteText.trim()) return;
    setSavingNote(true);
    try {
      await crmApi.addNote(clientId, noteText.trim());
      setNoteText("");
      await loadSummary();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the note.");
    } finally {
      setSavingNote(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-lg">Client detail</h3>
        <button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-800">
          Close
        </button>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {loading && <p className="text-sm text-slate-500">Loading…</p>}

      {summary && (
        <>
          <div className="text-sm text-slate-700 space-y-1">
            <p className="font-medium">{summary.email}</p>
            {summary.distress_level != null && <p>Distress level (latest intake): {summary.distress_level}</p>}
            {summary.presenting_concerns.length > 0 && (
              <p>Presenting concerns: {summary.presenting_concerns.join(", ")}</p>
            )}
            {summary.protective_factors.length > 0 && (
              <p>Protective factors: {summary.protective_factors.join(", ")}</p>
            )}
            <p>
              Sessions: {summary.completed_sessions_count} completed, {summary.upcoming_sessions_count} upcoming
            </p>
            <p>Open prayer requests: {summary.open_prayer_requests_count}</p>
          </div>

          <div>
            <h4 className="text-sm font-semibold text-slate-800 mb-1">Recent session notes</h4>
            {summary.recent_session_notes.length === 0 ? (
              <p className="text-sm text-slate-500">None yet.</p>
            ) : (
              <ul className="text-sm text-slate-700 space-y-1">
                {summary.recent_session_notes.map((n) => (
                  <li key={n.note_id}>
                    <span className="text-slate-500">[{n.note_type}]</span> {n.content}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h4 className="text-sm font-semibold text-slate-800 mb-1">Caseload notes</h4>
            {summary.recent_crm_notes.length === 0 ? (
              <p className="text-sm text-slate-500 mb-2">None yet.</p>
            ) : (
              <ul className="text-sm text-slate-700 space-y-1 mb-2">
                {summary.recent_crm_notes.map((n) => (
                  <li key={n.note_id}>{n.content}</li>
                ))}
              </ul>
            )}
            <form onSubmit={handleAddNote} className="flex gap-2">
              <input
                type="text"
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                placeholder="Log a caseload note…"
                className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
              <button
                type="submit"
                disabled={savingNote}
                className="rounded-md bg-slate-900 text-white px-3 py-2 text-sm font-medium disabled:opacity-50"
              >
                Add
              </button>
            </form>
          </div>
        </>
      )}
    </div>
  );
}

function NewSessionForm({ clients, onCreated }) {
  const [clientId, setClientId] = useState("");
  const [sessionType, setSessionType] = useState("coaching");
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
        session_type: sessionType,
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

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="flex gap-2 flex-wrap">
        <select
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-2 text-sm"
        >
          <option value="">Select a client…</option>
          {clients.map((c) => (
            <option key={c.client_id} value={c.client_id}>
              {c.email}
            </option>
          ))}
        </select>
        <select
          value={sessionType}
          onChange={(e) => setSessionType(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-2 text-sm"
        >
          <option value="coaching">Coaching</option>
          <option value="prayer">Prayer</option>
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

export default function CoachDashboardPage() {
  const [clients, setClients] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [prayerRequests, setPrayerRequests] = useState([]);
  const [selectedClientId, setSelectedClientId] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadAll() {
    try {
      const [clientsData, sessionsData, prayerData] = await Promise.all([
        crmApi.listClients(),
        schedulingApi.listSessions().catch(() => []),
        schedulingApi.listPrayerRequests().catch(() => []),
      ]);
      setClients(clientsData || []);
      setSessions(sessionsData || []);
      setPrayerRequests(prayerData || []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your caseload.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handlePrayerStatusChange(id, status) {
    try {
      await schedulingApi.updatePrayerRequest(id, { status });
      setPrayerRequests((prev) => prev.map((p) => (p.prayer_request_id === id ? { ...p, status } : p)));
    } catch (err) {
      setError(err.message || "Could not update the prayer request.");
    }
  }

  if (loading) return <div className="max-w-4xl mx-auto p-6 text-slate-500">Loading…</div>;

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {error && (
        <div role="alert" className="rounded-md bg-red-50 border border-red-300 text-red-800 p-3 text-sm">
          {error}
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-3">Your caseload</h2>
        {clients.length === 0 ? (
          <p className="text-sm text-slate-500">No clients assigned to you yet.</p>
        ) : (
          <ul className="text-sm divide-y divide-slate-100">
            {clients.map((c) => (
              <li key={c.client_id} className="py-2 flex items-center justify-between">
                <span>
                  {c.email}
                  {c.church_sponsor_id && <span className="text-slate-400"> · church-sponsored</span>}
                </span>
                <button
                  onClick={() => setSelectedClientId(c.client_id)}
                  className="text-sm text-slate-900 underline"
                >
                  View
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {selectedClientId && (
        <ClientDetailPanel clientId={selectedClientId} onClose={() => setSelectedClientId(null)} />
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-3">
        <h2 className="font-semibold text-lg">Schedule a session</h2>
        <NewSessionForm clients={clients} onCreated={loadAll} />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-2">Your sessions</h2>
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
        <h2 className="font-semibold text-lg mb-2">Prayer requests assigned to you</h2>
        {prayerRequests.length === 0 ? (
          <p className="text-sm text-slate-500">Nothing assigned right now.</p>
        ) : (
          <ul className="text-sm text-slate-700 space-y-2">
            {prayerRequests.map((p) => (
              <li key={p.prayer_request_id} className="flex items-center justify-between gap-3">
                <span>
                  {p.request_text} <span className="text-slate-400">({p.urgency})</span>
                </span>
                <select
                  value={p.status}
                  onChange={(e) => handlePrayerStatusChange(p.prayer_request_id, e.target.value)}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs"
                >
                  <option value="open">Open</option>
                  <option value="in_progress">In progress</option>
                  <option value="closed">Closed</option>
                </select>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

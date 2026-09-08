import { useEffect, useState } from "react";
import { billingApi, churchApi, clientsApi, coachesApi, crmApi, providersApi, ApiError } from "../api/client.js";

function ProviderVettingQueue({ providers, onDecision }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="font-semibold text-lg mb-3">Provider vetting</h2>
      {providers.length === 0 ? (
        <p className="text-sm text-slate-500">No providers on file yet.</p>
      ) : (
        <ul className="text-sm divide-y divide-slate-100">
          {providers.map((p) => (
            <li key={p.provider_id} className="py-2 flex items-center justify-between gap-3">
              <span>
                {p.email} — {p.provider_type} ({p.license_state}) ·{" "}
                <span className="font-medium">{p.vetting_status}</span>
                {p.accepting_referrals && <span className="text-emerald-700"> · accepting referrals</span>}
              </span>
              {p.vetting_status !== "approved" && (
                <button
                  onClick={() => onDecision(p.provider_id, { vetting_status: "approved", accepting_referrals: true })}
                  className="text-xs rounded-md bg-emerald-700 text-white px-2 py-1 shrink-0"
                >
                  Approve
                </button>
              )}
              {p.vetting_status === "approved" && p.accepting_referrals && (
                <button
                  onClick={() => onDecision(p.provider_id, { vetting_status: "approved", accepting_referrals: false })}
                  className="text-xs rounded-md bg-slate-200 text-slate-800 px-2 py-1 shrink-0"
                >
                  Pause referrals
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CoachesPanel({ coaches, onCreated }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await coachesApi.create({ email, password });
      setEmail("");
      setPassword("");
      onCreated();
    } catch (err) {
      setError(err.message || "Could not create the coach account.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="font-semibold text-lg mb-3">Coaches</h2>
      {coaches.length === 0 ? (
        <p className="text-sm text-slate-500 mb-3">No coach accounts yet.</p>
      ) : (
        <ul className="text-sm text-slate-700 space-y-1 mb-3">
          {coaches.map((c) => (
            <li key={c.coach_id}>{c.email}</li>
          ))}
        </ul>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2 flex-wrap">
        <input
          type="email"
          required
          placeholder="Coach email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-2 text-sm"
        />
        <input
          type="password"
          required
          minLength={12}
          placeholder="Temporary password (12+ chars)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-slate-900 text-white px-3 py-2 text-sm font-medium disabled:opacity-50"
        >
          Create coach
        </button>
      </form>
      {error && <p className="text-sm text-red-700 mt-2">{error}</p>}
    </div>
  );
}

function ChurchesPanel({ churches, onCreated }) {
  const [name, setName] = useState("");
  const [billingEmail, setBillingEmail] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await churchApi.create({ name, billing_email: billingEmail || null });
      setName("");
      setBillingEmail("");
      onCreated();
    } catch (err) {
      setError(err.message || "Could not create the church.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="font-semibold text-lg mb-3">Churches</h2>
      {churches.length === 0 ? (
        <p className="text-sm text-slate-500 mb-3">No churches on file yet.</p>
      ) : (
        <ul className="text-sm text-slate-700 space-y-1 mb-3">
          {churches.map((c) => (
            <li key={c.church_id}>
              {c.name}
              {c.billing_email && <span className="text-slate-400"> · {c.billing_email}</span>}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2 flex-wrap">
        <input
          type="text"
          required
          placeholder="Church name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-2 text-sm"
        />
        <input
          type="email"
          placeholder="Billing email (optional)"
          value={billingEmail}
          onChange={(e) => setBillingEmail(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-slate-900 text-white px-3 py-2 text-sm font-medium disabled:opacity-50"
        >
          Create church
        </button>
      </form>
      {error && <p className="text-sm text-red-700 mt-2">{error}</p>}
      <p className="text-xs text-slate-400 mt-2">
        Churches only self-onboard a sponsorship once a client has consented to disclosure — see the ROI consent
        flow. Provisioning the church record itself stays admin-only.
      </p>
    </div>
  );
}

function ClientAssignmentPanel({ clients, coaches, churches, onAssigned }) {
  const [selections, setSelections] = useState({});
  const [savingId, setSavingId] = useState(null);
  const [error, setError] = useState(null);

  function setSelection(clientId, field, value) {
    setSelections((prev) => ({ ...prev, [clientId]: { ...prev[clientId], [field]: value } }));
  }

  async function handleAssign(clientId) {
    const selection = selections[clientId] || {};
    const patch = {};
    if (selection.coach_id) patch.coach_id = selection.coach_id;
    if (selection.church_sponsor_id) patch.church_sponsor_id = selection.church_sponsor_id;
    if (Object.keys(patch).length === 0) return;

    setSavingId(clientId);
    setError(null);
    try {
      await clientsApi.assign(clientId, patch);
      onAssigned();
    } catch (err) {
      setError(err.message || "Could not save the assignment.");
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="font-semibold text-lg mb-3">Clients</h2>
      {error && <p className="text-sm text-red-700 mb-2">{error}</p>}
      {clients.length === 0 ? (
        <p className="text-sm text-slate-500">No clients registered yet.</p>
      ) : (
        <ul className="text-sm divide-y divide-slate-100">
          {clients.map((c) => (
            <li key={c.client_id} className="py-3 flex flex-wrap items-center gap-2">
              <span className="min-w-[180px]">{c.email}</span>
              <select
                value={selections[c.client_id]?.coach_id || c.coach_id || ""}
                onChange={(e) => setSelection(c.client_id, "coach_id", e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs"
              >
                <option value="">No coach</option>
                {coaches.map((co) => (
                  <option key={co.coach_id} value={co.coach_id}>
                    {co.email}
                  </option>
                ))}
              </select>
              <select
                value={selections[c.client_id]?.church_sponsor_id || c.church_sponsor_id || ""}
                onChange={(e) => setSelection(c.client_id, "church_sponsor_id", e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs"
              >
                <option value="">No church sponsor</option>
                {churches.map((ch) => (
                  <option key={ch.church_id} value={ch.church_id}>
                    {ch.name}
                  </option>
                ))}
              </select>
              <button
                onClick={() => handleAssign(c.client_id)}
                disabled={savingId === c.client_id}
                className="text-xs rounded-md bg-slate-900 text-white px-2 py-1 disabled:opacity-50"
              >
                Save
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function InvoicesPanel({ invoices, churches, onCreated }) {
  const [churchId, setChurchId] = useState("");
  const [description, setDescription] = useState("");
  const [amountDollars, setAmountDollars] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const amountCents = Math.round(parseFloat(amountDollars) * 100);
    if (!churchId || !description || Number.isNaN(amountCents) || amountCents <= 0) return;

    setSaving(true);
    setError(null);
    try {
      await billingApi.createInvoice({
        church_id: churchId,
        line_items: [{ description, amount_cents: amountCents }],
      });
      setDescription("");
      setAmountDollars("");
      onCreated();
    } catch (err) {
      setError(err.message || "Could not create the invoice.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="font-semibold text-lg mb-3">Invoices</h2>
      {invoices.length === 0 ? (
        <p className="text-sm text-slate-500 mb-3">No invoices yet.</p>
      ) : (
        <ul className="text-sm text-slate-700 divide-y divide-slate-100 mb-3">
          {invoices.map((inv) => (
            <li key={inv.invoice_id} className="py-2 flex items-center justify-between">
              <span>${(inv.amount_cents / 100).toFixed(2)}</span>
              <span className="text-slate-400">{inv.status}</span>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={handleSubmit} className="space-y-2">
        <p className="text-xs text-slate-400">
          A single-line-item invoice, billed to a church. Server computes the total from line items — never a
          client-supplied number.
        </p>
        <div className="flex gap-2 flex-wrap">
          <select
            value={churchId}
            onChange={(e) => setChurchId(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-2 text-sm"
          >
            <option value="">Select a church…</option>
            {churches.map((ch) => (
              <option key={ch.church_id} value={ch.church_id}>
                {ch.name}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Line item description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-2 text-sm"
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Amount ($)"
            value={amountDollars}
            onChange={(e) => setAmountDollars(e.target.value)}
            className="w-28 rounded-md border border-slate-300 px-2 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-slate-900 text-white px-3 py-2 text-sm font-medium disabled:opacity-50"
          >
            Create invoice
          </button>
        </div>
      </form>
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}

export default function AdminDashboardPage() {
  const [providers, setProviders] = useState([]);
  const [coaches, setCoaches] = useState([]);
  const [churches, setChurches] = useState([]);
  const [clients, setClients] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadAll() {
    try {
      const [providersData, coachesData, churchesData, clientsData, invoicesData] = await Promise.all([
        providersApi.list(),
        coachesApi.list(),
        churchApi.list(),
        crmApi.listClients(),
        billingApi.listInvoices(),
      ]);
      setProviders(providersData || []);
      setCoaches(coachesData || []);
      setChurches(churchesData || []);
      setClients(clientsData || []);
      setInvoices(invoicesData || []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the admin dashboard.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function handleVettingDecision(providerId, decision) {
    try {
      await providersApi.updateVetting(providerId, decision);
      await loadAll();
    } catch (err) {
      setError(err.message || "Could not update the provider's vetting status.");
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

      <ProviderVettingQueue providers={providers} onDecision={handleVettingDecision} />
      <CoachesPanel coaches={coaches} onCreated={loadAll} />
      <ChurchesPanel churches={churches} onCreated={loadAll} />
      <ClientAssignmentPanel clients={clients} coaches={coaches} churches={churches} onAssigned={loadAll} />
      <InvoicesPanel invoices={invoices} churches={churches} onCreated={loadAll} />
    </div>
  );
}

import { useEffect, useState } from "react";
import { billingApi, churchApi, ApiError } from "../api/client.js";

/**
 * Read-only for now — a church_admin can see the sponsorships and invoices
 * for the members it sponsors, and nothing else. This is deliberate: the
 * backend (see backend/app/api/v1/church.py) never exposes any path from
 * an invoice or sponsorship to clinical data, so this page can't either —
 * there is no client name, no intake/session content, nothing beyond
 * billing detail. Creating new sponsorships/invoices stays admin-only via
 * AdminDashboardPage.jsx, matching providers.py's vetted-onboarding
 * posture for who gets to originate financial commitments.
 */
export default function ChurchAdminDashboardPage() {
  const [church, setChurch] = useState(null);
  const [sponsorships, setSponsorships] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [churchData, sponsorshipsData, invoicesData] = await Promise.all([
          churchApi.getMe(),
          churchApi.listSponsorships().catch(() => []),
          billingApi.listInvoices().catch(() => []),
        ]);
        if (cancelled) return;
        setChurch(churchData);
        setSponsorships(sponsorshipsData || []);
        setInvoices(invoicesData || []);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError && err.status === 404
              ? "No church record is linked to your account yet — ask a platform admin to set this up."
              : "Could not load your church's dashboard."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <div className="max-w-3xl mx-auto p-6 text-slate-500">Loading…</div>;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      {error && (
        <div role="alert" className="rounded-md bg-red-50 border border-red-300 text-red-800 p-3 text-sm">
          {error}
        </div>
      )}

      {church && (
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="font-semibold text-lg">{church.name}</h2>
          <p className="text-sm text-slate-500 mt-1">Billing email: {church.billing_email || "not on file"}</p>
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-3">Sponsorships</h2>
        <p className="text-xs text-slate-500 mb-3">
          Billing detail only — your dashboard never shows clinical notes, intake content, or session details for
          the members you sponsor.
        </p>
        {sponsorships.length === 0 ? (
          <p className="text-sm text-slate-500">No active sponsorships yet.</p>
        ) : (
          <ul className="text-sm divide-y divide-slate-100">
            {sponsorships.map((s) => (
              <li key={s.sponsorship_id} className="py-2">
                <div className="flex items-center justify-between">
                  <span>
                    {s.sponsor_type} — client {s.client_id.slice(0, 8)}… ({s.status})
                  </span>
                  {s.amount_covered_cents != null && (
                    <span className="text-slate-500">${(s.amount_covered_cents / 100).toFixed(2)} covered</span>
                  )}
                </div>
                {s.sessions_covered != null && (
                  <p className="text-xs text-slate-500 mt-0.5">{s.sessions_covered} session(s) covered</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-lg mb-3">Invoices</h2>
        {invoices.length === 0 ? (
          <p className="text-sm text-slate-500">No invoices yet.</p>
        ) : (
          <ul className="text-sm divide-y divide-slate-100">
            {invoices.map((inv) => (
              <li key={inv.invoice_id} className="py-2 flex items-center justify-between">
                <span>
                  Invoice {inv.invoice_id.slice(0, 8)}… — client {inv.client_id ? inv.client_id.slice(0, 8) + "…" : "—"}
                </span>
                <span className="text-slate-500">
                  ${(inv.amount_cents / 100).toFixed(2)} · {inv.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

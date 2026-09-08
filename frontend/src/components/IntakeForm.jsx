import { useState } from "react";

/**
 * Smart Intake Form
 *
 * IMPORTANT: The conditional routing logic here is for UI/UX only — showing
 * the right confirmation screen and crisis resources. The actual risk
 * decision is made server-side by app/services/risk_engine.py and must
 * never be trusted from the client. This component simply renders whatever
 * `risk_decision` the API returns.
 *
 * Presenting concerns must match the PresentingConcern enum in
 * backend/app/schemas.py.
 */

const PRESENTING_CONCERNS = [
  { value: "anxiety", label: "Anxiety" },
  { value: "depression", label: "Depression" },
  { value: "grief", label: "Grief / Loss" },
  { value: "marital_conflict", label: "Marital / Relationship Conflict" },
  { value: "parenting", label: "Parenting" },
  { value: "addiction_recovery", label: "Addiction Recovery" },
  { value: "identity_purpose", label: "Identity / Purpose" },
  { value: "financial_stress", label: "Financial Stress" },
  { value: "spiritual_dryness", label: "Spiritual Dryness" },
  { value: "trauma_history", label: "Trauma History" },
];

const initialFormState = {
  distress_level: 5,
  c9_suicidal_ideation: 0,
  substance_use_severity: 0,
  presenting_concerns: [],
  protective_factors: [],
};

function CrisisBanner() {
  return (
    <div
      role="alert"
      className="rounded-lg border-2 border-red-600 bg-red-50 p-5 text-red-900 mb-6"
    >
      <p className="font-semibold text-lg mb-1">You're not alone in this.</p>
      <p className="mb-2">
        If you are in immediate danger, please call or text{" "}
        <a href="tel:988" className="underline font-semibold">988</a>{" "}
        (Suicide &amp; Crisis Lifeline) right now, or go to your nearest emergency room.
      </p>
      <p className="text-sm">
        Your intake has also been securely and immediately routed to a licensed
        psychiatrist in our clinical network. Someone will reach out to you shortly.
      </p>
    </div>
  );
}

function ReferralConfirmation({ riskDecision }) {
  const providerLabel =
    {
      psychiatrist: "a licensed psychiatrist",
      addiction_specialist: "an addiction specialist",
    }[riskDecision.routed_provider_type] || "a clinical specialist";

  return (
    <div className="rounded-lg border border-amber-400 bg-amber-50 p-5 text-amber-900 mb-6">
      <p className="font-semibold mb-1">You've been connected with additional support.</p>
      <p>{riskDecision.message}</p>
      <p className="text-sm mt-2">
        We've routed your intake to {providerLabel} in our vetted clinical
        network. This is in addition to, not instead of, your coaching relationship.
      </p>
    </div>
  );
}

function ScriptureCards({ cards }) {
  if (!cards || cards.length === 0) return null;
  return (
    <div className="mb-6">
      <h3 className="font-semibold text-lg mb-3">A word for you today</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        {cards.map((card) => (
          <div key={card.reference} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-sm font-medium text-slate-500 mb-1">
              {card.reference} ({card.translation})
            </p>
            <p className="italic mb-2">&ldquo;{card.verse_text}&rdquo;</p>
            {card.reflection_text && (
              <p className="text-sm text-slate-600">{card.reflection_text}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function IntakeForm({ clientId, intakeId, apiBaseUrl, authToken }) {
  const [form, setForm] = useState(initialFormState);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // API response: { risk_decision, scripture_cards, ... }
  const [error, setError] = useState(null);

  function toggleConcern(value) {
    setForm((prev) => {
      const has = prev.presenting_concerns.includes(value);
      return {
        ...prev,
        presenting_concerns: has
          ? prev.presenting_concerns.filter((c) => c !== value)
          : [...prev.presenting_concerns, value],
      };
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (form.presenting_concerns.length === 0) {
      setError("Please select at least one area you'd like support with.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/intake/${intakeId}/submit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          client_id: clientId,
          distress_level: Number(form.distress_level),
          c9_suicidal_ideation: Number(form.c9_suicidal_ideation),
          substance_use_severity: Number(form.substance_use_severity),
          presenting_concerns: form.presenting_concerns,
          protective_factors: form.protective_factors,
          raw_responses: form,
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Submission failed (${response.status})`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message || "Something went wrong submitting your intake. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  // --- Post-submit view: render exactly what the server decided ---
  if (result) {
    const { risk_decision: riskDecision, scripture_cards: scriptureCards } = result;
    const isImminent = riskDecision.severity === "imminent";

    return (
      <div className="max-w-2xl mx-auto p-6">
        {riskDecision.is_hard_stop && isImminent && <CrisisBanner />}
        {riskDecision.is_hard_stop && !isImminent && (
          <ReferralConfirmation riskDecision={riskDecision} />
        )}
        {!riskDecision.is_hard_stop && (
          <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-5 text-emerald-900 mb-6">
            <p>{riskDecision.message}</p>
          </div>
        )}
        <ScriptureCards cards={scriptureCards} />
      </div>
    );
  }

  // --- Intake form view ---
  return (
    <form onSubmit={handleSubmit} className="max-w-2xl mx-auto p-6 space-y-8">
      <div>
        <h2 className="text-xl font-semibold mb-1">Let's get to know where you are</h2>
        <p className="text-sm text-slate-600">
          Everything you share here is confidential and reviewed by your coach and,
          if needed, a licensed clinical partner.
        </p>
      </div>

      <fieldset>
        <label className="block font-medium mb-2" htmlFor="distress_level">
          Overall, how would you rate your distress right now? (0 = none, 10 = severe)
        </label>
        <input
          id="distress_level"
          type="range"
          min={0}
          max={10}
          value={form.distress_level}
          onChange={(e) => setForm((p) => ({ ...p, distress_level: e.target.value }))}
          className="w-full"
        />
        <p className="text-sm text-slate-500">{form.distress_level} / 10</p>
      </fieldset>

      <fieldset>
        <legend className="font-medium mb-2">
          Over the last two weeks, how often have you had thoughts that you would be
          better off dead, or of hurting yourself in some way?
        </legend>
        <div className="space-y-1">
          {[
            { value: 0, label: "Not at all" },
            { value: 1, label: "Several days" },
            { value: 2, label: "More than half the days" },
            { value: 3, label: "Nearly every day" },
          ].map((opt) => (
            <label key={opt.value} className="flex items-center gap-2">
              <input
                type="radio"
                name="c9_suicidal_ideation"
                value={opt.value}
                checked={Number(form.c9_suicidal_ideation) === opt.value}
                onChange={() => setForm((p) => ({ ...p, c9_suicidal_ideation: opt.value }))}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="font-medium mb-2">
          In the past 3 months, how often has your use of alcohol or other substances
          caused problems in your life?
        </legend>
        <div className="space-y-1">
          {[
            { value: 0, label: "Never" },
            { value: 1, label: "Once or twice" },
            { value: 2, label: "Monthly" },
            { value: 3, label: "Weekly" },
            { value: 4, label: "Daily or almost daily" },
          ].map((opt) => (
            <label key={opt.value} className="flex items-center gap-2">
              <input
                type="radio"
                name="substance_use_severity"
                value={opt.value}
                checked={Number(form.substance_use_severity) === opt.value}
                onChange={() => setForm((p) => ({ ...p, substance_use_severity: opt.value }))}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="font-medium mb-2">
          What would you like support with? (select all that apply)
        </legend>
        <div className="grid grid-cols-2 gap-2">
          {PRESENTING_CONCERNS.map((concern) => (
            <label key={concern.value} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.presenting_concerns.includes(concern.value)}
                onChange={() => toggleConcern(concern.value)}
              />
              {concern.label}
            </label>
          ))}
        </div>
      </fieldset>

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
        {submitting ? "Submitting…" : "Submit Intake"}
      </button>
    </form>
  );
}

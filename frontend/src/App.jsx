import IntakeForm from "./components/IntakeForm.jsx";

/**
 * Dev harness for the Smart Intake module. In the real app, clientId /
 * intakeId / authToken come from the authenticated session and the intake
 * draft created by POST /api/v1/intake — hardcoded here only so the
 * component renders standalone during local development.
 */
export default function App() {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

  return (
    <div className="min-h-screen bg-slate-50">
      <IntakeForm
        clientId="00000000-0000-0000-0000-000000000001"
        intakeId="00000000-0000-0000-0000-000000000002"
        apiBaseUrl={apiBaseUrl}
        authToken="dev-token-replace-with-real-session-token"
      />
    </div>
  );
}

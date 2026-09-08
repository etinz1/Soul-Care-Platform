import { useAuth } from "../context/AuthContext.jsx";
import AdminDashboardPage from "./AdminDashboardPage.jsx";
import ClientDashboardPage from "./ClientDashboardPage.jsx";
import CoachDashboardPage from "./CoachDashboardPage.jsx";
import ProviderDashboardPage from "./ProviderDashboardPage.jsx";

/**
 * Routes to a role-specific dashboard. Each role's dashboard is its own
 * page component (client/coach/provider/admin) — this file just picks
 * which one to render based on the JWT's role claim (UI display only; the
 * backend re-checks role on every request these pages make).
 */
export default function DashboardPage() {
  const { user } = useAuth();

  if (user?.role === "client") return <ClientDashboardPage />;
  if (user?.role === "coach") return <CoachDashboardPage />;
  if (user?.role === "provider") return <ProviderDashboardPage />;
  if (user?.role === "platform_admin") return <AdminDashboardPage />;

  return (
    <div className="max-w-2xl mx-auto p-6">
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <p className="font-medium text-slate-900">Signed in as {user?.role}.</p>
        <p className="text-sm text-slate-600 mt-1">
          A dedicated {user?.role} dashboard isn't built yet — client, coach, provider, and admin dashboards are
          live. The API for this role is testable via{" "}
          <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">/docs</code> in the meantime.
        </p>
      </div>
    </div>
  );
}

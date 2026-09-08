import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="max-w-4xl mx-auto flex items-center justify-between px-6 py-4">
        <span className="font-semibold text-slate-900">Soul Care Platform</span>
        {user && (
          <div className="flex items-center gap-4 text-sm text-slate-600">
            <span className="capitalize">{user.role}</span>
            <button type="button" onClick={handleLogout} className="text-slate-500 hover:text-slate-900 underline">
              Log out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

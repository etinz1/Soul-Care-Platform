import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

/**
 * The bold masthead carried over from LoginPage/RegisterPage's "Bold Faith"
 * treatment (deep purple/burgundy, white, black, a heavy display serif) —
 * see LoginPage.jsx's comment. Everything below the masthead (each
 * dashboard's cards) intentionally stays on the plain slate/white styling.
 */
export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="bg-gradient-to-r from-brand-purpledark via-brand-purple to-brand-burgundy border-b-4 border-brand-ink">
      <div className="max-w-4xl mx-auto flex items-center justify-between px-6 py-4">
        <span className="font-display font-black text-lg tracking-tight text-white">Soul Care Platform</span>
        {user && (
          <div className="flex items-center gap-4 text-sm">
            <span className="capitalize rounded-full bg-white/15 text-white px-3 py-1 text-xs font-semibold tracking-wide">
              {user.role}
            </span>
            <button
              type="button"
              onClick={handleLogout}
              className="text-white/80 hover:text-white underline underline-offset-2"
            >
              Log out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

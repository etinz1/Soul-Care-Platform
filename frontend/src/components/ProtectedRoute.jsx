import { Navigate, Outlet } from "react-router-dom";
import NavBar from "./NavBar.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/** Layout route: gates everything nested under it on authentication, and
 * renders the NavBar above whichever child route matched. */
export default function ProtectedRoute() {
  const { isAuthenticated, initializing } = useAuth();

  if (initializing) return null; // avoid a login-page flash while tokens load
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <>
      <NavBar />
      <Outlet />
    </>
  );
}

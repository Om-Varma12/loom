import { useAuth } from "@clerk/react";
import { Navigate, Outlet } from "react-router";
import { AuthTokenBridge } from "../auth/AuthTokenBridge";

export function ProtectedRoute() {
  const { isSignedIn, isLoaded } = useAuth();

  if (!isLoaded) return null; // or a spinner

  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />;
  }

  return (
    <AuthTokenBridge>
      <Outlet />
    </AuthTokenBridge>
  );
}

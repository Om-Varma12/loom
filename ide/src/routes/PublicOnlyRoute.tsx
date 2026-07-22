import { useAuth } from "@clerk/react";
import { Navigate, Outlet } from "react-router";

export function PublicOnlyRoute() {
  const { isSignedIn, isLoaded } = useAuth();

  if (!isLoaded) return null;

  if (isSignedIn) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}

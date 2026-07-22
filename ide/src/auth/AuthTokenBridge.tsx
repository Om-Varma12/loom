import { useAuth } from "@clerk/react";
import { type ReactNode, useEffect, useState } from "react";
import { resetAuthCaches, setAuthTokenGetter } from "../lib/authFetch";

type AuthTokenBridgeProps = {
  children: ReactNode;
};

export function AuthTokenBridge({ children }: AuthTokenBridgeProps) {
  const { getToken, userId } = useAuth();
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    setAuthTokenGetter(getToken);
    setIsReady(true);

    return () => {
      setAuthTokenGetter(null);
      setIsReady(false);
    };
  }, [getToken]);

  useEffect(() => {
    resetAuthCaches();
  }, [userId]);

  if (!isReady) {
    return null;
  }

  return children;
}

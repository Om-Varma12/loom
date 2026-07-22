import { HandleSSOCallback, useAuth } from "@clerk/react";
import { Navigate, useNavigate } from "react-router";
import "./AuthPage.css";

export default function SsoCallback() {
  const { isSignedIn } = useAuth();
  const navigate = useNavigate();

  // If the session already exists, immediately go home.
  if (isSignedIn) {
    return <Navigate to="/" replace />;
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-live="polite">
        <div className="auth-card__brand">
          <span>L00m AI</span>
          <h1>Finishing sign-in</h1>
          <p>Securely connecting your session.</p>
        </div>

        <HandleSSOCallback
          navigateToApp={({ decorateUrl }) => {
            navigate(decorateUrl("/"), { replace: true });
          }}
          navigateToSignIn={() => {
            navigate("/sign-in", { replace: true });
          }}
          navigateToSignUp={() => {
            navigate("/sign-up", { replace: true });
          }}
        />
      </section>
    </main>
  );
}

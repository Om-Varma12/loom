import { useSignIn } from "@clerk/react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import "./AuthPage.css";

type SocialStrategy = "oauth_google" | "oauth_github";

export default function SignIn() {
  const { signIn, errors, fetchStatus } = useSignIn();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  const finalize = async () => {
    await signIn.finalize({
      navigate: ({ decorateUrl }) => navigate(decorateUrl("/")),
    });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setStatusMessage("");

    const { error } = await signIn.password({
      identifier: email,
      password,
    });

    if (error) {
      return;
    }

    if (signIn.status === "complete") {
      await finalize();
      return;
    }

    if (signIn.status === "needs_second_factor") {
      setStatusMessage("This account requires a second factor before sign-in.");
      return;
    }

    setStatusMessage("Additional verification is required to finish sign-in.");
  };

  const signInWith = async (strategy: SocialStrategy) => {
    await signIn.sso({
      strategy,
      redirectUrl: "/sso-callback",
      redirectCallbackUrl: "/sso-callback",
    });
  };

  const isLoading = fetchStatus === "fetching";

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="sign-in-title">
        <div className="auth-card__brand">
          <span>L00m AI</span>
          <h1 id="sign-in-title">Sign in</h1>
          <p>Continue to your developer workspace.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Email
            <input
              autoComplete="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>
          {errors.fields.identifier ? (
            <p className="auth-error">{errors.fields.identifier.message}</p>
          ) : null}

          <label>
            Password
            <input
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>
          {errors.fields.password ? (
            <p className="auth-error">{errors.fields.password.message}</p>
          ) : null}

          {statusMessage ? <p className="auth-error">{statusMessage}</p> : null}

          <button className="auth-button" disabled={isLoading} type="submit">
            {isLoading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div className="auth-divider" />

        <div className="auth-actions">
          <button
            className="auth-button auth-button--secondary"
            onClick={() => void signInWith("oauth_google")}
            type="button"
          >
            Continue with Google
          </button>
          <button
            className="auth-button auth-button--secondary"
            onClick={() => void signInWith("oauth_github")}
            type="button"
          >
            Continue with GitHub
          </button>
        </div>

        <p>
          New here?{" "}
          <Link className="auth-link" to="/sign-up">
            Create an account
          </Link>
        </p>
      </section>
    </main>
  );
}

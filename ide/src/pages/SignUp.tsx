import { useAuth, useSignUp } from "@clerk/react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import "./AuthPage.css";

type SocialStrategy = "oauth_google" | "oauth_github";

export default function SignUp() {
  const { isSignedIn } = useAuth();
  const { signUp, errors, fetchStatus } = useSignUp();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [isVerifyingEmail, setIsVerifyingEmail] = useState(false);

  const finalize = async () => {
    await signUp.finalize({
      navigate: ({ decorateUrl }) => navigate(decorateUrl("/")),
    });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    const { error } = await signUp.password({
      emailAddress: email,
      password,
    });

    if (error) {
      return;
    }

    if (signUp.status === "complete") {
      await finalize();
      return;
    }

    await signUp.verifications.sendEmailCode();
    setIsVerifyingEmail(true);
  };

  const handleVerify = async (event: React.FormEvent) => {
    event.preventDefault();

    const { error } = await signUp.verifications.verifyEmailCode({ code });
    if (error) {
      return;
    }

    if (signUp.status === "complete") {
      await finalize();
    }
  };

  const signUpWith = async (strategy: SocialStrategy) => {
    await signUp.sso({
      strategy,
      redirectUrl: "/sso-callback",
      redirectCallbackUrl: "/sso-callback",
    });
  };

  if (isSignedIn || signUp.status === "complete") {
    return null;
  }

  const isLoading = fetchStatus === "fetching";

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="sign-up-title">
        <div className="auth-card__brand">
          <span>L00m AI</span>
          <h1 id="sign-up-title">
            {isVerifyingEmail ? "Verify email" : "Create account"}
          </h1>
          <p>
            {isVerifyingEmail
              ? "Enter the code Clerk sent to your email."
              : "Start a protected workspace with your own projects and chats."}
          </p>
        </div>

        {isVerifyingEmail ? (
          <form className="auth-form" onSubmit={handleVerify}>
            <label>
              Verification code
              <input
                autoComplete="one-time-code"
                inputMode="numeric"
                onChange={(event) => setCode(event.target.value)}
                required
                value={code}
              />
            </label>
            {errors.fields.code ? (
              <p className="auth-error">{errors.fields.code.message}</p>
            ) : null}
            <button className="auth-button" disabled={isLoading} type="submit">
              {isLoading ? "Verifying..." : "Verify"}
            </button>
            <button
              className="auth-button auth-button--secondary"
              onClick={() => void signUp.verifications.sendEmailCode()}
              type="button"
            >
              Resend code
            </button>
          </form>
        ) : (
          <>
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
              {errors.fields.emailAddress ? (
                <p className="auth-error">
                  {errors.fields.emailAddress.message}
                </p>
              ) : null}

              <label>
                Password
                <input
                  autoComplete="new-password"
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type="password"
                  value={password}
                />
              </label>
              {errors.fields.password ? (
                <p className="auth-error">{errors.fields.password.message}</p>
              ) : null}

              <button
                className="auth-button"
                disabled={isLoading}
                type="submit"
              >
                {isLoading ? "Creating..." : "Create account"}
              </button>
              <div id="clerk-captcha" />
            </form>

            <div className="auth-divider" />

            <div className="auth-actions">
              <button
                className="auth-button auth-button--secondary"
                onClick={() => void signUpWith("oauth_google")}
                type="button"
              >
                Continue with Google
              </button>
              <button
                className="auth-button auth-button--secondary"
                onClick={() => void signUpWith("oauth_github")}
                type="button"
              >
                Continue with GitHub
              </button>
            </div>
          </>
        )}

        <p>
          Already have an account?{" "}
          <Link className="auth-link" to="/sign-in">
            Sign in
          </Link>
        </p>
      </section>
    </main>
  );
}

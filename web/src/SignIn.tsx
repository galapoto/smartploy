import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, LockKeyhole, ShieldCheck } from "lucide-react";
import BrandMark from "./BrandMark";

type Mode = "signin" | "signup";

/** The frontend collects no credentials; all authentication stays with ZITADEL. */
export default function SignIn() {
  const [mode, setMode] = useState<Mode>("signin");
  const [googleAvailable, setGoogleAvailable] = useState(false);
  const [providerChecked, setProviderChecked] = useState(false);
  const signup = mode === "signup";

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/auth/providers", {
      credentials: "same-origin", cache: "no-store", signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) return;
      const info: unknown = await response.json();
      if (!controller.signal.aborted && info && typeof info === "object" &&
          "google" in info) {
        setGoogleAvailable((info as { google: unknown }).google === true);
      }
    }).catch(() => {
      // A failed anonymous capability read cannot claim Google works.
    }).finally(() => {
      if (!controller.signal.aborted) setProviderChecked(true);
    });
    return () => controller.abort();
  }, []);

  const standardHref = signup ? "/auth/login?intent=signup" : "/auth/login";
  const googleHref = signup
    ? "/auth/login?intent=signup&provider=google"
    : "/auth/login?provider=google";
  const googleLabel = signup ? "Sign up with Google" : "Sign in with Google";
  const googleImage = signup
    ? "/google-signup-light.png" : "/google-signin-light.png";

  return <div className="sp-auth">
    <a className="sp-auth-skip" href="#smartploy-auth-heading">Skip to authentication</a>
    <section className="sp-auth-story" aria-labelledby="sp-auth-story-heading">
      <div className="sp-auth-brand">
        <BrandMark className="sp-auth-mark" /><span>SmartPloy</span>
      </div>
      <div className="sp-auth-story-main">
        <p className="sp-auth-kicker">THE JOB APPLICATION WORKSPACE</p>
        <h1 id="sp-auth-story-heading">Apply with <span>confidence.</span></h1>
        <p className="sp-auth-story-copy">Your profile. Your applications. Your next opportunity.</p>
        <div className="sp-auth-steps" aria-label="How SmartPloy works">
          <div><span>01</span><strong>Save your profile once</strong></div>
          <div><span>02</span><strong>Prepare each application</strong></div>
          <div><span>03</span><strong>Review before sending</strong></div>
        </div>
      </div>
      <p className="sp-auth-story-foot"><ShieldCheck size={17} aria-hidden="true" />
        Your career information stays under your control.</p>
    </section>
    <main className="sp-auth-panel">
      <div className="sp-auth-mobile-brand">
        <BrandMark className="sp-auth-mark" /><strong>SmartPloy</strong>
      </div>
      <section className="sp-auth-card" aria-labelledby="smartploy-auth-heading">
        <div className="sp-auth-switch" role="group" aria-label="Choose sign in or sign up">
          <button type="button" className={!signup ? "is-active" : ""}
            aria-pressed={!signup} onClick={() => setMode("signin")}>Sign in</button>
          <button type="button" className={signup ? "is-active" : ""}
            aria-pressed={signup} onClick={() => setMode("signup")}>Sign up</button>
        </div>
        <p className="sp-auth-eyebrow">{signup ? "GET STARTED" : "WELCOME BACK"}</p>
        <h2 id="smartploy-auth-heading">{signup ? "Create your account" : "Welcome back"}</h2>
        <p className="sp-auth-description">{signup
          ? "One account for your CV, job search and applications."
          : "Sign in to continue where you left off."}</p>
        <a className="sp-auth-main-action" href={standardHref}>
          <LockKeyhole size={18} aria-hidden="true" />
          {signup ? "Create account securely" : "Continue securely"}
          <ArrowRight size={18} aria-hidden="true" />
        </a>
        <div className="sp-auth-separator" aria-hidden="true"><span>or</span></div>
        <div className="sp-auth-google-slot">
          {googleAvailable
            ? <a className="sp-auth-google-button" href={googleHref}
                aria-label={googleLabel}>
                <img src={googleImage} alt="" loading="eager"
                  width={signup ? 179 : 175} height={40} />
              </a>
            : <button className="sp-auth-google-button" type="button"
                disabled aria-label={googleLabel + " (unavailable)"}>
                <img src={googleImage} alt=""
                  width={signup ? 179 : 175} height={40} />
              </button>}
        </div>
        {providerChecked && !googleAvailable ?
          <p className="sp-auth-provider-note" role="status">
            Google sign-in will be available after it is enabled in ZITADEL.
          </p> : null}
        <p className="sp-auth-footnote"><CheckCircle2 size={16} aria-hidden="true" />
          Secure authentication is managed by ZITADEL.</p>
        <p className="sp-auth-bottom-question">{signup
          ? "Already have an account?" : "New to SmartPloy?"}
          <button type="button" onClick={() => setMode(signup ? "signin" : "signup")}>
            {signup ? "Sign in" : "Create an account"}
          </button>
        </p>
      </section>
      <p className="sp-auth-panel-footer">SmartPloy · Secure, accessible job applications</p>
    </main>
  </div>;
}

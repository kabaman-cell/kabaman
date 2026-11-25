"use client";

import { use, useState } from "react";
import type { FormEvent } from "react";
import { notFound, useRouter } from "next/navigation";
import { isLocale, messages } from "@/i18n/config";

type LoginPageProps = {
  params: Promise<{ locale: string }>;
};

export default function LoginPage({ params }: LoginPageProps) {
  const { locale: localeParam } = use(params);
  const locale = isLocale(localeParam) ? localeParam : "fr";
  const copy = messages[locale];
  const login = copy.login;
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isLocale(localeParam)) {
    notFound();
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    const trimmedEmail = email.trim();
    if (trimmedEmail === "" || password === "") {
      setError(login.required);
      return;
    }
    setPending(true);
    setError(null);
    try {
      const response = await fetch("/api/employee/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: trimmedEmail, password }),
      });
      if (!response.ok) {
        setError(login.failed);
        setPending(false);
        return;
      }
    } catch {
      setError(login.failed);
      setPending(false);
      return;
    }
    router.refresh();
    router.push(`/${locale}/dashboard`);
  }

  return (
    <div className="shell">
      <main className="panel login-panel">
        <p className="mark" dir="ltr">
          {copy.brand}
        </p>
        <h1>{login.heading}</h1>
        <p className="welcome-text">{login.intro}</p>
        <form className="login-form" onSubmit={onSubmit} noValidate>
          <label htmlFor="employee-email">{login.emailLabel}</label>
          <input
            id="employee-email"
            name="email"
            type="email"
            autoComplete="username"
            dir="ltr"
            value={email}
            disabled={pending}
            aria-invalid={error ? true : undefined}
            onChange={(event) => setEmail(event.target.value)}
          />
          <label htmlFor="employee-password">{login.passwordLabel}</label>
          <input
            id="employee-password"
            name="password"
            type="password"
            autoComplete="current-password"
            dir="ltr"
            value={password}
            disabled={pending}
            aria-invalid={error ? true : undefined}
            onChange={(event) => setPassword(event.target.value)}
          />
          {error ? (
            <p className="login-error" role="alert">
              {error}
            </p>
          ) : null}
          <button type="submit" disabled={pending}>
            {pending ? login.submitting : login.submit}
          </button>
        </form>
      </main>
      <style>{`
        .login-panel {
          width: min(100%, 28rem);
        }
        .login-form {
          display: grid;
          gap: 0.45rem;
          margin-top: 1.5rem;
        }
        .login-form label {
          margin-top: 0.45rem;
          color: var(--text-secondary);
          font-size: 0.85rem;
        }
        .login-form input {
          min-height: 2.6rem;
          padding: 0.45rem 0.7rem;
          color: var(--text);
          background: var(--button-background);
          border: 1px solid var(--brown);
          border-radius: 0;
        }
        .login-form button {
          margin-top: 0.8rem;
          min-height: 2.7rem;
          color: var(--background);
          background: var(--accent);
          border: 1px solid var(--accent);
          font-weight: 600;
          cursor: pointer;
        }
        .login-form button:disabled {
          cursor: wait;
          opacity: 0.7;
        }
        .login-error {
          margin: 0.35rem 0 0;
          color: var(--text);
        }
        .login-form input:focus-visible,
        .login-form button:focus-visible {
          outline: 2px solid var(--accent);
          outline-offset: 2px;
        }
        @media (prefers-reduced-motion: reduce) {
          .login-form button {
            transition: none;
          }
        }
      `}</style>
    </div>
  );
}

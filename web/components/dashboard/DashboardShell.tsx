"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  activeSection,
  sectionHref,
  sectionIds,
  type SectionId,
} from "@/dashboard/sections";
import {
  isLocale,
  locales,
  messages,
  type DashboardCopy,
  type Locale,
} from "@/i18n/config";

type DashboardShellProps = {
  locale: Locale;
  children: ReactNode;
};

export function DashboardShell({ locale, children }: DashboardShellProps) {
  const pathname = usePathname();
  const pathLocale = pathname.split("/")[1] ?? "";
  const currentLocale = isLocale(pathLocale) ? pathLocale : locale;
  const copy = messages[currentLocale].dashboard;
  const current = activeSection(pathname);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
    setAccountOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen && !accountOpen) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        setAccountOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen, accountOpen]);

  return (
    <div className={collapsed ? "dashboard is-collapsed" : "dashboard"}>
      {mobileOpen ? (
        <button
          type="button"
          className="dashboard-backdrop"
          aria-label={copy.closeSidebar}
          onClick={() => setMobileOpen(false)}
        />
      ) : null}
      <Sidebar
        locale={currentLocale}
        copy={copy}
        brand={messages[currentLocale].brand}
        current={current}
        mobileOpen={mobileOpen}
        onNavigate={() => setMobileOpen(false)}
      />
      <div className="dashboard-main">
        <Topbar
          locale={currentLocale}
          pathname={pathname}
          copy={copy}
          title={copy.nav[current]}
          collapsed={collapsed}
          mobileOpen={mobileOpen}
          accountOpen={accountOpen}
          onToggleMobile={() => setMobileOpen((open) => !open)}
          onToggleDesktop={() => setCollapsed((value) => !value)}
          onToggleAccount={() => setAccountOpen((open) => !open)}
        />
        <main className="dashboard-content">{children}</main>
      </div>
    </div>
  );
}

function Sidebar({
  locale,
  copy,
  brand,
  current,
  mobileOpen,
  onNavigate,
}: {
  locale: Locale;
  copy: DashboardCopy;
  brand: string;
  current: SectionId;
  mobileOpen: boolean;
  onNavigate: () => void;
}) {
  return (
    <aside
      className={mobileOpen ? "sidebar is-mobile-open" : "sidebar"}
      id="dashboard-sidebar"
    >
      <p className="sidebar-brand" dir="ltr">
        <span className="sidebar-brand-mark" aria-hidden="true">
          K
        </span>
        <span className="sidebar-brand-text">{brand}</span>
      </p>
      <nav className="sidebar-nav" aria-label={copy.navigation}>
        <ul>
          {sectionIds.map((id) => {
            const active = id === current;
            return (
              <li key={id}>
                <Link
                  href={sectionHref(locale, id)}
                  className={active ? "nav-link is-active" : "nav-link"}
                  aria-current={active ? "page" : undefined}
                  onClick={onNavigate}
                >
                  <span className={`nav-mark nav-mark-${id}`} aria-hidden="true" />
                  <span className="nav-label">{copy.nav[id]}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}

function Topbar({
  locale,
  pathname,
  copy,
  title,
  collapsed,
  mobileOpen,
  accountOpen,
  onToggleMobile,
  onToggleDesktop,
  onToggleAccount,
}: {
  locale: Locale;
  pathname: string;
  copy: DashboardCopy;
  title: string;
  collapsed: boolean;
  mobileOpen: boolean;
  accountOpen: boolean;
  onToggleMobile: () => void;
  onToggleDesktop: () => void;
  onToggleAccount: () => void;
}) {
  const router = useRouter();
  const [logoutPending, setLogoutPending] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const parts = pathname.split("/");

  async function logout() {
    setLogoutPending(true);
    setLogoutError(null);
    try {
      const response = await fetch("/api/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) {
        setLogoutError(copy.logoutFailed);
        setLogoutPending(false);
        return;
      }
    } catch {
      setLogoutError(copy.logoutFailed);
      setLogoutPending(false);
      return;
    }
    router.refresh();
    router.push(`/${locale}/login`);
  }

  return (
    <header className="topbar">
      <button
        type="button"
        className="sidebar-toggle mobile-only"
        aria-expanded={mobileOpen}
        aria-controls="dashboard-sidebar"
        aria-label={mobileOpen ? copy.closeSidebar : copy.openSidebar}
        onClick={onToggleMobile}
      >
        <span className="menu-glyph" aria-hidden="true" />
      </button>
      <button
        type="button"
        className="sidebar-toggle desktop-only"
        aria-expanded={!collapsed}
        aria-controls="dashboard-sidebar"
        aria-label={collapsed ? copy.expandSidebar : copy.collapseSidebar}
        onClick={onToggleDesktop}
      >
        <span className="menu-glyph" aria-hidden="true" />
      </button>
      <p className="topbar-title">{title}</p>
      <nav className="locale-switcher" aria-label={copy.localeSwitcher} dir="ltr">
        {locales.map((code) => {
          const nextParts = [...parts];
          nextParts[1] = code;
          return (
            <Link
              key={code}
              href={nextParts.join("/") || `/${code}/dashboard`}
              hrefLang={code}
              lang={code}
              aria-current={code === locale ? "true" : undefined}
            >
              {code.toUpperCase()}
            </Link>
          );
        })}
      </nav>
      <div className="account">
        <button
          type="button"
          aria-expanded={accountOpen}
          aria-controls="account-menu"
          aria-haspopup="dialog"
          onClick={onToggleAccount}
        >
          {copy.account}
        </button>
        {accountOpen ? (
          <div id="account-menu" role="dialog" aria-label={copy.account}>
            <button type="button" onClick={logout} disabled={logoutPending}>
              {logoutPending ? copy.logoutPending : copy.logout}
            </button>
            {logoutError ? <p role="alert">{logoutError}</p> : null}
          </div>
        ) : null}
      </div>
    </header>
  );
}

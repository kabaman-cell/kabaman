import type { SectionId } from "@/dashboard/sections";
import ar from "./messages/ar";
import en from "./messages/en";
import fr from "./messages/fr";

export const locales = ["ar", "fr", "en"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "fr";

export type Direction = "rtl" | "ltr";

export type DashboardCopy = {
  navigation: string;
  openSidebar: string;
  closeSidebar: string;
  collapseSidebar: string;
  expandSidebar: string;
  localeSwitcher: string;
  account: string;
  accountUnavailable: string;
  logout: string;
  logoutPending: string;
  logoutFailed: string;
  overviewHeading: string;
  overviewBody: string;
  metricsHeading: string;
  metricsEmpty: string;
  notImplemented: string;
  nav: Record<SectionId, string>;
};

export type LoginCopy = {
  heading: string;
  intro: string;
  emailLabel: string;
  passwordLabel: string;
  submit: string;
  submitting: string;
  required: string;
  failed: string;
};

export type Messages = {
  documentTitle: string;
  brand: string;
  title: string;
  welcome: string;
  localeLabel: string;
  directionLabel: string;
  directionValue: string;
  preview: string;
  dashboard: DashboardCopy;
  login: LoginCopy;
};

export function isLocale(value: string): value is Locale {
  return locales.some((locale) => locale === value);
}

export function getDirection(locale: Locale): Direction {
  return locale === "ar" ? "rtl" : "ltr";
}

export const messages: Record<Locale, Messages> = {
  ar,
  fr,
  en,
};

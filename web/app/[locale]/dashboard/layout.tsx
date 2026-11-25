import type { ReactNode } from "react";
import { notFound, redirect } from "next/navigation";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { isLocale } from "@/i18n/config";
import { readEmployeeSession } from "@/lib/session";
import "../../dashboard.css";

type DashboardLayoutProps = {
  children: ReactNode;
  params: Promise<{ locale: string }>;
};

export const dynamic = "force-dynamic";

export default async function DashboardLayout({
  children,
  params,
}: DashboardLayoutProps) {
  const { locale } = await params;
  if (!isLocale(locale)) {
    notFound();
  }

  const employee = await readEmployeeSession();
  if (employee === null) {
    redirect(`/${locale}/login`);
  }

  return <DashboardShell locale={locale}>{children}</DashboardShell>;
}

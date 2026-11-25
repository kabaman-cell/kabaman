import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { isLocale, messages } from "@/i18n/config";

type OverviewPageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({
  params,
}: OverviewPageProps): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) {
    return {};
  }
  return {
    title: `${messages[locale].dashboard.nav.overview} · KABAMAN OS`,
  };
}

export default async function OverviewPage({ params }: OverviewPageProps) {
  const { locale } = await params;
  if (!isLocale(locale)) {
    notFound();
  }
  const copy = messages[locale].dashboard;

  return (
    <article className="dashboard-page">
      <h1>{copy.overviewHeading}</h1>
      <p className="dashboard-lead">{copy.overviewBody}</p>
      <section className="dashboard-panel" aria-labelledby="metrics-heading">
        <h2 id="metrics-heading">{copy.metricsHeading}</h2>
        <p className="dashboard-empty">{copy.metricsEmpty}</p>
      </section>
    </article>
  );
}

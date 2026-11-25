import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { routedSectionSlugs, sectionIdFromSlug } from "@/dashboard/sections";
import { isLocale, messages } from "@/i18n/config";

type SectionPageProps = {
  params: Promise<{ locale: string; section: string }>;
};

export function generateStaticParams() {
  return routedSectionSlugs.map((section) => ({ section }));
}

export const dynamicParams = false;

export async function generateMetadata({
  params,
}: SectionPageProps): Promise<Metadata> {
  const { locale, section } = await params;
  const id = sectionIdFromSlug(section);
  if (!isLocale(locale) || !id) {
    return {};
  }
  return { title: `${messages[locale].dashboard.nav[id]} · KABAMAN OS` };
}

export default async function SectionPage({ params }: SectionPageProps) {
  const { locale, section } = await params;
  const id = sectionIdFromSlug(section);
  if (!isLocale(locale) || !id) {
    notFound();
  }
  const copy = messages[locale].dashboard;

  return (
    <article className="dashboard-page">
      <h1>{copy.nav[id]}</h1>
      <p className="dashboard-empty">{copy.notImplemented}</p>
    </article>
  );
}

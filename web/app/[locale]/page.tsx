import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { isLocale, messages } from "@/i18n/config";

type LocalePageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({
  params,
}: LocalePageProps): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) {
    return {};
  }

  return { title: messages[locale].documentTitle };
}

export default async function LocalePage({ params }: LocalePageProps) {
  const { locale } = await params;
  if (!isLocale(locale)) {
    notFound();
  }

  const copy = messages[locale];

  return (
    <div className="shell">
    <main className="panel">
      <p className="mark" dir="ltr">
        {copy.brand}
      </p>
      <h1>{copy.title}</h1>
      <p className="welcome-text">{copy.welcome}</p>
      <dl className="facts">
        <div>
          <dt>{copy.localeLabel}</dt>
          <dd dir="ltr">{locale}</dd>
        </div>
        <div>
          <dt>{copy.directionLabel}</dt>
          <dd>{copy.directionValue}</dd>
        </div>
      </dl>
      <p className="preview">{copy.preview}</p>
    </main>
    </div>
  );
}

export const sectionIds = [
  "overview",
  "orders",
  "customers",
  "employees",
  "sourcing",
  "inspection",
  "shipments",
  "cargo",
  "documents",
  "finance",
  "whatsapp",
  "reports",
  "website",
  "settings",
] as const;

export type SectionId = (typeof sectionIds)[number];

export const sectionSlugs = {
  overview: null,
  orders: "orders",
  customers: "customers",
  employees: "employees",
  sourcing: "sourcing",
  inspection: "inspection",
  shipments: "shipments",
  cargo: "cargo",
  documents: "documents",
  finance: "finance",
  whatsapp: "whatsapp",
  reports: "reports",
  website: "website",
  settings: "settings",
} as const satisfies Record<SectionId, string | null>;

export type SectionSlug = Exclude<(typeof sectionSlugs)[SectionId], null>;

export function isSectionSlug(value: string): value is SectionSlug {
  return sectionIds.some((id) => sectionSlugs[id] === value);
}

export function sectionIdFromSlug(slug: string): SectionId | null {
  const match = sectionIds.find((id) => sectionSlugs[id] === slug);
  return match ?? null;
}

export function sectionHref(locale: string, id: SectionId): string {
  const slug = sectionSlugs[id];
  return slug ? `/${locale}/dashboard/${slug}` : `/${locale}/dashboard`;
}

export function activeSection(pathname: string): SectionId {
  const parts = pathname.split("/").filter(Boolean);
  const slug = parts[2];
  if (!slug) {
    return "overview";
  }
  return sectionIdFromSlug(slug) ?? "overview";
}

export const routedSectionSlugs: SectionSlug[] = sectionIds.flatMap((id) => {
  const slug = sectionSlugs[id];
  return slug ? [slug] : [];
});

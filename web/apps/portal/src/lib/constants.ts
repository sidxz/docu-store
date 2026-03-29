/** Mutable — set by AppConfigProvider during app init. */
export let API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Called once from Providers after runtime config is loaded. */
export function _setApiUrl(url: string) {
  API_URL = url;
}

export const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  GENERIC_PRESENTATION: "Presentation",
  SCIENTIFIC_PRESENTATION: "Scientific Presentation",
  RESEARCH_ARTICLE: "Research Article",
  SCIENTIFIC_DOCUMENT: "Scientific Document",
  DISCLOSURE_DOCUMENT: "Disclosure",
  MINUTE_OF_MEETING: "Minutes",
  UNCLASSIFIED: "Unclassified",
};

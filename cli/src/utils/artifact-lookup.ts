import { authHeaders } from "../api/client.js";

/**
 * Paginate through artifacts to find one by filename (case-insensitive).
 * Returns the artifact_id or null if not found.
 */
export async function findArtifactByFilename(
  apiUrl: string,
  creds: { idp_token: string; authz_token: string },
  filename: string,
): Promise<string | null> {
  let skip = 0;
  const limit = 100;

  while (true) {
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(limit),
      sort_by: "updated_at",
      sort_order: "-1",
    });

    const resp = await fetch(`${apiUrl}/artifacts?${params}`, {
      headers: authHeaders(creds),
    });

    if (!resp.ok) return null;

    const artifacts = (await resp.json()) as Array<{
      artifact_id: string;
      source_filename: string | null;
    }>;
    if (!artifacts.length) return null;

    const match = artifacts.find(
      (a) =>
        a.source_filename === filename ||
        a.source_filename?.toLowerCase() === filename.toLowerCase(),
    );

    if (match) return match.artifact_id;
    if (artifacts.length < limit) return null;
    skip += limit;
  }
}

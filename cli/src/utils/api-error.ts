/** Extract a human-readable error message from a failed API response. */
export async function extractApiError(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    return (body as { detail?: string }).detail || resp.statusText;
  } catch {
    return resp.statusText;
  }
}

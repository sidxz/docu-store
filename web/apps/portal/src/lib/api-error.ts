export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isNotFound() {
    return this.status === 404;
  }

  get isUnauthorized() {
    return this.status === 401;
  }

  get isForbidden() {
    return this.status === 403;
  }

  get isServerError() {
    return this.status !== undefined && this.status >= 500;
  }
}

/**
 * Throw an ApiError from an openapi-fetch error response.
 * Extracts `detail` from the error body (FastAPI convention).
 */
export function throwApiError(
  fallbackMessage: string,
  error: unknown,
  status?: number,
): never {
  let detail: string | undefined;
  if (error && typeof error === "object") {
    const e = error as Record<string, unknown>;
    if (typeof e.detail === "string") detail = e.detail;
    else if (typeof e.message === "string") detail = e.message;
  }
  throw new ApiError(detail ?? fallbackMessage, status, detail);
}

/** User-friendly message for display in error UIs. */
export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isNotFound) return "Not found. The resource may have been deleted.";
    if (error.isForbidden) return "You don't have permission to access this resource.";
    if (error.isUnauthorized) return "Your session has expired. Please sign in again.";
    if (error.isServerError) return error.detail ?? "Server error. Please try again later.";
    if (error.detail) return error.detail;
  }
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred.";
}

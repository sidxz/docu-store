export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export function appPath(path: string): string {
  return `${BASE_PATH}${path}`;
}

/** Convert browser return URLs to application-relative Next.js destinations. */
export function routePath(path: string): string | null {
  if (!path.startsWith("/") || path.startsWith("//") || /[\\\u0000-\u001f]/.test(path)) {
    return null;
  }
  const url = new URL(path, "https://app.invalid");
  if (url.origin !== "https://app.invalid") return null;
  const pathname =
    BASE_PATH && (url.pathname === BASE_PATH || url.pathname.startsWith(`${BASE_PATH}/`))
      ? url.pathname.slice(BASE_PATH.length) || "/"
      : url.pathname;
  if (pathname.startsWith("//")) return null;
  return `${pathname}${url.search}${url.hash}`;
}

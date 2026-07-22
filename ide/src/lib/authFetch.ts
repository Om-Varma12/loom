const API_BASE_URL =
  import.meta.env.VITE_BACKEND_ADDR ??
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";

type TokenGetter = () => Promise<string | null>;
type CacheResetter = () => void;

let tokenGetter: TokenGetter | null = null;
const cacheResetters = new Set<CacheResetter>();

export function apiUrl(path: string): string {
  const base = API_BASE_URL.replace(/\/$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

export function setAuthTokenGetter(getter: TokenGetter | null) {
  tokenGetter = getter;
}

export function registerAuthCacheResetter(resetter: CacheResetter) {
  cacheResetters.add(resetter);
  return () => cacheResetters.delete(resetter);
}

export function resetAuthCaches() {
  cacheResetters.forEach((resetter) => resetter());
}

export async function authFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = await tokenGetter?.();

  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return fetch(input, {
    ...init,
    headers,
  });
}

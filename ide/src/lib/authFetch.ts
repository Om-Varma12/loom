import { apiUrl, API_BASE_URL } from "./api";
export { apiUrl, API_BASE_URL };

type TokenGetter = () => Promise<string | null>;
type CacheResetter = () => void;

let tokenGetter: TokenGetter | null = null;
const cacheResetters = new Set<CacheResetter>();

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

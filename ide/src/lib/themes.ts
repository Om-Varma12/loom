let _rawApiBaseUrl = import.meta.env.VITE_BACKEND_ADDR ?? import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
if (_rawApiBaseUrl && !_rawApiBaseUrl.startsWith("http://") && !_rawApiBaseUrl.startsWith("https://")) {
  _rawApiBaseUrl = `http://${_rawApiBaseUrl}`;
}
const API_BASE_URL = _rawApiBaseUrl;

export type ThemeMetadata = {
  id: string          // stem of the filename, e.g. "theme_claude"
  name: string        // human-readable name from frontmatter
  description: string // short description from frontmatter
  filename: string    // e.g. "theme_claude.md"
}

/**
 * Fetch all available themes from the backend.
 * No client-side caching — themes can be added at any time without a server
 * restart, so we always hit the API to get the latest list.
 * Returns an empty array on network/parse error (graceful degradation).
 */
export async function getThemes(): Promise<ThemeMetadata[]> {
  try {
    const response = await fetch(
      `${API_BASE_URL.replace(/\/$/, '')}/themes`,
      { method: 'GET' },
    )

    if (!response.ok) {
      console.warn('[themes] Failed to fetch themes:', response.status)
      return []
    }

    const data: ThemeMetadata[] = await response.json()
    return data
  } catch (err) {
    console.warn('[themes] Network error fetching themes:', err)
    return []
  }
}

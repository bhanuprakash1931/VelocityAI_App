/**
 * common/frontend/api.ts
 * ──────────────────────────
 * Shared API client used by all Velocity AI frontend applications.
 *
 * Usage in any app's src/api.ts:
 *
 *   export { api, BASE } from '../../../common/frontend/api';
 *
 * Or copy-reference in vite.config.ts resolve.alias if preferred.
 *
 * Design notes
 * ─────────────
 * - BASE is empty string in development so all /api/* requests are handled
 *   by the Vite dev-server proxy (see each app's vite.config.ts).
 * - In production set VITE_API_URL in the app's .env to the backend origin.
 * - FormData payloads must NOT have a Content-Type header (the browser sets
 *   the correct multipart boundary automatically).
 * - Any non-2xx response throws an Error whose message is the backend's
 *   `detail` field, falling back to the HTTP status text.
 */

export const BASE: string = (import.meta.env.VITE_API_URL as string) ?? '';

/**
 * Thin fetch wrapper.
 *
 * @param path  API path, e.g. '/api/sessions'
 * @param init  Standard RequestInit options (method, body, headers, …)
 * @returns     Parsed JSON response body
 * @throws      Error with the backend detail message on non-2xx responses
 */
export async function api(
  path: string,
  init: RequestInit = {},
): Promise<any> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      // Do NOT set Content-Type for FormData — browser handles multipart boundary
      ...(init.body instanceof FormData
        ? {}
        : { 'Content-Type': 'application/json' }),
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    const errorData = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      errorData.detail ?? `Request failed with HTTP ${response.status}`,
    );
  }

  return response.json();
}

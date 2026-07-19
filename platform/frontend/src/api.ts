// All /api/platform/* calls are proxied to the platform backend (port 7000)
// via the Vite dev server proxy. In production, set VITE_PLATFORM_API_URL.
const BASE = import.meta.env.VITE_PLATFORM_API_URL ?? '';

export async function api(
  path: string,
  init: RequestInit = {}
): Promise<any> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(init.body instanceof FormData
        ? {}
        : { 'Content-Type': 'application/json' }),
      ...(init.headers || {}),
    },
  });

  if (!response.ok) {
    const errorData = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      errorData.detail || `Request failed with HTTP ${response.status}`
    );
  }

  return response.json();
}

export { BASE };
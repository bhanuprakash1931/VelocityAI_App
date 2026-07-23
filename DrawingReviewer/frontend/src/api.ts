const BASE = import.meta.env.VITE_API_URL ?? '';

export async function api(
  path: string,
  init: RequestInit = {}
) {
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
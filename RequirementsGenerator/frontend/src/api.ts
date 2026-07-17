// const BASE=import.meta.env.VITE_API_URL||'http://localhost:8000';

// export async function api(path:string,init:RequestInit={})
// {const r=await fetch(BASE+path,
//     {...init,headers:
//         {...(init.body instanceof FormData?{}:
//             {'Content-Type':'application/json'}
//         ),...(init.headers||{})}});
//         if(!r.ok)throw new Error
//         ((await r.json().catch(()=>({detail:r.statusText}))).detail||'Request failed');
//         return r.json()}
// export{BASE};

// BASE is empty in dev — all /api/* requests go through the Vite proxy
// (see vite.config.ts → server.proxy) which forwards to localhost:8000.
// This means network users on any IP never make cross-port requests.
// Set VITE_API_URL in .env only for production deployments where the
// frontend and backend are on different origins.
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
        : { "Content-Type": "application/json" }),
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
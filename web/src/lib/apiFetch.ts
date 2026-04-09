/**
 * Authenticated fetch wrapper used by all protected pages.
 * Injects Authorization header from localStorage JWT.
 * Redirects to /login on 401.
 */

export function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('dgraphai_token')
  return token
    ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' }
}

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem('dgraphai_token')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  const resp = await fetch(input, { ...init, headers })
  if (resp.status === 401) {
    localStorage.removeItem('dgraphai_token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  return resp
}

/** GET with auth */
export const authGet  = (url: string) => apiFetch(url)
/** POST with auth and JSON body */
export const authPost = (url: string, body?: unknown) =>
  apiFetch(url, { method: 'POST', body: body ? JSON.stringify(body) : undefined })
/** PATCH with auth and JSON body */
export const authPatch = (url: string, body?: unknown) =>
  apiFetch(url, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined })
/** DELETE with auth */
export const authDelete = (url: string) =>
  apiFetch(url, { method: 'DELETE' })

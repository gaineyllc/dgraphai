/**
 * Auth utilities — JWT storage, header injection, token parsing.
 * All API calls go through these helpers to ensure auth headers are present.
 */

const TOKEN_KEY = 'dgraphai_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function isAuthenticated(): boolean {
  const token = getToken()
  if (!token) return false
  try {
    const payload = parseJWT(token)
    // Check expiry
    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) {
      clearToken()
      return false
    }
    return true
  } catch {
    clearToken()
    return false
  }
}

export function parseJWT(token: string): Record<string, any> {
  const parts = token.split('.')
  if (parts.length !== 3) throw new Error('Invalid JWT')
  return JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
}

export function getCurrentUser(): { id: string; email: string; name: string; tenant_id: string; plan: string } | null {
  const token = getToken()
  if (!token) return null
  try {
    const p = parseJWT(token)
    return {
      id:        p.sub,
      email:     p.email,
      name:      p.name || p.email,
      tenant_id: p.tenant_id,
      plan:      p.plan || 'starter',
    }
  } catch {
    return null
  }
}

export function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** Authenticated fetch wrapper — injects auth header, redirects on 401 */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  const resp = await fetch(input, { ...init, headers })
  if (resp.status === 401) {
    clearToken()
    window.location.href = '/login'
  }
  return resp
}

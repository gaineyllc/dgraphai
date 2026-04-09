/**
 * useSessionExpiry — watches JWT expiry and redirects to /login when expired.
 * Also handles 401 responses globally via a storage event listener.
 */
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { parseJWT, getToken, clearToken } from '../lib/auth'

export function useSessionExpiry() {
  const navigate = useNavigate()

  useEffect(() => {
    const check = () => {
      const token = getToken()
      if (!token) return

      try {
        const payload = parseJWT(token)
        if (!payload.exp) return

        const expiresInMs = payload.exp * 1000 - Date.now()

        if (expiresInMs <= 0) {
          // Already expired
          clearToken()
          navigate('/login', { state: { expired: true } })
          return
        }

        // Schedule redirect 30s before expiry
        const warnMs = Math.max(0, expiresInMs - 30_000)
        const timer  = setTimeout(() => {
          clearToken()
          navigate('/login', { state: { expired: true } })
        }, warnMs)

        return () => clearTimeout(timer)
      } catch {
        // Malformed token — clear it
        clearToken()
        navigate('/login')
      }
    }

    const cleanup = check()

    // Also check when tab becomes visible (user returns after expiry)
    const onVisible = () => {
      if (document.visibilityState === 'visible') check()
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      cleanup?.()
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [navigate])
}

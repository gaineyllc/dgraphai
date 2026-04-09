// @ts-nocheck
/**
 * AuthProvider — React context for current user + logout.
 */
import { createContext, useContext, useState, useEffect } from 'react'
import { getCurrentUser, clearToken, isAuthenticated } from '../lib/auth'

interface User {
  id: string; email: string; name: string; tenant_id: string; plan: string
}

interface AuthContextType {
  user:     User | null
  loading:  boolean
  logout:   () => void
  setUser:  (u: User | null) => void
}

const AuthContext = createContext<AuthContextType>({
  user: null, loading: true,
  logout: () => {}, setUser: () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,    setUser]    = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (isAuthenticated()) {
      setUser(getCurrentUser())
    }
    setLoading(false)
  }, [])

  const logout = () => {
    clearToken()
    setUser(null)
    window.location.href = '/login'
  }

  return (
    <AuthContext.Provider value={{ user, loading, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)

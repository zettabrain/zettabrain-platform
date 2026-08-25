import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { login as apiLogin, getMe, type User } from '../api/auth'

interface AuthContextValue {
  user: User | null
  token: string | null
  isLoading: boolean
  isAdmin: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('zb_token'))
  const [isLoading, setIsLoading] = useState(true)

  const logout = useCallback(() => {
    localStorage.removeItem('zb_token')
    localStorage.removeItem('zb_user')
    setToken(null)
    setUser(null)
  }, [])

  // Restore session on mount
  useEffect(() => {
    const stored = localStorage.getItem('zb_token')
    if (!stored) {
      setIsLoading(false)
      return
    }
    getMe()
      .then((me) => {
        setUser(me)
        setToken(stored)
      })
      .catch(() => {
        logout()
      })
      .finally(() => setIsLoading(false))
  }, [logout])

  const login = async (username: string, password: string) => {
    const res = await apiLogin(username, password)
    localStorage.setItem('zb_token', res.access_token)
    setToken(res.access_token)
    const me = await getMe()
    localStorage.setItem('zb_user', JSON.stringify(me))
    setUser(me)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAdmin: user?.system_role === 'admin',
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

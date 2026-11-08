import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { authApi, type Credentials } from '../api/auth'
import { SESSION_EXPIRED_EVENT, setAccessToken } from '../api/client'
import type { User } from '../types/api'
import { AuthContext } from './AuthContext'

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    function expireSession() {
      setUser(null)
      queryClient.clear()
    }

    window.addEventListener(SESSION_EXPIRED_EVENT, expireSession)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expireSession)
  }, [queryClient])

  const signIn = useCallback(async (credentials: Credentials) => {
    setBusy(true)
    try {
      return await authApi.login(credentials)
    } finally {
      setBusy(false)
    }
  }, [])

  const startGoogleSignIn = useCallback(async (
    credential: string,
    confirmAccountLink = false,
  ) => {
    setBusy(true)
    try {
      return await authApi.google(credential, confirmAccountLink)
    } finally {
      setBusy(false)
    }
  }, [])

  const verifyOtp = useCallback(async (challengeId: string, code: string) => {
    setBusy(true)
    try {
      const token = await authApi.verifyOtp(challengeId, code)
      setAccessToken(token.access_token, token.expires_in)
      const profile = await authApi.me()
      setUser(profile)
      return profile
    } catch (error) {
      setAccessToken(null)
      setUser(null)
      throw error
    } finally {
      setBusy(false)
    }
  }, [])

  const signOut = useCallback(() => {
    setAccessToken(null)
    setUser(null)
    queryClient.clear()
  }, [queryClient])

  const value = useMemo(
    () => ({ user, busy, signIn, startGoogleSignIn, verifyOtp, signOut }),
    [user, busy, signIn, startGoogleSignIn, verifyOtp, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

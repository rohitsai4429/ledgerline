import { createContext, useContext } from 'react'
import type { Credentials, GoogleStartResponse, OtpChallenge } from '../api/auth'
import type { User } from '../types/api'

export interface AuthContextValue {
  user: User | null
  busy: boolean
  signIn: (credentials: Credentials) => Promise<OtpChallenge>
  startGoogleSignIn: (credential: string, confirmAccountLink?: boolean) => Promise<GoogleStartResponse>
  verifyOtp: (challengeId: string, code: string) => Promise<User>
  signOut: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}

import { request } from './client'
import type { TokenResponse, User } from '../types/api'

export interface OtpChallenge {
  status: 'OTP_REQUIRED'
  challenge_id: string
  expires_in_seconds: number
  resend_after_seconds: number
  message: string
}

export interface GoogleLinkConfirmation {
  status: 'LINK_CONFIRMATION_REQUIRED'
  message: string
}

export type GoogleStartResponse = OtpChallenge | GoogleLinkConfirmation

export interface Credentials {
  email: string
  password: string
}

export interface Registration extends Credentials {}

export const authApi = {
  login: (credentials: Credentials) =>
    request<OtpChallenge>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    }),
  register: (registration: Registration) =>
    request<OtpChallenge>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(registration),
    }),
  google: (credential: string, confirmAccountLink = false) =>
    request<GoogleStartResponse>('/api/v1/auth/google', {
      method: 'POST',
      body: JSON.stringify({
        credential,
        confirm_account_link: confirmAccountLink,
      }),
    }),
  verifyOtp: (challengeId: string, code: string) =>
    request<TokenResponse>('/api/v1/auth/otp/verify', {
      method: 'POST',
      body: JSON.stringify({ challenge_id: challengeId, code }),
    }),
  resendOtp: (challengeId: string) =>
    request<{ challenge_id: string; retry_after_seconds: number; message: string }>(
      '/api/v1/auth/otp/resend',
      {
        method: 'POST',
        body: JSON.stringify({ challenge_id: challengeId }),
      },
    ),
  me: () => request<User>('/api/v1/auth/me'),
}

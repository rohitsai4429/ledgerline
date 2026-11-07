import { request } from './client'
import type { TokenResponse, User } from '../types/api'

export interface Credentials {
  email: string
  password: string
}

export interface Registration extends Credentials {}

export const authApi = {
  login: (credentials: Credentials) =>
    request<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    }),
  register: (registration: Registration) =>
    request<User>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(registration),
    }),
  me: () => request<User>('/api/v1/auth/me'),
}

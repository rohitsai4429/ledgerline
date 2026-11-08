import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authApi } from '../api/auth'
import { ApiError, getAccessToken, setAccessToken } from '../api/client'
import { AuthProvider } from '../auth/AuthProvider'
import { RequireAuth } from '../auth/RoleGate'
import { useAuth } from '../auth/AuthContext'
import { LoginPage, RegisterPage } from './AuthPages'

vi.mock('../api/auth', () => ({
  authApi: {
    login: vi.fn(),
    me: vi.fn(),
    register: vi.fn(),
    google: vi.fn(),
    verifyOtp: vi.fn(),
    resendOtp: vi.fn(),
  },
}))

const challenge = {
  status: 'OTP_REQUIRED' as const,
  challenge_id: 'challenge-1',
  expires_in_seconds: 300,
  resend_after_seconds: 0,
  message: 'A verification code has been sent to your email.',
}

const token = { access_token: 'ledgerline-token', expires_in: 1800, token_type: 'bearer' as const }

const user = {
  id: 'user-id',
  email: 'holder@example.com',
  role: 'ACCOUNT_HOLDER' as const,
  status: 'ACTIVE' as const,
  created_at: '2026-01-01T00:00:00Z',
}

function renderAuthPage(page: 'login' | 'register') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MemoryRouter initialEntries={[`/${page}`]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/dashboard" element={<p>Workspace home</p>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function ProviderSessionHarness() {
  const { verifyOtp } = useAuth()
  const navigate = useNavigate()
  return (
    <button onClick={async () => {
      await verifyOtp('challenge-1', '12345678')
      navigate('/protected')
    }}>Complete verification</button>
  )
}

function ProtectedSessionHarness() {
  const { signOut } = useAuth()
  return (
    <>
      <p>Protected dashboard</p>
      <button onClick={signOut}>Sign out</button>
    </>
  )
}

beforeEach(() => {
  setAccessToken(null)
  vi.mocked(authApi.login).mockReset()
  vi.mocked(authApi.me).mockReset()
  vi.mocked(authApi.register).mockReset()
  vi.mocked(authApi.google).mockReset()
  vi.mocked(authApi.verifyOtp).mockReset()
  vi.mocked(authApi.resendOtp).mockReset()
})

describe('OTP authentication', () => {
  it('validates required login fields before calling the API', async () => {
    renderAuthPage('login')
    fireEvent.click(screen.getByRole('button', { name: /sign in securely/i }))

    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument()
    expect(authApi.login).not.toHaveBeenCalled()
  })

  it('registers, requires OTP, then installs the LedgerLine JWT', async () => {
    vi.mocked(authApi.register).mockResolvedValue(challenge)
    vi.mocked(authApi.verifyOtp).mockResolvedValue(token)
    vi.mocked(authApi.me).mockResolvedValue(user)
    renderAuthPage('register')
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'holder@example.com' } })
    fireEvent.change(screen.getByPlaceholderText('Create a strong password'), { target: { value: 'secure-password-123' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'secure-password-123' } })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await screen.findByLabelText('Email verification code')
    expect(authApi.register).toHaveBeenCalledWith({
      email: 'holder@example.com',
      password: 'secure-password-123',
    })
    expect(getAccessToken()).toBeNull()
    expect(authApi.verifyOtp).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Email verification code'), { target: { value: '12345678' } })
    fireEvent.click(screen.getByRole('button', { name: /verify and continue/i }))
    expect(await screen.findByText('Workspace home')).toBeInTheDocument()
    expect(authApi.verifyOtp).toHaveBeenCalledWith('challenge-1', '12345678')
    expect(getAccessToken()).toBe('ledgerline-token')
  })

  it('password login does not install a JWT until OTP succeeds', async () => {
    vi.mocked(authApi.login).mockResolvedValue(challenge)
    vi.mocked(authApi.verifyOtp).mockResolvedValue(token)
    vi.mocked(authApi.me).mockResolvedValue(user)
    renderAuthPage('login')
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'holder@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct horse battery staple' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in securely/i }))

    await screen.findByLabelText('Email verification code')
    expect(authApi.login).toHaveBeenCalled()
    expect(getAccessToken()).toBeNull()
    expect(authApi.me).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Email verification code'), { target: { value: '87654321' } })
    fireEvent.click(screen.getByRole('button', { name: /verify and continue/i }))
    expect(await screen.findByText('Workspace home')).toBeInTheDocument()
    expect(getAccessToken()).toBe('ledgerline-token')
  })

  it('handles invalid OTP and offers resend without authenticating', async () => {
    vi.mocked(authApi.login).mockResolvedValue(challenge)
    vi.mocked(authApi.verifyOtp).mockRejectedValue(new ApiError('Verification code is invalid or expired', 400))
    vi.mocked(authApi.resendOtp).mockResolvedValue({
      challenge_id: 'challenge-1',
      retry_after_seconds: 60,
      message: 'If this sign-in can be completed, a code has been sent.',
    })
    renderAuthPage('login')
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'holder@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in securely/i }))
    await screen.findByLabelText('Email verification code')
    fireEvent.change(screen.getByLabelText('Email verification code'), { target: { value: '00000000' } })
    fireEvent.click(screen.getByRole('button', { name: /verify and continue/i }))
    expect(await screen.findByText('Verification code is invalid or expired')).toBeInTheDocument()
    expect(getAccessToken()).toBeNull()
    expect(authApi.me).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Resend code' }))
    await waitFor(() => expect(authApi.resendOtp).toHaveBeenCalledWith('challenge-1'))
  })

  it('uses the Google ID token as an OTP entry point, not a LedgerLine token', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'public-client-id')
    let googleCallback: ((response: { credential: string }) => void) | undefined
    const initialize = vi.fn((options: { callback: (response: { credential: string }) => void }) => {
      googleCallback = options.callback
    })
    const renderButton = vi.fn()
    Object.defineProperty(window, 'google', {
      configurable: true,
      value: { accounts: { id: { initialize, renderButton } } },
    })
    vi.mocked(authApi.google).mockResolvedValue(challenge)
    vi.mocked(authApi.verifyOtp).mockResolvedValue(token)
    vi.mocked(authApi.me).mockResolvedValue(user)
    renderAuthPage('login')
    await waitFor(() => expect(initialize).toHaveBeenCalled())
    googleCallback?.({ credential: 'signed-google-id-token' })

    await screen.findByLabelText('Email verification code')
    expect(authApi.google).toHaveBeenCalledWith('signed-google-id-token', false)
    expect(getAccessToken()).toBeNull()
    expect(authApi.me).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Email verification code'), { target: { value: '12345678' } })
    fireEvent.click(screen.getByRole('button', { name: /verify and continue/i }))
    expect(await screen.findByText('Workspace home')).toBeInTheDocument()
    expect(getAccessToken()).toBe('ledgerline-token')
    vi.unstubAllEnvs()
    delete (window as Window & { google?: unknown }).google
  })

  it('protects authenticated routes and clears the token on logout', async () => {
    vi.mocked(authApi.verifyOtp).mockResolvedValue(token)
    vi.mocked(authApi.me).mockResolvedValue(user)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <MemoryRouter initialEntries={['/login']}>
            <Routes>
              <Route path="/login" element={<ProviderSessionHarness />} />
              <Route element={<RequireAuth />}>
                <Route path="/protected" element={<ProtectedSessionHarness />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Complete verification' }))
    expect(await screen.findByText('Protected dashboard')).toBeInTheDocument()
    expect(getAccessToken()).toBe('ledgerline-token')

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(getAccessToken()).toBeNull())
    expect(screen.queryByText('Protected dashboard')).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Complete verification' })).toBeInTheDocument()
  })
})

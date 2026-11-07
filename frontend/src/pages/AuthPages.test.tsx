import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthProvider'
import { authApi } from '../api/auth'
import { LoginPage, RegisterPage } from './AuthPages'

vi.mock('../api/auth', () => ({
  authApi: {
    login: vi.fn(),
    me: vi.fn(),
    register: vi.fn(),
  },
}))

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

beforeEach(() => {
  vi.mocked(authApi.login).mockReset()
  vi.mocked(authApi.me).mockReset()
  vi.mocked(authApi.register).mockReset()
})

describe('authentication forms', () => {
  it('validates required login fields before calling the API', async () => {
    renderAuthPage('login')
    fireEvent.click(screen.getByRole('button', { name: /sign in securely/i }))

    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument()
    expect(authApi.login).not.toHaveBeenCalled()
  })

  it('registers only with the public email and password fields', async () => {
    vi.mocked(authApi.register).mockResolvedValue({
      id: 'user-id',
      email: 'holder@example.com',
      role: 'ACCOUNT_HOLDER',
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
    })
    renderAuthPage('register')
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'holder@example.com' } })
    fireEvent.change(screen.getByPlaceholderText('Create a strong password'), { target: { value: 'secure-password-123' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'secure-password-123' } })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => expect(authApi.register).toHaveBeenCalledWith({
      email: 'holder@example.com',
      password: 'secure-password-123',
    }))
    expect(await screen.findByText('Account created. You can now sign in.')).toBeInTheDocument()
  })
})

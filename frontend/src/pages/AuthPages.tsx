import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowRight, BadgeCheck, BookOpenCheck, LockKeyhole } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, FieldError, ProductDisclosure } from '../components/ui'

const loginSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
})

const registerSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(12, 'Use at least 12 characters').max(128, 'Password must be 128 characters or fewer'),
  confirmPassword: z.string(),
}).refine((value) => value.password === value.confirmPassword, {
  path: ['confirmPassword'],
  message: 'Passwords do not match',
})

type LoginValues = z.infer<typeof loginSchema>
type RegisterValues = z.infer<typeof registerSchema>

function AuthFrame({ children, mode }: { children: React.ReactNode; mode: 'login' | 'register' }) {
  return (
    <main className="auth-page">
      <section className="auth-aside">
        <div className="brand-lockup auth-brand">
          <div className="brand-symbol"><span /></div>
          <div><span className="brand-name">ledgerline</span><span className="brand-caption">FINANCIAL OPERATIONS</span></div>
        </div>
        <div className="auth-story">
          <p className="auth-overline"><span /> TRUST, RECONCILED</p>
          <h1>Every movement.<br /><em>Accounted for.</em></h1>
          <p className="auth-story-copy">
            A clearer view of your money, grounded in a ledger designed for accuracy and accountability.
          </p>
          <div className="auth-proof">
            <div className="proof-icon"><BookOpenCheck size={18} /></div>
            <div><strong>Internal ledger platform</strong><span>Reliable movement with balanced accounting records.</span></div>
          </div>
        </div>
        <div className="auth-footer-copy">LEDGERLINE FINANCIAL SERVICES <span>·</span> SECURE ACCESS</div>
      </section>
      <section className="auth-main">
        <div className="auth-mobile-brand">
          <div className="brand-symbol"><span /></div><span className="brand-name">ledgerline</span>
        </div>
        <div className="auth-card">
          <div className="auth-card-icon">{mode === 'login' ? <LockKeyhole size={20} /> : <BadgeCheck size={20} />}</div>
          <p className="eyebrow">{mode === 'login' ? 'WELCOME BACK' : 'GET STARTED'}</p>
          <h2>{mode === 'login' ? 'Sign in to LedgerLine' : 'Create your account'}</h2>
          <p className="auth-subtitle">
            {mode === 'login'
              ? 'Access your accounts and recent activity.'
              : 'Registration creates an account-holder profile.'}
          </p>
          {children}
          <div className="auth-switch">
            {mode === 'login' ? (
              <>New to LedgerLine? <Link to="/register">Create an account <ArrowRight size={14} /></Link></>
            ) : (
              <>Already registered? <Link to="/login">Sign in <ArrowRight size={14} /></Link></>
            )}
          </div>
          <div className="auth-security"><LockKeyhole size={13} /> API requests use short-lived bearer authentication.</div>
          <ProductDisclosure compact />
        </div>
      </section>
    </main>
  )
}

export function LoginPage() {
  const { user, signIn, busy } = useAuth()
  const navigate = useNavigate()
  const [serverError, setServerError] = useState('')
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })

  if (user) return <Navigate to="/dashboard" replace />

  async function submit(values: LoginValues) {
    setServerError('')
    try {
      await signIn(values)
      navigate('/dashboard', { replace: true })
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : 'Sign in could not be completed.')
    }
  }

  return (
    <AuthFrame mode="login">
      <form className="auth-form" onSubmit={handleSubmit(submit)} noValidate>
        {serverError && <Alert>{serverError}</Alert>}
        <label className="form-field">
          <span>Email address</span>
          <input type="email" autoComplete="email" placeholder="you@company.com" {...register('email')} />
          <FieldError>{errors.email?.message}</FieldError>
        </label>
        <label className="form-field">
          <span>Password</span>
          <input type="password" autoComplete="current-password" placeholder="Enter your password" {...register('password')} />
          <FieldError>{errors.password?.message}</FieldError>
        </label>
        <Button type="submit" className="auth-submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in securely'} <ArrowRight size={16} />
        </Button>
      </form>
    </AuthFrame>
  )
}

export function RegisterPage() {
  const { user } = useAuth()
  const [serverError, setServerError] = useState('')
  const [created, setCreated] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) })

  if (user) return <Navigate to="/dashboard" replace />

  async function submit(values: RegisterValues) {
    setServerError('')
    try {
      await authApi.register({
        email: values.email,
        password: values.password,
      })
      setCreated(true)
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : 'Registration could not be completed.')
    }
  }

  return (
    <AuthFrame mode="register">
      <form className="auth-form" onSubmit={handleSubmit(submit)} noValidate>
        {serverError && <Alert>{serverError}</Alert>}
        {created && <Alert tone="success">Account created. You can now sign in.</Alert>}
        <label className="form-field">
          <span>Email address</span>
          <input type="email" autoComplete="email" placeholder="you@company.com" {...register('email')} />
          <FieldError>{errors.email?.message}</FieldError>
        </label>
        <label className="form-field">
          <span>Password <small>At least 12 characters</small></span>
          <input type="password" autoComplete="new-password" placeholder="Create a strong password" {...register('password')} />
          <FieldError>{errors.password?.message}</FieldError>
        </label>
        <label className="form-field">
          <span>Confirm password</span>
          <input type="password" autoComplete="new-password" placeholder="Enter it again" {...register('confirmPassword')} />
          <FieldError>{errors.confirmPassword?.message}</FieldError>
        </label>
        <Button type="submit" className="auth-submit" disabled={isSubmitting || created}>
          {isSubmitting ? 'Creating account…' : 'Create account'} <ArrowRight size={16} />
        </Button>
        <p className="role-notice">New registrations receive the account-holder role. Privileged roles are assigned outside public registration.</p>
      </form>
    </AuthFrame>
  )
}

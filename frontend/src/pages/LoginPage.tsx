import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { UserRound } from 'lucide-react'

import { ApiError, NetworkError } from '../api/client'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Alert } from '../components/ui/feedback'
import { Field, Input } from '../components/ui/form'
import { useAuthStore } from '../stores/auth'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const { signIn, continueAsGuest, loading } = useAuthStore()
  const navigate = useNavigate()

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await signIn(email.trim(), password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) setError(err.message)
      else if (err instanceof NetworkError) setError(err.message)
      else setError('登录失败，请稍后重试')
    }
  }

  const onGuest = async () => {
    setError(null)
    try {
      await continueAsGuest()
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '游客登录失败，请稍后重试')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-secondary/25 px-4 py-10">
      <div className="w-full max-w-md">
        <Link to="/" className="mb-6 flex items-center justify-center gap-2 font-semibold">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
            AI
          </span>
          秋招面试陪练
        </Link>

        <Card>
          <CardHeader>
            <CardTitle>登录</CardTitle>
            <CardDescription>继续你的面试练习</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
              {error && <Alert tone="destructive">{error}</Alert>}

              <Field label="邮箱">
                {(id) => (
                  <Input
                    id={id}
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                  />
                )}
              </Field>

              <Field label="密码">
                {(id) => (
                  <Input
                    id={id}
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="至少 6 位"
                  />
                )}
              </Field>

              <Button type="submit" loading={loading} disabled={!email || !password}>
                登录
              </Button>
            </form>

            <div className="my-4 flex items-center gap-3 text-xs text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              或者
              <span className="h-px flex-1 bg-border" />
            </div>

            <Button variant="outline" className="w-full" onClick={onGuest} disabled={loading}>
              <UserRound className="h-4 w-4" aria-hidden />
              游客快速体验（无需注册）
            </Button>

            <p className="mt-5 text-center text-sm text-muted-foreground">
              还没有账号？{' '}
              <Link to="/register" className="text-primary underline-offset-4 hover:underline">
                免费注册
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

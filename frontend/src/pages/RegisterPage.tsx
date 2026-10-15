import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, NetworkError } from '../api/client'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Alert } from '../components/ui/feedback'
import { Field, Input } from '../components/ui/form'
import { useAuthStore } from '../stores/auth'

export function RegisterPage() {
  const [nickname, setNickname] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const { signUp, loading } = useAuthStore()
  const navigate = useNavigate()

  const passwordMismatch = confirm.length > 0 && confirm !== password
  const canSubmit = email.trim() && password.length >= 6 && !passwordMismatch

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setError(null)
    try {
      await signUp(email.trim(), password, nickname.trim() || '同学')
      navigate('/dashboard', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) setError(err.message)
      else if (err instanceof NetworkError) setError(err.message)
      else setError('注册失败，请稍后重试')
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
            <CardTitle>注册</CardTitle>
            <CardDescription>1 分钟建好账号，马上开始第一场面试</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
              {error && <Alert tone="destructive">{error}</Alert>}

              <Field label="昵称" hint="面试官会用这个称呼你">
                {(id) => (
                  <Input
                    id={id}
                    value={nickname}
                    onChange={(e) => setNickname(e.target.value)}
                    placeholder="例如：小王"
                    maxLength={32}
                  />
                )}
              </Field>

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

              <Field label="密码" hint="至少 6 位">
                {(id) => (
                  <Input
                    id={id}
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={6}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                )}
              </Field>

              <Field
                label="确认密码"
                error={passwordMismatch ? '两次输入的密码不一致' : null}
              >
                {(id) => (
                  <Input
                    id={id}
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                  />
                )}
              </Field>

              <Button type="submit" loading={loading} disabled={!canSubmit}>
                创建账号
              </Button>
            </form>

            <p className="mt-5 text-center text-sm text-muted-foreground">
              已有账号？{' '}
              <Link to="/login" className="text-primary underline-offset-4 hover:underline">
                去登录
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

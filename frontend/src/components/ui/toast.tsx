import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { cn } from '../../lib/utils'

type ToastTone = 'info' | 'success' | 'warning' | 'error'

interface Toast {
  id: number
  tone: ToastTone
  message: string
  /** 毫秒；0 表示不自动关闭 */
  duration: number
}

interface ToastContextValue {
  push: (message: string, tone?: ToastTone, duration?: number) => void
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const TONE_STYLES: Record<ToastTone, string> = {
  info: 'border-border bg-card',
  success: 'border-success/40 bg-success/10',
  warning: 'border-amber-500/40 bg-amber-500/10',
  error: 'border-destructive/40 bg-destructive/10',
}

let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (message: string, tone: ToastTone = 'info', duration = 4500) => {
      const id = nextId++
      setToasts((prev) => [...prev.slice(-3), { id, tone, message, duration }])
    },
    [],
  )

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      success: (m: string) => push(m, 'success'),
      error: (m: string) => push(m, 'error', 6500),
      info: (m: string) => push(m, 'info'),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(92vw,22rem)] flex-col gap-2"
        aria-live="polite"
      >
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onClose={() => remove(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  useEffect(() => {
    if (toast.duration <= 0) return
    const timer = window.setTimeout(onClose, toast.duration)
    return () => window.clearTimeout(timer)
  }, [toast.duration, onClose])

  return (
    <div
      className={cn(
        'pointer-events-auto animate-fade-in rounded-lg border p-3 text-sm shadow-lg backdrop-blur',
        TONE_STYLES[toast.tone],
      )}
    >
      <div className="flex items-start gap-3">
        <span className="flex-1">{toast.message}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭提示"
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          ×
        </button>
      </div>
    </div>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast 必须在 <ToastProvider> 内部使用')
  return ctx
}

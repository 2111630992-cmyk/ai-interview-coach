import type { ReactNode } from 'react'

import { cn } from '../../lib/utils'

// ======================================================================
// Badge
// ======================================================================

type BadgeTone = 'default' | 'primary' | 'success' | 'warning' | 'destructive' | 'outline'

const BADGE_TONES: Record<BadgeTone, string> = {
  default: 'bg-secondary text-secondary-foreground',
  primary: 'bg-primary/12 text-primary',
  success: 'bg-success/15 text-success',
  warning: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  destructive: 'bg-destructive/12 text-destructive',
  outline: 'border border-border text-muted-foreground',
}

export function Badge({
  tone = 'default',
  className,
  children,
}: {
  tone?: BadgeTone
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium',
        BADGE_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

// ======================================================================
// Progress
// ======================================================================

export function Progress({
  value,
  className,
  tone = 'primary',
}: {
  /** 0-100 */
  value: number
  className?: string
  tone?: 'primary' | 'success' | 'warning' | 'destructive'
}) {
  const pct = Math.max(0, Math.min(100, value))
  const bar = {
    primary: 'bg-primary',
    success: 'bg-success',
    warning: 'bg-amber-500',
    destructive: 'bg-destructive',
  }[tone]
  return (
    <div
      className={cn('h-2 w-full overflow-hidden rounded-full bg-secondary', className)}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={cn('h-full rounded-full transition-all duration-500', bar)} style={{ width: `${pct}%` }} />
    </div>
  )
}

// ======================================================================
// 加载态
// ======================================================================

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-block h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent',
        className,
      )}
    />
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-muted', className)} />
}

/** 生成计划等多步加载时用的骨架屏（比一个大转圈更有信息量）。 */
export function SkeletonSteps({ steps }: { steps: string[] }) {
  return (
    <div className="flex flex-col gap-3" aria-live="polite" aria-busy="true">
      {steps.map((step, i) => (
        <div key={step} className="flex items-center gap-3">
          <Skeleton className="h-2 w-2 rounded-full" />
          <span className="text-sm text-muted-foreground" style={{ opacity: 1 - i * 0.22 }}>
            {step}
          </span>
        </div>
      ))}
    </div>
  )
}

// ======================================================================
// Alert
// ======================================================================

type AlertTone = 'info' | 'warning' | 'destructive' | 'success'

const ALERT_TONES: Record<AlertTone, string> = {
  info: 'border-primary/30 bg-primary/5 text-foreground',
  warning: 'border-amber-500/40 bg-amber-500/10 text-foreground',
  destructive: 'border-destructive/40 bg-destructive/10 text-foreground',
  success: 'border-success/40 bg-success/10 text-foreground',
}

export function Alert({
  tone = 'info',
  title,
  children,
  action,
  className,
}: {
  tone?: AlertTone
  title?: string
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn('flex items-start gap-3 rounded-md border p-3 text-sm', ALERT_TONES[tone], className)}
    >
      <div className="flex flex-1 flex-col gap-1">
        {title && <span className="font-medium">{title}</span>}
        {children && <div className="text-muted-foreground">{children}</div>}
      </div>
      {action}
    </div>
  )
}

// ======================================================================
// EmptyState
// ======================================================================

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-12 text-center">
      {icon && <div className="text-muted-foreground">{icon}</div>}
      <div className="flex flex-col gap-1">
        <p className="font-medium">{title}</p>
        {description && <p className="max-w-md text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  )
}

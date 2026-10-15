import { Check, Circle, Loader2 } from 'lucide-react'

import { STAGE_LABELS, STAGE_ORDER, STAGE_SHORT } from '../../lib/constants'
import type { LiveTurn } from '../../stores/interviewRoom'
import { cn } from '../../lib/utils'

interface StageRailProps {
  currentStage: string | null
  turns: LiveTurn[]
  className?: string
}

/**
 * 环节进度条。
 *
 * 刻意**只展示到哪一步**，不展示任何分数 —— 面试过程中看到分数会打断沉浸感，
 * 也会让人分心去猜测评分标准。
 */
export function StageRail({ currentStage, turns, className }: StageRailProps) {
  const indexOf = (stage: string) => STAGE_ORDER.indexOf(stage as (typeof STAGE_ORDER)[number])
  const currentIndex = currentStage ? indexOf(currentStage) : 0

  const counts = turns.reduce<Record<string, number>>((acc, t) => {
    acc[t.stage] = (acc[t.stage] ?? 0) + 1
    return acc
  }, {})

  return (
    <ol className={cn('flex flex-wrap items-center gap-x-1 gap-y-2', className)} aria-label="面试环节进度">
      {STAGE_ORDER.map((stage, i) => {
        const done = i < currentIndex
        const active = i === currentIndex
        const count = counts[stage] ?? 0
        return (
          <li key={stage} className="flex items-center gap-1">
            <span
              className={cn(
                'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                active && 'border-primary bg-primary/10 font-medium text-primary',
                done && 'border-success/40 bg-success/10 text-success',
                !active && !done && 'border-border text-muted-foreground',
              )}
              aria-current={active ? 'step' : undefined}
              title={STAGE_LABELS[stage]}
            >
              {active ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              ) : done ? (
                <Check className="h-3 w-3" aria-hidden />
              ) : (
                <Circle className="h-3 w-3" aria-hidden />
              )}
              {STAGE_SHORT[stage]}
              {count > 0 && <span className="text-[10px] opacity-70">{count}</span>}
            </span>
            {i < STAGE_ORDER.length - 1 && (
              <span className="hidden h-px w-3 bg-border sm:block" aria-hidden />
            )}
          </li>
        )
      })}
    </ol>
  )
}

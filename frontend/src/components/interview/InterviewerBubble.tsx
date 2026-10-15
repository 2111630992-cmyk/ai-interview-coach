import { CornerDownRight, User } from 'lucide-react'

import { STAGE_LABELS } from '../../lib/constants'
import { cn } from '../../lib/utils'
import { Badge } from '../ui/feedback'

interface InterviewerBubbleProps {
  text: string
  streaming?: boolean
  stage?: string | null
  competency?: string | null
  isFollowup?: boolean
  followupDepth?: number
}

/** 面试官气泡。流式输出时带打字光标。 */
export function InterviewerBubble({
  text,
  streaming = false,
  stage,
  competency,
  isFollowup = false,
  followupDepth = 0,
}: InterviewerBubbleProps) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/12 text-primary">
        <User className="h-4 w-4" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">面试官</span>
          {stage && <span>{STAGE_LABELS[stage] ?? stage}</span>}
          {competency && (
            <Badge tone="outline" className="max-w-[16rem] truncate">
              {competency}
            </Badge>
          )}
          {isFollowup && (
            <Badge tone="primary">
              <CornerDownRight className="h-3 w-3" aria-hidden />
              追问第 {followupDepth} 层
            </Badge>
          )}
        </div>
        <div
          className={cn(
            'rounded-lg rounded-tl-sm border border-border bg-card p-3 text-sm leading-7 shadow-sm',
            streaming && text.length === 0 && 'text-muted-foreground',
          )}
          aria-live={streaming ? 'polite' : undefined}
        >
          {text.length > 0 ? (
            <span className={cn(streaming && 'typing-cursor')}>{text}</span>
          ) : (
            <span className="flex gap-1" aria-label="面试官正在思考">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-muted-foreground"
                  style={{ animationDelay: `${i * 0.18}s` }}
                />
              ))}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

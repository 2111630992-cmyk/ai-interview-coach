import { Info, Volume2 } from 'lucide-react'
import { useState } from 'react'

import type { InterviewerPublic } from '../../api/types'
import { accent } from '../../lib/constants'
import { cn } from '../../lib/utils'
import { Badge } from '../ui/feedback'

interface InterviewerPanelProps {
  interviewer: InterviewerPublic | null
  speaking?: boolean
  /** 是否刚刚换人（换人时给一次身份说明，否则考生会觉得突兀） */
  justChanged?: boolean
  className?: string
  /** 是否显示"人格详情"折叠区 */
  expandable?: boolean
}

/**
 * 面试官面板。
 *
 * 视频面试里，这块是"对面那个人"的位置。真人面试有表情和语气，
 * 我们只有文字，所以用**人格信息 + 说话状态**来补足临场感：
 * 名字、职位、关注点、正在说话的动效。
 */
export function InterviewerPanel({
  interviewer,
  speaking = false,
  justChanged = false,
  className,
  expandable = true,
}: InterviewerPanelProps) {
  const [openBio, setOpenBio] = useState(false)

  if (!interviewer) {
    return (
      <div
        className={cn(
          'flex aspect-video w-full items-center justify-center rounded-xl border border-border bg-secondary/40 text-sm text-muted-foreground',
          className,
        )}
      >
        面试官准备中…
      </div>
    )
  }

  const tone = accent(interviewer.accent)

  return (
    <div
      className={cn(
        'relative flex aspect-video w-full flex-col overflow-hidden rounded-xl border transition-colors',
        tone.bg,
        speaking ? cn('border-transparent ring-2', tone.ring) : 'border-border',
        'ring-offset-0',
        className,
      )}
      aria-live="polite"
    >
      {/* 说话时的呼吸光晕，让"对面在说"这件事可见 */}
      {speaking && (
        <span
          aria-hidden
          className={cn('absolute inset-0 animate-pulse opacity-25', tone.bg)}
        />
      )}

      <div className="relative flex flex-1 flex-col items-center justify-center gap-3 p-4">
        <div className="relative">
          <span
            className={cn(
              'flex h-16 w-16 items-center justify-center rounded-full text-3xl',
              'bg-background/80 shadow-sm',
            )}
            aria-hidden
          >
            {interviewer.emoji}
          </span>
          {speaking && (
            <span
              className={cn(
                'absolute -inset-1 animate-ping rounded-full opacity-30',
                tone.solid,
              )}
              aria-hidden
            />
          )}
        </div>

        <div className="text-center">
          <p className="text-lg font-semibold leading-tight">{interviewer.name}</p>
          <p className="text-xs text-muted-foreground">{interviewer.title}</p>
        </div>

        {justChanged && (
          <Badge tone="primary" className="animate-fade-in">
            本轮换人
          </Badge>
        )}

        <div className="flex flex-wrap justify-center gap-1.5">
          {interviewer.focus_areas.slice(0, 3).map((f) => (
            <span
              key={f}
              className={cn('rounded-full border px-2 py-0.5 text-[11px]', tone.chip)}
            >
              {f}
            </span>
          ))}
        </div>
      </div>

      <div className="relative flex items-center gap-2 border-t border-border/60 bg-background/60 px-3 py-1.5 text-[11px] text-muted-foreground">
        {speaking ? (
          <>
            <Volume2 className="h-3 w-3 text-primary" aria-hidden />
            <span className="flex items-end gap-0.5" aria-hidden>
              {[0, 1, 2, 3].map((i) => (
                <span
                  key={i}
                  className="w-0.5 animate-pulse-dot rounded-full bg-primary"
                  style={{ height: `${5 + (i % 3) * 4}px`, animationDelay: `${i * 0.12}s` }}
                />
              ))}
            </span>
            面试官正在说话
          </>
        ) : (
          <span>面试官在听你说</span>
        )}

        {expandable && (
          <button
            type="button"
            onClick={() => setOpenBio((v) => !v)}
            aria-expanded={openBio}
            className="ml-auto flex items-center gap-1 underline-offset-4 hover:underline"
          >
            <Info className="h-3 w-3" aria-hidden />
            {openBio ? '收起' : '了解这位面试官'}
          </button>
        )}
      </div>

      {expandable && openBio && (
        <div className="animate-fade-in border-t border-border/60 bg-background/85 p-3 text-xs leading-6">
          <p className="font-medium">背景</p>
          <p className="mt-0.5 text-muted-foreground">{interviewer.bio}</p>
          <p className="mt-2 font-medium">提问风格</p>
          <p className="mt-0.5 text-muted-foreground">{interviewer.style}</p>
          <p className="mt-2 font-medium">性格</p>
          <p className="mt-0.5 text-muted-foreground">{interviewer.personality}</p>
        </div>
      )}
    </div>
  )
}

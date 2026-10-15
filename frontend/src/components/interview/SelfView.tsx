import { Mic, MicOff, Video, VideoOff } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { cn } from '../../lib/utils'

interface SelfViewProps {
  stream: MediaStream | null
  recording?: boolean
  level?: number
  hasVideo?: boolean
  /** 录音时长（毫秒），显示在角标上 */
  elapsedMs?: number
  className?: string
  /** 是否镜像。自视窗必须镜像，否则抬手方向是反的，看着很别扭 */
  mirrored?: boolean
}

function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

/**
 * 自视窗（视频面试的"自己在屏幕上"那一块）。
 *
 * 真实视频面试里这个小窗是压力的来源之一 —— 你会看到自己的表情和状态。
 * 我们保留它，但在面试过程中**不显示任何评分**，避免变成"盯着自己找毛病"。
 */
export function SelfView({
  stream,
  recording = false,
  level = 0,
  hasVideo = true,
  elapsedMs = 0,
  className,
  mirrored = true,
}: SelfViewProps) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    if (el.srcObject !== stream) {
      el.srcObject = stream
    }
    if (stream) {
      // 某些浏览器需要显式 play() 才会开始渲染
      void el.play().catch(() => undefined)
    }
  }, [stream])

  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-xl border border-border bg-slate-900',
        className,
      )}
    >
      {hasVideo && stream ? (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          aria-label="你的摄像头画面"
          className={cn('h-full w-full object-cover', mirrored && 'scale-x-[-1]')}
        />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-slate-400">
          {hasVideo ? <VideoOff className="h-6 w-6" aria-hidden /> : <Mic className="h-6 w-6" aria-hidden />}
          <span className="px-3 text-center text-xs">
            {hasVideo ? '摄像头未开启' : '仅录音模式'}
          </span>
        </div>
      )}

      {/* 录制角标 */}
      <div className="absolute left-2 top-2 flex items-center gap-2">
        {recording && (
          <span className="flex items-center gap-1.5 rounded-full bg-red-600/90 px-2 py-0.5 text-[11px] font-medium text-white">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" aria-hidden />
            REC {formatClock(elapsedMs)}
          </span>
        )}
      </div>

      {/* 麦克风音量：静音时能立刻发现 */}
      <div className="absolute bottom-2 left-2 flex items-center gap-1.5 rounded-full bg-black/50 px-2 py-1">
        {level > 0.02 ? (
          <Mic className="h-3 w-3 text-emerald-400" aria-hidden />
        ) : (
          <MicOff className="h-3 w-3 text-slate-400" aria-hidden />
        )}
        <span className="h-1.5 w-14 overflow-hidden rounded-full bg-white/25">
          <span
            className={cn(
              'block h-full rounded-full transition-[width] duration-75',
              level > 0.75 ? 'bg-red-400' : level > 0.02 ? 'bg-emerald-400' : 'bg-slate-500',
            )}
            style={{ width: `${Math.min(100, Math.round(level * 100))}%` }}
          />
        </span>
      </div>

      <span className="absolute bottom-2 right-2 rounded-full bg-black/50 px-2 py-0.5 text-[11px] text-white/80">
        你
      </span>
    </div>
  )
}

/** 设备检测页用的纯预览（带"能看到我吗"的确认语气）。 */
export function DevicePreview({
  stream,
  hasVideo,
  className,
}: {
  stream: MediaStream | null
  hasVideo: boolean
  className?: string
}) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    if (el.srcObject !== stream) el.srcObject = stream
    if (stream) void el.play().catch(() => undefined)
  }, [stream])

  return (
    <div
      className={cn(
        'relative aspect-video w-full overflow-hidden rounded-xl border border-border bg-slate-900',
        className,
      )}
    >
      {hasVideo && stream ? (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          aria-label="设备预览画面"
          className="h-full w-full scale-x-[-1] object-cover"
        />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-slate-400">
          <Video className="h-7 w-7" aria-hidden />
          <span className="text-sm">等待开启摄像头…</span>
        </div>
      )}
    </div>
  )
}

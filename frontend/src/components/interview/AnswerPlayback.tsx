import { AlertTriangle, Download, Trash2, Video } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Button } from '../ui/button'
import { Spinner } from '../ui/feedback'
import { deleteRecording, formatBytes, getRecording } from '../../lib/videoStore'

interface AnswerPlaybackProps {
  recordingKey: string
  /** 用于展示在标题上，例如「第 3 题的录像」 */
  label: string
  onDeleted?: () => void
}

/**
 * 回放自己某一题的回答。
 *
 * 这是视频面试最有学习价值的部分之一 —— 很多人第一次看到自己答题的录像，
 * 才会发现"我以为我很镇定，其实一直在抖腿/眼神乱飘/语速飞快"。
 *
 * 录像从浏览器 IndexedDB 读取，不经过服务器；地址用 objectURL，用完即释放。
 */
export function AnswerPlayback({ recordingKey, label, onDeleted }: AnswerPlaybackProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [meta, setMeta] = useState<{ mimeType: string; size: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let revoked: string | null = null
    let cancelled = false

    void (async () => {
      setLoading(true)
      setMissing(false)
      const rec = await getRecording(recordingKey)
      if (cancelled) return
      if (!rec) {
        setMissing(true)
        setLoading(false)
        return
      }
      const objectUrl = URL.createObjectURL(rec.blob)
      revoked = objectUrl
      setUrl(objectUrl)
      setMeta({ mimeType: rec.mimeType, size: rec.size })
      setLoading(false)
    })()

    return () => {
      cancelled = true
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [recordingKey])

  const isVideo = useMemo(() => (meta?.mimeType ?? '').startsWith('video'), [meta?.mimeType])

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Spinner className="h-3 w-3" />
        正在读取本机录像…
      </div>
    )
  }

  if (missing || !url) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-border bg-secondary/40 p-2.5 text-xs text-muted-foreground">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        <span>
          本机找不到这段录像。录像只存在你当前浏览器的本地存储里 ——
          换设备、换浏览器，或者清理过浏览器数据后就会丢失（这是"录像不上传服务器"的代价）。
        </span>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Video className="h-3 w-3" aria-hidden />
        {label}
        {meta && <span className="font-normal">· {formatBytes(meta.size)}</span>}
      </p>

      {isVideo ? (
        <video
          src={url}
          controls
          playsInline
          className="w-full max-w-md rounded-md border border-border bg-slate-900"
        />
      ) : (
        <audio src={url} controls className="w-full max-w-md" />
      )}

      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span>仅存于本机，从未上传服务器</span>
        <a
          href={url}
          download={`${label.replace(/[^\w\u4e00-\u9fff-]/g, '_')}.${isVideo ? 'webm' : 'webm'}`}
          className="ml-auto inline-flex items-center gap-1 underline-offset-4 hover:underline"
        >
          <Download className="h-3 w-3" aria-hidden />
          下载
        </a>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-2 text-[11px] text-destructive"
          onClick={async () => {
            await deleteRecording(recordingKey)
            onDeleted?.()
          }}
        >
          <Trash2 className="h-3 w-3" aria-hidden />
          删除这段
        </Button>
      </div>
    </div>
  )
}

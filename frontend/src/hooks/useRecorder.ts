/**
 * MediaRecorder 封装：录一段回答 → 得到一个 Blob。
 *
 * 只处理"录一轮回答"这一个场景，不做长时间录制、不做上传。
 * 录像交给 videoStore 存进 IndexedDB，**永远不离开浏览器**。
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export interface RecordingResult {
  blob: Blob
  mimeType: string
  durationMs: number
}

/** 按优先级挑一个浏览器支持的容器。webm/vp9 体积最小，Safari 只认 mp4。 */
function pickMimeType(hasVideo: boolean): string {
  const candidates = hasVideo
    ? [
        'video/webm;codecs=vp9,opus',
        'video/webm;codecs=vp8,opus',
        'video/webm',
        'video/mp4',
      ]
    : ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']

  if (typeof MediaRecorder === 'undefined') return ''
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported(type)) return type
  }
  return ''
}

export function useRecorder() {
  const [recording, setRecording] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [bytes, setBytes] = useState(0)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const startedAtRef = useRef(0)
  const timerRef = useRef<number | null>(null)
  const resolveRef = useRef<((r: RecordingResult | null) => void) | null>(null)

  const supported = typeof MediaRecorder !== 'undefined'

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  const start = useCallback(
    (stream: MediaStream): boolean => {
      if (!supported) {
        setError('当前浏览器不支持录制（MediaRecorder 不可用），已切换为文字作答')
        return false
      }
      if (recorderRef.current) return true

      const hasVideo = stream.getVideoTracks().length > 0
      const mimeType = pickMimeType(hasVideo)

      try {
        const recorder = mimeType
          ? new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 1_200_000 })
          : new MediaRecorder(stream)

        chunksRef.current = []
        setBytes(0)
        setError(null)

        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) {
            chunksRef.current.push(e.data)
            setBytes((prev) => prev + e.data.size)
          }
        }
        recorder.onerror = () => {
          setError('录制过程中出错，这一段可能无法回放')
        }
        recorder.onstop = () => {
          const durationMs = Math.max(0, Date.now() - startedAtRef.current)
          const type = recorder.mimeType || mimeType || 'video/webm'
          const blob = new Blob(chunksRef.current, { type })
          chunksRef.current = []
          setRecording(false)
          setElapsedMs(0)
          clearTimer()
          resolveRef.current?.(blob.size > 0 ? { blob, mimeType: type, durationMs } : null)
          resolveRef.current = null
        }

        // timeslice：定期落盘，避免长回答内存里堆一大块
        recorder.start(1000)
        recorderRef.current = recorder
        startedAtRef.current = Date.now()
        setRecording(true)
        setElapsedMs(0)
        timerRef.current = window.setInterval(() => {
          setElapsedMs(Date.now() - startedAtRef.current)
        }, 500)
        return true
      } catch (err) {
        setError(`无法开始录制：${(err as Error)?.message ?? '未知错误'}`)
        return false
      }
    },
    [supported],
  )

  /** 停止并拿到录像。没录到内容时返回 null（而不是抛异常）。 */
  const stop = useCallback((): Promise<RecordingResult | null> => {
    const recorder = recorderRef.current
    if (!recorder) return Promise.resolve(null)

    return new Promise<RecordingResult | null>((resolve) => {
      resolveRef.current = resolve
      try {
        recorder.stop()
      } catch {
        resolve(null)
      }
      recorderRef.current = null
    })
  }, [])

  /** 丢弃这一段（比如用户重录）。 */
  const cancel = useCallback(() => {
    const recorder = recorderRef.current
    chunksRef.current = []
    resolveRef.current = null
    recorderRef.current = null
    setRecording(false)
    setElapsedMs(0)
    setBytes(0)
    clearTimer()
    try {
      recorder?.stop()
    } catch {
      /* 已经停了 */
    }
  }, [])

  useEffect(() => {
    return () => {
      clearTimer()
      try {
        recorderRef.current?.stop()
      } catch {
        /* 忽略 */
      }
      recorderRef.current = null
    }
  }, [])

  return { supported, recording, elapsedMs, bytes, error, start, stop, cancel, clearError: () => setError(null) }
}

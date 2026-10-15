/** 简单倒计时/计时 hook，用于回答计时与整场剩余时间。 */

import { useEffect, useRef, useState } from 'react'

/** 从 startAt（毫秒时间戳）开始累计经过的秒数；running 为 false 时暂停累计。 */
export function useElapsedSeconds(running: boolean, startAt: number | null) {
  const [seconds, setSeconds] = useState(0)
  const frozenRef = useRef(0)

  useEffect(() => {
    if (startAt == null) {
      setSeconds(0)
      return
    }
    if (!running) return

    const tick = () => setSeconds(Math.floor((Date.now() - startAt) / 1000))
    tick()
    const timer = window.setInterval(tick, 500)
    return () => {
      window.clearInterval(timer)
      frozenRef.current = Math.floor((Date.now() - startAt) / 1000)
    }
  }, [running, startAt])

  return seconds
}

/** 整场面试剩余时间（秒），由后端进度推算，避免前后端时间不一致。 */
export function useRemainingSeconds(durationMin: number, elapsedMin: number) {
  const remaining = Math.max(0, Math.round(durationMin * 60 - elapsedMin * 60))
  return remaining
}

export function formatDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(safe / 60)
  const s = safe % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

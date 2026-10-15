/** 面试进行页的 SSE 编排：开始面试、提交回答、跳过、暂停、错误处理与重试。 */

import { useCallback, useRef, useState } from 'react'

import { ApiError, NetworkError } from '../api/client'
import { getInterview } from '../api/endpoints'
import { streamPost } from '../api/sse'
import type {
  Evaluation,
  InterviewDetail,
  SSEDonePayload,
  SSEErrorPayload,
  SSEQuestionPayload,
  SSEStagePayload,
} from '../api/types'
import type { DeliveryMetrics } from '../lib/deliveryMetrics'
import { useRoomStore, type LiveTurn } from '../stores/interviewRoom'

export function toLiveTurns(detail: InterviewDetail): LiveTurn[] {
  return detail.turns.map((t) => ({
    id: t.id,
    turnIndex: t.turn_index,
    stage: t.stage,
    competency: t.competency,
    question: t.question,
    answer: t.answer,
    isFollowup: t.is_followup,
    followupDepth: t.followup_depth,
    interviewer: t.interviewer,
    hinted: t.hinted,
    skipped: t.skipped,
    marked: t.marked,
    deliveryMetrics: t.delivery_metrics,
    recordingKey: t.recording_key,
  }))
}

/** 从详情里抽出已有的单题评分（练习模式刷新后仍能看到反馈）。 */
export function evaluationsFromDetail(detail: InterviewDetail): Record<string, Evaluation> {
  const map: Record<string, Evaluation> = {}
  for (const t of detail.turns) {
    if (t.evaluation) map[t.id] = t.evaluation
  }
  return map
}

export function useInterviewStream(sessionId: string | undefined) {
  const room = useRoomStore()
  const [busy, setBusy] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  /** 从服务端同步一次，用于刷新页面后恢复现场。 */
  const sync = useCallback(async () => {
    if (!sessionId) return
    const detail = await getInterview(sessionId)
    room.init(sessionId, toLiveTurns(detail), detail.current_stage, detail.status === 'paused')
    room.seedEvaluations(evaluationsFromDetail(detail))
    return detail
  }, [sessionId, room])

  const run = useCallback(
    async (path: string, body: unknown) => {
      if (!sessionId) return
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      setBusy(true)
      room.clearError()
      room.beginStreaming()

      let sawError = false

      try {
        await streamPost({
          path,
          body,
          signal: controller.signal,
          onEvent: (event, payload) => {
            switch (event) {
              case 'stage': {
                const p = payload as SSEStagePayload
                room.setStage(p.stage, p.progress, p.elapsed_min)
                break
              }
              case 'token': {
                room.appendToken((payload as { delta: string }).delta)
                break
              }
              case 'eval': {
                const p = payload as { turnId?: string; turn_id?: string; score: number; isWeak?: boolean; is_weak?: boolean }
                room.setEval({
                  turnId: p.turnId ?? p.turn_id ?? '',
                  score: p.score,
                  isWeak: p.isWeak ?? p.is_weak ?? false,
                })
                break
              }
              case 'question': {
                const p = payload as SSEQuestionPayload
                room.commitQuestion({
                  id: p.turn_id,
                  turnIndex: p.turn_index,
                  question: p.question,
                  stage: p.stage,
                  competency: p.competency,
                  isFollowup: p.is_followup,
                  followupDepth: p.followup_depth,
                  interviewer: p.interviewer,
                })
                break
              }
              case 'done': {
                const p = payload as SSEDonePayload
                room.finishStreaming({
                  sessionFinished: p.session_finished,
                  progress: p.progress,
                })
                break
              }
              case 'error': {
                sawError = true
                const p = payload as SSEErrorPayload
                room.fail(p.message || 'AI 服务出了点问题，请点击重试')
                break
              }
              default:
                break
            }
          },
        })
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError || err instanceof NetworkError) {
          room.fail(err.message)
        } else {
          room.fail('连接中断，请检查网络后重试')
        }
        sawError = true
      } finally {
        setBusy(false)
      }

      // 出错后回源一次，保证本地界面与服务端一致（例如问题其实已落库）
      if (sawError) {
        try {
          await sync()
        } catch {
          /* 同步失败就保持当前错误提示 */
        }
      }
    },
    [sessionId, room, sync],
  )

  const start = useCallback(() => run(`/interviews/${sessionId}/start`, undefined), [run, sessionId])

  /** 断流恢复：上一题已答、下一题未生成时继续。 */
  const resume = useCallback(() => run(`/interviews/${sessionId}/next`, undefined), [run, sessionId])

  const submitAnswer = useCallback(
    (
      answer: string,
      elapsedMs: number,
      opts?: { metrics?: DeliveryMetrics | null; recordingKey?: string | null },
    ) => {
      room.setPendingAnswer(answer)
      room.setNotice(null)
      return run(`/interviews/${sessionId}/answer`, {
        answer,
        client_elapsed_ms: Math.round(elapsedMs),
        // 纯文字作答不发指标，避免后端拿到一堆 0 还以为在分析语速
        delivery_metrics: opts?.metrics ?? undefined,
        recording_key: opts?.recordingKey ?? undefined,
      })
    },
    [room, run, sessionId],
  )

  /** 跳过当前题：记 0 分但不中断面试。 */
  const skipQuestion = useCallback(
    (reason = '') => run(`/interviews/${sessionId}/skip`, { reason }),
    [run, sessionId],
  )

  return { ...room, busy, start, resume, submitAnswer, skipQuestion, sync }
}

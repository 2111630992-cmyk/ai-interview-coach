/**
 * 面试进行页的实时状态。
 *
 * 放在 store 而不是组件 useState 的原因：
 * 1. SSE 回调是异步、跨渲染的，集中管理更容易保证一致；
 * 2. 用户误触后退再回来时，已收到的对话不会丢（服务端也有持久化兜底）。
 */

import { create } from 'zustand'

import type { Evaluation, InterviewerPublic, SuggestedAnswerPayload } from '../api/types'
import type { DeliveryMetrics } from '../lib/deliveryMetrics'

export interface LiveTurn {
  id: string | null
  turnIndex: number
  stage: string
  competency: string | null
  question: string
  answer: string | null
  isFollowup: boolean
  followupDepth: number
  /** 本轮面试官 */
  interviewer: InterviewerPublic | null
  // ---- 真实面试行为 ----
  hinted: boolean
  skipped: boolean
  marked: boolean
  deliveryMetrics: DeliveryMetrics | null
  recordingKey: string | null
}

export interface LiveEval {
  turnId: string
  score: number
  isWeak: boolean
}

interface RoomState {
  sessionId: string | null
  turns: LiveTurn[]
  /** 面试官正在流式输出的文字（尚未落为 turn） */
  streamingText: string
  /** 考生刚提交的回答（乐观渲染，先出现在屏幕上再等服务端确认） */
  pendingAnswer: string | null
  /** 已提交回答、正在等待面试官开口 */
  thinking: boolean
  streaming: boolean
  /** 面试整体进度 0-1 */
  progress: number
  currentStage: string | null
  elapsedMin: number
  sessionFinished: boolean
  paused: boolean
  error: string | null
  notice: string | null

  /** 按 turn id 索引的单题评分（练习模式用；模拟模式不下发） */
  evaluations: Record<string, Evaluation>
  /** 按 turn id 索引的提示文案 */
  hints: Record<string, string>
  /** 按 turn id 索引的参考答案 */
  suggestedAnswers: Record<string, SuggestedAnswerPayload>
  lastEval: LiveEval | null

  init: (sessionId: string, turns: LiveTurn[], stage: string | null, paused?: boolean) => void
  seedEvaluations: (map: Record<string, Evaluation>) => void
  reset: () => void
  setStage: (stage: string, progress: number, elapsedMin: number) => void
  beginStreaming: () => void
  appendToken: (delta: string) => void
  commitQuestion: (payload: {
    id: string
    turnIndex: number
    question: string
    stage: string
    competency: string | null
    isFollowup: boolean
    followupDepth: number
    interviewer: InterviewerPublic | null
  }) => void
  /** 乐观显示考生刚打的回答 */
  setPendingAnswer: (answer: string | null) => void
  /** 服务端确认后把回答挂到对应轮次 */
  attachAnswer: (answer: string, opts?: { skipped?: boolean; deliveryMetrics?: DeliveryMetrics | null; recordingKey?: string | null }) => void
  finishStreaming: (payload: { sessionFinished: boolean; progress: number }) => void
  setEval: (payload: LiveEval) => void
  recordEvaluation: (turnId: string, evaluation: Evaluation) => void
  setHint: (turnId: string, hint: string) => void
  setSuggestedAnswer: (turnId: string, payload: SuggestedAnswerPayload) => void
  toggleMark: (turnId: string, marked: boolean) => void
  setPaused: (paused: boolean) => void
  fail: (message: string) => void
  clearError: () => void
  clearNotice: () => void
  setNotice: (message: string | null) => void
}

const EMPTY = {
  sessionId: null,
  turns: [] as LiveTurn[],
  streamingText: '',
  pendingAnswer: null,
  thinking: false,
  streaming: false,
  progress: 0,
  currentStage: null,
  elapsedMin: 0,
  sessionFinished: false,
  paused: false,
  error: null,
  notice: null,
  evaluations: {} as Record<string, Evaluation>,
  hints: {} as Record<string, string>,
  suggestedAnswers: {} as Record<string, SuggestedAnswerPayload>,
  lastEval: null,
}

export const useRoomStore = create<RoomState>((set) => ({
  ...EMPTY,

  init: (sessionId, turns, stage, paused = false) =>
    set({
      ...EMPTY,
      sessionId,
      turns,
      currentStage: stage,
      paused,
    }),

  /** 用服务端已存的评分填充（练习模式刷新页面后仍能看到每题反馈）。 */
  seedEvaluations: (map) => set({ evaluations: map }),

  reset: () => set({ ...EMPTY }),

  setStage: (stage, progress, elapsedMin) => set({ currentStage: stage, progress, elapsedMin }),

  beginStreaming: () => set({ streaming: true, thinking: false, streamingText: '', error: null }),

  appendToken: (delta) => set((s) => ({ streamingText: s.streamingText + delta })),

  commitQuestion: (payload) =>
    set((s) => ({
      turns: [
        ...s.turns,
        {
          id: payload.id,
          turnIndex: payload.turnIndex,
          question: payload.question,
          stage: payload.stage,
          competency: payload.competency,
          answer: null,
          isFollowup: payload.isFollowup,
          followupDepth: payload.followupDepth,
          interviewer: payload.interviewer,
          hinted: false,
          skipped: false,
          marked: false,
          deliveryMetrics: null,
          recordingKey: null,
        },
      ],
      streamingText: '',
      streaming: false,
      thinking: false,
      pendingAnswer: null,
    })),

  setPendingAnswer: (answer) => set({ pendingAnswer: answer }),

  attachAnswer: (answer, opts) =>
    set((s) => {
      if (s.turns.length === 0) return {}
      const turns = [...s.turns]
      const last = { ...turns[turns.length - 1] }
      last.answer = answer
      if (opts?.skipped) last.skipped = true
      if (opts?.deliveryMetrics !== undefined) last.deliveryMetrics = opts.deliveryMetrics
      if (opts?.recordingKey !== undefined) last.recordingKey = opts.recordingKey
      turns[turns.length - 1] = last
      return { turns, thinking: false, pendingAnswer: null }
    }),

  finishStreaming: ({ sessionFinished, progress }) =>
    set({ streaming: false, thinking: false, sessionFinished, progress }),

  setEval: (payload) => set({ lastEval: payload }),

  recordEvaluation: (turnId, evaluation) =>
    set((s) => ({ evaluations: { ...s.evaluations, [turnId]: evaluation } })),

  setHint: (turnId, hint) =>
    set((s) => {
      const turns = s.turns.map((t) => (t.id === turnId ? { ...t, hinted: true } : t))
      return { turns, hints: { ...s.hints, [turnId]: hint } }
    }),

  setSuggestedAnswer: (turnId, payload) =>
    set((s) => ({ suggestedAnswers: { ...s.suggestedAnswers, [turnId]: payload } })),

  toggleMark: (turnId, marked) =>
    set((s) => ({ turns: s.turns.map((t) => (t.id === turnId ? { ...t, marked } : t)) })),

  setPaused: (paused) => set({ paused }),

  fail: (message) => set({ error: message, streaming: false, thinking: false, pendingAnswer: null }),

  clearError: () => set({ error: null }),

  clearNotice: () => set({ notice: null }),

  setNotice: (message) => set({ notice: message }),
}))

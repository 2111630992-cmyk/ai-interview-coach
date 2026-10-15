/** 所有后端接口的集中封装，页面只调用这里，不直接拼 URL。 */

import { request } from './client'
import type {
  HealthInfo,
  InterviewConfig,
  InterviewDetail,
  InterviewSummary,
  InterviewerPublic,
  JDPublic,
  MatchPublic,
  Overview,
  ReportPublic,
  ResumePublic,
  SuggestedAnswerPayload,
  TokenResponse,
  TrendPoint,
  UserPublic,
} from './types'

// ---------------- 系统 ----------------

export const getHealth = () => request<HealthInfo>('/health')

// ---------------- 认证 ----------------

export const register = (payload: {
  email: string
  password: string
  nickname?: string
}) => request<TokenResponse>('/auth/register', { method: 'POST', body: payload })

export const login = (payload: { email: string; password: string }) =>
  request<TokenResponse>('/auth/login', { method: 'POST', body: payload })

export const loginAsGuest = () => request<TokenResponse>('/auth/guest', { method: 'POST' })

export const fetchMe = () => request<UserPublic>('/auth/me')

// ---------------- 简历 ----------------

export function uploadResume(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<ResumePublic>('/resumes', { method: 'POST', rawBody: form })
}

export const listResumes = () => request<ResumePublic[]>('/resumes')

export const getResume = (id: string) => request<ResumePublic>(`/resumes/${id}`)

export const updateResume = (id: string, parsed: Record<string, unknown>) =>
  request<ResumePublic>(`/resumes/${id}`, { method: 'PATCH', body: { parsed } })

export const deleteResume = (id: string) => request<{ ok: boolean }>(`/resumes/${id}`, { method: 'DELETE' })

// ---------------- 岗位 JD ----------------

export const createJd = (payload: { title: string; company?: string; raw_text: string }) =>
  request<JDPublic>('/jds', { method: 'POST', body: payload })

export const listJds = () => request<JDPublic[]>('/jds')

export const getJd = (id: string) => request<JDPublic>(`/jds/${id}`)

export const deleteJd = (id: string) => request<{ ok: boolean }>(`/jds/${id}`, { method: 'DELETE' })

// ---------------- 匹配 ----------------

export const analyzeMatch = (resume_id: string, jd_id: string) =>
  request<MatchPublic>('/match', { method: 'POST', body: { resume_id, jd_id } })

export const listMatches = () => request<MatchPublic[]>('/match')

// ---------------- 面试 ----------------

export const createInterview = (payload: {
  resume_id: string
  jd_id?: string | null
  config: Partial<InterviewConfig>
}) => request<InterviewDetail>('/interviews', { method: 'POST', body: payload })

export const listInterviews = () => request<InterviewSummary[]>('/interviews')

export const getInterview = (id: string) => request<InterviewDetail>(`/interviews/${id}`)

export const finishInterview = (id: string) =>
  request<ReportPublic>(`/interviews/${id}/finish`, { method: 'POST' })

export const abortInterview = (id: string) =>
  request<{ ok: boolean; status: string }>(`/interviews/${id}/abort`, { method: 'POST' })

export const getReport = (id: string) => request<ReportPublic>(`/interviews/${id}/report`)

/** 断流恢复：上一题已作答但下一题未生成时，用它继续推进（SSE）。 */
export const nextQuestionPath = (id: string) => `/interviews/${id}/next`

// ---------------- 面试官人格 ----------------

export const listInterviewers = (language = 'zh') =>
  request<InterviewerPublic[]>(`/interviews/meta/interviewers?language=${language}`)

// ---------------- 提示 / 标记 / 跳过 / 参考答案 ----------------

/** 请求「回答结构提示」。提示只给结构不给答案，且会被永久记录。 */
export const requestHint = (sessionId: string, turnId: string) =>
  request<{ turn_id: string; hint: string | null; already_used: boolean; hinted: boolean; message: string }>(
    `/interviews/${sessionId}/turns/${turnId}/hint`,
    { method: 'POST' },
  )

export const markTurn = (sessionId: string, turnId: string, marked: boolean) =>
  request<{ turn_id: string; marked: boolean }>(`/interviews/${sessionId}/turns/${turnId}/mark`, {
    method: 'POST',
    body: { marked },
  })

export const generateSuggestedAnswer = (sessionId: string, turnId: string) =>
  request<{ turn_id: string; suggested_answer: SuggestedAnswerPayload }>(
    `/interviews/${sessionId}/turns/${turnId}/suggested-answer`,
    { method: 'POST' },
  )

// ---------------- 暂停 / 继续 ----------------

export const pauseInterview = (id: string) =>
  request<{ ok: boolean; status: string }>(`/interviews/${id}/pause`, { method: 'POST' })

export const resumeInterview = (id: string) =>
  request<{ ok: boolean; status: string; paused_seconds: number }>(`/interviews/${id}/resume`, {
    method: 'POST',
  })

// ---------------- 统计 ----------------

export const getTrend = (limit = 20) => request<TrendPoint[]>(`/stats/trend?limit=${limit}`)

export const getOverview = () => request<Overview>('/stats/overview')

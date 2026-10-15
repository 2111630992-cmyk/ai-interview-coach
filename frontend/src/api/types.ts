/** 与后端 schemas 对应的类型定义。字段名保持 snake_case，避免无谓的转换层。 */

export interface UserPublic {
  id: string
  email: string
  nickname: string
  is_guest: boolean
  created_at: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: UserPublic
}

export interface ResumePublic {
  id: string
  filename: string
  parsed: ResumeParsed
  parse_warning: string | null
  text_length: number
  created_at: string | null
}

export interface ResumeParsed {
  name?: string
  education?: Array<Record<string, string>>
  skills?: string[]
  projects?: Array<{
    name?: string
    role?: string
    period?: string
    description?: string
    tech?: string[]
    highlights?: string[]
  }>
  internships?: Array<{
    company?: string
    role?: string
    period?: string
    description?: string
    achievements?: string[]
  }>
  awards?: string[]
  highlights?: string[]
}

export interface CompetencyModel {
  hard_skills?: string[]
  soft_skills?: string[]
  domains?: string[]
  weights?: Record<string, number>
  summary?: string
}

export interface JDPublic {
  id: string
  title: string
  company: string | null
  competency_model: CompetencyModel
  raw_text_length: number
  created_at: string | null
}

export interface MatchPublic {
  id: string
  resume_id: string
  jd_id: string
  match_score: number
  strengths: string[]
  risks: string[]
  likely_questions: string[]
  summary: string
  cached: boolean
  created_at: string | null
}

export interface InterviewConfig {
  interview_type: string
  duration_min: number
  difficulty: string
  language: string
  pressure_mode: boolean
  // 练习模式（每题即时评分） / 模拟模式（全程隐藏分数）
  feedback_mode: 'practice' | 'simulation'
  realtime_feedback: boolean
  voice_enabled: boolean
  // 文字面试 / 视频面试
  mode: 'text' | 'video'
  // panel = 每环节换一位面试官；single = 整场同一位
  interviewer_mode: 'panel' | 'single'
  interviewer_type: string
  allow_hint: boolean
  allow_skip: boolean
  require_camera: boolean
  /** 后端内部记账：暂停累计秒数、诚实记录，以下划线开头 */
  _paused_seconds?: number
  _paused_at?: string
  _honesty?: { hint_count: number; skip_count: number; marked_count: number }
}

/** 面试官人格。名字、背景、风格都会真正影响提问与评分口径。 */
export interface InterviewerPublic {
  type: string
  name: string
  title: string
  emoji: string
  accent: string
  bio: string
  style: string
  personality: string
  focus_areas: string[]
}

/** 视频/语音作答的表达指标（前端本地实测，随回答一起上报）。 */
export interface DeliveryMetricsPayload {
  duration_ms: number
  word_count: number
  speech_rate: number
  filler_count: number
  filler_ratio: number
  long_pause_count: number
  longest_pause_ms: number
  transcript_source: 'asr' | 'typed' | 'mixed'
}

export interface SuggestedAnswerPayload {
  outline: string[]
  key_points: string[]
  improvements: string[]
  reference_answer: string
  placeholders: string[]
  generated_at?: string
}

export interface PlanStage {
  stage: string
  weight: number
  goal: string
}

export interface CompetencyItem {
  name: string
  source: 'jd' | 'resume' | 'general'
  weight: number
  probe_questions: string[]
}

export interface InterviewPlan {
  total_rounds: number
  stages: PlanStage[]
  competencies: CompetencyItem[]
  constraints: string[]
  opening_line: string
}

export interface Evaluation {
  relevance: number
  structure: number
  depth: number
  delivery: number
  fit: number
  evidence: string[]
  strengths: string[]
  problems: Array<{ issue: string; why: string; fix: string }>
  /** 面试官下一步会拿什么来质疑 —— 前瞻性提示 */
  risk_points: string[]
  rewritten_answer: string
  is_weak: boolean
}

export interface TurnPublic {
  id: string
  turn_index: number
  stage: string
  competency: string | null
  question: string
  answer: string | null
  is_followup: boolean
  followup_depth: number
  parent_turn_id: string | null
  /** 本轮由哪位面试官发问 */
  interviewer: InterviewerPublic | null
  // ---- 真实面试行为记录 ----
  hinted: boolean
  skipped: boolean
  marked: boolean
  delivery_metrics: DeliveryMetricsPayload | null
  /** 本地录像 key（视频存在浏览器 IndexedDB，不在服务器） */
  recording_key: string | null
  has_suggested_answer: boolean
  evaluation: Evaluation | null
  created_at: string | null
}

export interface InterviewSummary {
  id: string
  status: string
  config: InterviewConfig
  plan_summary: string
  current_stage: string | null
  current_turn_index: number
  turn_count: number
  total_score: number | null
  dimensions: Record<string, number> | null
  /** 视频面试的表达指标汇总 */
  delivery_summary: DeliveryMetricsPayload | { is_voice: false }
  resume_filename: string
  jd_title: string | null
  current_interviewer: InterviewerPublic | null
  started_at: string | null
  finished_at: string | null
  created_at: string | null
}

export interface InterviewDetail extends InterviewSummary {
  plan: InterviewPlan
  /** 环节 → 面试官人格 */
  roster: Record<string, InterviewerPublic>
  token_usage: Record<string, unknown>
  turns: TurnPublic[]
  expose_scores: boolean
}

export interface TopProblem {
  title: string
  evidence: string
  why_bad: string
  how_to_fix: string
  demo_answer: string
}

export interface TrainingDay {
  day: number
  task: string
  goal: string
  link_competency: string
}

export interface PerTurnFeedback {
  turn_id: string
  turn_index: number
  stage: string
  stage_label: string
  competency: string | null
  question: string
  answer: string
  is_followup: boolean
  followup_depth: number
  interviewer_name: string | null
  interviewer_title: string | null
  hinted: boolean
  skipped: boolean
  marked: boolean
  delivery_metrics: DeliveryMetricsPayload | null
  recording_key: string | null
  scores: Record<string, number | null>
  weighted_score: number | null
  evidence: string[]
  strengths: string[]
  problems: Array<{ issue: string; why: string; fix: string }>
  risk_points: string[]
  rewritten_answer: string
}

export interface ReportPublic {
  id: string
  session_id: string
  verdict: string
  verdict_label: string
  summary: string
  dimension_scores: Record<string, number>
  top_problems: TopProblem[]
  per_turn_feedback: PerTurnFeedback[]
  training_plan: TrainingDay[]
  /** 视频面试的表达指标汇总；纯文字面试为 { is_voice: false } */
  delivery_summary: Record<string, number | boolean> | { is_voice: false }
  created_at: string | null
}

export interface TrendPoint {
  session_id: string
  date: string | null
  jd_title: string | null
  interview_type: string
  total_score: number | null
}

export interface Overview {
  resume_count: number
  jd_count: number
  interview_count: number
  finished_count: number
  match_count: number
  avg_score: number | null
  best_score: number | null
  dimension_avg: Record<string, number>
}

export interface HealthInfo {
  status: string
  app: string
  version: string
  env: string
  llm_mode: 'mock' | 'live'
  llm_model: string | null
}

// ---------------- SSE ----------------

export interface SSEQuestionPayload {
  turn_id: string
  turn_index: number
  question: string
  is_followup: boolean
  followup_depth: number
  stage: string
  competency: string | null
  interviewer: InterviewerPublic | null
}

export interface SSEDonePayload {
  turn_index: number
  stage_finished: boolean
  session_finished: boolean
  progress: number
  usage: Record<string, unknown>
}

export interface SSEStagePayload {
  stage: string
  progress: number
  elapsed_min: number
  first: boolean
}

export interface SSEErrorPayload {
  code: string
  message: string
  detail?: Record<string, unknown>
}

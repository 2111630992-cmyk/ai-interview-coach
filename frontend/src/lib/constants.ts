/**
 * 与后端 constants.py 一一对应的展示常量。
 * key 必须与后端保持一致，否则界面会出现"未知环节"。
 */

export const STAGE_LABELS: Record<string, string> = {
  intro: '开场与自我介绍',
  resume_deep_dive: '简历深挖',
  hard_skill: '专业技能',
  behavioral: '行为面试',
  pressure: '压力追问',
  candidate_ask: '候选人反问',
}

export const STAGE_ORDER = [
  'intro',
  'resume_deep_dive',
  'hard_skill',
  'behavioral',
  'pressure',
  'candidate_ask',
] as const

export const STAGE_SHORT: Record<string, string> = {
  intro: '开场',
  resume_deep_dive: '简历',
  hard_skill: '技能',
  behavioral: '行为',
  pressure: '压力',
  candidate_ask: '反问',
}

export const DIMENSION_LABELS: Record<string, string> = {
  relevance: '内容相关性',
  structure: '结构逻辑',
  depth: '专业深度',
  delivery: '表达流畅',
  fit: '岗位匹配',
}

export const DIMENSION_ORDER = ['relevance', 'structure', 'depth', 'delivery', 'fit'] as const

export const DIMENSION_HINTS: Record<string, string> = {
  relevance: '是否正面回答了问题',
  structure: '是否 STAR / 分层清晰',
  depth: '技术细节、数据、权衡取舍',
  delivery: '简洁度、口头禅、时长',
  fit: '是否体现岗位所需能力',
}

export const INTERVIEW_TYPES = [
  { value: 'technical', label: '技术面', desc: '深挖技术栈与项目实现细节' },
  { value: 'behavioral', label: '行为面', desc: '用 STAR 考察协作、抗压、主动性' },
  { value: 'comprehensive', label: '综合终面', desc: '技术 + 行为 + 动机全覆盖' },
  { value: 'hr', label: 'HR 面', desc: '求职动机、稳定性、沟通表达' },
] as const

export const DIFFICULTIES = [
  { value: 'intern', label: '实习', desc: '基础问题为主，容错率高' },
  { value: 'campus', label: '校招', desc: '标准校招强度' },
  { value: 'bigtech', label: '大厂', desc: '追问更深，压力面开启' },
] as const

export const DURATIONS = [
  { value: 15, label: '15 分钟', desc: '快速热身' },
  { value: 30, label: '30 分钟', desc: '标准一面' },
  { value: 45, label: '45 分钟', desc: '完整技术面' },
] as const

export const LANGUAGES = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
] as const

/** 反馈模式：练习（每题即时评分） vs 模拟（全程隐藏分数） */
export const FEEDBACK_MODES: Record<string, string> = {
  simulation: '模拟模式（全程不看分数）',
  practice: '练习模式（每题即时评分）',
}

export const VERDICT_META: Record<
  string,
  { label: string; tone: 'success' | 'primary' | 'warning' | 'destructive' }
> = {
  strong_pass: { label: '强烈推荐通过', tone: 'success' },
  pass: { label: '可以通过', tone: 'primary' },
  borderline: { label: '边缘，需补强', tone: 'warning' },
  fail: { label: '不通过', tone: 'destructive' },
}

export const STATUS_LABELS: Record<string, string> = {
  created: '待开始',
  running: '进行中',
  paused: '已暂停',
  finished: '已完成',
  aborted: '已放弃',
}

/** 面试官人格的强调色。
 *  Tailwind 无法从变量拼类名，所以这里写死完整类串。 */
export const ACCENT_CLASSES: Record<
  string,
  { chip: string; ring: string; bg: string; text: string; solid: string }
> = {
  slate: {
    chip: 'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200',
    ring: 'ring-slate-400/40',
    bg: 'bg-slate-100 dark:bg-slate-800/50',
    text: 'text-slate-700 dark:text-slate-200',
    solid: 'bg-slate-500',
  },
  blue: {
    chip: 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/50 dark:text-blue-200',
    ring: 'ring-blue-400/40',
    bg: 'bg-blue-50 dark:bg-blue-950/40',
    text: 'text-blue-700 dark:text-blue-200',
    solid: 'bg-blue-500',
  },
  emerald: {
    chip: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200',
    ring: 'ring-emerald-400/40',
    bg: 'bg-emerald-50 dark:bg-emerald-950/40',
    text: 'text-emerald-700 dark:text-emerald-200',
    solid: 'bg-emerald-500',
  },
  violet: {
    chip: 'border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-950/50 dark:text-violet-200',
    ring: 'ring-violet-400/40',
    bg: 'bg-violet-50 dark:bg-violet-950/40',
    text: 'text-violet-700 dark:text-violet-200',
    solid: 'bg-violet-500',
  },
  amber: {
    chip: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-200',
    ring: 'ring-amber-400/40',
    bg: 'bg-amber-50 dark:bg-amber-950/40',
    text: 'text-amber-700 dark:text-amber-200',
    solid: 'bg-amber-500',
  },
  rose: {
    chip: 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-200',
    ring: 'ring-rose-400/40',
    bg: 'bg-rose-50 dark:bg-rose-950/40',
    text: 'text-rose-700 dark:text-rose-200',
    solid: 'bg-rose-500',
  },
}

export function accent(accentName: string | undefined) {
  return ACCENT_CLASSES[accentName ?? 'slate'] ?? ACCENT_CLASSES.slate
}

/** 分数配色语义：一处定义，气泡与报告共用。 */
export function scoreTone(score: number | null | undefined) {
  if (score == null) {
    return { text: 'text-muted-foreground', chip: 'border-border bg-secondary text-muted-foreground', bar: 'bg-muted-foreground/40' }
  }
  if (score >= 4)
    return {
      text: 'text-success',
      chip: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200',
      bar: 'bg-success',
    }
  if (score >= 3)
    return {
      text: 'text-primary',
      chip: 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200',
      bar: 'bg-primary',
    }
  if (score >= 2)
    return {
      text: 'text-amber-600 dark:text-amber-400',
      chip: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200',
      bar: 'bg-amber-500',
    }
  return {
    text: 'text-destructive',
    chip: 'border-red-300 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200',
    bar: 'bg-destructive',
  }
}

/** 面试进行页在客户端维护的每轮节奏提示（仅本地倒计时用，不约束后端） */
export const ANSWER_SOFT_LIMIT_SECONDS = 150
/** 每轮回答的硬性时长上限，用于自动停止录制 */
export const ANSWER_HARD_LIMIT_SECONDS = 300

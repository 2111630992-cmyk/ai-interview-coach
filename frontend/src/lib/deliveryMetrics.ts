/**
 * 表达指标计算。
 *
 * ## 为什么要算这些数字
 *
 * 「表达流畅」是全靠主观印象最容易失真的一个维度 —— 模型读一段文字，
 * 既听不出你语速多快，也听不出你卡了几次。所以在视频/语音模式下，
 * 前端从 **ASR 结果 + 录音时间轴** 算出客观指标，再交给后端评分。
 *
 * 这样做的效果是：评分提示词里可以写"语速低于 180 字/分钟最高 3.5 分"这种
 * 可核对的规则，而不是让模型自由发挥。
 *
 * 所有阈值与后端 `app/constants.py` 保持一致（180-320 字/分钟、长停顿 2.5 秒）。
 */

/** 与后端 FILLER_WORDS 保持一致 —— 改一处必须改两处，否则指标会对不上。 */
export const FILLER_WORDS = [
  '然后',
  '就是',
  '那个',
  '这个',
  '其实',
  '反正',
  '怎么说呢',
  '呃',
  '嗯',
  '啊',
  '吧',
  '嘛',
  '的话',
  '对吧',
  '你知道',
]

export const SPEECH_RATE_MIN = 180
export const SPEECH_RATE_MAX = 320
export const LONG_PAUSE_MS = 2500

export interface DeliveryMetrics {
  duration_ms: number
  word_count: number
  speech_rate: number
  filler_count: number
  filler_ratio: number
  long_pause_count: number
  longest_pause_ms: number
  transcript_source: 'asr' | 'typed' | 'mixed'
}

export function countFillers(text: string): { count: number; chars: number } {
  let count = 0
  let chars = 0
  for (const word of FILLER_WORDS) {
    let from = 0
    for (;;) {
      const idx = text.indexOf(word, from)
      if (idx === -1) break
      count += 1
      chars += word.length
      from = idx + word.length
    }
  }
  return { count, chars }
}

/** 中英混排的"字数"：CJK 按字算，英文按空白分词算。 */
export function countWords(text: string): number {
  const cjk = (text.match(/[\u4e00-\u9fff]/g) ?? []).length
  const latin = (text.replace(/[\u4e00-\u9fff]/g, ' ').match(/[A-Za-z0-9][A-Za-z0-9+#._-]*/g) ?? [])
    .length
  return cjk + latin
}

export interface DeliveryInput {
  text: string
  durationMs: number
  source: 'asr' | 'typed' | 'mixed'
  /** 录音期间检测到的停顿（毫秒），由 DeliveryTracker 提供 */
  pauses?: number[]
}

export function computeDeliveryMetrics({
  text,
  durationMs,
  source,
  pauses = [],
}: DeliveryInput): DeliveryMetrics {
  const wordCount = countWords(text)
  const { count: fillerCount, chars: fillerChars } = countFillers(text)
  const minutes = Math.max(durationMs, 1) / 60_000
  const longPauses = pauses.filter((p) => p >= LONG_PAUSE_MS)

  return {
    duration_ms: Math.max(0, Math.round(durationMs)),
    word_count: wordCount,
    speech_rate: wordCount > 0 ? Math.round((wordCount / minutes) * 10) / 10 : 0,
    filler_count: fillerCount,
    // 占比按"口头禅字数 / 总字数"，比按次数更能反映听感
    filler_ratio: wordCount > 0 ? Math.round((fillerChars / wordCount) * 10000) / 10000 : 0,
    long_pause_count: longPauses.length,
    longest_pause_ms: pauses.length ? Math.round(Math.max(...pauses)) : 0,
    transcript_source: source,
  }
}

/**
 * 追踪一次作答过程中的说话节奏。
 *
 * 用法：`start()` → 每次拿到语音识别结果时 `noteSpeech()` → 结束时 `stop()`。
 * 相邻两次识别之间的间隔超过阈值就记一次停顿。
 */
export class DeliveryTracker {
  private startedAt = 0
  private lastSpeechAt = 0
  private pauses: number[] = []
  private running = false

  start(now = Date.now()): void {
    this.startedAt = now
    this.lastSpeechAt = now
    this.pauses = []
    this.running = true
  }

  noteSpeech(now = Date.now()): void {
    if (!this.running) return
    const gap = now - this.lastSpeechAt
    // 第一次 noteSpeech 紧跟 start，不算停顿
    if (gap >= LONG_PAUSE_MS) this.pauses.push(gap)
    this.lastSpeechAt = now
  }

  stop(now = Date.now()): { durationMs: number; pauses: number[] } {
    this.running = false
    // 结尾到提交之间的空档也算一次停顿（很多人是"说完了想半天才点提交"）
    const tail = now - this.lastSpeechAt
    const pauses = tail >= LONG_PAUSE_MS ? [...this.pauses, tail] : [...this.pauses]
    return { durationMs: Math.max(0, now - this.startedAt), pauses }
  }

  get elapsedMs(): number {
    return this.running ? Date.now() - this.startedAt : 0
  }
}

export interface DeliveryVerdict {
  tone: 'good' | 'warn' | 'bad'
  label: string
  detail: string
}

/** 判断 delivery_summary 是否代表"确实有语音作答"。 */
export function isVoiceSummary(summary: unknown): boolean {
  return Boolean(summary && typeof summary === 'object' && (summary as { is_voice?: boolean }).is_voice)
}

/** 安全读取汇总里的数值字段（汇总结构在后端是 dict，字段可能缺失）。 */
export function voiceSummaryNumber(summary: unknown, key: string): number {
  if (!summary || typeof summary !== 'object') return 0
  const value = (summary as Record<string, unknown>)[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

/** 把指标翻译成一句人话，用于报告页与答题后的即时反馈。 */
export function judgeDelivery(m: DeliveryMetrics | null | undefined): DeliveryVerdict | null {
  if (!m || (m.transcript_source !== 'asr' && m.transcript_source !== 'mixed')) return null
  if (!m.word_count) return null

  const problems: string[] = []
  if (m.speech_rate < SPEECH_RATE_MIN) problems.push(`语速偏慢（${m.speech_rate} 字/分）`)
  if (m.speech_rate > SPEECH_RATE_MAX) problems.push(`语速偏快（${m.speech_rate} 字/分）`)
  if (m.filler_ratio > 0.06) problems.push(`口头禅偏多（${(m.filler_ratio * 100).toFixed(1)}%）`)
  if (m.long_pause_count > 3) problems.push(`卡壳 ${m.long_pause_count} 次`)

  if (problems.length === 0) {
    return {
      tone: 'good',
      label: '口播节奏正常',
      detail: `语速 ${m.speech_rate} 字/分，口头禅占比 ${(m.filler_ratio * 100).toFixed(1)}%，节奏在正常区间内。`,
    }
  }
  return {
    tone: problems.length >= 2 ? 'bad' : 'warn',
    label: problems.join('；'),
    detail: `实测：语速 ${m.speech_rate} 字/分（正常 180-320），口头禅占比 ${(
      m.filler_ratio * 100
    ).toFixed(1)}%（建议 <2%），长停顿 ${m.long_pause_count} 次，最长 ${(
      m.longest_pause_ms / 1000
    ).toFixed(1)} 秒。`,
  }
}

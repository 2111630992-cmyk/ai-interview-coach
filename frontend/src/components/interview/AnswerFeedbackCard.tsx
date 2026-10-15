import { AlertTriangle, BarChart3, Lightbulb, Quote, Sparkles, Target } from 'lucide-react'
import { useState } from 'react'

import type { Evaluation } from '../../api/types'
import { DIMENSION_HINTS, DIMENSION_LABELS, scoreTone } from '../../lib/constants'
import type { DeliveryMetrics } from '../../lib/deliveryMetrics'
import { judgeDelivery } from '../../lib/deliveryMetrics'
import { cn } from '../../lib/utils'
import { Button } from '../ui/button'
import { Spinner } from '../ui/feedback'

interface AnswerFeedbackCardProps {
  evaluation: Evaluation
  deliveryMetrics?: DeliveryMetrics | null
  /** 参考答案按需拉取 */
  onRequestSuggested?: () => Promise<void>
  suggestedAnswer?: {
    outline: string[]
    key_points: string[]
    improvements: string[]
    reference_answer: string
    placeholders: string[]
  } | null
}

/**
 * 单题即时评分卡（练习模式）。
 *
 * 借鉴自 JobPilot 的 `AnswerEvaluationCard`：把分数直接贴在**考生自己的那句话下面**，
 * 而不是等到整场结束。反馈离回答越近，学得越快。
 *
 * 但只在**练习模式**出现 —— 模拟模式（尤其是视频面试）全程不显示，
 * 因为真实面试里你不会当场知道自己得几分。
 */
export function AnswerFeedbackCard({
  evaluation,
  deliveryMetrics,
  onRequestSuggested,
  suggestedAnswer,
}: AnswerFeedbackCardProps) {
  const [loadingSuggested, setLoadingSuggested] = useState(false)
  const [suggestError, setSuggestError] = useState<string | null>(null)
  const [open, setOpen] = useState(true)

  const score = evaluation.is_weak
    ? weighted(evaluation)
    : weighted(evaluation)
  const tone = scoreTone(score)
  const delivery = judgeDelivery(deliveryMetrics)

  const dims = (['relevance', 'structure', 'depth', 'delivery', 'fit'] as const).map((d) => ({
    key: d,
    label: DIMENSION_LABELS[d],
    hint: DIMENSION_HINTS[d],
    value: evaluation[d],
  }))

  const requestSuggested = async () => {
    if (!onRequestSuggested) return
    setLoadingSuggested(true)
    setSuggestError(null)
    try {
      await onRequestSuggested()
    } catch (err) {
      setSuggestError(err instanceof Error ? err.message : '参考答案生成失败，请稍后重试')
    } finally {
      setLoadingSuggested(false)
    }
  }

  return (
    <div className="max-w-[88%] rounded-lg rounded-tl-sm border border-border bg-card p-4 shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 text-left"
      >
        <BarChart3 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="flex-1 text-sm font-medium">这一题的反馈</span>
        <span
          className={cn(
            'shrink-0 rounded-full border px-3 py-0.5 font-mono text-sm font-semibold',
            tone.chip,
          )}
        >
          {score.toFixed(1)}
          <span className="text-xs font-normal opacity-70">/5</span>
        </span>
      </button>

      {open && (
        <div className="mt-3 flex flex-col gap-3 text-sm">
          {/* 五维 */}
          <div className="grid gap-2 md:grid-cols-2">
            {dims.map((d) => (
              <div key={d.key} className="rounded-md bg-secondary/50 px-3 py-2">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-xs font-medium">{d.label}</span>
                  <span className={cn('font-mono text-sm font-semibold', scoreTone(d.value).text)}>
                    {d.value.toFixed(1)}
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] text-muted-foreground">{d.hint}</p>
              </div>
            ))}
          </div>

          {/* 语音作答的表达指标：客观数字，不是模型印象 */}
          {delivery && (
            <div
              className={cn(
                'rounded-md border p-2.5 text-xs',
                delivery.tone === 'good'
                  ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30'
                  : 'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30',
              )}
            >
              <p className="font-medium">{delivery.label}</p>
              <p className="mt-0.5 text-muted-foreground">{delivery.detail}</p>
            </div>
          )}

          {/* 证据 */}
          {evaluation.evidence.length > 0 && (
            <div>
              <p className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
                <Quote className="h-3 w-3" aria-hidden />
                评分依据（你的原话）
              </p>
              <ul className="flex flex-col gap-1">
                {evaluation.evidence.map((e, i) => (
                  <li
                    key={i}
                    className="border-l-2 border-primary/30 pl-2 text-xs italic text-muted-foreground"
                  >
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 问题 */}
          {evaluation.problems.length > 0 && (
            <div className="flex flex-col gap-2">
              {evaluation.problems.map((p, i) => (
                <div
                  key={i}
                  className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5"
                >
                  <p className="text-xs font-medium">{p.issue}</p>
                  {p.why && <p className="mt-1 text-[11px] text-muted-foreground">后果：{p.why}</p>}
                  {p.fix && <p className="mt-1 text-[11px] text-muted-foreground">改法：{p.fix}</p>}
                </div>
              ))}
            </div>
          )}

          {/* 面试官下一步会追什么 —— 前瞻性提示 */}
          {evaluation.risk_points?.length > 0 && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-2.5 dark:border-amber-800 dark:bg-amber-950/30">
              <p className="flex items-center gap-1 text-xs font-medium">
                <AlertTriangle className="h-3 w-3" aria-hidden />
                面试官接下来会追这里
              </p>
              <ul className="mt-1 flex flex-col gap-0.5">
                {evaluation.risk_points.map((r, i) => (
                  <li key={i} className="text-[11px] text-muted-foreground">
                    · {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 优点 */}
          {evaluation.strengths.length > 0 && (
            <div className="rounded-md border border-emerald-300 bg-emerald-50 p-2.5 dark:border-emerald-800 dark:bg-emerald-950/30">
              <p className="flex items-center gap-1 text-xs font-medium">
                <Lightbulb className="h-3 w-3" aria-hidden />
                做得好的地方
              </p>
              <ul className="mt-1 flex flex-col gap-0.5">
                {evaluation.strengths.map((s, i) => (
                  <li key={i} className="text-[11px] text-muted-foreground">
                    · {s}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 参考答案：按需、只生成一次 */}
          {onRequestSuggested && (
            <div className="rounded-md border border-primary/25 bg-primary/5 p-2.5">
              {suggestedAnswer ? (
                <div className="flex flex-col gap-2">
                  {suggestedAnswer.placeholders.length > 0 && (
                    <div className="rounded border border-amber-300 bg-amber-50 p-2 dark:border-amber-800 dark:bg-amber-950/40">
                      <p className="text-[11px] font-medium">
                        这些地方需要你补上真实数据（AI 不会替你编）
                      </p>
                      <ul className="mt-0.5 flex flex-wrap gap-1">
                        {suggestedAnswer.placeholders.map((p, i) => (
                          <li
                            key={i}
                            className="rounded bg-background/80 px-1.5 py-0.5 text-[11px] text-muted-foreground"
                          >
                            {p}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div>
                    <p className="text-[11px] font-medium">回答结构</p>
                    <ol className="mt-0.5 list-decimal space-y-0.5 pl-4 text-[11px] text-muted-foreground">
                      {suggestedAnswer.outline.map((o, i) => (
                        <li key={i}>{o}</li>
                      ))}
                    </ol>
                  </div>
                  <div>
                    <p className="text-[11px] font-medium">参考回答</p>
                    <p className="mt-0.5 whitespace-pre-wrap text-xs leading-6 text-muted-foreground">
                      {suggestedAnswer.reference_answer}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={requestSuggested}
                    disabled={loadingSuggested}
                  >
                    {loadingSuggested ? <Spinner className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" aria-hidden />}
                    {loadingSuggested ? '生成中…' : '看参考答案'}
                  </Button>
                  <span className="text-[11px] text-muted-foreground">
                    <Target className="mr-1 inline h-3 w-3" aria-hidden />
                    只基于你说过的事实，缺数据的地方会留占位符
                  </span>
                </div>
              )}
              {suggestError && (
                <p className="mt-1 text-[11px] text-destructive" role="alert">
                  {suggestError}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function weighted(e: Evaluation): number {
  const w = { relevance: 0.2, structure: 0.2, depth: 0.25, delivery: 0.15, fit: 0.2 }
  return (
    e.relevance * w.relevance +
    e.structure * w.structure +
    e.depth * w.depth +
    e.delivery * w.delivery +
    e.fit * w.fit
  )
}

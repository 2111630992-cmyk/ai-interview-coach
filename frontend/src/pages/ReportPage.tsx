import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  CalendarCheck,
  ChevronDown,
  Lightbulb,
  Mic,
  Quote,
  RefreshCw,
  Star,
  Target,
  TrendingUp,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import { getReport } from '../api/endpoints'
import type { PerTurnFeedback } from '../api/types'
import { DimensionRadar } from '../components/charts/Charts'
import { AnswerPlayback } from '../components/interview/AnswerPlayback'
import { Markdown } from '../components/Markdown'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Alert, Badge, EmptyState, Progress, Skeleton } from '../components/ui/feedback'
import { DIMENSION_LABELS, VERDICT_META } from '../lib/constants'
import { judgeDelivery } from '../lib/deliveryMetrics'
import { cn } from '../lib/utils'

export function ReportPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const report = useQuery({
    queryKey: ['report', sessionId],
    queryFn: () => getReport(sessionId as string),
    enabled: Boolean(sessionId),
  })

  if (report.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
        <Skeleton className="h-40" />
      </div>
    )
  }

  if (report.isError) {
    const err = report.error
    return (
      <EmptyState
        title="还没有生成报告"
        description={err instanceof ApiError ? err.message : '请稍后重试'}
        action={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void report.refetch()}>
              <RefreshCw className="h-4 w-4" aria-hidden />
              重试
            </Button>
            <Link to={`/interview/${sessionId}`}>
              <Button>回到面试</Button>
            </Link>
          </div>
        }
      />
    )
  }

  const data = report.data
  if (!data) return null

  const verdict = VERDICT_META[data.verdict] ?? VERDICT_META.borderline
  const total = Object.keys(data.dimension_scores).length
    ? Object.values(data.dimension_scores).reduce((a, b) => a + b, 0) /
      Object.keys(data.dimension_scores).length
    : 0

  // 视频面试才有表达指标汇总
  const deliverySummary = data.delivery_summary as
    | (Record<string, number | boolean> & { is_voice?: boolean })
    | undefined
  const hasVoice = Boolean(deliverySummary?.is_voice)
  const voiceVerdict = hasVoice
    ? judgeDelivery({
        duration_ms: Number(deliverySummary?.total_speaking_ms ?? 0),
        word_count: 0,
        speech_rate: Number(deliverySummary?.avg_speech_rate ?? 0),
        filler_count: Number(deliverySummary?.total_filler_count ?? 0),
        filler_ratio: Number(deliverySummary?.avg_filler_ratio ?? 0),
        long_pause_count: Number(deliverySummary?.total_long_pauses ?? 0),
        longest_pause_ms: Number(deliverySummary?.longest_pause_ms ?? 0),
        transcript_source: 'asr',
      })
    : null

  // 诚实机制：用了提示、跳过了几题
  const honest = (data as unknown as { config?: Record<string, unknown> }).config?._honesty as
    | { hint_count: number; skip_count: number; marked_count: number }
    | undefined
  const markedTurns = data.per_turn_feedback.filter((t) => t.marked)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">面试报告</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data.created_at ? new Date(data.created_at).toLocaleString('zh-CN') : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/interview/setup">
            <Button variant="outline">
              <Target className="h-4 w-4" aria-hidden />
              再练一场
            </Button>
          </Link>
          <Link to="/history">
            <Button variant="ghost">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              全部记录
            </Button>
          </Link>
        </div>
      </div>

      {honest && (honest.hint_count > 0 || honest.skip_count > 0) && (
        <Alert tone="warning" title="本场诚实记录">
          你在本场面试中使用了 <strong className="text-foreground">{honest.hint_count}</strong> 次提示、
          跳过了 <strong className="text-foreground">{honest.skip_count}</strong> 道题
          {honest.marked_count > 0 && `、标记了 ${honest.marked_count} 道题待复习`}。
          这不是"扣分项"，而是帮你看清哪些知识点是真的没掌握 —— 跳过的那几题往往就是最该补的。
        </Alert>
      )}

      {/* 结论 */}
      <Card>
        <CardContent className="flex flex-col gap-4 pt-5 sm:flex-row sm:items-center sm:gap-6">
          <div
            className={cn(
              'flex h-24 w-24 shrink-0 flex-col items-center justify-center rounded-full border-4',
              verdict.tone === 'success' && 'border-success/40',
              verdict.tone === 'primary' && 'border-primary/40',
              verdict.tone === 'warning' && 'border-amber-500/40',
              verdict.tone === 'destructive' && 'border-destructive/40',
            )}
          >
            <span className="text-3xl font-bold tabular-nums">{total.toFixed(0)}</span>
            <span className="text-[10px] text-muted-foreground">加权总分</span>
          </div>

          <div className="min-w-0 flex-1">
            <Badge tone={verdict.tone}>{verdict.label}</Badge>
            <div className="mt-2">
              <Markdown className="text-sm leading-7 text-muted-foreground">{data.summary}</Markdown>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 五维 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">五维评分</CardTitle>
          <CardDescription>
            评分由独立于出题的模型给出，每个分数都必须引用你的原话作为依据
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DimensionRadar scores={data.dimension_scores} />
        </CardContent>
      </Card>

      {/* 视频面试：客观表达指标 */}
      {hasVoice && voiceVerdict && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Mic className="h-4 w-4 text-primary" aria-hidden />
              表达实测数据
            </CardTitle>
            <CardDescription>
              这些是从你的录音里算出来的客观数字，不是模型的印象判断
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div
              className={cn(
                'rounded-md border p-3',
                voiceVerdict.tone === 'good'
                  ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30'
                  : voiceVerdict.tone === 'warn'
                    ? 'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30'
                    : 'border-destructive/40 bg-destructive/5',
              )}
            >
              <p className="text-sm font-medium">{voiceVerdict.label}</p>
              <p className="mt-1 text-xs text-muted-foreground">{voiceVerdict.detail}</p>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MetricTile
                label="平均语速"
                value={`${Number(deliverySummary?.avg_speech_rate ?? 0).toFixed(0)}`}
                unit="字/分"
                hint="正常 180-320"
              />
              <MetricTile
                label="口头禅占比"
                value={`${(Number(deliverySummary?.avg_filler_ratio ?? 0) * 100).toFixed(1)}`}
                unit="%"
                hint="建议低于 2%"
              />
              <MetricTile
                label="长停顿次数"
                value={`${Number(deliverySummary?.total_long_pauses ?? 0)}`}
                unit="次"
                hint="单次超过 2.5 秒"
              />
              <MetricTile
                label="有效说话时长"
                value={`${(Number(deliverySummary?.total_speaking_ms ?? 0) / 60000).toFixed(1)}`}
                unit="分钟"
                hint={`共 ${Number(deliverySummary?.answered_voice_turns ?? 0)} 题语音作答`}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* 标记待复习 */}
      {markedTurns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Star className="h-4 w-4 text-amber-500" aria-hidden />
              你标记了 {markedTurns.length} 道题要复习
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-2 text-sm">
              {markedTurns.map((t) => (
                <li key={t.turn_id} className="flex gap-2">
                  <span className="font-mono text-xs text-muted-foreground">#{t.turn_index}</span>
                  <span className="min-w-0 flex-1 truncate">{t.question}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {/* Top 问题 */}
      <section>
        <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
          <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden />
          最该先改的 {data.top_problems.length} 个问题
        </h2>
        <div className="flex flex-col gap-3">
          {data.top_problems.map((p, i) => (
            <Card key={i}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-500/15 text-xs font-semibold text-amber-600 dark:text-amber-400">
                    {i + 1}
                  </span>
                  {p.title}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                {p.evidence && (
                  <div className="flex gap-2 rounded-md border border-border bg-secondary/40 p-3">
                    <Quote className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    <div>
                      <p className="text-xs text-muted-foreground">你的原话</p>
                      <p className="mt-0.5 italic">{p.evidence}</p>
                    </div>
                  </div>
                )}

                <div>
                  <p className="text-xs font-medium text-muted-foreground">为什么这是问题</p>
                  <p className="mt-0.5 leading-7">{p.why_bad}</p>
                </div>

                <div>
                  <p className="text-xs font-medium text-muted-foreground">具体怎么改</p>
                  <p className="mt-0.5 leading-7">{p.how_to_fix}</p>
                </div>

                {p.demo_answer && (
                  <details className="group rounded-md border border-primary/25 bg-primary/5 p-3">
                    <summary className="cursor-pointer text-xs font-medium text-primary">
                      查看改写示范（基于你真实经历，未新增事实）
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-7">{p.demo_answer}</p>
                  </details>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* 7 天计划 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarCheck className="h-4 w-4 text-primary" aria-hidden />
            7 天训练计划
          </CardTitle>
          <CardDescription>每天只做一件事，但必须做到能口述出来</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col gap-3">
            {data.training_plan.map((day) => (
              <li key={day.day} className="flex gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/12 text-xs font-semibold text-primary">
                  D{day.day}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-7">{day.task}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    目标：{day.goal}
                    {day.link_competency && ` · 对应考察点：${day.link_competency}`}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      {/* 逐题点评 */}
      <section>
        <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
          <TrendingUp className="h-4 w-4 text-primary" aria-hidden />
          逐题点评（{data.per_turn_feedback.length} 题）
        </h2>
        <div className="flex flex-col gap-2">
          {data.per_turn_feedback.map((t) => (
            <TurnCard key={t.turn_id} turn={t} />
          ))}
        </div>
      </section>

      <Alert tone="info" title="关于这份报告的诚实说明">
        评分由 AI 给出，存在主观漂移，不等于真实面试结果。它最可靠的部分是
        <strong className="mx-1 text-foreground">结构与表达问题</strong>
        以及
        <strong className="mx-1 text-foreground">"你以为讲清楚了、但面试官听不出你的贡献"</strong>
        这类问题。技术正确性请自行核对。
      </Alert>
    </div>
  )
}

function scoreTone(score: number | null | undefined) {
  if (score == null) return 'text-muted-foreground'
  if (score >= 4) return 'text-success'
  if (score >= 3) return 'text-primary'
  if (score >= 2) return 'text-amber-600 dark:text-amber-400'
  return 'text-destructive'
}

function MetricTile({
  label,
  value,
  unit,
  hint,
}: {
  label: string
  value: string
  unit: string
  hint: string
}) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-mono text-lg font-semibold tabular-nums">
        {value}
        <span className="ml-0.5 text-xs font-normal text-muted-foreground">{unit}</span>
      </p>
      <p className="text-[11px] text-muted-foreground">{hint}</p>
    </div>
  )
}

function TurnCard({ turn }: { turn: PerTurnFeedback }) {
  const [open, setOpen] = useState(
    turn.problems.length > 0 || turn.skipped || (turn.weighted_score ?? 5) < 3.5,
  )
  const [recordingGone, setRecordingGone] = useState(false)
  const delivery = judgeDelivery(turn.delivery_metrics)

  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 p-4 text-left"
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium">
          {turn.turn_index}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm">{turn.question}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            {turn.interviewer_name && (
              <span className="font-medium text-foreground">{turn.interviewer_name}</span>
            )}
            <span>{turn.stage_label}</span>
            {turn.competency && <span>· {turn.competency}</span>}
            {turn.is_followup && <span>· 追问第 {turn.followup_depth} 层</span>}
            {turn.skipped && <Badge tone="warning">已跳过</Badge>}
            {turn.hinted && <Badge tone="outline">用过提示</Badge>}
            {turn.marked && (
              <Badge tone="primary">
                <Star className="h-3 w-3" aria-hidden />
                待复习
              </Badge>
            )}
            {turn.recording_key && <Badge tone="primary">有录像</Badge>}
            {turn.problems.length > 0 && <span>· {turn.problems.length} 个问题</span>}
          </span>
        </span>
        {turn.weighted_score != null && (
          <span className={cn('shrink-0 font-mono text-sm font-semibold', scoreTone(turn.weighted_score))}>
            {turn.weighted_score.toFixed(1)}
            <span className="text-xs font-normal text-muted-foreground">/5</span>
          </span>
        )}
        <ChevronDown
          className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')}
          aria-hidden
        />
      </button>

      {open && (
        <CardContent className="flex flex-col gap-4 border-t border-border pt-4">
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">你的回答</p>
            <p className="whitespace-pre-wrap rounded-md bg-secondary/40 p-3 text-sm leading-7">
              {turn.answer}
            </p>
          </div>

          {/* 本机录像回放 —— 视频面试最有价值的部分：看见自己的表现 */}
          {turn.recording_key && !recordingGone && (
            <AnswerPlayback
              recordingKey={turn.recording_key}
              label={`第 ${turn.turn_index} 题的录像`}
              onDeleted={() => setRecordingGone(true)}
            />
          )}

          {/* 客观表达指标 */}
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

          {Object.keys(turn.scores).length > 0 && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {Object.entries(turn.scores).map(([key, value]) => (
                <div key={key} className="rounded-md border border-border p-2 text-center">
                  <p className="text-[10px] text-muted-foreground">{DIMENSION_LABELS[key] ?? key}</p>
                  <p className={cn('font-mono text-sm font-semibold', scoreTone(value))}>
                    {value != null ? value.toFixed(1) : '—'}
                  </p>
                </div>
              ))}
            </div>
          )}

          {turn.evidence.length > 0 && (
            <div>
              <p className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
                <Quote className="h-3 w-3" aria-hidden />
                评分依据（引用你的原话）
              </p>
              <ul className="flex flex-col gap-1">
                {turn.evidence.map((e, i) => (
                  <li key={i} className="border-l-2 border-primary/30 pl-2 text-xs italic text-muted-foreground">
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {turn.strengths.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">做得好的地方</p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {turn.strengths.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          {turn.problems.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-xs font-medium text-muted-foreground">需要改进</p>
              {turn.problems.map((p, i) => (
                <div key={i} className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
                  <p className="font-medium">{p.issue}</p>
                  {p.why && <p className="mt-1 text-xs text-muted-foreground">后果：{p.why}</p>}
                  {p.fix && <p className="mt-1 text-xs text-muted-foreground">改法：{p.fix}</p>}
                </div>
              ))}
            </div>
          )}

          {/* 面试官下一步会往哪追 —— 比"这题答得不好"更可操作 */}
          {turn.risk_points?.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3">
              <p className="flex items-center gap-1 text-xs font-medium">
                <AlertTriangle className="h-3 w-3" aria-hidden />
                就凭这句话，面试官下一步会追这里
              </p>
              <ul className="mt-1 flex flex-col gap-0.5">
                {turn.risk_points.map((r, i) => (
                  <li key={i} className="text-xs text-muted-foreground">
                    · {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {turn.rewritten_answer && (
            <details className="rounded-md border border-primary/25 bg-primary/5 p-3">
              <summary className="cursor-pointer text-xs font-medium text-primary">
                查看这一段的高分改写
              </summary>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-7">{turn.rewritten_answer}</p>
            </details>
          )}

          {turn.problems.length === 0 && turn.strengths.length === 0 && (
            <>
              <Progress value={((turn.weighted_score ?? 0) / 5) * 100} />
              <p className="text-xs text-muted-foreground">本题未生成详细点评。</p>
            </>
          )}
        </CardContent>
      )}
    </Card>
  )
}

import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, MessageCircleQuestion, Target, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/client'
import { analyzeMatch, listJds, listResumes } from '../api/endpoints'
import type { MatchPublic } from '../api/types'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Alert, Badge, EmptyState, Skeleton } from '../components/ui/feedback'
import { Label } from '../components/ui/form'
import { useToast } from '../components/ui/toast'
import { cn } from '../lib/utils'

function scoreTone(score: number) {
  if (score >= 75) return { text: 'text-success', bar: 'bg-success', label: '匹配度较高' }
  if (score >= 55) return { text: 'text-primary', bar: 'bg-primary', label: '基本达标' }
  if (score >= 40) return { text: 'text-amber-600 dark:text-amber-400', bar: 'bg-amber-500', label: '偏弱，需要补强' }
  return { text: 'text-destructive', bar: 'bg-destructive', label: '匹配度较低' }
}

export function MatchPage() {
  const toast = useToast()
  const [resumeId, setResumeId] = useState('')
  const [jdId, setJdId] = useState('')

  const resumes = useQuery({ queryKey: ['resumes'], queryFn: listResumes })
  const jds = useQuery({ queryKey: ['jds'], queryFn: listJds })

  const run = useMutation({
    mutationFn: () => analyzeMatch(resumeId, jdId),
    onError: (err) => toast.error(err instanceof ApiError ? err.message : '分析失败'),
  })

  const loading = resumes.isLoading || jds.isLoading
  const hasResume = (resumes.data ?? []).length > 0
  const hasJd = (jds.data ?? []).length > 0

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">匹配分析</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          先看清"这份简历投这个岗位会被怎么看"，再去面试会更有底。结果会缓存，同一组合不重复调用模型。
        </p>
      </div>

      {(!hasResume || !hasJd) && !loading && (
        <Alert tone="warning" title="还缺材料">
          <div className="flex flex-col gap-1">
            {!hasResume && <span>· 还没有简历，请先去「简历」页上传</span>}
            {!hasJd && <span>· 还没有岗位 JD，请先去「岗位 JD」页添加</span>}
          </div>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>选择组合</CardTitle>
          <CardDescription>用哪份简历，投哪个岗位</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {loading ? (
            <Skeleton className="h-24" />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor="match-resume">简历</Label>
                <select
                  id="match-resume"
                  value={resumeId}
                  onChange={(e) => setResumeId(e.target.value)}
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="">请选择…</option>
                  {(resumes.data ?? []).map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.filename}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="match-jd">岗位 JD</Label>
                <select
                  id="match-jd"
                  value={jdId}
                  onChange={(e) => setJdId(e.target.value)}
                  className="h-10 rounded-md border border-border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="">请选择…</option>
                  {(jds.data ?? []).map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.title}
                      {j.company ? ` · ${j.company}` : ''}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          <div className="flex items-center gap-3">
            <Button
              onClick={() => run.mutate()}
              disabled={!resumeId || !jdId}
              loading={run.isPending}
            >
              <Target className="h-4 w-4" aria-hidden />
              {run.isPending ? '正在分析…' : '开始匹配分析'}
            </Button>
            {run.data?.cached && <Badge tone="outline">命中缓存</Badge>}
          </div>
        </CardContent>
      </Card>

      {run.isPending && (
        <Card>
          <CardContent className="flex flex-col gap-2 pt-5 text-sm text-muted-foreground">
            <p>正在读取岗位能力模型…</p>
            <p>正在比对简历中的技能与经历…</p>
            <p>正在预判面试官会问的问题…</p>
          </CardContent>
        </Card>
      )}

      {run.data && <MatchResult data={run.data} />}

      {!run.data && !run.isPending && hasResume && hasJd && (
        <EmptyState
          icon={<Target className="h-6 w-6" aria-hidden />}
          title="选择组合后开始分析"
          description="你会看到匹配度评分、优势项、风险项，以及面试官最可能问的 5 个问题。"
        />
      )}
    </div>
  )
}

function MatchResult({ data }: { data: MatchPublic }) {
  const tone = scoreTone(data.match_score)

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-4 pt-5 sm:flex-row sm:items-center sm:gap-6">
          <div className="flex items-center gap-4">
            <div
              className={cn(
                'flex h-24 w-24 shrink-0 flex-col items-center justify-center rounded-full border-4',
                data.match_score >= 55 ? 'border-primary/40' : 'border-amber-500/40',
              )}
            >
              <span className={cn('text-3xl font-bold tabular-nums', tone.text)}>
                {data.match_score}
              </span>
              <span className="text-[10px] text-muted-foreground">满分 100</span>
            </div>
            <div>
              <p className={cn('font-semibold', tone.text)}>{tone.label}</p>
              <p className="mt-1 max-w-xl text-sm leading-7 text-muted-foreground">{data.summary}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
              优势项
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2 text-sm">
              {data.strengths.map((s, i) => (
                <li key={i} className="flex gap-2 leading-7">
                  <span className="text-success">·</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <AlertTriangle className="h-4 w-4 text-amber-500" aria-hidden />
              风险项（面试官可能质疑的点）
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2 text-sm">
              {data.risks.map((s, i) => (
                <li key={i} className="flex gap-2 leading-7">
                  <span className="text-amber-500">·</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <MessageCircleQuestion className="h-4 w-4 text-primary" aria-hidden />
            面试官大概率会问的 {data.likely_questions.length} 个问题
          </CardTitle>
          <CardDescription>先自己口述一遍，再进模拟面试验证</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col gap-2 text-sm">
            {data.likely_questions.map((q, i) => (
              <li key={i} className="flex gap-3 leading-7">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium">
                  {i + 1}
                </span>
                <span>{q}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-3 pt-5">
          <TrendingUp className="h-4 w-4 text-primary" aria-hidden />
          <span className="text-sm">准备好接受真实追问了吗？</span>
          <Link to="/interview/setup" className="ml-auto">
            <Button>开始模拟面试</Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  )
}

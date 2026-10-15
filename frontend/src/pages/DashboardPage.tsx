import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  BarChart3,
  Briefcase,
  FileText,
  Info,
  PlayCircle,
  Target,
  Video,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { getHealth, getOverview, listInterviews } from '../api/endpoints'
import { Badge, EmptyState, Progress, Skeleton } from '../components/ui/feedback'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { STATUS_LABELS } from '../lib/constants'
import { useAuthStore } from '../stores/auth'

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string
  value: string | number
  hint?: string
  icon: React.ComponentType<{ className?: string }>
}) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3 pt-5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/12 text-primary">
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-xl font-semibold tabular-nums">{value}</p>
          {hint && <p className="truncate text-xs text-muted-foreground">{hint}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

export function DashboardPage() {
  const user = useAuthStore((s) => s.user)

  const health = useQuery({ queryKey: ['health'], queryFn: getHealth, staleTime: 60_000 })
  const overview = useQuery({ queryKey: ['overview'], queryFn: getOverview })
  const interviews = useQuery({ queryKey: ['interviews'], queryFn: listInterviews })

  const recent = (interviews.data ?? []).slice(0, 5)
  const data = overview.data

  const steps = [
    {
      to: '/resume',
      done: (data?.resume_count ?? 0) > 0,
      label: '上传简历',
      desc: '解析出技能与项目亮点',
      icon: FileText,
    },
    {
      to: '/jd',
      done: (data?.jd_count ?? 0) > 0,
      label: '粘贴岗位 JD',
      desc: '生成岗位能力模型',
      icon: Briefcase,
    },
    {
      to: '/match',
      done: (data?.match_count ?? 0) > 0,
      label: '做一次匹配分析',
      desc: '看看会被问哪些问题',
      icon: Target,
    },
    {
      to: '/interview/setup',
      done: (data?.interview_count ?? 0) > 0,
      label: '开始视频面试',
      desc: '六位面试官，会追问，全程不显示分数',
      icon: PlayCircle,
    },
  ]

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">
            你好{user?.nickname ? `，${user.nickname}` : ''}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            秋招面试机会有限，先用这里把该踩的坑踩完。
          </p>
        </div>
        <Link to="/interview/setup">
          <Button>
            <PlayCircle className="h-4 w-4" aria-hidden />
            开始新的视频面试
          </Button>
        </Link>
      </div>

      {health.data?.llm_mode === 'mock' && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden />
          <div>
            <p className="font-medium">当前为演示模式（内置 Mock 面试官）</p>
            <p className="text-muted-foreground">
              后端未配置 <code className="rounded bg-secondary px-1">LLM_API_KEY</code>
              ，所有流程都能跑通，但分数由规则引擎给出，不代表真实模型效果。
              在 <code className="rounded bg-secondary px-1">backend/.env</code> 填入 Key 后重启即可切换。
            </p>
          </div>
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {overview.isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[86px]" />)
        ) : (
          <>
            <StatCard label="已完成面试" value={data?.finished_count ?? 0} icon={BarChart3} />
            <StatCard
              label="平均总分"
              value={data?.avg_score != null ? `${data.avg_score}` : '—'}
              hint={data?.best_score != null ? `最高 ${data.best_score} 分` : '完成一场后显示'}
              icon={Target}
            />
            <StatCard label="简历数量" value={data?.resume_count ?? 0} icon={FileText} />
            <StatCard label="岗位 JD" value={data?.jd_count ?? 0} icon={Briefcase} />
          </>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">四步跑通一次完整练习</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map(({ to, done, label, desc, icon: Icon }) => (
            <Link key={to} to={to} className="group">
              <Card className="h-full transition-colors group-hover:border-primary/50">
                <CardContent className="flex flex-col gap-2 pt-5">
                  <div className="flex items-center justify-between">
                    <span className="flex h-8 w-8 items-center justify-center rounded-md bg-secondary text-foreground">
                      <Icon className="h-4 w-4" aria-hidden />
                    </span>
                    {done ? (
                      <Badge tone="success">已完成</Badge>
                    ) : (
                      <ArrowRight className="h-4 w-4 text-muted-foreground" aria-hidden />
                    )}
                  </div>
                  <p className="font-medium">{label}</p>
                  <p className="text-xs text-muted-foreground">{desc}</p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">最近的面试</h2>
          {recent.length > 0 && (
            <Link to="/history" className="text-sm text-primary underline-offset-4 hover:underline">
              查看全部
            </Link>
          )}
        </div>

        {interviews.isLoading ? (
          <Skeleton className="h-40" />
        ) : recent.length === 0 ? (
          <EmptyState
            icon={<PlayCircle className="h-6 w-6" aria-hidden />}
            title="还没有面试记录"
            description="先上传一份简历，30 秒就能开始第一场模拟面试。"
            action={
              <Link to="/resume">
                <Button variant="outline">上传简历</Button>
              </Link>
            }
          />
        ) : (
          <div className="flex flex-col gap-2">
            {recent.map((item) => (
                <Card key={item.id}>
                  <CardContent className="flex flex-wrap items-center gap-3 pt-5">
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 truncate font-medium">
                        {item.config?.mode === 'video' && (
                          <Video className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
                        )}
                        <span className="truncate">{item.jd_title ?? '未指定岗位'}</span>
                        <span className="shrink-0 text-xs font-normal text-muted-foreground">
                          {item.resume_filename}
                        </span>
                      </p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                        <span>
                          {item.created_at
                            ? new Date(item.created_at).toLocaleString('zh-CN')
                            : '—'}
                        </span>
                        <span>已答 {item.turn_count} 题</span>
                        {item.config?.feedback_mode === 'practice' && <span>练习模式</span>}
                        <span>
                          {item.config?.interviewer_mode === 'single' ? '单人面试' : '多轮换人'}
                        </span>
                        {item.current_interviewer && (
                          <span>
                            {item.current_interviewer.emoji} {item.current_interviewer.name}
                          </span>
                        )}
                        {Boolean(
                          (item.delivery_summary as { is_voice?: boolean } | undefined)?.is_voice,
                        ) && <span>有语音指标</span>}
                      </p>
                    </div>

                    <Badge tone={item.status === 'finished' ? 'success' : 'outline'}>
                      {STATUS_LABELS[item.status] ?? item.status}
                    </Badge>

                    {item.total_score != null && (
                      <div className="w-24">
                        <div className="mb-1 flex items-baseline justify-between">
                          <span className="text-xs text-muted-foreground">总分</span>
                          <span className="text-sm font-semibold tabular-nums">
                            {item.total_score.toFixed(0)}
                          </span>
                        </div>
                        <Progress
                          value={item.total_score}
                          tone={
                            item.total_score >= 75
                              ? 'success'
                              : item.total_score >= 50
                                ? 'primary'
                                : 'destructive'
                          }
                        />
                      </div>
                    )}

                    {item.status === 'finished' ? (
                      <Link to={`/interview/${item.id}/report`}>
                        <Button size="sm" variant="outline">
                          查看报告
                        </Button>
                      </Link>
                    ) : item.status === 'aborted' ? (
                      <Badge tone="outline">已放弃</Badge>
                    ) : (
                      <Link to={`/interview/${item.id}`}>
                        <Button size="sm">继续面试</Button>
                      </Link>
                    )}
                  </CardContent>
                </Card>
              ))}
          </div>
        )}
      </section>

      {data && Object.keys(data.dimension_avg).length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">你的五维平均分</h2>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">历史累计</CardTitle>
              <CardDescription>基于所有已完成评分的面试</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-5">
              {Object.entries(data.dimension_avg).map(([name, value]) => (
                <div key={name} className="flex flex-col gap-1">
                  <span className="text-xs text-muted-foreground">{name}</span>
                  <span className="text-lg font-semibold tabular-nums">{value.toFixed(0)}</span>
                  <Progress value={value} />
                </div>
              ))}
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  )
}

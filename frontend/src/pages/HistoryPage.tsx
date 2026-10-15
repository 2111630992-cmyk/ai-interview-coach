import { useQuery } from '@tanstack/react-query'
import { BarChart3, Filter, PlayCircle, Video } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { getTrend, listInterviews } from '../api/endpoints'
import { ScoreTrend } from '../components/charts/Charts'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Badge, EmptyState, Progress, Skeleton } from '../components/ui/feedback'
import { Tabs } from '../components/ui/tabs'
import { INTERVIEW_TYPES, STATUS_LABELS } from '../lib/constants'
import { isVoiceSummary, voiceSummaryNumber } from '../lib/deliveryMetrics'

type FilterValue = 'all' | 'finished' | 'running' | 'aborted'

export function HistoryPage() {
  const [filter, setFilter] = useState<FilterValue>('all')

  const interviews = useQuery({ queryKey: ['interviews'], queryFn: listInterviews })
  const trend = useQuery({ queryKey: ['trend'], queryFn: () => getTrend(20) })

  const all = interviews.data ?? []

  const counts = useMemo(
    () => ({
      all: all.length,
      finished: all.filter((i) => i.status === 'finished').length,
      running: all.filter((i) => i.status === 'created' || i.status === 'running').length,
      aborted: all.filter((i) => i.status === 'aborted').length,
    }),
    [all],
  )

  const filtered = useMemo(() => {
    if (filter === 'all') return all
    if (filter === 'running') return all.filter((i) => i.status === 'created' || i.status === 'running')
    return all.filter((i) => i.status === filter)
  }, [all, filter])

  const finished = all.filter((i) => i.total_score != null)
  const best = finished.length ? Math.max(...finished.map((i) => i.total_score as number)) : null
  const avg = finished.length
    ? finished.reduce((sum, i) => sum + (i.total_score ?? 0), 0) / finished.length
    : null

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">历史与趋势</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            看自己的进步曲线，比看单场分数更有意义。
          </p>
        </div>
        <Link to="/interview/setup">
          <Button>
            <PlayCircle className="h-4 w-4" aria-hidden />
            开始新面试
          </Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BarChart3 className="h-4 w-4 text-primary" aria-hidden />
            总分趋势
          </CardTitle>
          <CardDescription>
            {finished.length > 0
              ? `共 ${finished.length} 场有评分的面试 · 平均 ${avg?.toFixed(0)} 分 · 最高 ${best?.toFixed(0)} 分`
              : '完成面试并生成报告后会显示'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {trend.isLoading ? <Skeleton className="h-[260px]" /> : <ScoreTrend points={trend.data ?? []} />}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <Tabs
          items={[
            { value: 'all', label: '全部', count: counts.all },
            { value: 'finished', label: '已完成', count: counts.finished },
            { value: 'running', label: '进行中', count: counts.running },
            { value: 'aborted', label: '已放弃', count: counts.aborted },
          ]}
          value={filter}
          onChange={(v) => setFilter(v as FilterValue)}
        />
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Filter className="h-3 w-3" aria-hidden />
          {filtered.length} 条记录
        </span>
      </div>

      {interviews.isLoading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<PlayCircle className="h-6 w-6" aria-hidden />}
          title={all.length === 0 ? '还没有面试记录' : '没有符合条件的记录'}
          description={
            all.length === 0
              ? '先上传简历并添加一个目标岗位，就能开始第一场模拟面试。'
              : '换个筛选条件看看。'
          }
          action={
            all.length === 0 ? (
              <Link to="/interview/setup">
                <Button>开始模拟面试</Button>
              </Link>
            ) : undefined
          }
        />
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((item) => (
            <Card key={item.id}>
              <CardContent className="flex flex-wrap items-center gap-4 pt-5">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 truncate font-medium">
                    {item.config?.mode === 'video' && (
                      <Video className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
                    )}
                    <span className="truncate">{item.jd_title ?? '未指定岗位'}</span>
                    <span className="shrink-0 text-xs font-normal text-muted-foreground">
                      {INTERVIEW_TYPES.find((t) => t.value === item.config?.interview_type)?.label ??
                        item.config?.interview_type}
                      {' · '}
                      {item.config?.duration_min ?? '—'} 分钟
                    </span>
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                    <span>
                      {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '—'}
                    </span>
                    <span>{item.resume_filename || '简历已删除'}</span>
                    <span>已答 {item.turn_count} 题</span>
                    {item.config?.feedback_mode === 'practice' ? (
                      <span>练习模式</span>
                    ) : (
                      <span>模拟模式</span>
                    )}
                    {item.current_interviewer && <span>{item.current_interviewer.name}</span>}
                    {item.total_score != null && isVoiceSummary(item.delivery_summary) && (
                      <span>
                        语速{' '}
                        {Math.round(voiceSummaryNumber(item.delivery_summary, 'avg_speech_rate'))} 字/分
                      </span>
                    )}
                  </p>
                </div>

                <Badge
                  tone={
                    item.status === 'finished'
                      ? 'success'
                      : item.status === 'aborted'
                        ? 'outline'
                        : 'primary'
                  }
                >
                  {STATUS_LABELS[item.status] ?? item.status}
                </Badge>

                {item.total_score != null ? (
                  <div className="w-28">
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
                ) : (
                  <span className="w-28 text-right text-xs text-muted-foreground">未评分</span>
                )}

                {item.status === 'finished' ? (
                  <Link to={`/interview/${item.id}/report`}>
                    <Button size="sm" variant="outline">
                      查看报告
                    </Button>
                  </Link>
                ) : item.status === 'aborted' ? (
                  <Link to="/interview/setup">
                    <Button size="sm" variant="ghost">
                      再来一场
                    </Button>
                  </Link>
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
    </div>
  )
}

import {
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { DIMENSION_HINTS, DIMENSION_LABELS, DIMENSION_ORDER } from '../../lib/constants'
import type { TrendPoint } from '../../api/types'
import { cn } from '../../lib/utils'
import { EmptyState } from '../ui/feedback'

function toneFor(score: number): { text: string; bar: string } {
  if (score >= 75) return { text: 'text-success', bar: 'bg-success' }
  if (score >= 55) return { text: 'text-primary', bar: 'bg-primary' }
  if (score >= 40) return { text: 'text-amber-600 dark:text-amber-400', bar: 'bg-amber-500' }
  return { text: 'text-destructive', bar: 'bg-destructive' }
}

/** 五维雷达图 + 数值条。
 *  只用雷达图不够 —— 色觉障碍用户和打印场景都需要文字数值，所以两者并列。 */
export function DimensionRadar({ scores }: { scores: Record<string, number> }) {
  const data = DIMENSION_ORDER.map((key) => ({
    dimension: DIMENSION_LABELS[key],
    key,
    score: Number(scores[key] ?? 0),
  }))

  if (data.every((d) => d.score === 0)) {
    return <EmptyState title="暂无维度数据" description="完成一场面试后这里会显示五维评分。" />
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid stroke="hsl(var(--border))" />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }}
            />
            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
            <Radar
              name="得分"
              dataKey="score"
              stroke="hsl(var(--primary))"
              fill="hsl(var(--primary))"
              fillOpacity={0.28}
            />
            <Tooltip
              formatter={(v: number) => [`${v} 分`, '得分']}
              contentStyle={{
                background: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: 8,
                fontSize: 12,
                color: 'hsl(var(--foreground))',
              }}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-col justify-center gap-3">
        {data.map((d) => {
          const tone = toneFor(d.score)
          return (
            <div key={d.key} className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-medium">
                  {d.dimension}
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    {DIMENSION_HINTS[d.key]}
                  </span>
                </span>
                <span className={cn('font-mono text-sm font-semibold tabular-nums', tone.text)}>
                  {d.score.toFixed(0)}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                <div
                  className={cn('h-full rounded-full transition-all duration-700', tone.bar)}
                  style={{ width: `${Math.min(100, d.score)}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** 多次面试的分数趋势。 */
export function ScoreTrend({ points }: { points: TrendPoint[] }) {
  if (points.length === 0) {
    return (
      <EmptyState
        title="还没有已完成评分的面试"
        description="完成一场面试并生成报告后，这里会出现你的进步曲线。"
      />
    )
  }

  const data = points.map((p, i) => ({
    name: p.jd_title ? p.jd_title.slice(0, 8) : `第 ${i + 1} 场`,
    score: p.total_score ?? 0,
    date: p.date ? new Date(p.date).toLocaleDateString('zh-CN') : '',
  }))

  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: -12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis
            dataKey="name"
            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
            stroke="hsl(var(--border))"
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
            stroke="hsl(var(--border))"
          />
          <Tooltip
            formatter={(v: number) => [`${v} 分`, '总分']}
            labelFormatter={(label: string, payload) => {
              const item = payload?.[0]?.payload as { date?: string } | undefined
              return item?.date ? `${label} · ${item.date}` : label
            }}
            contentStyle={{
              background: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: 8,
              fontSize: 12,
              color: 'hsl(var(--foreground))',
            }}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={{ r: 4, fill: 'hsl(var(--primary))' }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

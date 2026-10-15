import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Briefcase, Info, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { ApiError } from '../api/client'
import { createJd, deleteJd, listJds } from '../api/endpoints'
import type { JDPublic } from '../api/types'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Alert, Badge, EmptyState, Progress, Skeleton } from '../components/ui/feedback'
import { Field, Input, Textarea } from '../components/ui/form'
import { useToast } from '../components/ui/toast'

const SAMPLE = `岗位职责：
1. 负责后端服务的设计与开发，参与高并发交易系统的架构优化；
2. 与产品、前端协作，推动需求按时高质量交付。

任职要求：
1. 熟练掌握 Java、Spring Boot，熟悉 MySQL 索引优化与事务机制；
2. 熟悉 Redis 缓存、Kafka 消息队列，了解分布式与微服务架构；
3. 有良好的沟通表达与团队协作能力，具备 owner 意识。`

export function JdPage() {
  const qc = useQueryClient()
  const toast = useToast()

  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [rawText, setRawText] = useState('')

  const jds = useQuery({ queryKey: ['jds'], queryFn: listJds })

  const create = useMutation({
    mutationFn: () =>
      createJd({ title: title.trim(), company: company.trim() || undefined, raw_text: rawText.trim() }),
    onSuccess: (data) => {
      toast.success(`已提取 ${data.competency_model.hard_skills?.length ?? 0} 项硬技能要求`)
      setTitle('')
      setCompany('')
      setRawText('')
      void qc.invalidateQueries({ queryKey: ['jds'] })
      void qc.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : '创建失败'),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteJd(id),
    onSuccess: () => {
      toast.success('已删除')
      void qc.invalidateQueries({ queryKey: ['jds'] })
      void qc.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : '删除失败'),
  })

  const tooShort = rawText.trim().length > 0 && rawText.trim().length < 20
  const canSubmit = title.trim().length > 0 && rawText.trim().length >= 20

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">岗位 JD</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          粘贴真实岗位描述。系统会抽出这个岗位真正要考的能力点与权重 —— 面试问题由此生成，而不是随机题库。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>新增岗位</CardTitle>
          <CardDescription>JD 越完整，提取出的能力模型越准</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="岗位名称">
              {(id) => (
                <Input
                  id={id}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="后端开发工程师"
                  maxLength={200}
                />
              )}
            </Field>
            <Field label="公司（可选）">
              {(id) => (
                <Input
                  id={id}
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="某某科技"
                  maxLength={200}
                />
              )}
            </Field>
          </div>

          <Field
            label="JD 原文"
            error={tooShort ? 'JD 太短了，至少 20 个字才能提取出有效的能力模型' : null}
            hint={
              rawText.length === 0
                ? '从招聘网站复制岗位描述粘贴到这里'
                : `${rawText.trim().length} 字`
            }
          >
            {(id) => (
              <Textarea
                id={id}
                rows={10}
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                placeholder={SAMPLE}
                maxLength={20000}
              />
            )}
          </Field>

          <div className="flex flex-wrap gap-2">
            <Button onClick={() => create.mutate()} disabled={!canSubmit} loading={create.isPending}>
              <Plus className="h-4 w-4" aria-hidden />
              提取能力模型
            </Button>
            <Button variant="ghost" onClick={() => setRawText(SAMPLE)}>
              填入示例 JD
            </Button>
          </div>
        </CardContent>
      </Card>

      {jds.isLoading ? (
        <Skeleton className="h-40" />
      ) : (jds.data ?? []).length === 0 ? (
        <EmptyState
          icon={<Briefcase className="h-6 w-6" aria-hidden />}
          title="还没有岗位 JD"
          description="至少添加一个目标岗位，才能做匹配分析并开始模拟面试。"
        />
      ) : (
        <div className="flex flex-col gap-3">
          {(jds.data ?? []).map((jd) => (
            <JdCard
              key={jd.id}
              jd={jd}
              onDelete={() => {
                if (window.confirm('确定删除这个岗位？')) remove.mutate(jd.id)
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function JdCard({ jd, onDelete }: { jd: JDPublic; onDelete: () => void }) {
  const model = jd.competency_model ?? {}
  const hard = model.hard_skills ?? []
  const soft = model.soft_skills ?? []
  const domains = model.domains ?? []
  const weights = model.weights ?? {}
  const top = [...hard].sort((a, b) => (weights[b] ?? 0) - (weights[a] ?? 0)).slice(0, 6)

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate">
              {jd.title}
              {jd.company && <span className="ml-2 text-sm font-normal text-muted-foreground">{jd.company}</span>}
            </CardTitle>
            <CardDescription>
              {jd.created_at ? new Date(jd.created_at).toLocaleString('zh-CN') : '—'} · 原文{' '}
              {jd.raw_text_length} 字
            </CardDescription>
          </div>
          <Button size="sm" variant="ghost" onClick={onDelete} aria-label="删除岗位">
            <Trash2 className="h-3.5 w-3.5 text-destructive" aria-hidden />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {model.summary && (
          <Alert tone="info">
            <span className="flex items-start gap-2">
              <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {model.summary}
            </span>
          </Alert>
        )}

        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">考察权重（按 JD 强调程度）</p>
          <div className="flex flex-col gap-2">
            {top.map((skill) => {
              const w = Math.round((weights[skill] ?? 0) * 100)
              return (
                <div key={skill} className="flex items-center gap-3">
                  <span className="w-32 shrink-0 truncate text-sm">{skill}</span>
                  <Progress value={w} className="h-1.5 flex-1" />
                  <span className="w-10 shrink-0 text-right font-mono text-xs text-muted-foreground">
                    {w}%
                  </span>
                </div>
              )
            })}
            {top.length === 0 && <p className="text-xs text-muted-foreground">未提取到硬技能</p>}
          </div>
        </div>

        {soft.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">软素质要求</p>
            <div className="flex flex-wrap gap-1.5">
              {soft.map((s) => (
                <Badge key={s} tone="outline">
                  {s}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {domains.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">业务/技术领域</p>
            <div className="flex flex-wrap gap-1.5">
              {domains.map((d) => (
                <Badge key={d} tone="primary">
                  {d}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

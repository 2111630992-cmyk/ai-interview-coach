import { useMutation, useQuery } from '@tanstack/react-query'
import { Info, Lightbulb, MonitorPlay, PlayCircle, ShieldCheck, Video } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { createInterview, listInterviewers, listJds, listResumes } from '../api/endpoints'
import type { InterviewConfig, InterviewerPublic } from '../api/types'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Alert, Badge, Skeleton } from '../components/ui/feedback'
import { Label, Switch } from '../components/ui/form'
import { OptionGroup } from '../components/ui/option-group'
import { useToast } from '../components/ui/toast'
import {
  accent,
  DIFFICULTIES,
  DURATIONS,
  FEEDBACK_MODES,
  INTERVIEW_TYPES,
  LANGUAGES,
  STAGE_LABELS,
  STAGE_ORDER,
} from '../lib/constants'
import { cn } from '../lib/utils'

const STAGE_WEIGHTS: Record<string, number> = {
  intro: 8,
  resume_deep_dive: 27,
  hard_skill: 30,
  behavioral: 15,
  pressure: 12,
  candidate_ask: 8,
}

const DEFAULT_CONFIG: InterviewConfig = {
  interview_type: 'comprehensive',
  duration_min: 30,
  difficulty: 'campus',
  language: 'zh',
  pressure_mode: true,
  feedback_mode: 'simulation',
  realtime_feedback: false,
  voice_enabled: true,
  mode: 'video',
  interviewer_mode: 'panel',
  interviewer_type: 'technical',
  allow_hint: true,
  allow_skip: true,
  require_camera: true,
}

export function InterviewSetupPage() {
  const toast = useToast()
  const navigate = useNavigate()

  const [resumeId, setResumeId] = useState('')
  const [jdId, setJdId] = useState('')
  const [config, setConfig] = useState<InterviewConfig>(DEFAULT_CONFIG)

  const resumes = useQuery({ queryKey: ['resumes'], queryFn: listResumes })
  const jds = useQuery({ queryKey: ['jds'], queryFn: listJds })
  const interviewers = useQuery({
    queryKey: ['interviewers', config.language],
    queryFn: () => listInterviewers(config.language),
    staleTime: 5 * 60_000,
  })

  const create = useMutation({
    mutationFn: () =>
      createInterview({
        resume_id: resumeId,
        jd_id: jdId || null,
        config,
      }),
    onSuccess: (data) => {
      toast.success('面试计划已生成')
      navigate(`/interview/${data.id}`, { replace: true })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : '创建面试失败'),
  })

  const loading = resumes.isLoading || jds.isLoading
  const noResume = !loading && (resumes.data ?? []).length === 0
  const isVideo = config.mode === 'video'

  const update = <K extends keyof InterviewConfig>(key: K, value: InterviewConfig[K]) =>
    setConfig((prev) => ({ ...prev, [key]: value }))

  /** 多轮模式下的实际分配预览，让用户知道会遇到几位面试官。 */
  const panelPreview = useMemo(() => {
    const list = interviewers.data ?? []
    if (list.length === 0) return []
    if (config.interviewer_mode === 'single') {
      const one = list.find((p) => p.type === config.interviewer_type) ?? list[0]
      return STAGE_ORDER.map((stage) => ({ stage, persona: one }))
    }
    const byType = new Map(list.map((p) => [p.type, p]))
    const stageMap: Record<string, string> = {
      intro: 'hr',
      resume_deep_dive: 'project',
      hard_skill: 'technical',
      behavioral: 'behavioral',
      pressure: 'stress',
      candidate_ask: 'hr',
    }
    return STAGE_ORDER.map((stage) => ({
      stage,
      persona: byType.get(stageMap[stage]) ?? list[0],
    }))
  }, [config.interviewer_mode, config.interviewer_type, interviewers.data])

  const distinctInterviewers = new Set(panelPreview.map((p) => p.persona?.type)).size

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">配置面试</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          系统会先根据你的简历和岗位 JD 生成一份面试计划（六个环节 + 具体考察点），然后才开始提问。
        </p>
      </div>

      {noResume && (
        <Alert tone="warning" title="还没有简历">
          模拟面试必须基于你的真实简历，否则无法深挖项目经历。请先上传简历。
        </Alert>
      )}

      {/* ---------- 面试形态 ---------- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Video className="h-4 w-4 text-primary" aria-hidden />
            面试形态
          </CardTitle>
          <CardDescription>
            视频面试会用摄像头和麦克风，并实测你的语速、口头禅与停顿
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => update('mode', 'video')}
              className={cn(
                'flex flex-col gap-1.5 rounded-lg border p-4 text-left transition-colors',
                isVideo ? 'border-primary bg-primary/5 ring-1 ring-primary/30' : 'border-border hover:border-primary/40',
              )}
              aria-pressed={isVideo}
            >
              <span className="flex items-center gap-2 font-medium">
                <MonitorPlay className="h-4 w-4" aria-hidden />
                视频面试
                <Badge tone="primary">推荐</Badge>
              </span>
              <span className="text-xs text-muted-foreground">
                摄像头 + 麦克风 + 实时字幕。面试官会语音提问，你说的每句话被转写成文字后评分。
                录像只存在你本机，可以回看自己的表现。
              </span>
            </button>

            <button
              type="button"
              onClick={() => update('mode', 'text')}
              className={cn(
                'flex flex-col gap-1.5 rounded-lg border p-4 text-left transition-colors',
                !isVideo ? 'border-primary bg-primary/5 ring-1 ring-primary/30' : 'border-border hover:border-primary/40',
              )}
              aria-pressed={!isVideo}
            >
              <span className="font-medium">文字面试</span>
              <span className="text-xs text-muted-foreground">
                纯打字作答。适合没有摄像头、或在图书馆等不方便说话的场景。
                练习不到表达节奏，但结构与内容同样能被评估。
              </span>
            </button>
          </div>

          {isVideo && (
            <div className="grid gap-3 md:grid-cols-2">
              <Switch
                checked={config.require_camera}
                onCheckedChange={(v) => update('require_camera', v)}
                label="要求开启摄像头"
                description="关闭后只录音，仍可练习语音表达（不想露脸时用）"
              />
              <Switch
                checked={config.voice_enabled}
                onCheckedChange={(v) => update('voice_enabled', v)}
                label="面试官语音播报"
                description="用 TTS 把问题读出来，更接近真实视频面试"
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---------- 面试官 ---------- */}
      <Card>
        <CardHeader>
          <CardTitle>面试官</CardTitle>
          <CardDescription>
            真实校招是多轮制的 —— HR 关心动机，技术专家关心原理，主管关心你的真实贡献
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <OptionGroup
            label="面试官模式"
            columns={2}
            items={[
              {
                value: 'panel',
                label: '多轮换人（推荐）',
                desc: `六个环节由 ${distinctInterviewers || 5} 位不同面试官负责，模拟完整校招流程`,
              },
              {
                value: 'single',
                label: '单人整场',
                desc: '一位面试官从头问到尾，风格统一',
              },
            ]}
            value={config.interviewer_mode}
            onChange={(v) => update('interviewer_mode', v)}
          />

          {config.interviewer_mode === 'single' && (
            <div>
              <p className="mb-2 text-sm font-medium">选择面试官</p>
              {interviewers.isLoading ? (
                <Skeleton className="h-24" />
              ) : (
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {(interviewers.data ?? []).map((p) => (
                    <PersonaCard
                      key={p.type}
                      persona={p}
                      selected={config.interviewer_type === p.type}
                      onSelect={() => update('interviewer_type', p.type)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 分配预览 */}
          {panelPreview.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium">
                {config.interviewer_mode === 'panel' ? '这场面试的面试官安排' : '整场面试官'}
              </p>
              <ol className="flex flex-col gap-1.5">
                {panelPreview.map(({ stage, persona }) => (
                  <li key={stage} className="flex items-center gap-3 text-sm">
                    <span className="w-28 shrink-0 text-xs text-muted-foreground">
                      {STAGE_LABELS[stage]}
                    </span>
                    {persona && (
                      <>
                        <span
                          className={cn(
                            'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs',
                            accent(persona.accent).bg,
                          )}
                          aria-hidden
                        >
                          {persona.emoji}
                        </span>
                        <span className="font-medium">{persona.name}</span>
                        <span className="truncate text-xs text-muted-foreground">
                          {persona.title}
                        </span>
                      </>
                    )}
                    <span className="ml-auto w-10 shrink-0 text-right font-mono text-xs text-muted-foreground">
                      {STAGE_WEIGHTS[stage]}%
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---------- 材料 ---------- */}
      {loading ? (
        <Skeleton className="h-40" />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>选择材料</CardTitle>
            <CardDescription>考察点由简历经历与岗位要求共同决定</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="setup-resume">简历（必选）</Label>
              <select
                id="setup-resume"
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
              <Label htmlFor="setup-jd">岗位 JD（建议选，不选则按通用岗位设计）</Label>
              <select
                id="setup-jd"
                value={jdId}
                onChange={(e) => setJdId(e.target.value)}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="">不指定岗位</option>
                {(jds.data ?? []).map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.title}
                    {j.company ? ` · ${j.company}` : ''}
                  </option>
                ))}
              </select>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ---------- 强度与反馈 ---------- */}
      <Card>
        <CardHeader>
          <CardTitle>强度与反馈</CardTitle>
          <CardDescription>反馈模式决定了面试中你能不能看到分数</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <OptionGroup
            label="反馈模式"
            columns={2}
            items={[
              {
                value: 'simulation',
                label: FEEDBACK_MODES.simulation,
                desc: '像真实面试：全程不知道分数，结束后一次性看报告',
              },
              {
                value: 'practice',
                label: FEEDBACK_MODES.practice,
                desc: '像刻意练习：每答完一题立刻看到五维评分与改写示范',
              },
            ]}
            value={config.feedback_mode}
            onChange={(v) => update('feedback_mode', v as InterviewConfig['feedback_mode'])}
          />

          <OptionGroup
            label="面试类型"
            items={INTERVIEW_TYPES.map((t) => ({ value: t.value, label: t.label, desc: t.desc }))}
            value={config.interview_type}
            onChange={(v) => update('interview_type', v)}
          />

          <OptionGroup
            label="时长"
            items={DURATIONS.map((d) => ({ value: d.value, label: d.label, desc: d.desc }))}
            value={config.duration_min}
            onChange={(v) => update('duration_min', v)}
          />

          <div className="grid gap-5 md:grid-cols-2">
            <OptionGroup
              label="难度定位"
              columns={3}
              items={DIFFICULTIES.map((d) => ({ value: d.value, label: d.label, desc: d.desc }))}
              value={config.difficulty}
              onChange={(v) => update('difficulty', v)}
            />
            <OptionGroup
              label="面试语言"
              columns={2}
              items={LANGUAGES.map((l) => ({ value: l.value, label: l.label }))}
              value={config.language}
              onChange={(v) => update('language', v)}
            />
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <Switch
              checked={config.pressure_mode}
              onCheckedChange={(v) => update('pressure_mode', v)}
              label="压力追问"
              description="对你夸大的数据进行温和质疑"
            />
            <Switch
              checked={config.allow_hint}
              onCheckedChange={(v) => update('allow_hint', v)}
              label="允许请求提示"
              description="只给回答结构，不给答案；用过会记进报告"
            />
            <Switch
              checked={config.allow_skip}
              onCheckedChange={(v) => update('allow_skip', v)}
              label="允许跳过难题"
              description="记 0 分但不中断面试，避免一题卡死整场"
            />
          </div>
        </CardContent>
      </Card>

      {/* ---------- 环节权重 ---------- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">六个环节与权重</CardTitle>
          <CardDescription>权重固定，考察点由你的简历与岗位动态生成</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col gap-2">
            {STAGE_ORDER.map((stage) => (
              <li key={stage} className="flex items-center gap-3 text-sm">
                <span className="w-32 shrink-0">{STAGE_LABELS[stage]}</span>
                <span className="block h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                  <span
                    className="block h-full rounded-full bg-primary/70"
                    style={{ width: `${STAGE_WEIGHTS[stage]}%` }}
                  />
                </span>
                <span className="w-10 shrink-0 text-right font-mono text-xs text-muted-foreground">
                  {STAGE_WEIGHTS[stage]}%
                </span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Alert tone="info">
        <span className="flex items-start gap-2">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>
            面试官不会询问年龄、性别、婚育、籍贯等私人信息；评分维度不含形象与口音；
            改写示范只基于你真实说过的内容。
            {isVideo && ' 摄像头与麦克风数据只在你本机处理，录像不上传服务器。'}
          </span>
        </span>
      </Alert>

      <div className="flex flex-wrap items-center gap-3">
        <Button size="lg" onClick={() => create.mutate()} disabled={!resumeId} loading={create.isPending}>
          {isVideo ? <Video className="h-4 w-4" aria-hidden /> : <PlayCircle className="h-4 w-4" aria-hidden />}
          {create.isPending ? '正在生成面试计划…' : isVideo ? '生成计划并检测设备' : '生成计划并开始'}
        </Button>
        {create.isPending && (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <Info className="h-4 w-4" aria-hidden />
            正在分析 JD 能力模型 → 匹配简历亮点 → 设计考察点…
          </span>
        )}
      </div>
    </div>
  )
}

function PersonaCard({
  persona,
  selected,
  onSelect,
}: {
  persona: InterviewerPublic
  selected: boolean
  onSelect: () => void
}) {
  const tone = accent(persona.accent)
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'flex flex-col gap-2 rounded-lg border p-3 text-left transition-colors',
        selected ? cn('border-transparent ring-2', tone.ring, tone.bg) : 'border-border hover:border-primary/40',
      )}
    >
      <span className="flex items-center gap-2">
        <span className={cn('flex h-8 w-8 items-center justify-center rounded-full text-lg', 'bg-background/80')}>
          {persona.emoji}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{persona.name}</span>
          <span className="block truncate text-xs text-muted-foreground">{persona.title}</span>
        </span>
      </span>
      <span className={cn('rounded-md p-2 text-[11px] leading-5 text-muted-foreground', tone.bg)}>
        <Lightbulb className="mr-1 inline h-3 w-3" aria-hidden />
        {persona.style}
      </span>
      <span className="flex flex-wrap gap-1">
        {persona.focus_areas.slice(0, 3).map((f) => (
          <span key={f} className={cn('rounded-full border px-1.5 py-0.5 text-[10px]', tone.chip)}>
            {f}
          </span>
        ))}
      </span>
    </button>
  )
}

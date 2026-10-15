import { useMutation, useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  Clock,
  CornerDownRight,
  FileText,
  Hand,
  Lightbulb,
  Mic,
  Pause,
  Play,
  Quote,
  RefreshCw,
  Send,
  SkipForward,
  Sparkles,
  Star,
  Video,
  Volume2,
  VolumeX,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import {
  abortInterview,
  finishInterview,
  generateSuggestedAnswer,
  getInterview,
  markTurn,
  pauseInterview,
  requestHint,
  resumeInterview,
} from '../api/endpoints'
import type { InterviewerPublic } from '../api/types'
import { AnswerFeedbackCard } from '../components/interview/AnswerFeedbackCard'
import { DeviceCheck } from '../components/interview/DeviceCheck'
import { InterviewerPanel } from '../components/interview/InterviewerPanel'
import { SelfView } from '../components/interview/SelfView'
import { StageRail } from '../components/interview/StageRail'
import { Button } from '../components/ui/button'
import { Alert, Badge, Progress, Skeleton } from '../components/ui/feedback'
import { Textarea } from '../components/ui/form'
import { Modal } from '../components/ui/modal'
import { useToast } from '../components/ui/toast'
import { formatDuration, useElapsedSeconds, useRemainingSeconds } from '../hooks/useCountdown'
import {
  evaluationsFromDetail,
  toLiveTurns,
  useInterviewStream,
} from '../hooks/useInterviewStream'
import { useMediaStream } from '../hooks/useMediaStream'
import { useVoiceAnswer } from '../hooks/useVoiceAnswer'
import { STAGE_LABELS } from '../lib/constants'
import type { DeliveryMetrics } from '../lib/deliveryMetrics'
import { cn } from '../lib/utils'
import { newRecordingKey, putRecording } from '../lib/videoStore'
import type { LiveTurn } from '../stores/interviewRoom'

type Phase = 'precheck' | 'countdown' | 'running' | 'finished'
type AnswerMode = 'voice' | 'type'

export function InterviewRoomPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const toast = useToast()

  const room = useInterviewStream(sessionId)

  const detail = useQuery({
    queryKey: ['interview', sessionId],
    queryFn: () => getInterview(sessionId as string),
    enabled: Boolean(sessionId),
  })

  const config = detail.data?.config
  const isVideo = config?.mode === 'video'
  const feedbackMode = config?.feedback_mode ?? 'simulation'
  const allowHint = config?.allow_hint ?? true
  const allowSkip = config?.allow_skip ?? true
  const durationMin = config?.duration_min ?? 30
  const locale = config?.language === 'en' ? 'en-US' : 'zh-CN'

  const media = useMediaStream({ video: true, audio: true })
  const voice = useVoiceAnswer({ enabled: isVideo, lang: locale })

  const [phase, setPhase] = useState<Phase>('precheck')
  const [countdown, setCountdown] = useState(3)
  const [answerMode, setAnswerMode] = useState<AnswerMode>('type')
  const [typedAnswer, setTypedAnswer] = useState('')
  const [hintText, setHintText] = useState<string | null>(null)
  const [hintOpen, setHintOpen] = useState(false)
  const [skipOpen, setSkipOpen] = useState(false)
  const [skipReason, setSkipReason] = useState('')
  const [abortOpen, setAbortOpen] = useState(false)
  const [ttsOn, setTtsOn] = useState(true)
  const [speaking, setSpeaking] = useState(false)
  const [answerStartedAt, setAnswerStartedAt] = useState<number | null>(null)
  const [justChangedStage, setJustChangedStage] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const startedTurnRef = useRef<string | null>(null)
  const spokenRef = useRef<string | null>(null)
  const initializedRef = useRef<string | null>(null)
  const stageRef = useRef<string | null>(null)

  // ---------- 初始化本地状态 ----------
  useEffect(() => {
    if (!detail.data || !sessionId) return
    if (initializedRef.current === sessionId) return
    initializedRef.current = sessionId
    room.init(
      sessionId,
      toLiveTurns(detail.data),
      detail.data.current_stage,
      detail.data.status === 'paused',
    )
    room.seedEvaluations(evaluationsFromDetail(detail.data))
    setAnswerMode(isVideo ? 'voice' : 'type')
    if (detail.data.turns.length > 0) setPhase('running')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.data, sessionId])

  const lastTurn: LiveTurn | undefined = room.turns[room.turns.length - 1]
  const awaitingAnswer = Boolean(lastTurn && !lastTurn.answer && !room.busy && !room.sessionFinished)
  const needsResume = Boolean(lastTurn?.answer && !room.sessionFinished && !room.busy && phase === 'running')

  // ---------- 自动滚动 ----------
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [room.turns.length, room.streamingText.length, room.pendingAnswer])

  // ---------- 记录换人（用于显示"本轮换人"） ----------
  useEffect(() => {
    if (!lastTurn) return
    const changed = stageRef.current !== null && stageRef.current !== lastTurn.stage
    stageRef.current = lastTurn.stage
    if (changed && !lastTurn.answer) {
      setJustChangedStage(lastTurn.stage)
      const timer = window.setTimeout(() => setJustChangedStage(null), 6000)
      return () => window.clearTimeout(timer)
    }
  }, [lastTurn])

  // ---------- 朗读面试官的新问题（视频模式的临场感来源之一） ----------
  useEffect(() => {
    if (!isVideo || !ttsOn || phase !== 'running' || !lastTurn || lastTurn.answer) return
    if (!voice.supportedTts) return
    if (spokenRef.current === lastTurn.id) return
    spokenRef.current = lastTurn.id
    setSpeaking(true)
    voice.speak(lastTurn.question)
    const ms = Math.min(20000, Math.max(2500, lastTurn.question.length * 190))
    const timer = window.setTimeout(() => setSpeaking(false), ms)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastTurn?.id, isVideo, ttsOn, phase])

  // ---------- 新问题到达：重置作答区 ----------
  useEffect(() => {
    if (!lastTurn || lastTurn.answer || phase !== 'running') return
    setTypedAnswer('')
    setHintText(null)
    setHintOpen(false)
    setAnswerStartedAt(Date.now())
  }, [lastTurn?.id, lastTurn?.answer, phase])

  // ---------- 语音模式：自动开始录制 ----------
  useEffect(() => {
    if (phase !== 'running' || answerMode !== 'voice' || !isVideo) return
    if (!lastTurn || lastTurn.answer) return
    if (!awaitingAnswer) return
    if (startedTurnRef.current === lastTurn.id) return
    if (!media.stream) return

    startedTurnRef.current = lastTurn.id
    voice.begin(media.stream)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, answerMode, isVideo, lastTurn?.id, lastTurn?.answer, awaitingAnswer, media.stream])

  const remaining = useRemainingSeconds(durationMin, room.elapsedMin)
  const answerElapsed = useElapsedSeconds(Boolean(answerStartedAt) && !room.busy, answerStartedAt)

  const finish = useMutation({
    mutationFn: () => finishInterview(sessionId as string),
    onSuccess: () => {
      toast.success('报告已生成')
      media.stop()
      navigate(`/interview/${sessionId}/report`, { replace: true })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : '生成报告失败，请重试'),
  })

  const abort = useMutation({
    mutationFn: () => abortInterview(sessionId as string),
    onSuccess: () => {
      media.stop()
      toast.info('已放弃本场面试')
      navigate('/dashboard', { replace: true })
    },
  })

  const paused = room.paused
  const togglePause = async () => {
    if (!sessionId) return
    try {
      if (paused) {
        const res = await resumeInterview(sessionId)
        room.setPaused(false)
        toast.success(`已继续（暂停了 ${Math.round(res.paused_seconds / 60)} 分钟，不计入面试时长）`)
      } else {
        if (answerMode === 'voice' && voice.active) voice.reset()
        await pauseInterview(sessionId)
        room.setPaused(true)
        toast.info('已暂停。暂停时间不计入面试时长。')
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : '操作失败')
    }
  }

  // ---------- 提交回答 ----------
  const handleSubmit = useCallback(async () => {
    if (!lastTurn || room.busy) return
    setSubmitting(true)
    try {
      let text = typedAnswer.trim()
      let metrics: DeliveryMetrics | null = null
      let recordingKey: string | null = null

      if (answerMode === 'voice' && isVideo) {
        const result = await voice.end()
        // 语音识别结果优先；识别失败时回退到用户的手打内容
        text = (result.text || typedAnswer).trim()
        metrics = result.metrics
        if (text.length < 10) {
          toast.error('回答太短（少于 10 字），面试官无法评分。请补充具体内容。')
          setSubmitting(false)
          return
        }
        if (result.recording && sessionId) {
          const key = newRecordingKey(sessionId, lastTurn.turnIndex)
          try {
            await putRecording({
              key,
              sessionId,
              turnIndex: lastTurn.turnIndex,
              blob: result.recording.blob,
              mimeType: result.recording.mimeType,
              durationMs: result.recording.durationMs,
              createdAt: Date.now(),
            })
            recordingKey = key
          } catch {
            toast.info('录像未能保存到本机（存储空间可能不足），但回答已提交。')
          }
        }
      }

      if (text.length < 5) {
        toast.error('回答太短，请补充具体内容后再提交。')
        setSubmitting(false)
        return
      }

      startedTurnRef.current = null
      await room.submitAnswer(text, answerElapsed > 0 ? answerElapsed * 1000 : 30000, {
        metrics,
        recordingKey,
      })
      setTypedAnswer('')
    } finally {
      setSubmitting(false)
    }
  }, [answerElapsed, answerMode, isVideo, lastTurn, room, sessionId, typedAnswer, toast, voice])

  // ---------- 请求提示 ----------
  const handleHint = async () => {
    if (!sessionId || !lastTurn?.id) return
    try {
      const res = await requestHint(sessionId, lastTurn.id)
      room.setHint(res.turn_id, res.hint ?? '')
      setHintText(res.hint ?? '这道题已经用过提示了。')
      setHintOpen(true)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : '获取提示失败')
    }
  }

  // ---------- 跳过 ----------
  const handleSkip = async () => {
    if (answerMode === 'voice' && voice.active) voice.reset()
    setSkipOpen(false)
    setSkipReason('')
    const reason = skipReason
    await room.skipQuestion(reason)
    startedTurnRef.current = null
  }

  // ---------- 标记上一题 ----------
  const handleMark = async () => {
    if (!sessionId) return
    const target = [...room.turns].reverse().find((t) => t.answer)
    if (!target?.id) {
      toast.info('还没有可标记的回答')
      return
    }
    try {
      const next = !target.marked
      await markTurn(sessionId, target.id, next)
      room.toggleMark(target.id, next)
      toast.success(next ? '已标记，报告里会提醒你复习这题' : '已取消标记')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : '标记失败')
    }
  }

  const handleSuggestedAnswer = async (turnId: string) => {
    if (!sessionId) return
    const res = await generateSuggestedAnswer(sessionId, turnId)
    room.setSuggestedAnswer(turnId, res.suggested_answer)
  }

  const currentInterviewer: InterviewerPublic | null = useMemo(() => {
    if (lastTurn?.interviewer) return lastTurn.interviewer
    const roster = detail.data?.roster ?? {}
    const stage = room.currentStage ?? detail.data?.current_stage ?? 'intro'
    return roster[stage] ?? null
  }, [detail.data?.roster, detail.data?.current_stage, lastTurn?.interviewer, room.currentStage])

  // ---------- 渲染 ----------

  if (detail.isLoading) {
    return (
      <div className="mx-auto flex min-h-screen max-w-4xl flex-col gap-4 p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32" />
      </div>
    )
  }

  if (detail.isError) {
    const err = detail.error
    return (
      <div className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-4 p-6 text-center">
        <AlertTriangle className="h-8 w-8 text-destructive" aria-hidden />
        <p className="font-medium">无法加载这场面试</p>
        <p className="text-sm text-muted-foreground">
          {err instanceof ApiError ? err.message : '请检查网络连接后重试'}
        </p>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void detail.refetch()}>
            <RefreshCw className="h-4 w-4" aria-hidden />
            重试
          </Button>
          <Button variant="ghost" onClick={() => navigate('/dashboard')}>
            返回工作台
          </Button>
        </div>
      </div>
    )
  }

  // ===== 阶段一：设备检测 / 面试须知 =====
  if (phase === 'precheck') {
    return (
      <DeviceCheck
        plan={detail.data?.plan ?? null}
        roster={detail.data?.roster ?? {}}
        mode={isVideo ? 'video' : 'text'}
        requireCamera={config?.require_camera ?? true}
        durationMin={durationMin}
        supported={media.supported}
        status={media.status}
        error={media.error}
        stream={media.stream}
        cameras={media.cameras}
        microphones={media.microphones}
        videoDeviceId={media.videoDeviceId}
        audioDeviceId={media.audioDeviceId}
        level={media.level}
        hasVideoTrack={media.hasVideoTrack}
        onStartDevices={() => void media.start()}
        onSwitchDevice={(kind, id) => void media.switchDevice(kind, id)}
        onBegin={() => {
          setAnswerMode(isVideo ? 'voice' : 'type')
          setPhase('countdown')
          setCountdown(3)
        }}
        starting={room.busy}
      />
    )
  }

  // ===== 阶段二：3-2-1 倒计时（真实视频面试的开场仪式感） =====
  if (phase === 'countdown') {
    return (
      <CountdownOverlay
        seconds={countdown}
        interviewer={currentInterviewer}
        onTick={() => setCountdown((c) => c - 1)}
        onDone={() => {
          setPhase('running')
          void room.start()
        }}
      />
    )
  }

  return (
    <div className="flex min-h-screen flex-col bg-secondary/20">
      {/* ---------------- 顶部状态条：只有进度与时间，没有任何分数 ---------------- */}
      <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-4 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setAbortOpen(true)} aria-label="退出面试">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              退出
            </Button>

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {detail.data?.jd_title ?? '模拟面试'}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {isVideo ? '视频面试' : '文字面试'} ·{' '}
                  {feedbackMode === 'practice' ? '练习模式' : '模拟模式'}
                </span>
              </p>
            </div>

            <Badge tone={paused ? 'warning' : remaining < 120 ? 'warning' : 'outline'}>
              <Clock className="h-3 w-3" aria-hidden />
              {paused ? '已暂停' : `剩余 ${formatDuration(remaining)}`}
            </Badge>

            <Button
              variant="ghost"
              size="icon"
              onClick={() => void togglePause()}
              aria-label={paused ? '继续面试' : '暂停面试'}
              title={paused ? '继续面试' : '暂停（不计入面试时长）'}
            >
              {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            </Button>

            {isVideo && voice.supportedTts && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => {
                  setTtsOn((v) => !v)
                  if (ttsOn) voice.stopSpeaking()
                }}
                aria-label={ttsOn ? '关闭面试官语音' : '开启面试官语音'}
                title={ttsOn ? '关闭语音播报' : '开启语音播报'}
              >
                {ttsOn ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              </Button>
            )}
          </div>

          <Progress value={room.progress * 100} tone={room.progress > 0.85 ? 'warning' : 'primary'} />
          <StageRail currentStage={room.currentStage} turns={room.turns} />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-5 px-4 py-5">
        {room.notice && (
          <Alert tone="info" action={<Button size="sm" variant="ghost" onClick={room.clearNotice}>知道了</Button>}>
            {room.notice}
          </Alert>
        )}
        {voice.notice && (
          <Alert tone="warning" action={<Button size="sm" variant="ghost" onClick={voice.clearNotice}>知道了</Button>}>
            {voice.notice}
          </Alert>
        )}
        {voice.asrError && (
          <Alert tone="warning" title="语音识别提示">{voice.asrError}</Alert>
        )}

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
          {/* ================= 左：对话与作答 ================= */}
          <div className="flex min-w-0 flex-col gap-4">
            {/* 对话记录 */}
            <div className="flex flex-col gap-4">
              {room.turns.map((turn, index) => {
                const ev = turn.id ? room.evaluations[turn.id] : undefined
                return (
                  <div key={turn.id ?? turn.turnIndex} className="flex flex-col gap-3">
                    <InterviewerBubbleCompact
                      turn={turn}
                      showHandover={justChangedStage === turn.stage && index > 0}
                    />

                    {turn.answer && (
                      <div className="flex flex-col items-end gap-2">
                        <div
                          className={cn(
                            'max-w-[88%] rounded-lg rounded-tr-sm border p-3 text-sm leading-7',
                            turn.skipped
                              ? 'border-amber-300/60 bg-amber-50/70 dark:border-amber-800 dark:bg-amber-950/30'
                              : 'border-primary/25 bg-primary/8',
                          )}
                        >
                          <p className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                            <span>你 · 第 {index + 1} 题</span>
                            {turn.skipped && <Badge tone="warning">已跳过</Badge>}
                            {turn.marked && (
                              <Badge tone="primary">
                                <Star className="h-3 w-3" aria-hidden />
                                待复习
                              </Badge>
                            )}
                            {turn.hinted && <Badge tone="outline">用过提示</Badge>}
                          </p>
                          <p className="whitespace-pre-wrap">{turn.answer}</p>
                        </div>

                        {/* 练习模式：评分直接贴在这句回答下面 */}
                        {feedbackMode === 'practice' && ev && (
                          <AnswerFeedbackCard
                            evaluation={ev}
                            deliveryMetrics={turn.deliveryMetrics}
                            onRequestSuggested={
                              turn.id ? () => handleSuggestedAnswer(turn.id as string) : undefined
                            }
                            suggestedAnswer={turn.id ? room.suggestedAnswers[turn.id] : null}
                          />
                        )}
                      </div>
                    )}

                    {/* 乐观渲染：刚提交的回答 + 面试官正在生成 */}
                    {room.pendingAnswer && index === room.turns.length - 1 && (
                      <div className="flex justify-end">
                        <div className="max-w-[88%] rounded-lg rounded-tr-sm border border-primary/20 bg-primary/5 p-3 text-sm leading-7 opacity-70">
                          <p className="mb-1 text-xs text-muted-foreground">你 · 提交中…</p>
                          <p className="whitespace-pre-wrap">{room.pendingAnswer}</p>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}

              {room.streaming && (
                <div className="flex gap-3">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/12 text-lg">
                    {currentInterviewer?.emoji ?? '🙂'}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="mb-1 text-xs text-muted-foreground">
                      {currentInterviewer?.name ?? '面试官'}
                      <span className="ml-2 text-primary">正在说话…</span>
                    </p>
                    <div className="rounded-lg rounded-tl-sm border border-border bg-card p-3 text-sm leading-7">
                      {room.streamingText ? (
                        <span className="typing-cursor">{room.streamingText}</span>
                      ) : (
                        <span className="flex gap-1">
                          {[0, 1, 2].map((i) => (
                            <span
                              key={i}
                              className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-muted-foreground"
                              style={{ animationDelay: `${i * 0.18}s` }}
                            />
                          ))}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 回答区 */}
            {awaitingAnswer && !paused && (
              <div className="rounded-lg border border-border bg-card p-4">
                <AnswerComposer
                  isVideo={isVideo}
                  answerMode={answerMode}
                  onModeChange={(m) => {
                    if (answerMode === 'voice' && voice.active) voice.reset()
                    setAnswerMode(m)
                    if (m === 'voice' && media.stream) {
                      startedTurnRef.current = null
                      voice.begin(media.stream)
                      startedTurnRef.current = lastTurn?.id ?? null
                    }
                  }}
                  typedAnswer={typedAnswer}
                  onTypedChange={setTypedAnswer}
                  transcript={voice.transcript}
                  onTranscriptChange={voice.setTranscript}
                  interim={voice.interim}
                  recording={voice.recording}
                  recordingMs={voice.elapsedMs}
                  recordingBytes={voice.recordingBytes}
                  wordCount={voice.wordCount}
                  answerElapsed={answerElapsed}
                  onResubmit={() => {
                    voice.reset()
                    startedTurnRef.current = null
                    if (media.stream) {
                      voice.begin(media.stream)
                      startedTurnRef.current = lastTurn?.id ?? null
                    }
                  }}
                  onSubmit={() => void handleSubmit()}
                  submitting={submitting || room.busy}
                  disabled={room.busy}
                  allowHint={allowHint}
                  allowSkip={allowSkip}
                  onHint={() => void handleHint()}
                  onSkip={() => setSkipOpen(true)}
                  onMark={() => void handleMark()}
                  hasAnswered={room.turns.some((t) => t.answer)}
                  asrSupported={voice.asrSupported}
                />
              </div>
            )}

            {paused && (
              <Alert
                tone="warning"
                title="面试已暂停"
                action={
                  <Button size="sm" onClick={() => void togglePause()}>
                    <Play className="h-3.5 w-3.5" aria-hidden />
                    继续
                  </Button>
                }
              >
                暂停期间不计入面试时长。你可以离开去查资料，但真实面试里没有这个按钮 —— 想清楚什么时候用。
              </Alert>
            )}

            {needsResume && (
              <Alert
                tone="warning"
                title="上一轮回答已保存，但下一题没有生成"
                action={
                  <Button size="sm" onClick={() => void room.resume()} loading={room.busy}>
                    继续面试
                  </Button>
                }
              >
                常见于网络波动或中途关闭页面。你的回答不会丢失。
              </Alert>
            )}

            {room.error && (
              <Alert
                tone="destructive"
                title="出了点问题"
                action={
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      room.clearError()
                      if (room.turns.length > 0) void room.resume()
                      else void room.start()
                    }}
                  >
                    重试
                  </Button>
                }
              >
                {room.error}
              </Alert>
            )}

            {room.sessionFinished && (
              <div className="rounded-lg border border-border bg-card p-6 text-center">
                <Sparkles className="mx-auto h-6 w-6 text-primary" aria-hidden />
                <p className="mt-2 font-medium">面试结束</p>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  你以为面试官只是在聊天 —— 其实每一句回答都被单独评了分。
                  现在生成报告，看看哪几道题真正扣了分。
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  共回答 {room.turns.filter((t) => t.answer).length} 题 · 覆盖{' '}
                  {new Set(room.turns.map((t) => STAGE_LABELS[t.stage] ?? t.stage)).size} 个环节
                </p>
                <Button size="lg" className="mt-4" onClick={() => finish.mutate()} loading={finish.isPending}>
                  <FileText className="h-4 w-4" aria-hidden />
                  {finish.isPending ? '正在生成报告…' : '生成面试报告'}
                </Button>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* ================= 右：面试官 + 自视窗 + 上下文 ================= */}
          <aside className="flex flex-col gap-4 lg:sticky lg:top-32 lg:self-start">
            {isVideo ? (
              <>
                <InterviewerPanel
                  interviewer={currentInterviewer}
                  speaking={speaking || room.streaming}
                  justChanged={Boolean(justChangedStage)}
                />
                <SelfView
                  stream={media.stream}
                  recording={voice.recording}
                  level={media.level}
                  hasVideo={media.hasVideoTrack}
                  elapsedMs={voice.elapsedMs}
                  className="aspect-video w-full"
                />
                {media.error && <Alert tone="warning">{media.error}</Alert>}
              </>
            ) : (
              <InterviewerPanel
                interviewer={currentInterviewer}
                speaking={speaking || room.streaming}
                justChanged={Boolean(justChangedStage)}
              />
            )}

            {/* 本轮考察点 */}
            {lastTurn && (
              <div className="rounded-lg border border-border bg-card p-3.5">
                <p className="text-xs font-medium text-muted-foreground">本轮考察点</p>
                <p className="mt-1 text-sm">
                  {lastTurn.competency ?? '（自由提问）'}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {STAGE_LABELS[lastTurn.stage] ?? lastTurn.stage}
                  {lastTurn.isFollowup && ` · 追问第 ${lastTurn.followupDepth} 层`}
                </p>
                {lastTurn.isFollowup && (
                  <p className="mt-2 flex items-start gap-1 text-[11px] text-muted-foreground">
                    <CornerDownRight className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                    面试官在追你上一轮回答里的细节
                  </p>
                )}
              </div>
            )}

            {/* 提示 */}
            {hintOpen && hintText && (
              <div className="rounded-lg border border-amber-300 bg-amber-50 p-3.5 dark:border-amber-800 dark:bg-amber-950/30">
                <p className="flex items-center gap-1 text-xs font-medium">
                  <Lightbulb className="h-3.5 w-3.5" aria-hidden />
                  回答结构提示
                </p>
                <p className="mt-1 text-xs leading-6 text-muted-foreground">{hintText}</p>
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  提示只给结构，不给答案。用过了会记进报告。
                </p>
              </div>
            )}

            {config && (
              <div className="rounded-lg border border-border bg-secondary/30 p-3.5 text-[11px] text-muted-foreground">
                <p>
                  <Video className="mr-1 inline h-3 w-3" aria-hidden />
                  {isVideo ? '画面与声音只在本机录制，不上传服务器' : '文字面试'}
                </p>
                <p className="mt-1">
                  <Mic className="mr-1 inline h-3 w-3" aria-hidden />
                  面试过程中不显示分数，结束后统一给出
                </p>
              </div>
            )}
          </aside>
        </div>
      </main>

      {/* 跳过 */}
      <Modal
        open={skipOpen}
        onClose={() => setSkipOpen(false)}
        title="确定跳过这一题吗？"
        description="跳过会记 0 分并写进报告。真实面试里你可以说「这块我没做过」，但不该直接沉默。"
        footer={
          <>
            <Button variant="outline" onClick={() => setSkipOpen(false)}>
              再想想
            </Button>
            <Button variant="destructive" onClick={() => void handleSkip()}>
              <SkipForward className="h-4 w-4" aria-hidden />
              确认跳过
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-2">
          <label htmlFor="skip-reason" className="text-sm font-medium">
            写一句原因（会记进报告，帮你看清知识盲区）
          </label>
          <Textarea
            id="skip-reason"
            rows={3}
            value={skipReason}
            onChange={(e) => setSkipReason(e.target.value)}
            placeholder="例如：完全没接触过分布式事务，只在书上看过概念"
          />
        </div>
      </Modal>

      {/* 退出 */}
      <Modal
        open={abortOpen}
        onClose={() => setAbortOpen(false)}
        title="确定要退出这场面试吗？"
        description="已作答内容会保留，但这场会被标记为「已放弃」，且不会生成完整报告。"
        footer={
          <>
            <Button variant="outline" onClick={() => setAbortOpen(false)}>
              继续面试
            </Button>
            <Button variant="destructive" onClick={() => abort.mutate()} loading={abort.isPending}>
              放弃并退出
            </Button>
          </>
        }
      />
    </div>
  )
}

// ======================================================================
// 子组件
// ======================================================================

function InterviewerBubbleCompact({ turn, showHandover }: { turn: LiveTurn; showHandover: boolean }) {
  return (
    <div className="flex gap-3">
      <span
        className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/12 text-base"
        aria-hidden
      >
        {turn.interviewer?.emoji ?? '🙂'}
      </span>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{turn.interviewer?.name ?? '面试官'}</span>
          {turn.interviewer?.title && <span>{turn.interviewer.title}</span>}
          <span>{STAGE_LABELS[turn.stage] ?? turn.stage}</span>
          {turn.isFollowup && (
            <Badge tone="primary">
              <CornerDownRight className="h-3 w-3" aria-hidden />
              追问第 {turn.followupDepth} 层
            </Badge>
          )}
          {showHandover && <Badge tone="outline">本轮换人</Badge>}
        </div>
        <div className="rounded-lg rounded-tl-sm border border-border bg-card p-3 text-sm leading-7 shadow-sm">
          {turn.question}
        </div>
      </div>
    </div>
  )
}

interface AnswerComposerProps {
  isVideo: boolean
  answerMode: AnswerMode
  onModeChange: (mode: AnswerMode) => void
  typedAnswer: string
  onTypedChange: (v: string) => void
  transcript: string
  onTranscriptChange: (v: string) => void
  interim: string
  recording: boolean
  recordingMs: number
  recordingBytes: number
  wordCount: number
  answerElapsed: number
  onResubmit: () => void
  onSubmit: () => void
  submitting: boolean
  disabled: boolean
  allowHint: boolean
  allowSkip: boolean
  onHint: () => void
  onSkip: () => void
  onMark: () => void
  hasAnswered: boolean
  asrSupported: boolean
}

function AnswerComposer(props: AnswerComposerProps) {
  const {
    isVideo,
    answerMode,
    onModeChange,
    typedAnswer,
    onTypedChange,
    transcript,
    onTranscriptChange,
    interim,
    recording,
    recordingMs,
    recordingBytes,
    wordCount,
    answerElapsed,
    onResubmit,
    onSubmit,
    submitting,
    disabled,
    allowHint,
    allowSkip,
    onHint,
    onSkip,
    onMark,
    hasAnswered,
    asrSupported,
  } = props

  const voiceMode = isVideo && answerMode === 'voice'
  const text = voiceMode ? transcript : typedAnswer
  const ready = text.trim().length >= 10

  return (
    <div className="flex flex-col gap-3">
      {/* 操作行 */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">
          本题用时 <span className="font-mono tabular-nums">{formatDuration(answerElapsed)}</span>
          {' · '}
          {voiceMode ? `${wordCount} 字（语音转写）` : `${typedAnswer.trim().length} 字`}
        </span>

        {isVideo && (
          <div className="flex overflow-hidden rounded-md border border-border">
            <button
              type="button"
              onClick={() => onModeChange('voice')}
              className={cn(
                'flex items-center gap-1 px-2.5 py-1 text-xs transition-colors',
                voiceMode ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-secondary',
              )}
              aria-pressed={voiceMode}
            >
              <Mic className="h-3 w-3" aria-hidden />
              语音作答
            </button>
            <button
              type="button"
              onClick={() => onModeChange('type')}
              className={cn(
                'flex items-center gap-1 px-2.5 py-1 text-xs transition-colors',
                !voiceMode ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-secondary',
              )}
              aria-pressed={!voiceMode}
            >
              <Hand className="h-3 w-3" aria-hidden />
              手动输入
            </button>
          </div>
        )}

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {allowHint && (
            <Button size="sm" variant="outline" onClick={onHint} disabled={disabled}>
              <Lightbulb className="h-3.5 w-3.5" aria-hidden />
              提示
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={onMark}
            disabled={disabled || !hasAnswered}
            title="标记上一题，报告里会提醒复习"
          >
            <Star className="h-3.5 w-3.5" aria-hidden />
            标记
          </Button>
          {allowSkip && (
            <Button size="sm" variant="outline" onClick={onSkip} disabled={disabled}>
              <SkipForward className="h-3.5 w-3.5" aria-hidden />
              跳过
            </Button>
          )}
        </div>
      </div>

      {/* 语音模式：显示实时转写，可编辑（识别错误不该由考生背锅） */}
      {voiceMode ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs">
            {recording ? (
              <span className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
                <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" aria-hidden />
                正在录音与识别 {formatDuration(recordingMs / 1000)}
              </span>
            ) : (
              <span className="text-muted-foreground">录音未开始</span>
            )}
            <span className="text-muted-foreground">
              {(recordingBytes / 1024 / 1024).toFixed(1)} MB
            </span>
            {!asrSupported && (
              <Badge tone="warning">浏览器不支持语音识别，请手动输入</Badge>
            )}
          </div>

          <Textarea
            rows={5}
            value={transcript}
            onChange={(e) => onTranscriptChange(e.target.value)}
            aria-label="语音转写文本，可直接修改"
            placeholder="开始说话后，识别结果会出现在这里。识别错了可以直接改 —— 这不是你的错。"
          />

          {interim && <p className="text-xs text-muted-foreground">正在识别：{interim}</p>}

          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={onResubmit} disabled={disabled}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden />
              重新录这一段
            </Button>
            <Button
              size="sm"
              className="ml-auto"
              onClick={onSubmit}
              disabled={disabled || !ready}
              loading={submitting}
            >
              <Send className="h-3.5 w-3.5" aria-hidden />
              {submitting ? '面试官正在思考' : '说完了，提交'}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <Textarea
            rows={5}
            value={typedAnswer}
            onChange={(e) => onTypedChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                if (ready && !disabled) onSubmit()
              }
            }}
            disabled={disabled}
            aria-label="你的回答"
            placeholder="建议先说结论，再讲具体做法和结果数据。Enter 提交 · Shift+Enter 换行"
          />
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              {typedAnswer.trim().length < 10 && typedAnswer.length > 0
                ? '至少 10 字，太短没法评分'
                : '越具体、越贴近真实经历，后续追问越有价值'}
            </span>
            <Button
              size="sm"
              className="ml-auto"
              onClick={onSubmit}
              disabled={disabled || !ready}
              loading={submitting}
            >
              <Send className="h-3.5 w-3.5" aria-hidden />
              {submitting ? '面试官正在思考' : '提交回答'}
            </Button>
          </div>
        </div>
      )}

      {voiceMode && (
        <p className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
          <Quote className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          提交后我们会根据录音实测你的语速、口头禅占比和长停顿次数，这些数字会和内容一起进评分 ——
          比模型凭感觉说「表达流畅」靠谱。
        </p>
      )}
    </div>
  )
}

function CountdownOverlay({
  seconds,
  interviewer,
  onTick,
  onDone,
}: {
  seconds: number
  interviewer: InterviewerPublic | null
  onTick: () => void
  onDone: () => void
}) {
  useEffect(() => {
    if (seconds <= 0) {
      onDone()
      return
    }
    const timer = window.setTimeout(onTick, 900)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seconds])

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-950 text-slate-100">
      <p className="text-sm text-slate-400">面试即将开始</p>
      <div
        className="flex h-32 w-32 items-center justify-center rounded-full border-4 border-primary/60 text-6xl font-bold tabular-nums"
        aria-live="assertive"
      >
        {seconds > 0 ? seconds : 'GO'}
      </div>
      <p className="max-w-sm text-center text-sm text-slate-400">
        {interviewer ? `${interviewer.name}（${interviewer.title}）已就位` : '面试官已就位'}
        <br />
        像真实面试一样：看着镜头，先听完问题再回答。
      </p>
    </div>
  )
}

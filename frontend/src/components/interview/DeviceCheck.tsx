import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Loader2,
  Mic,
  PlayCircle,
  ShieldCheck,
  Video,
  XCircle,
} from 'lucide-react'

import type { InterviewerPublic, InterviewPlan } from '../../api/types'
import { STAGE_LABELS } from '../../lib/constants'
import { cn } from '../../lib/utils'
import { Button } from '../ui/button'
import { Alert, Badge } from '../ui/feedback'
import { Label } from '../ui/form'
import { DevicePreview } from './SelfView'
import { InterviewerPanel } from './InterviewerPanel'

interface DeviceCheckProps {
  plan: InterviewPlan | null
  roster: Record<string, InterviewerPublic>
  mode: 'text' | 'video'
  requireCamera: boolean
  durationMin: number
  // 设备状态
  supported: boolean
  status: 'idle' | 'requesting' | 'ready' | 'denied' | 'error' | 'unsupported'
  error: string | null
  stream: MediaStream | null
  cameras: Array<{ deviceId: string; label: string }>
  microphones: Array<{ deviceId: string; label: string }>
  videoDeviceId: string
  audioDeviceId: string
  level: number
  hasVideoTrack: boolean
  onStartDevices: () => void
  onSwitchDevice: (kind: 'videoinput' | 'audioinput', deviceId: string) => void
  onBegin: () => void
  starting: boolean
}

function ChecklistRow({
  ok,
  pending,
  label,
  detail,
}: {
  ok: boolean
  pending?: boolean
  label: string
  detail: string
}) {
  return (
    <li className="flex items-start gap-2 text-sm">
      {pending ? (
        <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-muted-foreground" aria-hidden />
      ) : ok ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
      ) : (
        <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
      )}
      <span className="min-w-0">
        <span className="font-medium">{label}</span>
        <span className="ml-1 text-muted-foreground">{detail}</span>
      </span>
    </li>
  )
}

/**
 * 设备检测页（视频面试的第一步）。
 *
 * 真实视频面试平台都有这一步，因为"面试官都能看到你了，你才发现麦克风没开"
 * 是最糟糕的开场。这里把设备、音量、座位提示、面试须知一次讲清楚。
 */
export function DeviceCheck({
  plan,
  roster,
  mode,
  requireCamera,
  durationMin,
  supported,
  status,
  error,
  stream,
  cameras,
  microphones,
  videoDeviceId,
  audioDeviceId,
  level,
  hasVideoTrack,
  onStartDevices,
  onSwitchDevice,
  onBegin,
  starting,
}: DeviceCheckProps) {
  const isVideo = mode === 'video'
  const micAlive = level > 0.02
  const ready = status === 'ready' && (!isVideo || !requireCamera || hasVideoTrack)
  const firstInterviewer = Object.values(roster)[0] ?? null

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">
          {isVideo ? '设备检测与面试须知' : '面试须知'}
        </h1>
        <p className="text-sm text-muted-foreground">
          {isVideo
            ? '先确认画面和声音，再进入面试。这一步大约 30 秒。'
            : '确认下面这些规则，然后进入面试。'}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {/* 左：设备 */}
        <div className="flex flex-col gap-4">
          {isVideo && (
            <>
              <DevicePreview stream={stream} hasVideo={hasVideoTrack} />

              <ul className="flex flex-col gap-2">
                <ChecklistRow
                  ok={hasVideoTrack && stream !== null}
                  pending={status === 'requesting'}
                  label="摄像头"
                  detail={
                    !supported
                      ? '当前环境不支持'
                      : stream === null
                        ? '尚未开启'
                        : hasVideoTrack
                          ? '画面正常'
                          : '不可用（已切换为只录音）'
                  }
                />
                <ChecklistRow
                  ok={micAlive}
                  pending={status === 'requesting'}
                  label="麦克风"
                  detail={
                    stream === null
                      ? '尚未开启'
                      : micAlive
                        ? '已捕捉到声音'
                        : '没有检测到声音，请对着麦克风说一句话测试'
                  }
                />
              </ul>

              {stream === null && (
                <Button onClick={onStartDevices} loading={status === 'requesting'} disabled={!supported}>
                  <Video className="h-4 w-4" aria-hidden />
                  开启摄像头与麦克风
                </Button>
              )}

              {stream !== null && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="dev-cam">摄像头</Label>
                    <select
                      id="dev-cam"
                      value={videoDeviceId}
                      onChange={(e) => onSwitchDevice('videoinput', e.target.value)}
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <option value="">默认摄像头</option>
                      {cameras.map((d) => (
                        <option key={d.deviceId} value={d.deviceId}>
                          {d.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="dev-mic">麦克风</Label>
                    <select
                      id="dev-mic"
                      value={audioDeviceId}
                      onChange={(e) => onSwitchDevice('audioinput', e.target.value)}
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <option value="">默认麦克风</option>
                      {microphones.map((d) => (
                        <option key={d.deviceId} value={d.deviceId}>
                          {d.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {error && (
                <Alert tone={status === 'denied' ? 'warning' : 'destructive'} title="设备提示">
                  {error}
                </Alert>
              )}

              <div className="flex items-start gap-2 rounded-md border border-border bg-secondary/30 p-3 text-xs text-muted-foreground">
                <Camera className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                <div className="flex flex-col gap-1">
                  <p className="font-medium text-foreground">坐姿与画面建议</p>
                  <p>镜头与眼睛齐平，画面里露出肩部以上；光从正面来，别背对窗户；背景尽量干净。</p>
                  <p>回答时看着镜头，不是看着屏幕上的自己 —— 这点和真实视频面试一样。</p>
                </div>
              </div>
            </>
          )}

          {!isVideo && plan && (
            <div className="flex flex-col gap-3">
              <p className="text-sm font-medium">本场考察点（{plan.competencies.length} 个）</p>
              <div className="flex flex-wrap gap-1.5">
                {plan.competencies.map((c) => (
                  <Badge key={c.name} tone={c.source === 'resume' ? 'primary' : 'outline'}>
                    {c.name}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 右：面试官 + 规则 */}
        <div className="flex flex-col gap-4">
          {isVideo && (
            <InterviewerPanel interviewer={firstInterviewer} speaking={false} expandable={false} />
          )}

          <div className="rounded-lg border border-border bg-card p-4">
            <p className="mb-2 text-sm font-medium">这场面试会怎么进行</p>
            <ul className="flex flex-col gap-1.5 text-xs text-muted-foreground">
              <li>· 共 {durationMin} 分钟，六个环节：{Object.values(STAGE_LABELS).join(' → ')}</li>
              <li>· 每个环节可能由不同面试官负责，换人时会先自报身份</li>
              <li>
                · 面试官会根据你的回答
                <span className="font-medium text-foreground">继续追问细节</span>，最多追两层
              </li>
              {isVideo && <li>· 你的画面与声音只在本机录制，不会上传服务器</li>}
              <li>· 卡住时可以请求「回答结构提示」或跳过，但都会被记录进报告</li>
              <li>· 中途可以暂停，暂停时间不计入面试时长</li>
            </ul>
          </div>

          <Alert tone="info" title="面试过程中不会显示分数">
            <span className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>
                这是刻意的 —— 真实面试你不会知道面试官给你打几分，知道了就会开始猜评分标准。
                所有评分会在结束后的报告里一次性给出，并附上你的原话作为依据。
              </span>
            </span>
          </Alert>

          {isVideo && !hasVideoTrack && stream !== null && requireCamera && (
            <Alert tone="warning" title="当前没有可用画面">
              <span className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <span>
                  摄像头不可用，已切换为「只录音」模式。语音面试同样能练习表达与结构，
                  但真实视频面试的画面表现（眼神、坐姿）无法练习到。
                </span>
              </span>
            </Alert>
          )}

          <Button
            size="lg"
            onClick={onBegin}
            loading={starting}
            disabled={isVideo && !supported}
            className={cn('w-full', ready && 'shadow-md')}
          >
            <PlayCircle className="h-4 w-4" aria-hidden />
            开始面试
          </Button>

          <p className="text-center text-xs text-muted-foreground">
            <Mic className="mr-1 inline h-3 w-3" aria-hidden />
            开始后请像真实面试一样口述作答，不要写书面语
          </p>
        </div>
      </div>
    </div>
  )
}

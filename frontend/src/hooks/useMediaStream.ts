/**
 * 摄像头 / 麦克风生命周期管理。
 *
 * 真实视频面试平台都有"设备检测"这一步，原因很实际：
 * 面试开始后才发现摄像头打不开、麦克风是静音的，是最糟糕的体验。
 * 所以这里把「权限申请 → 设备枚举 → 实时预览 → 音量检测」做成一个 hook。
 *
 * 几个必须处理好的细节：
 * - 权限被拒时要给出**可操作**的提示（去哪改设置），不是干巴巴的"出错了"
 * - 没有摄像头时要能降级为"只录音"
 * - 卸载/离开页面时必须 stop 所有 track，否则摄像头指示灯会一直亮着（用户会以为被偷拍）
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export type MediaStatus = 'idle' | 'requesting' | 'ready' | 'denied' | 'error' | 'unsupported'

export interface DeviceOption {
  deviceId: string
  label: string
}

export interface UseMediaStreamOptions {
  /** 是否请求视频轨（无摄像头场景可设为 false，只录音） */
  video?: boolean
  audio?: boolean
}

const PERMISSION_MESSAGES: Record<string, string> = {
  NotAllowedError:
    '摄像头/麦克风权限被拒绝。请点击浏览器地址栏左侧的锁形图标 → 允许摄像头与麦克风，然后刷新页面。',
  PermissionDeniedError:
    '摄像头/麦克风权限被拒绝。请在浏览器地址栏的权限设置里允许访问后刷新页面。',
  NotFoundError: '没有检测到可用的摄像头或麦克风设备，请检查设备连接。',
  DevicesNotFoundError: '没有检测到可用的摄像头或麦克风设备，请检查设备连接。',
  NotReadableError:
    '设备被其他程序占用了（常见于开着腾讯会议/钉钉/OBS）。请关掉其他占用摄像头的程序后重试。',
  TrackStartError: '设备启动失败，可能被其他程序占用。请关闭其他摄像头程序后重试。',
  OverconstrainedError: '当前设备不支持所请求的参数，请换一个摄像头试试。',
  SecurityError: '当前页面不是安全上下文（需要 https 或 localhost），浏览器禁止访问摄像头。',
}

function explain(err: unknown): string {
  const name = (err as { name?: string } | null)?.name ?? ''
  return PERMISSION_MESSAGES[name] ?? `无法访问媒体设备：${(err as Error)?.message ?? '未知错误'}`
}

export function useMediaStream({ video = true, audio = true }: UseMediaStreamOptions = {}) {
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [status, setStatus] = useState<MediaStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [cameras, setCameras] = useState<DeviceOption[]>([])
  const [microphones, setMicrophones] = useState<DeviceOption[]>([])
  const [videoDeviceId, setVideoDeviceId] = useState('')
  const [audioDeviceId, setAudioDeviceId] = useState('')
  const [level, setLevel] = useState(0)
  const [hasVideoTrack, setHasVideoTrack] = useState(video)

  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const rafRef = useRef<number | null>(null)

  const supported =
    typeof navigator !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof window !== 'undefined' &&
    window.isSecureContext !== false

  const stopLevelMeter = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    void audioCtxRef.current?.close().catch(() => undefined)
    audioCtxRef.current = null
    setLevel(0)
  }, [])

  const stop = useCallback(() => {
    stopLevelMeter()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    setStream(null)
    setStatus('idle')
  }, [stopLevelMeter])

  /** 用 AnalyserNode 算 RMS 音量，驱动音量计。 */
  const startLevelMeter = useCallback(
    (target: MediaStream) => {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return
      try {
        const ctx = new Ctor()
        audioCtxRef.current = ctx
        const source = ctx.createMediaStreamSource(target)
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 1024
        source.connect(analyser)
        const data = new Uint8Array(analyser.fftSize)

        const tick = () => {
          analyser.getByteTimeDomainData(data)
          let sum = 0
          for (let i = 0; i < data.length; i += 1) {
            const v = (data[i] - 128) / 128
            sum += v * v
          }
          const rms = Math.sqrt(sum / data.length)
          // 映射到 0-1，抬一点低音量的可见度
          setLevel(Math.min(1, rms * 3.2))
          rafRef.current = requestAnimationFrame(tick)
        }
        rafRef.current = requestAnimationFrame(tick)
      } catch {
        /* 音量计是锦上添花，失败不影响主流程 */
      }
    },
    [],
  )

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return
    const devices = await navigator.mediaDevices.enumerateDevices()
    setCameras(
      devices
        .filter((d) => d.kind === 'videoinput')
        .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `摄像头 ${i + 1}` })),
    )
    setMicrophones(
      devices
        .filter((d) => d.kind === 'audioinput')
        .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `麦克风 ${i + 1}` })),
    )
  }, [])

  const start = useCallback(
    async (opts?: { videoDeviceId?: string; audioDeviceId?: string; video?: boolean }) => {
      if (!supported) {
        setStatus('unsupported')
        setError('当前环境无法访问摄像头/麦克风（需要 https 或 localhost，且浏览器支持 getUserMedia）')
        return null
      }

      const wantVideo = opts?.video ?? video
      setStatus('requesting')
      setError(null)

      try {
        // 先停掉旧的，避免同时占用两个摄像头
        streamRef.current?.getTracks().forEach((t) => t.stop())

        const constraints: MediaStreamConstraints = {
          audio: audio
            ? {
                deviceId: (opts?.audioDeviceId || audioDeviceId)
                  ? { exact: opts?.audioDeviceId || audioDeviceId }
                  : undefined,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
              }
            : false,
          video: wantVideo
            ? {
                deviceId: (opts?.videoDeviceId || videoDeviceId)
                  ? { exact: opts?.videoDeviceId || videoDeviceId }
                  : undefined,
                width: { ideal: 1280 },
                height: { ideal: 720 },
                frameRate: { ideal: 30, max: 30 },
                facingMode: 'user',
              }
            : false,
        }

        let next: MediaStream
        try {
          next = await navigator.mediaDevices.getUserMedia(constraints)
        } catch (err) {
          // 摄像头不可用但麦克风可用时，自动降级为「只录音」
          const name = (err as { name?: string })?.name
          if (
            wantVideo &&
            audio &&
            ['NotFoundError', 'DevicesNotFoundError', 'NotReadableError', 'OverconstrainedError'].includes(
              name ?? '',
            )
          ) {
            next = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
            setHasVideoTrack(false)
            setError('摄像头不可用，已自动切换为「只录音」模式。你仍然可以用语音完整作答。')
          } else {
            throw err
          }
        }

        streamRef.current = next
        setStream(next)
        setHasVideoTrack(next.getVideoTracks().length > 0)
        setStatus('ready')
        // 拿到权限后 label 才会有值，所以必须在这之后重新枚举
        await refreshDevices()
        if (audio) startLevelMeter(next)
        return next
      } catch (err) {
        const name = (err as { name?: string })?.name
        setError(explain(err))
        setStatus(name === 'NotAllowedError' || name === 'PermissionDeniedError' ? 'denied' : 'error')
        return null
      }
    },
    [audio, audioDeviceId, refreshDevices, startLevelMeter, supported, video, videoDeviceId],
  )

  /** 切换设备：保留当前权限，只换 track。 */
  const switchDevice = useCallback(
    async (kind: 'videoinput' | 'audioinput', deviceId: string) => {
      if (kind === 'videoinput') setVideoDeviceId(deviceId)
      else setAudioDeviceId(deviceId)
      await start({
        videoDeviceId: kind === 'videoinput' ? deviceId : videoDeviceId,
        audioDeviceId: kind === 'audioinput' ? deviceId : audioDeviceId,
      })
    },
    [audioDeviceId, start, videoDeviceId],
  )

  // 页面卸载/组件销毁时必须关掉摄像头，否则指示灯常亮
  useEffect(() => {
    return () => {
      stopLevelMeter()
      streamRef.current?.getTracks().forEach((t) => t.stop())
    }
  }, [stopLevelMeter])

  // 拔掉设备时浏览器会触发 devicechange
  useEffect(() => {
    const handler = () => void refreshDevices()
    navigator.mediaDevices?.addEventListener?.('devicechange', handler)
    return () => navigator.mediaDevices?.removeEventListener?.('devicechange', handler)
  }, [refreshDevices])

  return {
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
    start,
    stop,
    switchDevice,
    refreshDevices,
    clearError: () => setError(null),
  }
}

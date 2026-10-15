/**
 * 一轮语音/视频作答的完整生命周期。
 *
 * 把三件必须同步的事情收在一个 hook 里：
 * 1. **语音识别（ASR）** → 得到文字，喂给后端评分
 * 2. **录音录像（MediaRecorder）** → 得到 Blob，存本地供回看
 * 3. **节奏追踪（DeliveryTracker）** → 得到语速/口头禅/停顿，作为客观评分依据
 *
 * 之所以要收在一起：这三者的开始与结束必须严格对齐，
 * 否则会出现"录音时长和转写文本对不上、算出来的语速是错的"这种隐蔽 bug。
 */

import { useCallback, useMemo, useRef, useState } from 'react'

import { useRecorder, type RecordingResult } from './useRecorder'
import { useSpeech } from './useSpeech'
import {
  computeDeliveryMetrics,
  countWords,
  DeliveryTracker,
  type DeliveryMetrics,
} from '../lib/deliveryMetrics'

export interface VoiceAnswerResult {
  text: string
  metrics: DeliveryMetrics | null
  recording: RecordingResult | null
}

export interface UseVoiceAnswerOptions {
  lang?: string
  enabled: boolean
}

export function useVoiceAnswer({ lang = 'zh-CN', enabled }: UseVoiceAnswerOptions) {
  const [transcript, setTranscript] = useState('')
  const [active, setActive] = useState(false)
  /** 用户是否真的说了话（用来区分"只用语音"和"语音+手打"） */
  const [usedVoice, setUsedVoice] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const trackerRef = useRef(new DeliveryTracker())
  const streamRef = useRef<MediaStream | null>(null)
  const recorder = useRecorder()

  const speech = useSpeech({
    lang,
    onTranscript: (text) => {
      setTranscript((prev) => prev + text)
      setUsedVoice(true)
      trackerRef.current.noteSpeech()
    },
  })

  const asrSupported = speech.supportedAsr
  const recorderSupported = recorder.supported

  /** 开始作答：计时 → 录音 → 开始识别。 */
  const begin = useCallback(
    (stream: MediaStream | null) => {
      if (!enabled) return
      setNotice(null)
      streamRef.current = stream
      trackerRef.current.start()
      setActive(true)

      if (stream) {
        const ok = recorder.start(stream)
        if (!ok) setNotice('录像不可用，本次仅保存文字与表达指标。')
      }

      if (asrSupported) {
        speech.start()
      } else {
        setNotice(
          '当前浏览器不支持语音识别（建议 Chrome / Edge），已切换为文字作答；录音仍会保存供你回看。',
        )
      }
    },
    [asrSupported, enabled, recorder, speech],
  )

  /** 结束作答：停识别 → 停录制 → 算指标。 */
  const end = useCallback(async (): Promise<VoiceAnswerResult> => {
    setActive(false)
    speech.stop()
    // stop() 会触发 onend，但我们需要的是一个确定的时刻
    const recording = await recorder.stop()
    const trackerResult = trackerRef.current.stop()

    const text = transcript.trim()
    const source: DeliveryMetrics['transcript_source'] =
      usedVoice && text ? 'asr' : 'typed'

    const metrics =
      text && source !== 'typed'
        ? computeDeliveryMetrics({
            text,
            durationMs: recording?.durationMs ?? trackerResult.durationMs,
            source,
            pauses: trackerResult.pauses,
          })
        : null
    return { text, metrics, recording }
  }, [recorder, speech, transcript, usedVoice])

  const reset = useCallback(() => {
    speech.stop()
    recorder.cancel()
    trackerRef.current.start()
    setTranscript('')
    setUsedVoice(false)
    setActive(false)
    setNotice(null)
  }, [recorder, speech])

  /** ASR 的中间结果实时展示，但不并入最终文本（避免重复）。 */
    const elapsedMs = recorder.recording ? recorder.elapsedMs : 0

  const wordCount = useMemo(() => countWords(transcript), [transcript])

  return {
    transcript,
    setTranscript,
    interim: speech.interim,
    active,
    usedVoice,
    wordCount,
    elapsedMs,
    metricsPreview: null as DeliveryMetrics | null,
    notice,
    asrSupported,
    recorderSupported,
    recording: recorder.recording,
    recordingBytes: recorder.bytes,
    asrError: speech.error,
    recorderError: recorder.error,
    begin,
    end,
    reset,
    stopSpeaking: speech.stopSpeaking,
    supportedTts: speech.supportedTts,
    speak: speech.speak,
    clearNotice: () => setNotice(null),
  }
}

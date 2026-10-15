/**
 * 语音输入/播报（Web Speech API）。
 *
 * 降级策略（对应 README 第 9 节）：
 *   1. 浏览器原生 SpeechRecognition + SpeechSynthesis（Chrome / Edge）
 *   2. 不支持时返回 supported=false，界面自动切纯文字模式并明确提示
 * 服务端 ASR（Whisper）为可选扩展，未接入时不影响主流程。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// --- Web Speech API 的最小类型声明（TS 的 lib.dom 未包含）---
interface SpeechAlternative {
  transcript: string
  confidence: number
}
interface SpeechResult {
  isFinal: boolean
  length: number
  [index: number]: SpeechAlternative
}
interface SpeechResultList {
  length: number
  [index: number]: SpeechResult
}
interface SpeechRecognitionEventLike {
  resultIndex: number
  results: SpeechResultList
}
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export interface UseSpeechOptions {
  lang?: string
  /** 识别出的文本如何并入输入框（默认追加） */
  onTranscript?: (text: string, isFinal: boolean) => void
}

export function useSpeech({ lang = 'zh-CN', onTranscript }: UseSpeechOptions = {}) {
  const ctor = useMemo(getRecognitionCtor, [])
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)

  const supportedAsr = ctor !== null
  const supportedTts =
    typeof window !== 'undefined' && typeof window.speechSynthesis !== 'undefined'

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort()
      if (supportedTts) window.speechSynthesis.cancel()
    }
  }, [supportedTts])

  const start = useCallback(() => {
    if (!ctor) {
      setError('当前浏览器不支持语音识别，请改用 Chrome / Edge，或直接文字作答')
      return
    }
    setError(null)

    const recognition = new ctor()
    recognition.lang = lang
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    recognition.onresult = (event) => {
      let finalText = ''
      let interimText = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const transcript = result[0]?.transcript ?? ''
        if (result.isFinal) finalText += transcript
        else interimText += transcript
      }
      setInterim(interimText)
      if (finalText) onTranscript?.(finalText, true)
    }

    recognition.onerror = (event) => {
      const map: Record<string, string> = {
        'not-allowed': '麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试',
        'service-not-allowed': '浏览器未提供语音识别服务，请改用文字作答',
        'no-speech': '没有听到声音，请靠近麦克风再试一次',
        network: '语音识别服务网络异常',
        aborted: '',
      }
      const message = map[event.error] ?? `语音识别出错（${event.error}）`
      if (message) setError(message)
      setListening(false)
    }

    recognition.onend = () => {
      setListening(false)
      setInterim('')
    }

    recognitionRef.current = recognition
    try {
      recognition.start()
      setListening(true)
    } catch {
      setError('语音识别启动失败，请刷新页面后重试')
      setListening(false)
    }
  }, [ctor, lang, onTranscript])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
    setListening(false)
  }, [])

  const speak = useCallback(
    (text: string, opts?: { rate?: number }) => {
      if (!supportedTts || !text.trim()) return
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = lang
      utterance.rate = opts?.rate ?? 1.02
      window.speechSynthesis.speak(utterance)
    },
    [lang, supportedTts],
  )

  const stopSpeaking = useCallback(() => {
    if (supportedTts) window.speechSynthesis.cancel()
  }, [supportedTts])

  return {
    supportedAsr,
    supportedTts,
    listening,
    interim,
    error,
    start,
    stop,
    speak,
    stopSpeaking,
    clearError: () => setError(null),
  }
}

import { Mic, MicOff, Send, Timer } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { formatDuration, useElapsedSeconds } from '../../hooks/useCountdown'
import { useSpeech } from '../../hooks/useSpeech'
import { cn } from '../../lib/utils'
import { Button } from '../ui/button'
import { Badge } from '../ui/feedback'
import { Textarea } from '../ui/form'

interface AnswerBoxProps {
  /** 当前题目标识；变化时重置计时与草稿 */
  questionKey: string | number
  onSubmit: (answer: string, elapsedMs: number) => void | Promise<void>
  disabled?: boolean
  thinking?: boolean
  /** 是否允许语音（面试配置里的 voice_enabled） */
  voiceEnabled?: boolean
  placeholder?: string
}

const MIN_LENGTH = 10

/**
 * 回答输入区。
 *
 * 交互约定：
 * - Enter 发送，Shift+Enter 换行（学生打字快，这个最省事）
 * - 显示本题用时，提醒别答太长（真实面试没有无限时间）
 * - 语音识别结果可手工编辑后再提交 —— 识别错误不该由学生背锅
 */
export function AnswerBox({
  questionKey,
  onSubmit,
  disabled = false,
  thinking = false,
  voiceEnabled = false,
  placeholder = '在这里输入你的回答。建议先说结论，再讲具体做法和结果数据…',
}: AnswerBoxProps) {
  const [value, setValue] = useState('')
  const [startAt, setStartAt] = useState<number>(() => Date.now())
  const submittedAtRef = useRef<number | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const speech = useSpeech({
    onTranscript: (text) => setValue((prev) => (prev ? `${prev}${text}` : text)),
  })

  // 新问题到达：清空草稿、重置计时、把焦点交回输入框
  useEffect(() => {
    setValue('')
    setStartAt(Date.now())
    submittedAtRef.current = null
    speech.stop()
    textareaRef.current?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionKey])

  const elapsed = useElapsedSeconds(!disabled && !thinking, startAt)
  const tooShort = value.trim().length > 0 && value.trim().length < MIN_LENGTH
  const canSubmit = value.trim().length >= MIN_LENGTH && !disabled && !thinking

  const submit = () => {
    if (!canSubmit) return
    const elapsedMs = Date.now() - startAt
    submittedAtRef.current = Date.now()
    void onSubmit(value.trim(), elapsedMs)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Timer className="h-3.5 w-3.5" aria-hidden />
          本题用时 <span className="font-mono tabular-nums">{formatDuration(elapsed)}</span>
        </span>
        <span className="text-xs text-muted-foreground">·</span>
        <span className="text-xs text-muted-foreground">{value.trim().length} 字</span>
        {tooShort && <Badge tone="warning">至少 {MIN_LENGTH} 字，太短没法评分</Badge>}
        {elapsed > 240 && <Badge tone="warning">答得太久了，面试官会打断你</Badge>}

        <span className="ml-auto text-xs text-muted-foreground">
          Enter 提交 · Shift+Enter 换行
        </span>
      </div>

      <div className="relative">
        <Textarea
          ref={textareaRef}
          rows={5}
          value={value}
          disabled={disabled || thinking}
          placeholder={placeholder}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="你的回答"
          className="resize-y pb-14 pr-3"
        />

        <div className="absolute bottom-2 left-2 right-2 flex items-center gap-2">
          {voiceEnabled && (
            <Button
              type="button"
              size="sm"
              variant={speech.listening ? 'destructive' : 'secondary'}
              onClick={() => (speech.listening ? speech.stop() : speech.start())}
              disabled={disabled || thinking || !speech.supportedAsr}
              title={speech.supportedAsr ? '语音输入' : '当前浏览器不支持语音识别'}
            >
              {speech.listening ? (
                <>
                  <MicOff className="h-3.5 w-3.5" aria-hidden />
                  停止录音
                </>
              ) : (
                <>
                  <Mic className="h-3.5 w-3.5" aria-hidden />
                  语音作答
                </>
              )}
            </Button>
          )}

          <Button
            type="button"
            size="sm"
            className={cn('ml-auto')}
            onClick={submit}
            disabled={!canSubmit}
            loading={thinking}
          >
            <Send className="h-3.5 w-3.5" aria-hidden />
            {thinking ? '面试官正在思考' : '提交回答'}
          </Button>
        </div>
      </div>

      {speech.listening && speech.interim && (
        <p className="text-xs text-muted-foreground">识别中：{speech.interim}</p>
      )}
      {speech.error && (
        <p className="text-xs text-destructive" role="alert">
          {speech.error}
        </p>
      )}
      {voiceEnabled && !speech.supportedAsr && (
        <p className="text-xs text-muted-foreground">
          当前浏览器不支持语音识别（建议 Chrome / Edge），已切换为文字作答。
        </p>
      )}
    </div>
  )
}

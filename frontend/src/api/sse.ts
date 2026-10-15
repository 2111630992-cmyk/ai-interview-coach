/**
 * SSE 客户端。
 *
 * 为什么不用原生 EventSource：
 * 1. EventSource 只支持 GET，无法带 JSON 请求体和 Authorization 头；
 * 2. 我们需要在 axios/fetch 层统一处理 401 与统一错误体。
 * 所以这里手工读 ReadableStream 并解析 SSE 帧。
 */

import { API_BASE_URL, ApiError, NetworkError } from './client'
import { getToken } from '../lib/token'

export type SSEEventHandler = (event: string, data: unknown) => void

export interface StreamOptions {
  path: string
  body?: unknown
  signal?: AbortSignal
  onEvent: SSEEventHandler
}

/** 解析一个 SSE 帧文本块。 */
function parseFrame(raw: string): { event: string; data: string } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of raw.split('\n')) {
    const trimmed = line.replace(/\r$/, '')
    if (trimmed.startsWith(':')) continue // 注释/心跳
    if (trimmed.startsWith('event:')) event = trimmed.slice(6).trim()
    else if (trimmed.startsWith('data:')) dataLines.push(trimmed.slice(5).replace(/^ /, ''))
  }
  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}

/**
 * 以 POST 打开 SSE 流并逐事件回调。
 * 返回时表示流已正常结束；抛出的错误表示没有得到任何有效事件就失败了。
 */
export async function streamPost({ path, body, signal, onEvent }: StreamOptions): Promise<void> {
  const token = getToken()

  let resp: Response
  try {
    resp = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new NetworkError()
  }

  if (!resp.ok) {
    let code = `HTTP_${resp.status}`
    let message = `请求失败（${resp.status}）`
    let detail: Record<string, unknown> = {}
    try {
      const parsed = await resp.json()
      code = parsed.code ?? code
      message = parsed.message ?? message
      detail = parsed.detail ?? {}
    } catch {
      /* 保留默认文案 */
    }
    throw new ApiError(resp.status, code, message, detail)
  }

  if (!resp.body) throw new NetworkError('当前浏览器不支持流式响应')

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以空行分帧；兼容 \r\n\r\n
      let boundary = buffer.search(/\r?\n\r?\n/)
      while (boundary !== -1) {
        const rawFrame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + (buffer[boundary] === '\r' ? 4 : 2))
        const frame = parseFrame(rawFrame)
        if (frame) {
          let payload: unknown = frame.data
          try {
            payload = JSON.parse(frame.data)
          } catch {
            /* 非 JSON 的 data 原样透传 */
          }
          onEvent(frame.event, payload)
        }
        boundary = buffer.search(/\r?\n\r?\n/)
      }
    }
    // 处理没有以空行结尾的最后一帧
    const tail = parseFrame(buffer)
    if (tail) {
      let payload: unknown = tail.data
      try {
        payload = JSON.parse(tail.data)
      } catch {
        /* 忽略 */
      }
      onEvent(tail.event, payload)
    }
  } finally {
    reader.releaseLock()
  }
}

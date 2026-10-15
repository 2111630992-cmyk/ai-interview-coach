/** HTTP 客户端：统一错误体、自动附带 token、401 全局登出。 */

import { getToken, setStoredUser, setToken } from '../lib/token'

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ??
  'http://localhost:8000/api/v1'

/** 后端统一错误体：{code, message, detail} */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: Record<string, unknown>

  constructor(status: number, code: string, message: string, detail: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }

  get isAuthError() {
    return this.status === 401
  }

  get isStateError() {
    return this.code === 'INTERVIEW_STATE_INVALID'
  }
}

/** 网络层错误（后端没起来 / 断网），与业务错误区分开，提示文案不同。 */
export class NetworkError extends Error {
  constructor(message = '无法连接到服务器，请确认后端已启动') {
    super(message)
    this.name = 'NetworkError'
  }
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getToken()
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(extra ?? {}),
  }
}

async function toApiError(resp: Response): Promise<ApiError> {
  let code = `HTTP_${resp.status}`
  let message = `请求失败（${resp.status}）`
  let detail: Record<string, unknown> = {}
  try {
    const body = await resp.json()
    if (body && typeof body === 'object') {
      code = body.code ?? code
      message = body.message ?? message
      detail = body.detail ?? {}
    }
  } catch {
    /* 非 JSON 响应，沿用默认文案 */
  }
  return new ApiError(resp.status, code, message, detail)
}

function handleAuthFailure(err: ApiError) {
  if (err.isAuthError) {
    setToken(null)
    setStoredUser(null)
    onUnauthorized?.()
  }
}

export interface RequestOptions {
  method?: string
  body?: unknown
  headers?: HeadersInit
  signal?: AbortSignal
  /** FormData 等已是最终形态的 body，跳过 JSON 序列化 */
  rawBody?: BodyInit
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, headers, signal, rawBody } = options

  const init: RequestInit = {
    method,
    headers: authHeaders(
      rawBody
        ? headers
        : {
            'Content-Type': 'application/json',
            ...(headers ?? {}),
          },
    ),
    signal,
  }

  if (rawBody !== undefined) init.body = rawBody
  else if (body !== undefined) init.body = JSON.stringify(body)

  let resp: Response
  try {
    resp = await fetch(`${API_BASE_URL}${path}`, init)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new NetworkError()
  }

  if (!resp.ok) {
    const apiError = await toApiError(resp)
    handleAuthFailure(apiError)
    throw apiError
  }

  if (resp.status === 204) return undefined as T
  const text = await resp.text()
  if (!text) return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    throw new ApiError(resp.status, 'BAD_JSON', '服务器返回了无法解析的数据')
  }
}

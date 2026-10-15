/** token 存取。独立成模块，避免 api 层反向依赖 store 造成循环导入。 */

const TOKEN_KEY = 'aicoach.token'
const USER_KEY = 'aicoach.user'

type Listener = () => void
const listeners = new Set<Listener>()

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* 隐私模式下 localStorage 可能不可用，静默降级为内存态 */
  }
  listeners.forEach((fn) => fn())
}

export function getStoredUser<T>(): T | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

export function setStoredUser(user: unknown | null) {
  try {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
    else localStorage.removeItem(USER_KEY)
  } catch {
    /* 同上 */
  }
}

/** 订阅 token 变化，401 时用于触发登出跳转。 */
export function subscribeToken(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

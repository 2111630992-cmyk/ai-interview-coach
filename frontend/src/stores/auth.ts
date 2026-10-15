import { create } from 'zustand'

import { fetchMe, loginAsGuest, login, register } from '../api/endpoints'
import type { UserPublic } from '../api/types'
import { getStoredUser, getToken, setStoredUser, setToken } from '../lib/token'

interface AuthState {
  user: UserPublic | null
  /** 首次校验 token 是否仍然有效期间为 false */
  ready: boolean
  loading: boolean
  bootstrap: () => Promise<void>
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, nickname: string) => Promise<void>
  continueAsGuest: () => Promise<void>
  signOut: () => void
}

function applySession(token: string, user: UserPublic, set: (p: Partial<AuthState>) => void) {
  setToken(token)
  setStoredUser(user)
  set({ user, ready: true })
}

export const useAuthStore = create<AuthState>((set) => ({
  // 先用本地缓存的用户信息渲染，避免刷新时闪一下登录页
  user: getStoredUser<UserPublic>(),
  ready: false,
  loading: false,

  bootstrap: async () => {
    if (!getToken()) {
      set({ ready: true, user: null })
      return
    }
    try {
      const user = await fetchMe()
      setStoredUser(user)
      set({ user, ready: true })
    } catch {
      // token 过期或被撤销：清理本地状态
      setToken(null)
      setStoredUser(null)
      set({ user: null, ready: true })
    }
  },

  signIn: async (email, password) => {
    set({ loading: true })
    try {
      const res = await login({ email, password })
      applySession(res.access_token, res.user, set)
    } finally {
      set({ loading: false })
    }
  },

  signUp: async (email, password, nickname) => {
    set({ loading: true })
    try {
      const res = await register({ email, password, nickname })
      applySession(res.access_token, res.user, set)
    } finally {
      set({ loading: false })
    }
  },

  continueAsGuest: async () => {
    set({ loading: true })
    try {
      const res = await loginAsGuest()
      applySession(res.access_token, res.user, set)
    } finally {
      set({ loading: false })
    }
  },

  signOut: () => {
    setToken(null)
    setStoredUser(null)
    set({ user: null })
  },
}))

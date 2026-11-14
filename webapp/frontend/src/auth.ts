import { reactive } from 'vue'
import { api, setCsrfToken } from './api'

type CsrfResponse = { authenticated: boolean; csrf_token: string }

export const auth = reactive({ ready: false, authenticated: false })

/** 화면이 처음 열릴 때 로그인 상태와 CSRF 토큰을 받아 온다. */
export async function refreshAuth(): Promise<void> {
  const res = await api<CsrfResponse>('/api/csrf')
  setCsrfToken(res.csrf_token)
  auth.authenticated = res.authenticated
  auth.ready = true
}

export async function login(password: string): Promise<void> {
  const res = await api<CsrfResponse>('/api/login', { json: { password } })
  setCsrfToken(res.csrf_token)
  auth.authenticated = true
}

export async function logout(): Promise<void> {
  await api('/api/logout', { method: 'POST' })
  await refreshAuth()
}

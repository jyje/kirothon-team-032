// 서버와 주고받는 fetch 래퍼. CSRF 토큰을 모든 쓰기 요청에 붙인다.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

let csrfToken = ''

export function setCsrfToken(token: string): void {
  csrfToken = token
}

export async function api<T = unknown>(
  path: string,
  init: { method?: string; json?: unknown; body?: BodyInit } = {},
): Promise<T> {
  const method = init.method ?? (init.json !== undefined || init.body ? 'POST' : 'GET')
  const headers: Record<string, string> = {}
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken
  let body: BodyInit | undefined = init.body
  if (init.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(init.json)
  }
  const res = await fetch(path, { method, headers, body, credentials: 'same-origin' })
  if (res.status === 204) return undefined as T
  const isJson = res.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await res.json() : null
  if (!res.ok) {
    const err = data?.error
    throw new ApiError(
      res.status,
      err?.code ?? 'http_error',
      err?.message ?? `요청에 실패했어요 (${res.status})`,
    )
  }
  return data as T
}

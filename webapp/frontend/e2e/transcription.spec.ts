import { expect, test } from '@playwright/test'
import { createEvent, login, record } from './session'

test('전사 결과를 저장하고 요약과 초안에 시간 구간 출처를 표시한다', async ({ page, context }) => {
  await context.setExtraHTTPHeaders({ 'X-Forwarded-For': '192.0.2.70' })
  await login(page)
  const event = await createEvent(page, '행사 전사')
  const { pathname } = new URL(event)
  const path = '/api' + pathname
  const { csrf_token: csrf } = await (await page.request.get('/api/csrf')).json()
  const headers = { 'X-CSRF-Token': csrf }
  const wav = Buffer.from('524946462600000057415645666d74201000000001000100401f0000803e00000200100064617461020000000000', 'hex')
  const uploaded = await page.request.post(path + '/assets', {
    headers,
    multipart: {
      kind: 'voice_memo', solo_voice: 'true',
      file: { name: '테스트.wav', mimeType: 'audio/wav', buffer: wav },
    },
  })
  expect(uploaded.status()).toBe(201)
  await page.goto(event + '#assets')
  await page.reload()
  await page.getByText('전사', { exact: true }).click()
  await page.getByRole('button', { name: '전사 시작', exact: true }).click()
  const locator = '00:00:00.100~00:00:01.500'
  await expect(page.getByText(locator, { exact: true })).toBeVisible()
  await expect(page.getByText(record, { exact: false })).toBeVisible()
  await expect(page.getByText('원본 삭제됨', { exact: true })).toBeVisible()
  const { id: assetId } = await uploaded.json()
  expect((await page.request.get(path + '/assets/' + assetId + '/file')).status()).toBe(404)

  await page.reload()
  await page.getByText('전사', { exact: true }).click()
  await expect(page.getByText(locator, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '전사 시작', exact: true })).toHaveCount(0)

  await page.goto(event + '#summary')
  await page.getByRole('button', { name: '요약 만들기', exact: true }).click()
  await expect(page.getByRole('list', { name: '출처' })).toContainText('테스트.wav ' + locator)

  await page.goto(event + '#draft')
  await page.getByRole('button', { name: '초안 만들기', exact: true }).click()
  const draft = page.getByRole('region', { name: '초안', exact: true })
  await expect(draft.getByText('테스트.wav ' + locator, { exact: false }).first()).toBeVisible()
})

test('행사 보관 설정을 새로고침 뒤에도 적용하고 전사 원본을 보존한다', async ({ page, context }) => {
  await context.setExtraHTTPHeaders({ 'X-Forwarded-For': '192.0.2.71' })
  await login(page)
  const event = await createEvent(page, '원본 보관')
  const path = '/api' + new URL(event).pathname
  await page.goto(event + '#assets')
  const retain = page.getByRole('checkbox', { name: '전사 후 음성 원본 보관', exact: true })
  await expect(retain).not.toBeChecked()
  await retain.check()
  await expect(page.getByText('원본 보관 설정을 저장했어요.', { exact: true })).toBeVisible()
  await page.reload()
  await expect(retain).toBeChecked()

  const { csrf_token: csrf } = await (await page.request.get('/api/csrf')).json()
  const wav = Buffer.from('524946462600000057415645666d74201000000001000100401f0000803e00000200100064617461020000000000', 'hex')
  const upload = await page.request.post(path + '/assets', {
    headers: { 'X-CSRF-Token': csrf },
    multipart: {
      kind: 'voice_memo', solo_voice: 'true',
      file: { name: '보관.wav', mimeType: 'audio/wav', buffer: wav },
    },
  })
  expect(upload.status()).toBe(201)
  await page.reload()
  await page.getByText('전사', { exact: true }).click()
  await page.getByRole('button', { name: '전사 시작', exact: true }).click()
  await expect(page.getByText('00:00:00.100~00:00:01.500', { exact: true })).toBeVisible()
  const fileLink = page.getByRole('link', { name: '녹음 내려받기', exact: true })
  const file = await page.request.get((await fileLink.getAttribute('href'))!)
  expect(file.status()).toBe(200)
  expect(await file.body()).toEqual(wav)
})

test('동의를 철회하면 이미 열었던 전사, 요약과 초안이 화면에서 사라진다', async ({ page, context }) => {
  await context.setExtraHTTPHeaders({ 'X-Forwarded-For': '192.0.2.72' })
  await login(page)
  const event = await createEvent(page, '녹음 동의 철회')
  const path = '/api' + new URL(event).pathname
  const { csrf_token: csrf } = await (await page.request.get('/api/csrf')).json()
  const headers = { 'X-CSRF-Token': csrf }
  const consent = await page.request.post(path + '/consents', { headers, form: {
    informed_all: 'true', can_document: 'true', no_outside_disclosure: 'true',
    obtained_on: '2026-11-16', method: '구두 동의',
  } })
  expect(consent.status()).toBe(201)
  const { id: consentId } = await consent.json()
  const wav = Buffer.from('524946462600000057415645666d74201000000001000100401f0000803e00000200100064617461020000000000', 'hex')
  const upload = await page.request.post(path + '/assets', {
    headers,
    multipart: {
      kind: 'recording', consent_id: consentId,
      file: { name: '철회 확인.wav', mimeType: 'audio/wav', buffer: wav },
    },
  })
  expect(upload.status()).toBe(201)
  const { id: assetId } = await upload.json()
  const raw = path + '/assets/' + assetId + '/file'
  const transcript = path + '/assets/' + assetId + '/transcript'
  expect((await page.request.get(raw)).status()).toBe(200)
  expect((await page.request.patch(path, { headers, data: { retain_audio: true } })).ok()).toBeTruthy()

  await page.goto(event + '#assets')
  await page.reload()
  await page.getByText('전사', { exact: true }).click()
  await page.getByRole('button', { name: '전사 시작', exact: true }).click()
  await expect(page.getByText('00:00:00.100~00:00:01.500', { exact: true })).toBeVisible()
  await page.goto(event + '#summary')
  const summary = page.getByRole('region', { name: 'AI 요약', exact: true })
  await summary.getByRole('button', { name: '요약 만들기', exact: true }).click()
  await expect(summary.getByText(record, { exact: true })).toBeVisible()
  await page.goto(event + '#draft')
  const draft = page.getByRole('region', { name: '초안', exact: true })
  await draft.getByRole('button', { name: '초안 만들기', exact: true }).click()
  await expect(draft.getByText(record, { exact: true })).toBeVisible()

  await page.goto(event + '#assets')
  await page.getByText('녹음 동의', { exact: true }).click()
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '2026-11-16 구두 동의 동의 철회' }).click()
  await expect(page.getByText('동의를 철회했어요.', { exact: true })).toBeVisible()
  await expect(page.getByText('녹음 동의가 철회됐어요', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '녹음 내려받기', exact: true })).toHaveCount(0)
  expect((await page.request.get(raw)).status()).toBe(403)
  expect((await page.request.get(transcript)).status()).toBe(403)

  await page.goto(event + '#summary')
  await expect(summary.getByText('녹음 동의가 철회돼 이전 요약을 열 수 없어요.', { exact: false })).toBeVisible()
  await expect(summary.getByText(record, { exact: true })).toHaveCount(0)
  await expect(summary.getByRole('button', { name: '요약 만들기', exact: true })).toBeEnabled()
  await page.goto(event + '#draft')
  await expect(draft.getByText('녹음 동의가 철회돼 이전 초안을 열 수 없어요.', { exact: false })).toBeVisible()
  await expect(draft.getByText(record, { exact: true })).toHaveCount(0)
  await expect(draft.getByRole('button', { name: '초안 만들기', exact: true })).toBeEnabled()
})

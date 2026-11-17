import { expect, test } from '@playwright/test'
import { createEvent, login } from './session'

test.use({ channel: 'chromium', launchOptions: { args: ['--use-fake-device-for-media-stream'] } })

test('동의 확인 후 마이크를 열고 화면을 이동하면 마이크를 닫는다', async ({ page, context }) => {
  await context.setExtraHTTPHeaders({ 'X-Forwarded-For': '192.0.2.67' })
  await context.grantPermissions(['microphone'])
  await page.addInitScript(() => {
    const originalStart = MediaRecorder.prototype.start
    MediaRecorder.prototype.start = function (timeslice) {
      delete document.documentElement.dataset.microphoneData
      this.addEventListener('dataavailable', event => {
        if (event.data.size > 0) document.documentElement.dataset.microphoneData = 'true'
      })
      originalStart.call(this, timeslice)
    }
    const originalStop = MediaStreamTrack.prototype.stop
    MediaStreamTrack.prototype.stop = function () {
      originalStop.call(this)
      if (this.kind === 'audio' && this.readyState === 'ended') {
        document.documentElement.dataset.microphoneReleased = 'true'
      }
    }
  })
  await login(page)
  const event = await createEvent(page, '마이크 녹음')
  const { pathname } = new URL(event)
  const { csrf_token: csrf } = await (await page.request.get('/api/csrf')).json()
  const headers = { 'X-CSRF-Token': csrf }
  await page.goto(event + '#assets')
  const start = page.getByRole('button', { name: '녹음 시작', exact: true })
  await expect(start).toBeDisabled()

  const consent = await page.request.post('/api' + pathname + '/consents', {
    headers,
    form: {
      informed_all: 'true', can_document: 'true', no_outside_disclosure: 'true',
      obtained_on: '2026-11-14', method: '브라우저 테스트 동의',
    },
  })
  expect(consent.status()).toBe(201)
  const { id } = await consent.json()
  await page.reload()
  const select = page.getByRole('combobox', { name: '사용할 녹음 동의', exact: true })
  await select.selectOption(id)
  await start.click()
  await expect(page.getByRole('status').filter({ hasText: /^녹음 중$/ })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-microphone-data', 'true')
  const nav = page.getByRole('navigation', { name: '작업 공간' })
  await nav.getByRole('link', { name: '필기', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-microphone-released', 'true')
  await nav.getByRole('link', { name: '자료', exact: true }).click()
  await expect(page.getByRole('status', { name: '' }).filter({ hasText: '녹음이 끝났어요.' })).toBeVisible()
  const save = page.getByRole('button', { name: '녹음 저장', exact: true })
  const uploaded = page.waitForResponse(res => res.url().endsWith('/assets') &&
    res.request().method() === 'POST')
  await save.click()
  expect((await uploaded).status()).toBe(201)
  await expect(page.getByText('녹음을 저장했어요.', { exact: true })).toBeVisible()
  const audio = page.getByRole('list', { name: '저장된 행사 녹음' })
    .getByRole('link', { name: '녹음 내려받기' })
  const file = await page.request.get((await audio.getAttribute('href'))!)
  expect(file.status()).toBe(200)
  const body = await file.body()
  expect(body.length).toBeGreaterThan(100)
  expect(body.subarray(0, 4).toString('hex')).toBe('1a45dfa3')

  await start.click()
  await expect(page.getByRole('status').filter({ hasText: /^녹음 중$/ })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-microphone-data', 'true')
  expect((await page.request.post(`/api/consents/${id}/revoke`, { headers })).status()).toBe(200)
  await page.getByRole('button', { name: '녹음 중지', exact: true }).click()
  const blocked = page.waitForResponse(res => res.url().endsWith('/assets') &&
    res.request().method() === 'POST')
  await save.click()
  expect((await blocked).status()).toBe(403)
  await expect(page.getByRole('alert')).toContainText('유효한 녹음 동의')
})

test('브라우저의 마이크 거부를 안내한다', async ({ page, context }) => {
  await context.setExtraHTTPHeaders({ 'X-Forwarded-For': '192.0.2.68' })
  await login(page)
  const event = await createEvent(page, '마이크 권한 거부')
  const { pathname, origin } = new URL(event)
  const { csrf_token: csrf } = await (await page.request.get('/api/csrf')).json()
  const consent = await page.request.post('/api' + pathname + '/consents', {
    headers: { 'X-CSRF-Token': csrf },
    form: {
      informed_all: 'true', can_document: 'true', no_outside_disclosure: 'true',
      obtained_on: '2026-11-14', method: '브라우저 테스트 동의',
    },
  })
  const cdp = await context.newCDPSession(page)
  const { targetInfo } = await cdp.send('Target.getTargetInfo')
  await cdp.send('Browser.setPermission', {
    permission: { name: 'microphone' }, setting: 'denied', origin,
    browserContextId: targetInfo.browserContextId,
  })
  expect(consent.status()).toBe(201)
  await page.goto(event + '#assets')
  await page.reload()
  await page.getByRole('combobox', { name: '사용할 녹음 동의', exact: true }).selectOption((await consent.json()).id)
  await page.getByRole('button', { name: '녹음 시작', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('마이크 권한이 거부됐어요')
})

test('녹음 저장 성공 응답을 잃어도 재시도하면 첨부가 하나만 남는다', async ({ page, context }) => {
  await context.setExtraHTTPHeaders({ 'X-Forwarded-For': '192.0.2.79' })
  await context.grantPermissions(['microphone'])
  await page.addInitScript(() => {
    const start = MediaRecorder.prototype.start
    MediaRecorder.prototype.start = function (timeslice) {
      this.addEventListener('dataavailable', event => {
        if (event.data.size) document.documentElement.dataset.microphoneData = 'true'
      })
      start.call(this, timeslice)
    }
  })
  await login(page)
  const event = await createEvent(page, '녹음 저장 재시도')
  const path = '/api' + new URL(event).pathname
  const { csrf_token: csrf } = await (await page.request.get('/api/csrf')).json()
  const consent = await page.request.post(path + '/consents', {
    headers: { 'X-CSRF-Token': csrf },
    form: {
      informed_all: 'true', can_document: 'true', no_outside_disclosure: 'true',
      obtained_on: '2026-11-17', method: '합성 음성 테스트',
    },
  })
  expect(consent.status()).toBe(201)
  await page.goto(event + '#assets')
  await page.reload()
  await page.getByRole('combobox', { name: '사용할 녹음 동의' }).selectOption((await consent.json()).id)
  await page.getByRole('button', { name: '녹음 시작', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-microphone-data', 'true')
  await page.getByRole('button', { name: '녹음 중지', exact: true }).click()

  let storedId = ''
  const matcher = '**' + path + '/assets'
  await page.route(matcher, async route => {
    if (route.request().method() !== 'POST') return route.continue()
    const stored = await route.fetch()
    expect(stored.status()).toBe(201)
    storedId = (await stored.json()).id
    await route.abort('connectionreset')
  })
  const save = page.getByRole('button', { name: '녹음 저장', exact: true })
  await save.click()
  await expect(page.getByRole('alert')).toContainText('녹음을 저장하지 못했어요.')
  await page.unroute(matcher)
  await save.click()
  await expect(page.getByText('녹음을 저장했어요.', { exact: true })).toBeVisible()

  const { items } = await (await page.request.get(path + '/assets')).json()
  expect(items.map((item: { id: string }) => item.id)).toEqual([storedId])
  const links = page.getByRole('list', { name: '저장된 행사 녹음' })
    .getByRole('link', { name: '녹음 내려받기' })
  await expect(links).toHaveCount(1)
  const response = await page.request.get((await links.getAttribute('href'))!)
  expect(response.status()).toBe(200)
  expect((await response.body()).subarray(0, 4).toString('hex')).toBe('1a45dfa3')
})

for (const hasAudio of [true, false]) {
  test(`마이크가 끊기면 ${hasAudio ? '중단 전 녹음을 저장할 수 있다' : '다시 녹음할 수 있다'}`, async ({ page, context }) => {
    await context.setExtraHTTPHeaders({ 'X-Forwarded-For': hasAudio ? '192.0.2.81' : '192.0.2.82' })
    await context.grantPermissions(['microphone'])
    await page.addInitScript(({ hasAudio }) => {
      const request = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
      navigator.mediaDevices.getUserMedia = async constraints => {
        const stream = await request(constraints)
        document.addEventListener('disconnect-test-microphone', () => {
          for (const track of stream.getAudioTracks()) {
            track.stop()
            track.dispatchEvent(new Event('ended'))
          }
        }, { once: true })
        return stream
      }
      const start = MediaRecorder.prototype.start
      MediaRecorder.prototype.start = function (timeslice) {
        if (hasAudio) {
          this.addEventListener('dataavailable', event => {
            if (event.data.size) document.documentElement.dataset.microphoneData = 'true'
          })
        } else {
          this.ondataavailable = null
        }
        start.call(this, timeslice)
      }
    }, { hasAudio })
    await login(page)
    const event = await createEvent(page, '마이크 중단')
    const path = '/api' + new URL(event).pathname
    const { csrf_token: csrf } = await (await page.request.get('/api/csrf')).json()
    const consent = await page.request.post(path + '/consents', {
      headers: { 'X-CSRF-Token': csrf },
      form: {
        informed_all: 'true', can_document: 'true', no_outside_disclosure: 'true',
        obtained_on: '2026-11-17', method: '합성 마이크 중단 테스트',
      },
    })
    expect(consent.status()).toBe(201)
    await page.goto(event + '#assets')
    await page.reload()
    const recording = page.getByRole('region', { name: '행사 녹음' })
    await recording.getByRole('combobox', { name: '사용할 녹음 동의' }).selectOption((await consent.json()).id)
    const start = recording.getByRole('button', { name: '녹음 시작', exact: true })
    const save = recording.getByRole('button', { name: '녹음 저장', exact: true })
    await start.click()
    await expect(recording.getByRole('status')).toHaveText('녹음 중')
    if (hasAudio) await expect(page.locator('html')).toHaveAttribute('data-microphone-data', 'true')
    await page.evaluate(() => document.dispatchEvent(new Event('disconnect-test-microphone')))

    if (hasAudio) {
      await expect(recording.getByRole('alert')).toContainText('중단 전까지 기록한 부분을 저장할 수 있어요.')
      await save.click()
      await expect(recording.getByRole('status')).toHaveText('녹음을 저장했어요.')
      await expect(page.getByRole('link', { name: '녹음 내려받기', exact: true })).toHaveCount(1)
    } else {
      await expect(recording.getByRole('alert')).toContainText('마이크를 확인하고 다시 녹음해 주세요.')
      await expect(save).toHaveCount(0)
      await start.click()
      await expect(recording.getByRole('status')).toHaveText('녹음 중')
      await expect(recording.getByRole('alert')).toHaveCount(0)
    }
  })
}

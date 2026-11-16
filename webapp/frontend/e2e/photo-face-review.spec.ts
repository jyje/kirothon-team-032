import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'
import { createEvent, login } from './session'

test('사진 후보가 없어도 영역을 추가하고 사진과 축소판을 교체한다', async ({ page, context }) => {
  await context.setExtraHTTPHeaders({ 'X-Forwarded-For': '192.0.2.74' })
  await login(page)
  const event = await createEvent(page, '얼굴 흐림 검토')
  await page.goto(event + '#assets')
  const server = fileURLToPath(new URL('../../src/', import.meta.url))
  const buffer = execFileSync('uv', [
    'run', '--frozen', 'python', '-c',
    'import sys; from tests.test_face_review import photo_fixture; sys.stdout.buffer.write(photo_fixture())',
  ], { cwd: server })
  const uploaded = page.waitForResponse(res => res.url().endsWith('/assets') &&
    res.request().method() === 'POST')
  await page.getByLabel('사진 올리기', { exact: true }).setInputFiles({
    name: '검토.png', mimeType: 'image/png', buffer,
  })
  const {id} = await (await uploaded).json()
  const path = '/api' + new URL(event).pathname + '/assets/' + id
  const previous = await (await page.request.get(path + '/thumbnail')).body()

  await page.getByText('얼굴 확인', { exact: true }).click()
  await expect(page.getByText(/선택한 영역이 없어요/)).toBeVisible()
  await page.getByRole('button', { name: '확인 완료', exact: true }).click()
  await page.getByText('얼굴 확인 완료', { exact: true }).click()
  await page.getByRole('button', { name: '영역 추가', exact: true }).click()
  const region = page.getByRole('group', { name: '영역 1', exact: true })
  await region.getByLabel('왼쪽 (%)', { exact: true }).fill('25')
  await page.getByRole('button', { name: '흐림 적용', exact: true }).click()
  await expect(page.getByText('얼굴 흐림 적용됨', { exact: true })).toBeVisible()
  const thumbnail = await (await page.request.get(path + '/thumbnail')).body()
  expect(thumbnail.equals(previous)).toBe(false)
  expect((await (await page.request.get(path + '/file')).body()).equals(buffer)).toBe(false)

  await page.reload()
  await expect(page.getByText('얼굴 흐림 적용됨', { exact: true })).toBeVisible()
})

import { execFileSync } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { expect, test } from '@playwright/test'
import { createEvent, login, record } from './session'

test('PPTX의 원래 슬라이드 번호를 출처에 표시하고 PDF도 첨부한다', async ({ page }) => {
  await login(page)
  await createEvent(page, '발표자료 업로드')
  const nav = page.getByRole('navigation', { name: '작업 공간' })
  await nav.getByRole('link', { name: '자료', exact: true }).click()
  const picker = page.getByLabel('발표자료(PDF, PPTX, 30MB까지)', { exact: true })
  const server = fileURLToPath(new URL('../../src/', import.meta.url))
  const fixture = (expression: string) => execFileSync('uv', [
    'run', '--frozen', 'python', '-c',
    `import sys; from tests.documents import make_pptx, make_pdf; sys.stdout.buffer.write(${expression})`,
  ], { cwd: server })
  const slides = fixture('make_pptx(["첫 슬라이드", "", "슬라이드 검증 문장"])')
  await picker.setInputFiles({
    name: 'slides.pptx',
    mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    buffer: slides,
  })
  const pptx = page.getByRole('listitem').filter({ hasText: 'slides.pptx' })
  await expect(pptx).toContainText('3페이지')
  await expect(pptx).toContainText('텍스트 2조각')
  const slidesLink = pptx.getByRole('link', { name: 'slides.pptx 내려받기', exact: true })
  await page.getByLabel('참고자료(PDF, TXT, MD)', { exact: true }).focus()
  await page.keyboard.press('Tab')
  await expect(slidesLink).toBeFocused()
  const [slidesDownload] = await Promise.all([
    page.waitForEvent('download'), page.keyboard.press('Enter'),
  ])
  expect(slidesDownload.suggestedFilename()).toBe('slides.pptx')
  expect(await readFile(await slidesDownload.path())).toEqual(slides)

  await nav.getByRole('link', { name: 'AI 요약', exact: true }).click()
  const summary = page.getByRole('region', { name: 'AI 요약' })
  await summary.getByRole('button', { name: '요약 만들기', exact: true }).click()
  await expect(summary.getByText('슬라이드 검증 문장', { exact: true })).toBeVisible()
  await expect(summary.getByRole('list', { name: '출처' })).toContainText('slides.pptx 슬라이드 3')

  await nav.getByRole('link', { name: '자료', exact: true }).click()
  await picker.setInputFiles({
    name: 'notes.pdf', mimeType: 'application/pdf', buffer: fixture('make_pdf(["PDF regression"])'),
  })
  const pdf = page.getByRole('listitem').filter({ hasText: 'notes.pdf' })
  await expect(pdf).toContainText('1페이지')
  await expect(pdf).toContainText('텍스트 1조각')

  const reference = Buffer.from('참고자료 원본을 내려받습니다.\n')
  await page.getByLabel('참고자료(PDF, TXT, MD)', { exact: true }).setInputFiles({
    name: '참고자료.txt', mimeType: 'text/plain', buffer: reference,
  })
  const referenceLink = page.getByRole('link', { name: '참고자료.txt 내려받기', exact: true })
  const [referenceDownload] = await Promise.all([
    page.waitForEvent('download'), referenceLink.click(),
  ])
  expect(referenceDownload.suggestedFilename()).toBe('참고자료.txt')
  expect(await readFile(await referenceDownload.path())).toEqual(reference)
})

test('템플릿을 저장하고 검토한 초안을 HTML과 Markdown으로 내려받는다', async ({
  page, context,
}, testInfo) => {
  await login(page)
  const title = '배포 밋업 <기록>'
  const event = await createEvent(page, title)
  const nav = page.getByRole('navigation', { name: '작업 공간' })
  const summary = page.getByRole('region', { name: 'AI 요약' })
  await nav.getByRole('link', { name: 'AI 요약', exact: true }).click()
  await summary.getByRole('button', { name: '요약 만들기', exact: true }).click()
  await expect(summary.getByRole('alert')).toHaveText('사용할 기록이 없어요. 메모나 자료를 추가해 주세요.')
  await nav.getByRole('link', { name: '필기', exact: true }).click()
  const note = page.getByPlaceholder('들으면서 적어 보세요')
  await note.fill(record)
  await note.press('Tab')
  await expect(page.getByText(/^저장됨/)).toBeVisible()
  await page.reload()
  await expect(note).toHaveValue(record)

  await nav.getByRole('link', { name: 'AI 요약', exact: true }).click()
  await summary.getByRole('button', { name: '요약 만들기', exact: true }).click()
  await expect(summary.getByText(record, { exact: true })).toBeVisible()
  await expect(summary.getByRole('list', { name: '출처' }).getByRole('listitem')).toHaveText(
    '메모 1번째 블록',
  )
  await nav.getByRole('link', { name: '템플릿', exact: true }).click()
  await expect(page.getByRole('heading', { name: '블로그', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '복제', exact: true }).click()
  await expect(page).toHaveURL(/\/templates\?template=.+/)
  const editor = page.url()
  const templateId = new URL(editor).searchParams.get('template')!
  const name = page.getByLabel('템플릿 이름', { exact: true })
  const firstSection = page.getByRole('group', { name: '섹션 1', exact: true })
  await name.fill('검토용 밋업 형식')
  await firstSection.getByLabel('섹션 제목').fill('배포 기록')
  await page.getByRole('button', { name: '템플릿 저장', exact: true }).click()
  await expect(page.getByText('템플릿을 저장했어요.')).toBeVisible()
  await page.reload()
  await expect(name).toHaveValue('검토용 밋업 형식')
  await expect(firstSection.getByLabel('섹션 제목')).toHaveValue('배포 기록')

  await page.goto(event + '#draft')
  await page.getByLabel('템플릿', { exact: true }).selectOption(templateId)
  const generatedPromise = page.waitForResponse(response =>
    response.request().method() === 'POST' && response.url().endsWith('/jobs'),
  )
  await page.getByRole('button', { name: '초안 만들기', exact: true }).click()
  const generated = await generatedPromise
  expect(generated.status()).toBe(202)
  const { id: jobId } = await generated.json()
  await page.reload()
  await expect(page.getByRole('heading', { name: '배포 기록', exact: true })).toBeVisible()
  const finished = await context.request.get(`/api/jobs/${jobId}`)
  const result = await finished.json()
  expect(result.status).toBe('done')
  const approve = page.getByRole('button', { name: /^승인하기/ })
  await expect(approve).toBeDisabled()
  await expect(page.getByRole('link', { name: 'HTML 내려받기' })).toHaveCount(0)
  for (const extension of ['md', 'html']) {
    const response = await context.request.get(`/api/drafts/${result.result_id}/export.${extension}`)
    expect(response.status()).toBe(409)
  }
  await page.getByRole('button', { name: '의견으로 유지', exact: true }).click()
  await expect(approve).toBeEnabled()
  const approval = page.waitForResponse(response => response.url().endsWith('/approve'))
  page.once('dialog', dialog => dialog.accept())
  await approve.click()
  const { review_seconds: seconds } = await (await approval).json()
  expect(Number.isInteger(seconds)).toBe(true)
  const elapsed = page.getByText(/마지막 기록부터 승인까지/)
  await expect(elapsed).toContainText(`${seconds % 60}초`)
  await page.reload()
  await expect(elapsed).toContainText(`${seconds % 60}초`)

  const htmlLink = page.getByRole('link', { name: 'HTML 내려받기', exact: true })
  const [html] = await Promise.all([page.waitForEvent('download'), htmlLink.click()])
  expect(html.suggestedFilename()).toBe('open-attendee-draft.html')
  const file = testInfo.outputPath('open-attendee-draft.html')
  await html.saveAs(file)

  const mdLink = page.getByRole('link', { name: '마크다운 내려받기', exact: true })
  const [markdown] = await Promise.all([page.waitForEvent('download'), mdLink.click()])
  expect(markdown.suggestedFilename()).toBe('open-attendee-draft.md')
  const contents = await readFile(await markdown.path(), 'utf8')
  expect(contents).toMatch(/^> 이 글은 AI가/)
  expect(contents).toContain('배포 비용이 40% 줄었다. (출처 미확인)')

  const exported = await context.newPage()
  await context.setOffline(true)
  await exported.goto(pathToFileURL(file).href)
  await expect(exported.getByRole('heading', { name: title, exact: true })).toBeVisible()
  await expect(exported.getByText('배포 비용이 40% 줄었다. (출처 미확인)', { exact: false })).toBeVisible()
  await expect(exported.locator('#source-1')).toHaveText('메모: 메모 1번째 블록')
  await exported.close()
  await context.setOffline(false)

  await page.goto(editor)
  await name.fill('바뀐 형식')
  await firstSection.getByLabel('섹션 제목').fill('바뀐 섹션')
  await page.getByRole('button', { name: '템플릿 저장', exact: true }).click()
  await expect(page.getByText('템플릿을 저장했어요.')).toBeVisible()
  await page.goto(event + '#draft')
  await expect(page.getByRole('heading', { name: '배포 기록', exact: true })).toBeVisible()
  await expect(page.getByText('템플릿 검토용 밋업 형식', { exact: false })).toBeVisible()
})

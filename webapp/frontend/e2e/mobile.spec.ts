import { expect, test } from '@playwright/test'
import { createEvent, login } from './session'

test('모바일에서 키보드로 사이드바를 열고 파일을 업로드한다', async ({ page }) => {
  await login(page)
  await createEvent(page, '모바일 업로드')
  await page.reload()
  const nav = page.getByRole('navigation', { name: '작업 공간' })
  const toggle = page.getByRole('button', { name: /메뉴 (열기|닫기)/ })
  await expect(nav).toBeHidden()
  await page.keyboard.press('Tab')
  await expect(toggle).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await page.keyboard.press('Tab')
  await expect(nav.getByRole('link', { name: '내 행사' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(toggle).toBeFocused()

  await page.keyboard.press('Enter')
  const assets = nav.getByRole('link', { name: '자료', exact: true })
  await assets.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: '사진', exact: true })).toBeVisible()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: '행사 삭제' })).toBeFocused()

  const uploadLabels = ['사진 올리기', '바로 찍기', '발표자료(PDF, 30MB까지)', '참고자료(PDF, TXT, MD)']
  for (const label of uploadLabels) {
    await page.keyboard.press('Tab')
    await expect(page.getByLabel(label, { exact: true })).toBeFocused()
  }
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.keyboard.press('Enter'),
  ])
  await chooser.setFiles({
    name: 'keyboard-reference.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('키보드로 선택한 참고자료입니다.'),
  })
  await expect(page.getByText('keyboard-reference.txt', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('keyboard-reference.txt', { exact: true })).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
  ).toBe(true)

  await toggle.click()
  await nav.getByRole('link', { name: 'AI 요약', exact: true }).click()
  const summary = page.getByRole('region', { name: 'AI 요약' })
  await summary.getByRole('button', { name: '요약 만들기', exact: true }).click()
  const source = summary.getByRole('list', { name: '출처' }).getByRole('listitem')
  await expect(source.getByText('참고자료', { exact: true })).toBeVisible()
  await expect(source).toContainText('keyboard-reference.txt')

  await toggle.click()
  await page.getByRole('button', { name: '로그아웃', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
})

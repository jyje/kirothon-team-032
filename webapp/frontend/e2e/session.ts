import { expect, type Page } from '@playwright/test'

export const record = '행사에서 배포 절차를 확인했어요.'

export async function login(page: Page) {
  await page.goto('/sessions')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('navigation', { name: '작업 공간' })).toHaveCount(0)
  await page.getByLabel('비밀번호').fill('local-browser-fixture')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page.getByRole('heading', { name: '내 행사', exact: true })).toBeVisible()
}

export async function createEvent(page: Page, title: string) {
  await page.getByLabel('행사 이름').fill(title)
  await page.getByRole('button', { name: '새 행사' }).click()
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  return page.url()
}

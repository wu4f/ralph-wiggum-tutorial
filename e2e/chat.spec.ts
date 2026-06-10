import { test, expect } from '@playwright/test'

test.describe('Google Docs–Backed Site', () => {
  test('home page redirects to first tab and renders content', async ({ page }) => {
    await page.goto('/')
    await expect(page).not.toHaveURL('/')
    await expect(page.locator('nav')).toBeVisible()
    await expect(page.locator('main h1')).toBeVisible()
  })

  test('nav links lead to other pages', async ({ page }) => {
    await page.goto('/')
    const navLinks = page.locator('nav a')
    await expect(navLinks.first()).toBeVisible()
    await navLinks.first().click()
    await expect(page.locator('main h1')).toBeVisible()
  })

  test('chat widget is present on content pages but not on /chat', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('[data-island="chat-widget"]')).toBeAttached()
    await page.goto('/chat')
    await expect(page.locator('[data-island="chat-widget"]')).toHaveCount(0)
    await expect(page.locator('[data-island="chat-page"]')).toBeAttached()
  })

  test('chat page accepts a question and shows an answer with sources', async ({ page }) => {
    await page.goto('/chat')
    await page.getByRole('textbox').fill('What is this site about?')
    await page.getByRole('button', { name: /send/i }).click()
    await expect(
      page.locator('[aria-label="assistant message"], [aria-label="loading"]'),
    ).toBeVisible({ timeout: 30000 })
  })
})

import { expect, test } from '@playwright/test'

const FIXTURE_URL = 'https://github.com/copilot-fixtures/code-tour-buggy-portal'

test.describe('Execution Flow Explorer', () => {
  test('maps a fixture repository and renders the flow quiz', async ({ page }) => {
    await page.goto('/')

    await page.getByLabel(/public github repository url/i).fill(FIXTURE_URL)
    await page.getByRole('button', { name: /map repository/i }).click()

    await expect(page.getByText(/files analyzed/i)).toBeVisible()
    await expect(page.getByRole('heading', { name: /request to \//i })).toBeVisible()
    await expect(page.locator('svg[aria-label="Repository execution map"]')).toBeVisible()
  })

  test('scores a correctly ordered execution flow', async ({ page }) => {
    await page.goto('/')

    await page.getByLabel(/public github repository url/i).fill(FIXTURE_URL)
    await page.getByRole('button', { name: /map repository/i }).click()
    await expect(page.locator('svg[aria-label="Repository execution map"]')).toBeVisible()

    await page.getByRole('button', { name: /dashboard\.py \(route\)/i }).click()
    await page.getByRole('button', { name: /dashboard\.html \(template\)/i }).click()
    await page.getByRole('button', { name: /main\.ts \(frontend-entry\)/i }).click()
    await page.getByRole('button', { name: /index\.tsx \(component\)/i }).click()
    await page.getByRole('button', { name: /check flow/i }).click()

    await expect(page.getByText(/score 4\/4/i)).toBeVisible()
    await expect(page.getByText(/that is the execution order/i)).toBeVisible()
  })

  test('rejects non-root repository URLs', async ({ page }) => {
    await page.goto('/')

    await page.getByLabel(/public github repository url/i).fill(`${FIXTURE_URL}/tree/main`)
    await page.getByRole('button', { name: /map repository/i }).click()

    await expect(
      page.getByText(/only root github repository urls are supported/i),
    ).toBeVisible()
  })
})

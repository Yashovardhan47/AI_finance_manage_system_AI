import { expect, test } from '@playwright/test'

test('user completes the financial decision-to-outcome workflow', async ({ page }) => {
  const browserErrors = []
  page.on('pageerror', (error) => browserErrors.push(error.message))

  await page.goto('/')
  await page.getByRole('button', { name: 'Open your workspace' }).click()
  await page.getByLabel('Full name').fill('Financial Operations E2E User')
  await page.getByLabel('Email address').fill(`financial-ops-e2e-${Date.now()}@example.com`)
  await page.getByLabel('Password').fill('SecurePass123')
  await page.getByRole('button', { name: 'Create account' }).click()

  await page.getByRole('button', { name: /Autopilot/ }).click()
  await expect(page.getByRole('heading', { name: 'Financial Autopilot' })).toBeVisible()
  await page.getByRole('button', { name: 'Load secure demo' }).click()
  await expect(page.getByText('A realistic obligation graph and decision inbox are ready.')).toBeVisible()
  await expect(page.locator('.decision-card')).toHaveCount(5)
  await expect(page.locator('.category-nodes article').first()).toBeVisible()

  await page.getByLabel('Autonomy level').selectOption('prepare')
  await page.getByLabel('Preparation limit').fill('100000')
  await page.getByRole('button', { name: 'Save policy' }).click()
  await expect(page.getByText('Autopilot policy saved. No payment authority was changed.')).toBeVisible()

  await page.getByLabel('Decision name').fill('E2E monthly decision')
  await page.getByLabel('Amount').fill('1200')
  await page.getByRole('button', { name: 'Simulate 90-day impact' }).click()
  await expect(page.locator('.scenario-result')).toBeVisible()

  await page.getByRole('button', { name: 'Approve' }).first().click()
  await expect(page.getByText('Decision approved. The action is prepared within your policy boundary.')).toBeVisible()
  await expect(page.getByText('Ready For Handoff')).toBeVisible()

  await page.getByText('+ Add obligation').click()
  await page.getByPlaceholder('Obligation name').fill('E2E membership')
  await page.getByPlaceholder('Provider or counterparty').fill('E2E Provider')
  await page.getByPlaceholder('Amount').fill('499')
  await page.getByRole('button', { name: 'Add and analyze' }).click()
  await expect(page.getByText('Obligation added and included in the 90-day forecast.')).toBeVisible()
  await expect(page.getByText('E2E membership')).toBeVisible()

  await page.getByRole('button', { name: 'Flag mismatch' }).first().click()
  await expect(page.getByText('Mismatch recorded. An exception case was opened without assuming success.')).toBeVisible()
  await expect(page.getByText('Provider Outcome Mismatch')).toBeVisible()
  await page.getByRole('button', { name: 'Resolve' }).click()
  await expect(page.getByText('Exception resolved with an audit record.')).toBeVisible()

  expect(browserErrors).toEqual([])
})

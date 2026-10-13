import { expect, test } from '@playwright/test'

test('operator completes the billing lifecycle workspace', async ({ page }) => {
  const browserErrors = []
  page.on('pageerror', (error) => browserErrors.push(error.message))

  await page.goto('/')
  await page.getByRole('button', { name: 'Sign in / create account' }).click()
  await page.getByLabel('Full name').fill('Billing E2E Operator')
  await page.getByLabel('Email address').fill(`billing-e2e-${Date.now()}@example.com`)
  await page.getByLabel('Password').fill('SecurePass123')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()

  await expect(page).toHaveURL('http://localhost:4173/home')
  await expect(page.getByText('Your financial home')).toBeVisible()
  await page.getByRole('button', { name: /Billing ops/ }).click()
  await expect(page.getByRole('heading', { name: 'Billing operations' })).toBeVisible()
  await page.getByRole('button', { name: 'Load live demo' }).click()
  await expect(page.getByText('A realistic billing workspace is ready to explore.')).toBeVisible()
  await expect(page.getByText('Monthly recurring revenue')).toBeVisible()
  await expect(page.locator('.recharts-wrapper')).toHaveCount(3)

  await page.getByRole('button', { name: 'Subscriptions', exact: true }).click()
  await expect(page.locator('.subscription-ops-card')).toHaveCount(4)
  const acme = page.locator('.subscription-ops-card').filter({ hasText: 'Acme Analytics' })
  await acme.getByRole('button', { name: 'Pause' }).click()
  await expect(acme.getByText('Paused')).toBeVisible()
  await acme.getByRole('button', { name: 'Resume' }).click()
  await expect(acme.getByText('Active')).toBeVisible()

  await page.getByRole('button', { name: 'Invoices', exact: true }).click()
  await expect(page.locator('.invoice-row')).toHaveCount(8)
  await page.locator('.invoice-link').first().click()
  await expect(page.locator('.invoice-lines')).toBeVisible()
  await expect(page.getByRole('link', { name: 'PDF' }).first()).toHaveAttribute('href', /\/billing\/invoices\/\d+\/pdf/)

  await page.getByRole('button', { name: 'Recovery', exact: true }).click()
  await expect(page.getByText('Day 1 · 3 · 7 retry queue')).toBeVisible()
  await expect(page.locator('.retry-row')).toHaveCount(3)

  await page.getByRole('button', { name: 'Incidents & alerts', exact: true }).click()
  await expect(page.getByText('Exceptions requiring attention')).toBeVisible()
  await expect(page.locator('.incident-row')).toHaveCount(1)
  await expect(page.getByText('Payment failed for')).toBeVisible()
  await page.locator('.incident-row').first().getByRole('button', { name: 'Acknowledge' }).click()
  await expect(page.getByText('Incident acknowledged.')).toBeVisible()
  await expect(page.locator('.incident-row').first().getByText('Acknowledged')).toBeVisible()
  await page.getByRole('button', { name: 'Save notification policy' }).click()
  await expect(page.getByText('Notification channels and escalation rules updated.')).toBeVisible()

  await page.getByRole('button', { name: 'Catalog & customers' }).click()
  await page.getByRole('button', { name: '+ Billing plan' }).click()
  await page.getByLabel('Plan code').fill(`e2e-${Date.now()}`)
  await page.getByLabel('Name').fill('E2E Verified Plan')
  await page.getByLabel('Price').fill('2499')
  await page.getByRole('button', { name: 'Create plan' }).click()
  await expect(page.getByText('Billing plan created.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'E2E Verified Plan' })).toBeVisible()

  await page.getByRole('button', { name: 'Tax & audit' }).click()
  await expect(page.getByText('Tax rates & summary')).toBeVisible()
  await expect(page.locator('.audit-ops-row').first()).toBeVisible()
  expect(browserErrors).toEqual([])
})

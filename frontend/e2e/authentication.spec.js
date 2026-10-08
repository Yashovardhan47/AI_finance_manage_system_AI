import { expect, test } from '@playwright/test'

test('password registration, JWT session, logout, and login work end to end', async ({ page }) => {
  const browserErrors = []
  page.on('pageerror', (error) => browserErrors.push(error.message))
  const email = `auth-e2e-${Date.now()}@example.com`

  await page.goto('/')
  await page.getByRole('button', { name: 'Open your workspace' }).click()
  await expect(page.getByRole('button', { name: 'Google sign-in not configured' })).toBeDisabled()
  await page.getByLabel('Full name').fill('Authentication E2E User')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password').fill('SecurePass123')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByText(email)).toBeVisible()

  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('button', { name: 'Open your workspace' })).toBeVisible()
  await page.getByRole('button', { name: 'Open your workspace' }).click()
  await page.getByRole('button', { name: 'Log in' }).click()
  await page.getByLabel('Email address').fill(email.toUpperCase())
  await page.getByLabel('Password').fill('SecurePass123')
  await page.locator('.auth-form').getByRole('button', { name: 'Log in' }).click()
  await expect(page.getByText(email)).toBeVisible()
  expect(browserErrors).toEqual([])
})

test('Google callback cancellation returns readable recovery UI', async ({ page }) => {
  await page.goto('/auth/callback?status=error&error=google_access_denied')
  await expect(page.getByText('Google sign-in was cancelled. No BillFlow account was changed.')).toBeVisible()
  await expect(page).toHaveURL('http://localhost:4173/')
})

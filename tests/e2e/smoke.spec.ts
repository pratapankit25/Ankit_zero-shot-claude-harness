/**
 * Smoke: page loads styled, upload works, profile renders, stubs are labelled.
 * No LLM required — runs in any environment against the live server.
 */
import { expect, test } from '@playwright/test'
import path from 'path'

const SAMPLES = path.join(__dirname, '..', 'fixtures', 'samples')

test.beforeEach(async ({ request }) => {
  // live-server tests: start from an empty library every time
  const r = await request.get('/datasets')
  for (const d of (await r.json()).data ?? []) {
    await request.delete(`/datasets/${d.id}`)
  }
})

test('workspace loads, styled, with empty states', async ({ page }) => {
  await page.goto('/app/')
  await expect(page.getByRole('heading', { name: 'UP Police Data Analyst' })).toBeVisible()

  // styled-render gate: the sidebar must actually be styled (navy command-center
  // theme per spec/ui.md Visual Identity) — an unstyled page has a transparent aside
  const aside = page.locator('aside')
  await expect(aside).toBeVisible()
  // resolve the computed color to rgb via canvas so the assertion survives
  // Tailwind emitting oklch(); unstyled = transparent, which fails both checks
  const [r, g, b, a] = await aside.evaluate(el => {
    const ctx = document.createElement('canvas').getContext('2d')!
    ctx.fillStyle = getComputedStyle(el).backgroundColor
    ctx.fillRect(0, 0, 1, 1)
    return Array.from(ctx.getImageData(0, 0, 1, 1).data)
  })
  expect(a).toBe(255)                     // painted, not transparent
  expect(r + g + b).toBeLessThan(150)     // dark navy per spec/ui.md Visual Identity

  // designed empty states, not blank panels
  await expect(page.getByText('No datasets yet')).toBeVisible()
  await expect(page.getByText('Two steps:')).toBeVisible()

  // all phases real: sources + scheduled-briefs sections replace the old stubs
  await expect(page.getByTestId('sources-section')).toBeVisible()
  await expect(page.getByTestId('reports-section')).toBeVisible()
  await page.getByTestId('sources-section').locator('summary').click()
  await expect(page.getByText(/Not configured|Connected to/)).toBeVisible()
})

test('uploading CSVs shows profiles; delete removes', async ({ page }) => {
  await page.goto('/app/')
  await page.getByTestId('file-input').setInputFiles([
    path.join(SAMPLES, 'personnel.csv'),
    path.join(SAMPLES, 'fir_records.csv'),
  ])

  const cards = page.getByTestId('dataset-card')
  await expect(cards).toHaveCount(2, { timeout: 60_000 })
  await expect(page.getByText('24 rows × 4 cols')).toBeVisible()
  await expect(page.getByText('3,200 rows × 8 cols')).toBeVisible()

  // profile disclosure lists columns and types
  await cards.filter({ hasText: 'personnel' }).getByText('Profile').click()
  await expect(page.getByText('sanctioned_strength')).toBeVisible()

  // two-step delete with a named confirmation
  await cards.filter({ hasText: 'personnel' }).getByLabel('Delete personnel').click()
  await expect(page.getByText('Removes “personnel” and its data')).toBeVisible()
  await cards.filter({ hasText: 'personnel' }).getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(cards).toHaveCount(1)
})

test('a bad file shows a human error, sibling still loads', async ({ page }) => {
  await page.goto('/app/')
  await page.getByTestId('file-input').setInputFiles([
    { name: 'book.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('PK\x03\x04' + '\x00'.repeat(64), 'binary') },
    { name: 'ok.csv', mimeType: 'text/csv', buffer: Buffer.from('a,b\n1,2\n') },
  ])
  const cards = page.getByTestId('dataset-card')
  await expect(cards).toHaveCount(2, { timeout: 30_000 })
  await expect(cards.getByText(/binary file/)).toBeVisible()
  await expect(page.getByText('1 rows × 2 cols')).toBeVisible()
})

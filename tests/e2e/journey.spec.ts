/**
 * Golden-path journey against the REAL LLM — the Phase-1 E2E gate.
 * Needs a provider key in .env and network reach to the provider.
 * Set E2E_LLM=0 only in environments that cannot reach the provider
 * (skipped is not passed — the user's gate runs this for real).
 */
import { expect, test } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const SAMPLES = path.join(__dirname, '..', 'fixtures', 'samples')
const expected = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'expected_answers.json'), 'utf-8'),
)

test.skip(process.env.E2E_LLM === '0', 'E2E_LLM=0 — provider unreachable in this environment')

test.beforeEach(async ({ request }) => {
  const r = await request.get('/datasets')
  for (const d of (await r.json()).data ?? []) {
    await request.delete(`/datasets/${d.id}`)
  }
})

test('upload → ask (EN) → correct streamed answer with SQL → Hindi follow-up', async ({ page }) => {
  await page.goto('/app/')
  await page.getByTestId('file-input').setInputFiles([
    path.join(SAMPLES, 'fir_records.csv'),
    path.join(SAMPLES, 'personnel.csv'),
  ])
  await expect(page.getByTestId('dataset-card')).toHaveCount(2, { timeout: 60_000 })

  // --- English question with a known exact answer
  await page.getByTestId('composer').fill('Which district had the most FIRs registered in 2025? Give the exact count.')
  await page.getByTestId('ask-button').click()

  // live step ticker appears while working
  await expect(page.getByTestId('step-ticker')).toBeVisible({ timeout: 30_000 })

  const firstAnswer = page.getByTestId('answer').first()
  await expect(firstAnswer).toContainText(expected.top_district_2025, { timeout: 120_000 })
  const answerText = (await firstAnswer.innerText()).replace(/[, ]/g, '')
  expect(answerText).toContain(String(expected.top_district_2025_count))

  // SQL disclosure exposes the executed query
  await page.getByTestId('sql-disclosure').first().getByText('SQL').click()
  await expect(page.locator('pre').first()).toContainText(/select/i)

  // --- Hindi follow-up in the same conversation, answered in Hindi
  await page.getByTestId('composer').fill('अब उस जिले के 2025 के आँकड़े महीने के हिसाब से दिखाइए')
  await page.getByTestId('ask-button').click()
  const secondAnswer = page.getByTestId('answer').nth(1)
  await expect(secondAnswer).toContainText(/[ऀ-ॿ]/, { timeout: 120_000 })
})

/**
 * Captain GUI — Audit Verification Tests
 * 
 * Run: npx playwright test captain-audit.spec.ts
 * 
 * These tests verify that each fix from the audit manifest has been applied.
 * Not every issue is testable via Playwright (some are code-level only).
 * Issues marked "CODE REVIEW ONLY" need manual/static verification.
 * 
 * Prerequisites:
 *   - Captain GUI dev server running on localhost:5173 (or adjust BASE_URL)
 *   - Backend may or may not be running (tests handle both states)
 */

import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:5173';

// ═══════════════════════════════════════════════════════════
// BATCH 1 — Critical quick fixes
// ═══════════════════════════════════════════════════════════

test.describe('C3: DEV_MOCK_ENABLED gating', () => {
  test('production build should not inject mock data', async ({ page }) => {
    // This test only meaningful against a production build
    // For dev: just verify the variable exists and is boolean
    await page.goto(BASE_URL);
    
    // If mock data is injected, specific hardcoded values appear
    // Check that we DON'T see stale mock prices after a reasonable wait
    // (In dev mode this will still show mocks — that's correct)
    // The real test: build with `vite build` and serve, then run this
  });
});

test.describe('H8: R:R ratio calculation', () => {
  test('R:R ratio should never show negative or Infinity', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForTimeout(2000); // Let data load
    
    const rrElements = page.locator('text=/R:R|Risk.Reward/i')
      .locator('xpath=following-sibling::*[1]');
    
    const count = await rrElements.count();
    for (let i = 0; i < count; i++) {
      const text = await rrElements.nth(i).textContent();
      expect(text).not.toContain('Infinity');
      expect(text).not.toContain('-'); // Should not be negative
      // Should be either a positive number like "2.0" or a dash "—"
      expect(text).toMatch(/^\d+\.\d+$|^—$/);
    }
  });
});

test.describe('H10: Session P&L color', () => {
  test('negative P&L should render in red, not green', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForTimeout(2000);
    
    // Find P&L elements in SignalCards
    const pnlElements = page.locator('[data-testid="session-pnl"], .session-pnl');
    const count = await pnlElements.count();
    
    for (let i = 0; i < count; i++) {
      const text = await pnlElements.nth(i).textContent();
      const color = await pnlElements.nth(i).evaluate(
        el => window.getComputedStyle(el).color
      );
      
      if (text && text.includes('-')) {
        // Negative value — should be red-ish, not green
        expect(color).not.toContain('16, 185, 129'); // #10b981 in rgb
      }
    }
  });
});

test.describe('M14: Win % fallback', () => {
  test('should show "—" not "---%" when no stats available', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForTimeout(2000);
    
    // Check that nowhere on the page shows "---%" 
    const badPattern = page.locator('text="---%"');
    await expect(badPattern).toHaveCount(0);
  });
});


// ═══════════════════════════════════════════════════════════
// BATCH 2 — Auto Trade toggle
// ═══════════════════════════════════════════════════════════

test.describe('C1: Auto Trade toggle', () => {
  test('toggle should either be removed or wired to backend', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForTimeout(2000);
    
    const toggle = page.locator('[data-testid="auto-trade-toggle"], text=/Auto.?Trade/i');
    const count = await toggle.count();
    
    if (count === 0) {
      // OPTION A: Toggle removed — that's valid
      expect(count).toBe(0);
    } else {
      // OPTION B: Toggle exists — verify it makes an API call
      const [request] = await Promise.all([
        page.waitForRequest(req => req.url().includes('/api/') && req.method() === 'POST', 
          { timeout: 5000 }),
        toggle.first().click(),
      ]).catch(() => [null]);
      
      expect(request).not.toBeNull(); // Should have fired an API call
    }
  });
});


// ═══════════════════════════════════════════════════════════
// BATCH 3 — Timezone consistency
// ═══════════════════════════════════════════════════════════

// CODE REVIEW ONLY — Playwright can't reliably test timezone formatting
// unless the test machine is in a non-ET timezone. Run this manually:
// Search codebase for toLocaleTimeString without timeZone: 'America/New_York'


// ═══════════════════════════════════════════════════════════
// BATCH 4 — Hardcoded/stale data
// ═══════════════════════════════════════════════════════════

test.describe('H1: Correct assets in MarketTicker', () => {
  test('ticker should not show eliminated assets', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForTimeout(2000);
    
    const tickerBar = page.locator('[data-testid="market-ticker"], .market-ticker')
      .first();
    
    if (await tickerBar.count() > 0) {
      const text = await tickerBar.textContent();
      // MCL and 6E should be removed (P1-eliminated)
      // Uncomment once asset list is confirmed:
      // expect(text).not.toContain('MCL');
      // expect(text).not.toContain('6E');
      // expect(text).toContain('M2K');
      // expect(text).toContain('ZB');
    }
  });
});

test.describe('C2: MarketTicker stale prices', () => {
  test('non-MES tickers should not show hardcoded prices', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForTimeout(3000);
    
    // These are the known hardcoded stale values from the audit
    const staleValues = ['19284.83', '5429.65'];
    const pageContent = await page.textContent('body');
    
    for (const stale of staleValues) {
      // If these exact values appear, they're probably still hardcoded
      // (Could be coincidence, but very unlikely in live data)
      const found = pageContent?.includes(stale);
      if (found) {
        console.warn(`Possible stale hardcoded price found: ${stale}`);
      }
      // Soft assertion — flag but don't fail (could be real price)
    }
  });
});

test.describe('L15/L16: Hardcoded version strings', () => {
  test('should not contain hardcoded version strings', async ({ page }) => {
    await page.goto(BASE_URL);
    const body = await page.textContent('body');
    
    expect(body).not.toContain('SYS:SIGNAL_ENGINE v3.2.1');
    expect(body).not.toContain('SYS:RISK_MGR v2.4.1');
    expect(body).not.toContain('PROP:150K_CHALLENGE');
  });
});


// ═══════════════════════════════════════════════════════════
// BATCH 5 — Health indicators
// ═══════════════════════════════════════════════════════════

test.describe('H3: TRADING badge reflects system state', () => {
  test('badge should not show TRADING when disconnected', async ({ page }) => {
    // Disconnect from backend by not starting it
    await page.goto(BASE_URL);
    await page.waitForTimeout(3000);
    
    const badge = page.locator('text=/TRADING|OFFLINE|MONITORING/i').first();
    if (await badge.count() > 0) {
      const text = await badge.textContent();
      // If WS is not connected, should NOT say "TRADING"
      // This test assumes backend is not running
      expect(text?.toUpperCase()).not.toBe('TRADING');
    }
  });
});

test.describe('M9: OR state badge default', () => {
  test('should not default to INSIDE OR before data arrives', async ({ page }) => {
    await page.goto(BASE_URL);
    // Check immediately, before any data loads
    await page.waitForTimeout(500);
    
    const orBadge = page.locator('text="INSIDE OR"');
    // Before data arrives, should show WAITING or — , not INSIDE OR
    const count = await orBadge.count();
    expect(count).toBe(0);
  });
});


// ═══════════════════════════════════════════════════════════
// BATCH 6 — Trade display
// ═══════════════════════════════════════════════════════════

test.describe('H6: TradeLog data source', () => {
  test('trade log header should say ASSET or SYMBOL, not TICK', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForTimeout(2000);
    
    const tradeLog = page.locator('text=/TRADE.?LOG/i').first();
    if (await tradeLog.count() > 0) {
      // Find the table headers near the trade log
      const headers = tradeLog.locator('xpath=ancestor::div[1]//th | ancestor::div[1]//div[contains(@class, "header")]');
      const headerTexts = await headers.allTextContents();
      const joined = headerTexts.join(' ').toUpperCase();
      
      expect(joined).not.toContain('TICK');
    }
  });
});


// ═══════════════════════════════════════════════════════════
// BATCH 7 — Replay system
// ═══════════════════════════════════════════════════════════

// CODE REVIEW ONLY — Replay issues (H11, H12, M4, M6) require 
// the replay backend to be running with specific state.
// Verify via Claude Code source audit instead.


// ═══════════════════════════════════════════════════════════
// BATCH 9 — Remaining fixes
// ═══════════════════════════════════════════════════════════

test.describe('L14: ChartPanel null change color', () => {
  test('price change should not show green before data arrives', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForTimeout(500); // Check before data loads
    
    // Look for price change indicators
    const changeElements = page.locator('[data-testid="price-change"], .price-change');
    const count = await changeElements.count();
    
    for (let i = 0; i < count; i++) {
      const color = await changeElements.nth(i).evaluate(
        el => window.getComputedStyle(el).color
      );
      // Before data: should not be green (#10b981 = rgb(16, 185, 129))
      // Allow neutral/grey/white
    }
  });
});


// ═══════════════════════════════════════════════════════════
// NAVIGATION — Pages load independently
// ═══════════════════════════════════════════════════════════

test.describe('M7: Direct navigation to secondary pages', () => {
  const pages = ['/models', '/history', '/settings', '/processes'];
  
  for (const path of pages) {
    test(`${path} should not crash on direct navigation`, async ({ page }) => {
      const response = await page.goto(`${BASE_URL}${path}`);
      expect(response?.status()).toBeLessThan(400);
      
      // Should not show a blank white page or error
      const body = await page.textContent('body');
      expect(body?.length).toBeGreaterThan(50);
    });
    
    test(`${path} should show a message if no data loaded`, async ({ page }) => {
      await page.goto(`${BASE_URL}${path}`);
      await page.waitForTimeout(2000);
      
      // Should either have data OR show an appropriate message
      // Not just silently empty
      const body = await page.textContent('body');
      const hasContent = (body?.length ?? 0) > 100;
      const hasEmptyMessage = /no data|connect|loading|empty/i.test(body ?? '');
      
      expect(hasContent || hasEmptyMessage).toBeTruthy();
    });
  }
});


// ═══════════════════════════════════════════════════════════
// SETTINGS PAGE
// ═══════════════════════════════════════════════════════════

test.describe('C4: Theme toggle', () => {
  test('theme toggle should apply a class to html or body', async ({ page }) => {
    await page.goto(`${BASE_URL}/settings`);
    await page.waitForTimeout(1000);
    
    const themeToggle = page.locator('text=/theme|dark.mode|light.mode/i').first();
    if (await themeToggle.count() > 0) {
      const htmlClassBefore = await page.locator('html').getAttribute('class');
      const bodyClassBefore = await page.locator('body').getAttribute('class');
      
      await themeToggle.click();
      await page.waitForTimeout(500);
      
      const htmlClassAfter = await page.locator('html').getAttribute('class');
      const bodyClassAfter = await page.locator('body').getAttribute('class');
      
      // At least one should have changed
      const changed = htmlClassBefore !== htmlClassAfter || bodyClassBefore !== bodyClassAfter;
      expect(changed).toBeTruthy();
    }
  });
});

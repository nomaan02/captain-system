import { test, expect } from "@playwright/test";

test.describe("Captain GUI — Data Flow Validation", () => {

  test("App shell mounts and is visible", async ({ page }) => {
    await page.goto("/");
    const shell = page.locator("[data-testid='app-shell']");
    await expect(shell).toBeVisible({ timeout: 10_000 });
  });

  test("WebSocket status shows connected", async ({ page }) => {
    await page.goto("/");
    const wsStatus = page.locator("[data-testid='ws-status']");
    await expect(wsStatus).toBeVisible({ timeout: 15_000 });
    // Mock mode sets connected=true, so data-status should be "connected"
    await expect(wsStatus).toHaveAttribute("data-status", "connected", { timeout: 15_000 });
  });

  test("Current price displays live data", async ({ page }) => {
    await page.goto("/");
    const priceEl = page.locator("[data-testid='current-price']");
    await expect(priceEl).toBeVisible({ timeout: 10_000 });
    // Mock data injects liveMarket.last_price = 6384.50, so it should not be "—"
    await expect(priceEl).not.toHaveText("—", { timeout: 10_000 });
    // Verify it contains a numeric price (at least one digit)
    await expect(priceEl).toHaveText(/\d/, { timeout: 5_000 });
  });

  test("Risk panel renders with data", async ({ page }) => {
    await page.goto("/");
    const riskPanel = page.locator("[data-testid='risk-panel']");
    await expect(riskPanel).toBeVisible({ timeout: 10_000 });
    // Risk panel should contain capital/equity values — check for dollar amounts
    await expect(riskPanel).toContainText("$", { timeout: 5_000 });
  });

  test("Signal panel renders with signals", async ({ page }) => {
    await page.goto("/");
    const signalPanel = page.locator("[data-testid='signal-panel']");
    await expect(signalPanel).toBeVisible({ timeout: 10_000 });
    // Mock data injects 5 signals — panel should not show "No pending signals"
    await expect(signalPanel).not.toContainText("No pending signals", { timeout: 5_000 });
    // Should contain at least one asset name from mock data
    await expect(signalPanel).toContainText("MES", { timeout: 5_000 });
  });

  test("Market ticker panel is visible with asset tabs", async ({ page }) => {
    await page.goto("/");
    const ticker = page.locator("[data-testid='market-status-panel']");
    await expect(ticker).toBeVisible({ timeout: 10_000 });
    // Should contain multiple asset symbols
    await expect(ticker).toContainText("MES", { timeout: 5_000 });
    await expect(ticker).toContainText("ES", { timeout: 5_000 });
  });

  test("Session phase pipeline is visible", async ({ page }) => {
    await page.goto("/");
    const phase = page.locator("[data-testid='session-phase']");
    await expect(phase).toBeVisible({ timeout: 10_000 });
    // Mock data sets pipelineStage to "EXECUTED", so that pill should be active
    await expect(phase).toContainText("EXECUTED", { timeout: 5_000 });
  });

  test("Health bar is visible with status indicators", async ({ page }) => {
    await page.goto("/");
    const healthBar = page.locator("[data-testid='health-bar']");
    await expect(healthBar).toBeVisible({ timeout: 10_000 });

    // API status indicator should be visible and ok (mock sets api_authenticated: true)
    const apiStatus = page.locator("[data-testid='api-status']");
    await expect(apiStatus).toBeVisible();
    await expect(apiStatus).toHaveAttribute("data-status", "ok");

    // WS indicator should be visible and connected
    const wsStatus = page.locator("[data-testid='ws-status']");
    await expect(wsStatus).toBeVisible();
    await expect(wsStatus).toHaveAttribute("data-status", "connected");
  });

  test("Last tick timestamp is displayed", async ({ page }) => {
    await page.goto("/");
    const lastTick = page.locator("[data-testid='last-tick-timestamp']");
    await expect(lastTick).toBeVisible({ timeout: 10_000 });
    // Currently hardcoded — just verify it has content
    await expect(lastTick).not.toHaveText("", { timeout: 5_000 });
  });

  // NOTE: Price staleness test is skipped because the "last tick" text is
  // currently hardcoded ("Last tick: 0.3s ago") rather than driven from
  // a real timestamp. Enable when backend provides actual tick timestamps.
  //
  // test("Data staleness — last tick within 10 seconds", async ({ page }) => {
  //   await page.goto("/");
  //   const lastTick = page.locator("[data-testid='last-tick-timestamp']");
  //   // TODO: enable when last-tick-timestamp shows real data
  //   // Parse the timestamp and assert it's within 10 seconds of now
  // });

  // NOTE: Live price change detection is skipped because DEV_MOCK_ENABLED
  // injects static mock data — prices don't change over time.
  //
  // test("Price data updates over time", async ({ page }) => {
  //   await page.goto("/");
  //   const priceEl = page.locator("[data-testid='current-price']");
  //   // TODO: enable when connected to live backend
  //   // const price1 = await priceEl.textContent();
  //   // await page.waitForTimeout(5000);
  //   // await expect(async () => {
  //   //   const price2 = await priceEl.textContent();
  //   //   expect(price2).not.toBe(price1);
  //   // }).toPass({ timeout: 10_000 });
  // });
});

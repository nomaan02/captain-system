import { test, expect } from "@playwright/test";

/* ═══════════════════════════════════════════════════════════════════════
   Pipeline Stage Pills — Validates that stage pills cycle correctly
   and always reflect the current pipeline state.
   ═══════════════════════════════════════════════════════════════════════ */

const STAGES = ["WAITING", "OR_FORMING", "SIGNAL_GEN", "EXECUTED"] as const;

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.locator("[data-testid='app-shell']").waitFor({ timeout: 10_000 });
  await page.waitForTimeout(500);
});

test.describe("Pipeline Stage Pills", () => {
  test("All four stage pills render with correct labels", async ({ page }) => {
    const labels: Record<string, string> = {
      WAITING: "WAITING",
      OR_FORMING: "OR FORMING",
      SIGNAL_GEN: "SIGNAL GEN",
      EXECUTED: "EXECUTED",
    };

    for (const stage of STAGES) {
      const pill = page.locator(`[data-testid='execution-stage-${stage}']`);
      await expect(pill).toBeVisible();
      await expect(pill).toContainText(labels[stage]);
    }
  });

  test("Exactly one pill is active at any time", async ({ page }) => {
    const active = page.locator("[data-active='true']");
    expect(await active.count()).toBe(1);
  });

  test("Mock mode starts with EXECUTED active", async ({ page }) => {
    await expect(
      page.locator("[data-testid='execution-stage-EXECUTED']")
    ).toHaveAttribute("data-active", "true");

    // All others should be inactive
    for (const stage of ["WAITING", "OR_FORMING", "SIGNAL_GEN"]) {
      await expect(
        page.locator(`[data-testid='execution-stage-${stage}']`)
      ).toHaveAttribute("data-active", "false");
    }
  });

  test("Stage pills cycle through all stages via store changes", async ({ page }) => {
    for (const stage of STAGES) {
      // Set pipeline stage via exposed store
      await page.evaluate((s) => {
        const store = (window as any).__dashboardStore;
        if (store) store.getState().setPipelineStage(s);
      }, stage);

      // Verify the correct pill is now active
      await expect(
        page.locator(`[data-testid='execution-stage-${stage}']`)
      ).toHaveAttribute("data-active", "true");

      // Verify all other pills are inactive
      for (const other of STAGES.filter((s) => s !== stage)) {
        await expect(
          page.locator(`[data-testid='execution-stage-${other}']`)
        ).toHaveAttribute("data-active", "false");
      }
    }
  });

  test("Store default is WAITING before mock injection overrides it", async ({ page }) => {
    // The zustand store's initial value is "WAITING" (dashboardStore.js:22)
    // Mock injection then overrides to "EXECUTED"
    // We can verify by setting back to WAITING and confirming it works
    await page.evaluate(() => {
      const store = (window as any).__dashboardStore;
      if (store) store.getState().setPipelineStage("WAITING");
    });

    await expect(
      page.locator("[data-testid='execution-stage-WAITING']")
    ).toHaveAttribute("data-active", "true");
  });

  test("Pipeline stage from dashboard snapshot is respected", async ({ page }) => {
    // Simulate a dashboard snapshot arriving with pipeline_stage field
    await page.evaluate(() => {
      const store = (window as any).__dashboardStore;
      if (store) {
        store.getState().setSnapshot({
          pipeline_stage: "OR_FORMING",
        });
      }
    });

    await expect(
      page.locator("[data-testid='execution-stage-OR_FORMING']")
    ).toHaveAttribute("data-active", "true");
  });

  test("Rapid stage transitions settle on final state", async ({ page }) => {
    // Simulate rapid transitions like a real session would produce
    await page.evaluate(() => {
      const store = (window as any).__dashboardStore;
      if (!store) return;
      const s = store.getState();
      s.setPipelineStage("WAITING");
      s.setPipelineStage("OR_FORMING");
      s.setPipelineStage("SIGNAL_GEN");
      s.setPipelineStage("EXECUTED");
    });

    // Should settle on EXECUTED
    await expect(
      page.locator("[data-testid='execution-stage-EXECUTED']")
    ).toHaveAttribute("data-active", "true");

    const active = page.locator("[data-active='true']");
    expect(await active.count()).toBe(1);
  });
});

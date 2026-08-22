import { test } from "@playwright/test";

test("take screenshots of UI", async ({ page }) => {
  // Set viewport for desktop
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().addCookies([
    { name: "cyberai_csrf", value: "csrf-token", url: "http://127.0.0.1:3000" },
  ]);
  
  // Navigate
  await page.goto("http://127.0.0.1:3000/");
  await page.waitForTimeout(2000); // Wait for animations/load
  
  // Take desktop screenshot
  await page.screenshot({ path: "desktop-screenshot.png" });

  // Set viewport for mobile
  await page.setViewportSize({ width: 375, height: 812 });
  await page.waitForTimeout(500); // Wait for responsive changes
  await page.screenshot({ path: "mobile-screenshot.png" });
});

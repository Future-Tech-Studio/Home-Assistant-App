const assert = require("node:assert/strict");
const { chromium } = require(process.env.FHT_PLAYWRIGHT || "playwright");

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, extraHTTPHeaders: { "X-Remote-User-Id": "a".repeat(32) } });
    const page = await context.newPage();
    const errors = [];
    const requests = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => requests.push(request.url()));
    await page.goto(process.env.FHT_MAINTENANCE_PREVIEW_URL, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(900);
    assert.equal(requests.filter(url => url.includes("maintenance")).length, 0, "No maintenance preload requests");
    await page.locator("#settings-toggle").click();
    const section = page.locator("#view-maintenance");
    await page.locator('[data-view="safe-cleanup"]').click();
    await section.getByRole("heading", { name: "Recovery history" }).waitFor();
    await section.getByRole("heading", { name: "Retired Future Homes Tech entities" }).waitFor();
    assert.equal(await section.getByLabel(/Old Pantry Group/).isChecked(), true, "Retired entities are listed for approval");
    await section.getByRole("button", { name: "Delete this entity" }).click();
    await section.getByRole("status").filter({ hasText: "Deleted 1 retired entity" }).waitFor();
    await section.getByText("Nothing is waiting for approval.").waitFor();
    assert.equal(requests.filter(url => url.includes("maintenance/review")).length, 0, "Cleanup scans require a click");
    await section.getByRole("button", { name: "Scan unused helpers" }).click();
    await section.getByLabel(/Retired Pantry Helper/).check();
    await section.getByRole("button", { name: "Archive selected" }).click();
    const dialog = page.locator("dialog[open]");
    assert.equal(await dialog.getByRole("button", { name: "Confirm archive" }).isDisabled(), true);
    await page.screenshot({ path: "/tmp/fht-maintenance-cleanup-desktop.png" });
    await dialog.getByLabel(/I reviewed external/).check();
    await dialog.getByRole("button", { name: "Confirm archive" }).click();
    await section.getByRole("status").filter({ hasText: "Archived 1 helpers" }).waitFor();
    await section.getByRole("button", { name: "Restore previous settings" }).click();
    await dialog.getByRole("button", { name: "Confirm restore" }).click();
    await section.getByText("restored", { exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: "/tmp/fht-maintenance-mobile.png" });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true, "No mobile horizontal overflow");
    await section.getByRole("button", { name: "Scan unused helpers" }).click();
    await section.getByLabel(/Retired Pantry Helper/).check();
    await section.getByRole("button", { name: "Archive selected" }).click();
    await dialog.getByRole("button", { name: "Confirm archive" }).waitFor();
    const bounds = await dialog.boundingBox();
    assert(bounds.x >= 0 && bounds.x + bounds.width <= 391, "Modal fits phone viewport");
    await page.screenshot({ path: "/tmp/fht-maintenance-modal-mobile.png" });
    await page.keyboard.press("Escape");
    assert.deepEqual(errors, []);
    console.log("Maintenance browser checks passed: lazy loading, retired-entity approval, confirmed archive/recovery, desktop and mobile.");
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

import { expect, test } from "@playwright/test";

async function canvasHasRenderedPixels(page: import("@playwright/test").Page) {
  return page.locator('[data-testid="three-canvas"]').evaluate((canvas: HTMLCanvasElement) => {
    const gl = (canvas.getContext("webgl2") || canvas.getContext("webgl")) as WebGLRenderingContext | null;
    if (!gl) return false;
    const width = gl.drawingBufferWidth;
    const height = gl.drawingBufferHeight;
    const samples = Array.from({ length: 5 }, (_, row) =>
      Array.from({ length: 5 }, (_, column) => [
        ((column + 0.5) / 5) * width,
        ((row + 0.5) / 5) * height,
      ]),
    ).flat();
    const colors = samples.map(([x, y]) => {
      const pixel = new Uint8Array(4);
      gl.readPixels(Math.floor(x), Math.floor(y), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      return Array.from(pixel).join(",");
    });
    return new Set(colors).size >= 2 && colors.some((color) => color !== "0,0,0,0");
  });
}

test("3D scene renders and calibration workflow updates", async ({ page }, testInfo) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "滚球视觉实验台" })).toBeVisible();
  await expect(page.locator('[data-testid="three-canvas"]')).toBeVisible();
  await page.waitForTimeout(800);
  expect(await canvasHasRenderedPixels(page)).toBeTruthy();

  await page.locator(".stage-tab[data-stage='calibration']").click();
  await expect(page.locator("#stage-title")).toHaveText("像素标定采集");
  const before = await page.locator("#sample-table tr").count();
  await page.locator("#capture-point").click();
  await expect(page.locator("#sample-table tr")).toHaveCount(before + 1);

  await page.locator(".stage-tab[data-stage='mapping']").click();
  await page.getByRole("button", { name: "射影" }).click();
  await expect(page.locator("#mapping-state")).toHaveText("有效");
  await expect(page.locator("#metric-rmse")).toContainText("cm");

  await page.screenshot({ path: testInfo.outputPath("workbench.png") });
});

test("simulation runs and layout remains separated", async ({ page }, testInfo) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator(".stage-tab[data-stage='simulation']").click();
  await page.locator("#sim-target").fill("5");
  await page.locator("#sim-play").click();
  await expect(page.locator("#sim-play")).toContainText("暂停");
  await page.waitForTimeout(700);

  const sceneBox = await page.locator(".scene-shell").boundingBox();
  const inspectorBox = await page.locator(".inspector").boundingBox();
  expect(sceneBox).not.toBeNull();
  expect(inspectorBox).not.toBeNull();
  if (sceneBox && inspectorBox) {
    const desktopLayout = testInfo.project.name === "desktop";
    if (desktopLayout) expect(sceneBox.x + sceneBox.width).toBeLessThanOrEqual(inspectorBox.x + 1);
    else expect(sceneBox.y + sceneBox.height).toBeLessThanOrEqual(inspectorBox.y + 1);
  }

  await expect(page.locator("#telemetry-true")).not.toHaveText("0.00 cm");
  expect(await canvasHasRenderedPixels(page)).toBeTruthy();
  await page.locator("#sim-play").click();
  await expect(page.locator("#sim-play")).toContainText("运行");
  await page.screenshot({ path: testInfo.outputPath("simulation.png") });
});

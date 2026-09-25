import { expect, test, type Page } from "@playwright/test";

/** Collects what should never happen on any screen: uncaught errors, React warnings, failed API calls. */
function watch(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") problems.push(`${m.type()}: ${m.text()}`);
  });
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 400) problems.push(`${r.status()} ${r.url()}`);
  });
  return problems;
}

const SCREENS: [string, RegExp][] = [
  ["/", /Добрый|Доброе|Доброй/],
  ["/hh", /HeadHunter/],
  ["/pipeline", /Воронка/],
  ["/chats", /Чаты/],
  ["/mail", /Письма компаниям/],
  ["/sites", /Другие сайты/],
  ["/answers", /База ответов/],
  ["/stats", /Статистика/],
  ["/settings", /Настройки/],
];

for (const [path, heading] of SCREENS) {
  test(`${path} renders without errors and fits the screen`, async ({ page }) => {
    const problems = watch(page);
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow, "no horizontal scroll").toBe(false);
    expect(problems).toEqual([]);
  });
}

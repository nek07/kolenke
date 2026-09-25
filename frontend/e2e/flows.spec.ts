import { expect, test } from "@playwright/test";

// These tests change the seeded database; they run in order on one worker (see playwright.config.ts).

test("today shows the weekly metric, what needs attention and the setup checklist", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Приглашения за неделю")).toBeVisible();
  await expect(page.getByRole("button", { name: /3 вакансии ждут проверки/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /1 сообщение ждёт ответа/ })).toBeVisible();
  await expect(page.getByText("Настроим всё за пару минут")).toBeVisible();
});

test("a vacancy row opens its history panel with the filter reasons", async ({ page }) => {
  await page.goto("/hh");
  await page
    .getByRole("row", { name: /Data Analyst/ })
    .getByText("Kaspi Bank")
    .click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByRole("heading", { name: "Data Analyst" })).toBeVisible();
  await expect(panel.getByText("совпадение навыков 82%")).toBeVisible();
  await expect(panel.getByText(/Найдена среди подходящих/)).toBeVisible();
});

test("filters live in the URL and bulk actions move the selected vacancies", async ({ page }) => {
  await page.goto("/hh?status=applied");
  await expect(page.getByRole("radio", { name: /Отправлены/ })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("radio", { name: /Новые/ }).click();
  await expect(page).toHaveURL(/\/hh$/);
  const table = page.getByRole("table", { name: "Вакансии hh" });
  await table.getByRole("checkbox", { name: "Выбрать" }).first().click();
  await table
    .getByRole("checkbox", { name: "Выбрать" })
    .nth(1)
    .click({ modifiers: ["Shift"] });
  await expect(page.getByText("Выбрано: 2")).toBeVisible();
  await page.getByRole("button", { name: "Пропустить" }).click();
  await expect(page.getByText("Готово: 2")).toBeVisible();
  await expect(table.getByRole("row")).toHaveCount(2); // header + the one left
});

test("the review deck swipes with the keyboard and can undo", async ({ page }) => {
  await page.goto("/hh");
  await page.getByRole("button", { name: "Проверить" }).click();
  const deck = page.getByRole("dialog", { name: "Проверка вакансий" });
  await expect(deck.getByText("1 из 1")).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(deck.getByText("Все карточки просмотрены")).toBeVisible();
  await deck.getByRole("button", { name: "Вернуть" }).click();
  await expect(deck.getByRole("heading", { level: 2 })).toBeVisible();
  await deck.getByRole("button", { name: "Закрыть" }).click();
});

test("⌘K finds a company in vacancies, chats and the mail list", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("ControlOrMeta+k");
  await page.getByPlaceholder(/Компания, вакансия/).fill("freedom");
  await expect(page.getByRole("group", { name: "Вакансии" }).getByText("Product Analyst")).toBeVisible();
  await expect(page.getByRole("group", { name: "Чаты" })).toBeVisible();
  await page
    .getByRole("group", { name: "Вакансии" })
    .getByRole("option", { name: /Product Analyst/ })
    .click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Product Analyst" })).toBeVisible();
});

test("settings validate on the server and show the error next to the field", async ({ page }) => {
  await page.goto("/settings");
  const limit = page.getByLabel("Не больше откликов в день");
  await limit.fill("0");
  await page.locator("#limits").getByRole("button", { name: "Сохранить" }).click();
  await expect(page.locator("#limits").getByRole("alert")).toBeVisible();
  await limit.fill("40");
  await page.locator("#limits").getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByText("Сохранено").first()).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Не больше откликов в день")).toHaveValue("40");
});

test("the answer base asks to save changes and remembers them", async ({ page }) => {
  await page.goto("/answers");
  await page.getByLabel("Ответ", { exact: true }).first().fill("от 800 000 ₸");
  await page.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByText("Есть несохранённые изменения")).toBeHidden();
  await page.getByLabel("Вопрос").fill("Какие у вас зарплатные ожидания?");
  await page.getByRole("button", { name: "Проверить", exact: true }).click();
  await expect(page.getByText(/Бот ответит: от 800 000 ₸/)).toBeVisible();
});

test("the pipeline moves a card and the panel edits the next step", async ({ page }) => {
  await page.goto("/pipeline");
  const card = page.getByRole("button", { name: /Junior Analyst/ });
  await card.dragTo(page.getByRole("region", { name: "Собеседование" }));
  await expect(page.getByRole("region", { name: "Собеседование" }).getByText("Junior Analyst")).toBeVisible();
  await page.getByRole("region", { name: "Собеседование" }).getByText("Junior Analyst").click();
  const panel = page.getByRole("dialog");
  await panel.getByLabel("Следующий шаг").fill("Техническое интервью");
  await panel.getByLabel("Когда").fill("2031-03-01T15:00");
  await panel.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByText(/Запомнил/)).toBeVisible();
});

test("an e-mail from another site goes to «Письма компаниям»", async ({ page }) => {
  await page.goto("/sites");
  const table = page.getByRole("table", { name: "Вакансии с других сайтов" });
  await expect(table.getByText("hr@kmf.kz")).toBeVisible();
  await table.getByRole("checkbox", { name: "Выбрать" }).first().click();
  await page.getByRole("button", { name: "В письма компаниям" }).click();
  await expect(page.getByText(/добавлено адресов: 1/)).toBeVisible();
  await page.goto("/mail");
  await expect(page.getByRole("table", { name: "Компании" }).getByText("hr@kmf.kz")).toBeVisible();
});

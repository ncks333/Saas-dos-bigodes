import {expect, test} from "@playwright/test";

const noHorizontalOverflow = async (page: import("@playwright/test").Page) => {
  const sizes = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(sizes.content).toBeLessThanOrEqual(sizes.viewport);
};

test("login cabe e permanece utilizável no celular", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Bem-vindo"})).toBeVisible();
  await expect(page.getByLabel("Usuário")).toBeVisible();
  await expect(page.getByLabel("Senha")).toBeVisible();
  await expect(page.getByRole("button", {name: "Entrar"})).toBeVisible();
  await noHorizontalOverflow(page);
});

test("agendamento público funciona no celular", async ({page}) => {
  const start = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  start.setHours(10, 0, 0, 0);
  const slot = start.toISOString();
  await page.route("**/api/v1/public/bigodes/**", async route => {
    const url = route.request().url();
    if (url.includes("/services/")) {
      await route.fulfill({json: [{id: 1, name: "Corte", description: "", price: "50.00", duration_minutes: 30, active: true}]});
    } else if (url.includes("/availability/")) {
      await route.fulfill({json: {slots: [slot]}});
    } else {
      await route.fulfill({json: {id: 1, name: "Bigodes", slug: "bigodes", whatsapp: "", timezone: "America/Sao_Paulo", active: true, operating_hours: []}});
    }
  });
  await page.goto("/agendar/bigodes");
  await page.getByRole("button", {name: /Corte/}).click();
  await expect(page.locator(".slots button")).toBeVisible();
  await page.locator(".slots button").click();
  await page.getByLabel("Nome").fill("Cliente Mobile");
  await page.getByLabel("WhatsApp").fill("11999999999");
  await expect(page.getByRole("button", {name: "Confirmar agendamento"})).toBeEnabled();
  await noHorizontalOverflow(page);
});

test("painel abre a navegação móvel sem estourar a tela", async ({page}) => {
  await page.addInitScript(() => {
    localStorage.setItem("access", "teste");
    localStorage.setItem("refresh", "teste");
    localStorage.setItem("user", JSON.stringify({id: 1, name: "Admin", role: "ADMIN"}));
  });
  await page.route("**/api/v1/**", async route => {
    const url = route.request().url();
    await route.fulfill({json: url.includes("daily_summary")
      ? {total: 0, confirmed: 0, pending: 0, awaiting: 0, cancelled: 0, completed: 0, no_show: 0, revenue: 0}
      : {daily_revenue: 0, monthly_revenue: 0, cancellation_rate: 0, popular_hours: []}});
  });
  await page.goto("/");
  await page.locator(".mobile-menu").click();
  await expect(page.locator(".sidebar.open")).toBeVisible();
  await expect(page.getByRole("button", {name: "Agenda", exact: true})).toBeVisible();
  await noHorizontalOverflow(page);
});

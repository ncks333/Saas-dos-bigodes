import {expect, test} from "@playwright/test";

const noHorizontalOverflow = async (page: import("@playwright/test").Page) => {
  const sizes = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(sizes.content).toBeLessThanOrEqual(sizes.viewport);
};

test("login cabe e permanece utilizável no celular", async ({page}) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", {name: "Bem-vindo"})).toBeVisible();
  await expect(page.getByLabel("Usuário")).toBeVisible();
  await expect(page.getByLabel("Senha")).toBeVisible();
  await expect(page.getByRole("button", {name: "Entrar"})).toBeVisible();
  await noHorizontalOverflow(page);
});

test("landing page apresenta produto e chamadas principais", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: /Menos conversa perdida/})).toBeVisible();
  await expect(page.getByRole("link", {name: /Ver agendamento/})).toBeVisible();
  await expect(page.getByRole("link", {name: /Acessar painel/})).toBeVisible();
  await noHorizontalOverflow(page);
});

test("recuperação de senha confirma pedido sem expor cadastro", async ({page}) => {
  await page.route("**/api/v1/auth/password-reset/", route => route.fulfill({json: {message: "Se o e-mail existir, as instruções serão enviadas."}}));
  await page.goto("/recuperar-senha");
  await page.getByLabel("E-mail").fill("admin@example.com");
  await page.getByRole("button", {name: "Enviar link"}).click();
  await expect(page.getByRole("heading", {name: "Link enviado"})).toBeVisible();
  await noHorizontalOverflow(page);
});

test("aviso de privacidade permanece legível no celular", async ({page}) => {
  await page.goto("/privacidade");
  await expect(page.getByRole("heading", {name: /Seus dados servem/})).toBeVisible();
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
  const publicDateBounds = await page.evaluate(() => {
    const field = document.querySelector<HTMLInputElement>('.booking-card input[type="date"]')!.getBoundingClientRect();
    const card = document.querySelector<HTMLElement>('.booking-card')!.getBoundingClientRect();
    return {fieldRight: field.right, cardRight: card.right, fieldLeft: field.left, cardLeft: card.left};
  });
  expect(publicDateBounds.fieldRight).toBeLessThanOrEqual(publicDateBounds.cardRight);
  expect(publicDateBounds.fieldLeft).toBeGreaterThanOrEqual(publicDateBounds.cardLeft);
  await page.getByRole("button", {name: /Corte/}).click();
  await expect(page.locator(".slots button")).toBeVisible();
  await page.locator(".slots button").click();
  await page.getByLabel("Nome").fill("Cliente Mobile");
  await page.getByLabel("WhatsApp").fill("11999999999");
  await page.getByRole("checkbox", {name: /aviso de privacidade/}).check();
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
    const json = url.includes("daily_summary")
      ? {total: 0, confirmed: 0, pending: 0, awaiting: 0, cancelled: 0, completed: 0, no_show: 0, revenue: 0}
      : url.includes("/appointments/") ? []
      : {daily_revenue: 0, monthly_revenue: 0, cancellation_rate: 0, popular_hours: []};
    await route.fulfill({json});
  });
  await page.goto("/login");
  await page.locator(".mobile-menu").click();
  await expect(page.locator(".sidebar.open")).toBeVisible();
  await page.getByRole("button", {name: "Agenda", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Agenda"})).toBeVisible();
  await expect(page.getByRole("button", {name: "Novo agendamento"})).toBeVisible();
  const toolbarOverlaps = await page.evaluate(() => {
    const field = document.querySelector<HTMLInputElement>('.toolbar input[type="date"]')!.getBoundingClientRect();
    const count = document.querySelector<HTMLElement>('.toolbar > span')!.getBoundingClientRect();
    return !(field.right <= count.left || count.right <= field.left || field.bottom <= count.top || count.bottom <= field.top);
  });
  expect(toolbarOverlaps).toBe(false);
  await page.locator(".mobile-menu").click();
  await expect(page.locator(".sidebar.open")).toBeVisible();
  await expect(page.getByRole("button", {name: "Agenda", exact: true})).toBeVisible();
  await noHorizontalOverflow(page);
});

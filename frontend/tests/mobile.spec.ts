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

test("login traduz erro de credenciais inválidas", async ({page}) => {
  await page.route("**/api/v1/auth/login/", route => route.fulfill({
    status: 401,
    json: {detail: "No active account found with the given credentials"},
  }));
  await page.goto("/login");
  await page.getByLabel("Usuário").fill("admin");
  await page.getByLabel("Senha").fill("SenhaAntiga123");
  await page.getByRole("button", {name: "Entrar"}).click();

  await expect(page.getByText("Usuário ou senha inválidos.")).toBeVisible();
  await expect(page.getByText("No active account found with the given credentials")).toHaveCount(0);
});

test("landing page apresenta produto e chamadas principais", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: /Menos conversa perdida/})).toBeVisible();
  await expect(page.getByRole("link", {name: /Começar .*grátis/}).first()).toHaveAttribute("href", "/cadastro");
  await expect(page.getByRole("link", {name: "Já sou cliente"}).first()).toHaveAttribute("href", "/login");
  await noHorizontalOverflow(page);
});

test("landing da M&R Solutions apresenta serviços e contato pelo WhatsApp", async ({page}) => {
  await page.goto("/mr-solutions");
  await expect(page.getByRole("heading", {name: /Sistemas, sites e automações/})).toBeVisible();
  await expect(page.getByText("Sites", {exact: true})).toBeVisible();
  await expect(page.getByText("Sistemas", {exact: true})).toBeVisible();
  await expect(page.getByText("Consultoria digital", {exact: true}).first()).toBeVisible();
  await expect(page.getByRole("heading", {name: "Sites e produtos digitais", exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Automações", exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Consultoria digital", exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: /BarberHub nasceu como produto próprio/})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Como começamos"})).toBeVisible();
  await expect(page.getByText("Projetos selecionados em preparação").first()).toBeVisible();
  await expect(page.locator(".solutions-orbit [style*='globe.jpeg']")).toBeVisible();
  await expect(page.locator(".solutions-orbit [class*='d4af37']").first()).toBeVisible();
  await expect(page.locator(".shooting-star")).toHaveCount(6);
  await expect(page.locator(".solutions-reveal.is-visible").first()).toBeVisible();
  await page.locator(".solutions-services").scrollIntoViewIfNeeded();
  await expect(page.locator(".solutions-services.is-visible")).toBeVisible();
  await page.locator(".solutions-case").scrollIntoViewIfNeeded();
  await expect(page.locator(".solutions-case.is-visible")).toBeVisible();
  await expect(page.locator(".solutions-nav.is-scrolled")).toBeVisible();
  await expect(page.getByRole("link", {name: /Conversar sobre meu projeto/}).first())
    .toHaveAttribute("href", /^https:\/\/wa\.me\/5511999999999\?text=Teste$/);
  await noHorizontalOverflow(page);
});

test("globo respeita preferência por movimento reduzido", async ({page}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/mr-solutions");
  const globe = page.locator(".mr-solutions-globe");
  await expect(globe).toBeVisible();
  await expect(globe).toHaveCSS("animation-name", "none");
  await expect(page.locator(".mr-solutions-globe-star").first()).toHaveCSS("animation-name", "none");
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
  await expect(page.locator(".public-header img").first()).toHaveAttribute("src", "/barberhub-icon-v2.png");
  await expect(page.getByRole("button", {name: "Escolher data"})).toBeVisible();
  const publicDateBounds = await page.evaluate(() => {
    const field = document.querySelector<HTMLButtonElement>('.public-date-trigger')!.getBoundingClientRect();
    const card = document.querySelector<HTMLElement>('.booking-card')!.getBoundingClientRect();
    return {fieldRight: field.right, cardRight: card.right, fieldLeft: field.left, cardLeft: card.left};
  });
  expect(publicDateBounds.fieldRight).toBeLessThanOrEqual(publicDateBounds.cardRight);
  expect(publicDateBounds.fieldLeft).toBeGreaterThanOrEqual(publicDateBounds.cardLeft);
  await page.getByRole("button", {name: "Escolher data"}).click();
  await expect(page.getByRole("heading", {name: "Escolha a data"})).toBeVisible();
  await page.keyboard.press("Escape");
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
    const json = url.endsWith("/barbershop/")
      ? {id: 1, name: "Bigodes", slug: "bigodes", whatsapp: "", timezone: "America/Sao_Paulo", active: true, operating_hours: []}
      : url.includes("daily_summary")
      ? {total: 0, confirmed: 0, pending: 0, awaiting: 0, cancelled: 0, completed: 0, no_show: 0, revenue: 0}
      : url.includes("/appointments/") ? []
      : {daily_revenue: 0, monthly_revenue: 0, cancellation_rate: 0, popular_hours: []};
    await route.fulfill({json});
  });
  await page.goto("/login");
  await expect(page.locator(".sidebar-brand img").first()).toHaveAttribute("src", "/barberhub-icon-v2.png");
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

test("status da agenda atualiza antes da resposta e não recarrega a lista", async ({page}) => {
  await page.addInitScript(() => {
    localStorage.setItem("access", "teste");
    localStorage.setItem("refresh", "teste");
    localStorage.setItem("user", JSON.stringify({id: 1, name: "Admin", role: "ADMIN"}));
  });
  let listGets = 0;
  let releasePatch!: () => void;
  let completePatch!: () => void;
  const patchReleased = new Promise<void>(resolve => { releasePatch = resolve; });
  const patchCompleted = new Promise<void>(resolve => { completePatch = resolve; });
  const appointmentStartsAt = new Date().toISOString();
  const appointmentEndsAt = new Date(Date.now() + 30 * 60 * 1000).toISOString();
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/barbershop/") && request.method() === "GET") {
      await route.fulfill({json: {id: 1, name: "Bigodes", slug: "bigodes", whatsapp: "", timezone: "America/Sao_Paulo", active: true, operating_hours: []}});
      return;
    }
    if (url.pathname.endsWith("/appointments/") && request.method() === "GET") {
      listGets += 1;
      await route.fulfill({json: [{id: 7, customer: 2, customer_name: "Cliente", service: 3, service_name: "Corte", employee: null, starts_at: appointmentStartsAt, ends_at: appointmentEndsAt, notes: "", status: "PENDENTE", source: "MANUAL"}]});
      return;
    }
    if (url.pathname.endsWith("/appointments/7/") && request.method() === "PATCH") {
      await patchReleased;
      await route.fulfill({json: {id: 7, customer: 2, customer_name: "Cliente", service: 3, service_name: "Corte", employee: null, starts_at: appointmentStartsAt, ends_at: appointmentEndsAt, notes: "", status: "CONFIRMADO", source: "MANUAL"}});
      completePatch();
      return;
    }
    if (url.pathname.endsWith("/daily_summary/")) {
      await route.fulfill({json: {total: 1, confirmed: 0, pending: 1, awaiting: 0, cancelled: 0, completed: 0, no_show: 0, revenue: 0}});
      return;
    }
    if (url.pathname.endsWith("/dashboard/")) {
      await route.fulfill({json: {daily_revenue: 0, monthly_revenue: 0, cancellation_rate: 0, popular_hours: []}});
      return;
    }
    await route.fulfill({json: []});
  });
  await page.goto("/login");
  await expect(page.locator(".sidebar-brand img").first()).toBeVisible();
  await page.locator(".mobile-menu").click();
  await page.getByRole("button", {name: "Agenda", exact: true}).click();
  await page.getByLabel("Status").selectOption("CONFIRMADO");
  await expect(page.getByLabel("Status")).toHaveValue("CONFIRMADO", {timeout: 1000});
  releasePatch();
  await patchCompleted;
  await page.waitForTimeout(100);
  expect(listGets).toBe(1);
});

test("status da agenda volta ao valor anterior quando API falha", async ({page}) => {
  await page.addInitScript(() => {
    localStorage.setItem("access", "teste");
    localStorage.setItem("refresh", "teste");
    localStorage.setItem("user", JSON.stringify({id: 1, name: "Admin", role: "ADMIN"}));
  });
  const appointmentStartsAt = new Date().toISOString();
  const appointmentEndsAt = new Date(Date.now() + 30 * 60 * 1000).toISOString();
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/barbershop/") && request.method() === "GET") {
      await route.fulfill({json: {id: 1, name: "Bigodes", slug: "bigodes", whatsapp: "", timezone: "America/Sao_Paulo", active: true, operating_hours: []}});
      return;
    }
    if (url.pathname.endsWith("/appointments/") && request.method() === "GET") {
      await route.fulfill({json: [{id: 7, customer: 2, customer_name: "Cliente", service: 3, service_name: "Corte", employee: null, starts_at: appointmentStartsAt, ends_at: appointmentEndsAt, notes: "", status: "PENDENTE", source: "MANUAL"}]});
      return;
    }
    if (url.pathname.endsWith("/appointments/7/") && request.method() === "PATCH") {
      await route.fulfill({status: 500, json: {detail: "Falha controlada"}});
      return;
    }
    if (url.pathname.endsWith("/daily_summary/")) {
      await route.fulfill({json: {total: 1, confirmed: 0, pending: 1, awaiting: 0, cancelled: 0, completed: 0, no_show: 0, revenue: 0}});
      return;
    }
    if (url.pathname.endsWith("/dashboard/")) {
      await route.fulfill({json: {daily_revenue: 0, monthly_revenue: 0, cancellation_rate: 0, popular_hours: []}});
      return;
    }
    await route.fulfill({json: []});
  });
  await page.goto("/login");
  await expect(page.locator(".sidebar-brand img").first()).toBeVisible();
  await page.locator(".mobile-menu").click();
  await page.getByRole("button", {name: "Agenda", exact: true}).click();
  await page.getByLabel("Status").selectOption("CONFIRMADO");
  await expect(page.getByLabel("Status")).toHaveValue("PENDENTE", {timeout: 2000});
  await expect(page.getByText("Serviço temporariamente indisponível. Tente novamente em instantes.")).toBeVisible();
});

test("busca de clientes aguarda digitação antes de consultar API", async ({page}) => {
  await page.addInitScript(() => {
    localStorage.setItem("access", "teste");
    localStorage.setItem("refresh", "teste");
    localStorage.setItem("user", JSON.stringify({id: 1, name: "Admin", role: "ADMIN"}));
  });
  const searchRequests: string[] = [];
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/customers/") && request.method() === "GET") {
      const search = url.searchParams.get("search");
      if (search) searchRequests.push(search);
      await route.fulfill({json: []});
      return;
    }
    if (url.pathname.endsWith("/daily_summary/")) {
      await route.fulfill({json: {total: 0, confirmed: 0, pending: 0, awaiting: 0, cancelled: 0, completed: 0, no_show: 0, revenue: 0}});
      return;
    }
    if (url.pathname.endsWith("/dashboard/")) {
      await route.fulfill({json: {daily_revenue: 0, monthly_revenue: 0, cancellation_rate: 0, popular_hours: []}});
      return;
    }
    await route.fulfill({json: []});
  });
  await page.goto("/login");
  await expect(page.locator(".sidebar-brand img").first()).toBeVisible();
  await page.locator(".mobile-menu").click();
  await page.getByRole("button", {name: "Clientes", exact: true}).click();
  await page.getByPlaceholder("Buscar por nome ou WhatsApp").pressSequentially("abc", {delay: 25});
  await page.waitForTimeout(500);
  expect(searchRequests).toEqual(["abc"]);
});

const currentPlan = {
  code: "barberhub",
  name: "BarberHub",
  amount: "79.90",
  currency: "BRL",
  trial_days: 30,
};

const fillSignup = async (page: import("@playwright/test").Page) => {
  await page.getByLabel("Nome *", {exact: true}).fill("João");
  await page.getByLabel("E-mail").fill("joao@example.com");
  await page.getByLabel("Usuário").fill("joao");
  await page.getByLabel("Senha").fill("SenhaForte123");
  await page.getByLabel("Nome da barbearia").fill("Barbearia João");
  await page.getByLabel("Endereço público").fill("barbearia-joao");
  await page.getByLabel("WhatsApp").fill("11999999999");
  await page.getByRole("checkbox", {name: /termos/}).check();
};

test("landing leva ao cadastro e mostra plano do servidor", async ({page}) => {
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: currentPlan}));
  await page.goto("/");
  await expect(page.getByText("30 dias grátis").first()).toBeVisible();
  await expect(page.getByText("R$ 79,90").first()).toBeVisible();
  await expect(page.getByRole("link", {name: "Começar 30 dias grátis"}).first()).toHaveAttribute("href", "/cadastro");
});

test("cadastro envia somente campos declarados e usa checkout seguro do servidor", async ({page}) => {
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: currentPlan}));
  await page.route("**/api/v1/billing/signup/", route => route.fulfill({status: 201, json: {checkout_url: "/checkout/concluido"}}));
  await page.setViewportSize({width: 375, height: 812});
  await page.goto("/cadastro");
  await noHorizontalOverflow(page);
  await fillSignup(page);
  const requestPromise = page.waitForRequest("**/api/v1/billing/signup/");
  await page.getByRole("button", {name: /Começar 30 dias grátis/}).click();
  const request = await requestPromise;
  expect(request.postDataJSON()).toEqual({
    first_name: "João",
    email: "joao@example.com",
    username: "joao",
    password: "SenhaForte123",
    barbershop_name: "Barbearia João",
    slug: "barbearia-joao",
    whatsapp: "11999999999",
    captcha_token: process.env.VITE_TURNSTILE_SITE_KEY
      ? "XXXX.DUMMY.TOKEN.XXXX"
      : "development",
    terms_accepted: true,
  });
  await expect(page).toHaveURL(/\/checkout\/concluido$/);
});

test("cadastro rejeita checkout inseguro", async ({page}) => {
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: currentPlan}));
  await page.route("**/api/v1/billing/signup/", route => route.fulfill({status: 201, json: {checkout_url: "javascript:alert(1)"}}));
  await page.goto("/cadastro");
  await fillSignup(page);
  await page.getByRole("button", {name: /Começar 30 dias grátis/}).click();
  await expect(page).toHaveURL(/\/cadastro$/);
  await expect(page.getByRole("alert")).toContainText("Link de pagamento inválido");
});

test("cadastro rejeita HTTPS fora das origens Asaas configuradas", async ({page}) => {
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: currentPlan}));
  await page.route("**/api/v1/billing/signup/", route => route.fulfill({status: 201, json: {checkout_url: "https://evil.example/checkout/chk_1"}}));
  await page.goto("/cadastro");
  await fillSignup(page);
  await page.getByRole("button", {name: /Começar 30 dias grátis/}).click();
  await expect(page).toHaveURL(/\/cadastro$/);
  await expect(page.getByRole("alert")).toContainText("Link de pagamento inválido");
});

test("login bloqueado oferece regularização para erro direto e envelope", async ({page}) => {
  let envelope = false;
  await page.route("**/api/v1/auth/login/", route => route.fulfill({
    status: 403,
    json: envelope
      ? {detail: {code: "subscription_required", detail: "Assinatura precisa ser regularizada."}}
      : {code: "subscription_required", detail: "Assinatura precisa ser regularizada."},
  }));
  await page.goto("/login");
  await page.getByLabel("Usuário").fill("admin");
  await page.getByLabel("Senha").fill("Senha123");
  await page.getByRole("button", {name: "Entrar"}).click();
  await expect(page.getByRole("link", {name: /Regularizar assinatura/})).toHaveAttribute("href", "/regularizar");

  envelope = true;
  await page.reload();
  await page.getByLabel("Usuário").fill("admin");
  await page.getByLabel("Senha").fill("Senha123");
  await page.getByRole("button", {name: "Entrar"}).click();
  await expect(page.getByRole("link", {name: /Regularizar assinatura/})).toBeVisible();
  await expect(page.evaluate(() => localStorage.getItem("access"))).resolves.toBeNull();
});

test("regularização solicita email ou usa checkout seguro de token", async ({page}) => {
  await page.route("**/api/v1/billing/regularization/request/", route => route.fulfill({json: {message: "Se a conta precisar de regularização, enviaremos as instruções."}}));
  await page.goto("/regularizar");
  await page.getByLabel("E-mail").fill("admin@example.com");
  await page.getByRole("button", {name: /Enviar instruções/}).click();
  await expect(page.getByRole("status")).toContainText("instruções");

  await page.route("**/api/v1/billing/regularization/checkout/", route => route.fulfill({json: {checkout_url: "/checkout/concluido"}}));
  await page.goto("/regularizar?token=assinatura-segura&utm_source=email");
  await expect(page).toHaveURL(/\/regularizar\?utm_source=email$/);
  await page.getByRole("button", {name: /Regularizar assinatura/}).click();
  await expect(page).toHaveURL(/\/checkout\/concluido$/);
});

test("regularização remove token antes de qualquer carregamento de analytics", async ({page}) => {
  const analyticsRequests: string[] = [];
  page.on("request", request => {
    if (request.url().includes("posthog")) analyticsRequests.push(request.url());
  });
  await page.goto("/regularizar?token=capacidade-secreta");
  await expect(page).toHaveURL(/\/regularizar$/);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, nofollow");
  expect(analyticsRequests).toEqual([]);
});

test("checkout informa espera por confirmação do provedor", async ({page}) => {
  for (const path of ["/checkout/concluido", "/checkout/cancelado", "/checkout/expirado"]) {
    await page.goto(path);
    await expect(page.getByText(/confirmação do provedor/i)).toBeVisible();
    await noHorizontalOverflow(page);
  }
});

test("checkout cancelado ou expirado recupera por email sem duplicar signup", async ({page}) => {
  for (const path of ["/checkout/cancelado", "/checkout/expirado"]) {
    await page.goto(path);
    await expect(page.getByRole("link", {name: /Recuperar checkout por e-mail/})).toHaveAttribute("href", "/regularizar");
    await expect(page.getByRole("link", {name: /Começar teste grátis/})).toHaveCount(0);
  }
});

test("cadastro mostra erro do backend em português", async ({page}) => {
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: currentPlan}));
  await page.route("**/api/v1/billing/signup/", route => route.fulfill({status: 400, json: {details: {slug: ["Endereço público já está em uso."]}}}));
  await page.goto("/cadastro");
  await fillSignup(page);
  await page.getByRole("button", {name: /Começar 30 dias grátis/}).click();
  await expect(page.getByRole("alert")).toContainText("Endereço público já está em uso.");
});

test("cadastro mostra indisponibilidade do checkout", async ({page}) => {
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: currentPlan}));
  await page.route("**/api/v1/billing/signup/", route => route.fulfill({status: 503, json: {}}));
  await page.goto("/cadastro");
  await fillSignup(page);
  await page.getByRole("button", {name: /Começar 30 dias grátis/}).click();
  await expect(page.getByRole("alert")).toContainText("Checkout indisponível. Tente novamente.");
});

test("regularização mostra erro serializado e indisponibilidade", async ({page}) => {
  let unavailable = false;
  await page.route("**/api/v1/billing/regularization/checkout/", route => route.fulfill(unavailable
    ? {status: 503, json: {}}
    : {status: 400, json: {token: ["Token inválido ou expirado."]}}));
  await page.goto("/regularizar?token=assinatura-segura");
  await page.getByRole("button", {name: /Regularizar assinatura/}).click();
  await expect(page.getByRole("alert")).toContainText("Token inválido ou expirado.");
  unavailable = true;
  await page.getByRole("button", {name: /Regularizar assinatura/}).click();
  await expect(page.getByRole("alert")).toContainText("Checkout indisponível. Tente novamente.");
});

test("cadastro deriva todo período de teste do plano publicado", async ({page}) => {
  const plan45 = {...currentPlan, trial_days: 45};
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: plan45}));
  await page.goto("/cadastro");
  await expect(page).toHaveTitle(/45 dias grátis/);
  await expect(page.getByRole("button", {name: /Começar 45 dias grátis/})).toBeVisible();
  await expect(page.getByText("45 dias grátis", {exact: true})).toBeVisible();
  await expect(page.getByText("30 dias grátis")).toHaveCount(0);

  await page.goto("/");
  await expect(page.getByRole("link", {name: "Começar 45 dias grátis"}).first()).toHaveAttribute("href", "/cadastro");
  await expect(page.getByText("30 dias grátis")).toHaveCount(0);
});

test("termos possui alvo de toque de 44px", async ({page}) => {
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: currentPlan}));
  await page.goto("/cadastro");
  const bounds = await page.locator(".billing-check").evaluate(element => element.getBoundingClientRect());
  expect(bounds.height).toBeGreaterThanOrEqual(44);
  await page.getByRole("checkbox", {name: /termos/}).focus();
  await expect(page.getByRole("checkbox", {name: /termos/})).toBeFocused();
});

test("Turnstile falho mostra recuperação e permite nova tentativa", async ({page}) => {
  test.skip(!process.env.VITE_TURNSTILE_SITE_KEY, "executado com site key de teste");
  await page.route("**/turnstile/v0/api.js**", route => route.abort("failed"));
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: currentPlan}));
  await page.goto("/cadastro");
  await expect(page.getByRole("alert")).toContainText("Não foi possível carregar a verificação anti-bot.");
  const retryBounds = await page.getByRole("button", {name: "Tentar novamente"}).evaluate(element => element.getBoundingClientRect());
  expect(retryBounds.height).toBeGreaterThanOrEqual(44);
  await page.evaluate(() => {
    window.turnstile = {render: (_element, options) => { options.callback("turnstile-test-token"); return "turnstile-test-widget"; }};
  });
  await page.getByRole("button", {name: "Tentar novamente"}).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("button", {name: /Começar 30 dias grátis/})).toBeDisabled();
  await fillSignup(page);
  await expect(page.getByRole("button", {name: /Começar 30 dias grátis/})).toBeEnabled();
});

let regularizationToken: string | null = null;

export function extractRegularizationToken() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path !== "/regularizar") return false;

  const url = new URL(window.location.href);
  const token = url.searchParams.get("token");
  if (!token) return false;

  regularizationToken = token;
  url.searchParams.delete("token");
  window.history.replaceState(
    window.history.state,
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
  return true;
}

export function getRegularizationToken() {
  return regularizationToken;
}

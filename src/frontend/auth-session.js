/* Same-tab authentication across service, intro and forest navigations.
 * Storage is only a transport: every restored session is verified by the API. */
((root) => {
  "use strict";
  const KEY = "gandang-auth-session-v1";
  function clear() { try { root.sessionStorage.removeItem(KEY); } catch {} }
  function save(token) {
    if (typeof token !== "string" || !token || token === "local-demo-token") return;
    let expiresAt = Date.now() + 30 * 60 * 1000;
    try {
      const payload = JSON.parse(root.atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
      if (Number.isFinite(payload.exp)) expiresAt = payload.exp * 1000;
    } catch { /* The server remains responsible for token validation. */ }
    if (expiresAt <= Date.now()) { clear(); return; }
    try { root.sessionStorage.setItem(KEY, JSON.stringify({ token, expiresAt })); } catch {}
  }
  function read() {
    try {
      const session = JSON.parse(root.sessionStorage.getItem(KEY));
      if (typeof session?.token === "string" && session.token && Number.isFinite(session.expiresAt) && session.expiresAt > Date.now()) return session.token;
    } catch {}
    clear(); return null;
  }
  function authError() { return Object.assign(new Error("로그인이 필요합니다."), { status: 401 }); }
  async function resolve({ signal, fetchImpl = root.fetch.bind(root), forceRefresh = false } = {}) {
    const options = { credentials: "same-origin", cache: "no-store", signal };
    async function verify(token) {
      const response = await fetchImpl("/api/v1/users/me", { ...options, headers: { Authorization: "Bearer " + token } });
      if ([401, 403].includes(response.status)) { clear(); return null; }
      if (!response.ok) throw Object.assign(new Error("로그인 상태를 확인하지 못했습니다."), { status: response.status });
      const payload = await response.json();
      save(token); return { token, profile: payload.data ?? payload };
    }
    const current = forceRefresh ? null : read();
    if (current) {
      const verified = await verify(current);
      if (verified) return verified;
    }
    const response = await fetchImpl("/api/v1/auth/token/refresh", options);
    if ([400, 401, 403].includes(response.status)) { clear(); throw authError(); }
    if (!response.ok) throw Object.assign(new Error("로그인 상태를 확인하지 못했습니다."), { status: response.status });
    const payload = await response.json(), token = (payload.data ?? payload).access_token;
    if (typeof token !== "string" || !token) { clear(); throw authError(); }
    const verified = await verify(token);
    if (!verified) throw authError();
    return verified;
  }
  root.GandangAuthSession = Object.freeze({ save, read, clear, resolve });
})(typeof window !== "undefined" ? window : globalThis);

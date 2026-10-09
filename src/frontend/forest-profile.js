/* Display-only account name bridge. Editing belongs to the main MVP profile. */
((root) => {
  "use strict";
  const PROFILE_URL = "/?account=profile";
  const REVISION_KEY = "gandang-account-profile-revision";
  async function loadName(fetchImpl = root.fetch.bind(root), signal) {
    if (root.GandangAuthSession) {
      const { profile } = await root.GandangAuthSession.resolve({ signal, fetchImpl });
      return typeof profile.name === "string" && profile.name.trim() ? profile.name.trim() : "숲지기";
    }
    const options = { credentials: "same-origin", cache: "no-store", signal };
    const session = await fetchImpl("/api/v1/auth/token/refresh", options);
    if (!session.ok) return null;
    const token = (await session.json()).access_token;
    if (typeof token !== "string" || !token) return null;
    const response = await fetchImpl("/api/v1/users/me", {
      ...options, headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) return null;
    const payload = await response.json();
    const name = payload.name;
    if (name === null || (typeof name === "string" && !name.trim())) return "숲지기";
    return typeof name === "string" ? name.trim() : null;
  }

  function watch(onName) {
    let disposed = false, sequence = 0, controller = null;
    const channel = typeof root.BroadcastChannel === "function"
      ? new root.BroadcastChannel("gandang-account-profile") : null;
    async function refresh() {
      const current = ++sequence;
      controller?.abort();
      controller = new AbortController();
      const active = controller;
      const timeout = root.setTimeout(() => active.abort(), 5000);
      let name = null;
      try { name = await loadName(root.fetch.bind(root), active.signal); } catch { /* Keep the last display name on temporary errors; forest-access.js guards entry. */ }
      finally { root.clearTimeout(timeout); }
      if (!disposed && current === sequence) onName(name);
    }
    const visible = () => { if (!root.document.hidden) refresh(); };
    const changed = event => { if (event.key === REVISION_KEY) refresh(); };
    const message = event => { if (event.data?.type === "updated") refresh(); };
    root.addEventListener("focus", visible);
    root.addEventListener("pageshow", visible);
    root.addEventListener("storage", changed);
    root.document.addEventListener("visibilitychange", visible);
    channel?.addEventListener("message", message);
    refresh();
    return {
      refresh,
      dispose() {
        disposed = true; ++sequence; controller?.abort(); channel?.close();
        root.removeEventListener("focus", visible);
        root.removeEventListener("pageshow", visible);
        root.removeEventListener("storage", changed);
        root.document.removeEventListener("visibilitychange", visible);
      },
    };
  }
  root.ForestProfile = Object.freeze({ PROFILE_URL, REVISION_KEY, loadName, watch });
})(typeof window !== "undefined" ? window : globalThis);

/* Authenticate before any game code runs, including direct and native URLs. */
(() => {
  "use strict";
  const loginUrl = "/service?auth=login&returnTo=forest";
  let loaded = false, checking = false, restoreReady = false;
  const status = () => document.querySelector(".forest-boot-status");
  function message(text) { if (status()) status().textContent = text; }
  function failure() {
    document.documentElement.classList.remove("forest-script-ready");
    message("로그인 상태를 확인하지 못했어요. 연결을 확인한 뒤 다시 시도해 주세요.");
    let retry = document.getElementById("forest-access-retry");
    if (!retry) {
      retry = document.createElement("button"); retry.id = "forest-access-retry"; retry.type = "button";
      retry.textContent = "다시 확인"; retry.style.cssText = "margin-top:16px;padding:12px 20px;border:2px solid #39752d;border-radius:12px;background:#fff;color:#155528;font:inherit;cursor:pointer";
      retry.addEventListener("click", check); document.querySelector(".forest-boot-panel").append(retry);
    }
    retry.hidden = false;
  }
  async function check() {
    if (checking) return;
    checking = true;
    restoreReady ||= document.documentElement.classList.contains("forest-script-ready");
    document.documentElement.classList.remove("forest-script-ready");
    document.getElementById("forest-access-retry")?.setAttribute("hidden", "");
    message("로그인 상태를 확인하고 있어요");
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 10000);
    try {
      await window.GandangAuthSession.resolve({ signal: controller.signal });
      clearTimeout(timer);
      if (!loaded) {
        message("숲을 준비하고 있어요");
        // async=false preserves the original dependency order while downloads overlap.
        const pending = [...document.querySelectorAll("script[data-forest-script]")].map(source => new Promise((resolve,reject) => {
          const script = document.createElement("script"); script.async = false; script.src = source.src;
          script.onload = resolve; script.onerror = reject; document.head.append(script);
        }));
        await Promise.all(pending); loaded = true;
      } else if (restoreReady) document.documentElement.classList.add("forest-script-ready");
    } catch (error) {
      if ([401, 403].includes(error.status)) { location.replace(loginUrl); return; }
      failure();
    }
    finally { clearTimeout(timer); checking = false; }
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && loaded) void check(); });
  window.addEventListener("pageshow", event => { if (event.persisted) void check(); });
  void check();
})();

/* Server receipts own currency. Browser saves contain only game presentation. */
((root) => {
  "use strict";
  class ForestAccountWallet {
    constructor(host = root) {
      this.host = host;
      this.userId = null;
      this.token = null;
      this.value = null;
      this.queue = Promise.resolve();
    }
    async connect() {
      const session = await this.host.GandangAuthSession.resolve();
      this.userId = session.profile.id;
      this.token = session.token;
      return this.refresh();
    }
    accept(payload) {
      if (!payload || payload.user_id !== this.userId || !Number.isInteger(payload.carrot_balance) || payload.carrot_balance < 0) return false;
      const stamp = payload.wallet_updated_at || payload.updated_at;
      const previous = this.value?.wallet_updated_at || this.value?.updated_at;
      if (Number.isInteger(this.value?.wallet_revision) && Number.isInteger(payload.wallet_revision) && payload.wallet_revision < this.value.wallet_revision) return true;
      if (previous && stamp && Date.parse(stamp) < Date.parse(previous)) return true;
      this.value = { ...this.value, ...payload };
      this.host.dispatchEvent(new this.host.CustomEvent("forest-wallet-updated", { detail: this.value }));
      return true;
    }
    async request(path, options = {}, retry = true) {
      if (!this.token || this.userId == null) throw new Error("계정 지갑에 연결한 뒤 다시 시도해 주세요.");
      const response = await this.host.fetch(`/api/v1${path}`, {
        ...options, credentials: "same-origin", cache: "no-store",
        headers: { Authorization: `Bearer ${this.token}`, ...(options.body ? { "Content-Type": "application/json" } : {}) },
      });
      if (response.status === 401 && retry) {
        const session = await this.host.GandangAuthSession.resolve({ forceRefresh: true });
        if (session.profile.id !== this.userId) throw new Error("계정이 변경되었습니다. 숲을 다시 열어 주세요.");
        this.token = session.token;
        return this.request(path, options, false);
      }
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "당근 기록을 저장하지 못했습니다. 다시 시도해 주세요.");
      const payload = result.data ?? result;
      if (!this.accept(payload)) throw new Error("계정 지갑 응답을 확인하지 못했습니다. 다시 열어 주세요.");
      return payload;
    }
    refresh() { return this.request("/wallet"); }
    newRequestId() {
      if (this.host.crypto.randomUUID) return this.host.crypto.randomUUID();
      const bytes = this.host.crypto.getRandomValues(new Uint8Array(16));
      bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
      const hex = [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
      return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
    }
    perform(action, requestId = this.newRequestId()) {
      const body = JSON.stringify({ action, request_id: requestId });
      const operation = this.queue.catch(() => {}).then(async () => {
        try { return await this.request("/forest/wallet/actions", { method: "POST", body }); }
        catch (error) {
          // A dropped response can follow a committed debit/grant. Reuse the exact
          // receipt key when retrying; an HTTP validation error is not retried.
          if (!(error instanceof TypeError)) throw error;
          return this.request("/forest/wallet/actions", { method: "POST", body });
        }
      });
      this.queue = operation;
      return operation;
    }
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { ForestAccountWallet };
  else root.ForestWallet = new ForestAccountWallet(root);
})(typeof window !== "undefined" ? window : globalThis);

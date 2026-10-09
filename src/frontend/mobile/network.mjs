
export function validateApiOrigin(value) {
  const url = new URL(value);
  const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
  if (url.username || url.password || url.pathname !== '/' || url.search || url.hash ||
      !(url.protocol === 'https:' || (url.protocol === 'http:' && loopback))) {
    throw new Error('API address must be an HTTPS origin or a local loopback HTTP origin');
  }
  return url.origin;
}
export const API_ORIGIN = validateApiOrigin(
  typeof __MOBILE_API_ORIGIN__ === 'undefined' ? 'https://www.dang-no.life' : __MOBILE_API_ORIGIN__
);

// Rewrite only this app's API paths. Never forward credentials from another host.
export function createApiFetch(fetchImpl, localOrigin) {
  const local = new URL(localOrigin);
  return (input, init) => {
    const isRequest = input instanceof Request;
    const url = new URL(isRequest ? input.url : input, localOrigin);
    if (url.protocol !== local.protocol || url.host !== local.host || !url.pathname.startsWith('/api/')) {
      return fetchImpl(input, init);
    }
    const target = API_ORIGIN + url.pathname + url.search;
    const options = { ...init, credentials: 'include' };
    // Preserve FormData boundaries and bodies; do not JSON-encode file uploads.
    return fetchImpl(isRequest ? new Request(target, input) : target, options);
  };
}

// A compatibility gate, not an identity/security check: browsers can spoof
// their identity. Prefer Chrome's explicit brand over the shared Chrome UA token.
export function isDesktopChrome(browser = navigator) {
  const ua = browser.userAgent || '', hints = browser.userAgentData;
  if (hints?.mobile || hints?.platform === 'Android' || /Android|Mobile|iPhone|iPad|iPod|CriOS/i.test(ua) ||
      (browser.platform === 'MacIntel' && browser.maxTouchPoints > 1)) return false;
  if (browser.brave || /Edg(?:e|A|iOS)?\/|OPR\/|Opera|Vivaldi\/|YaBrowser\/|SamsungBrowser\//i.test(ua)) return false;
  if (hints?.brands?.length) return hints.brands.some(({brand}) => brand === 'Google Chrome');
  return browser.vendor === 'Google Inc.' && /\bChrome\/\d+/.test(ua) && !/\bChromium\//.test(ua);
}

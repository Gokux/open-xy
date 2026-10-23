// Check exposed APIs without requesting permissions or touching a device.
// Mobile browsers are outside the desktop setup workflow, including iPadOS
// presenting a desktop user agent. Browser identity is not a security boundary.
export function supportsDeviceApis(browser = navigator) {
  const ua = browser.userAgent || '', hints = browser.userAgentData;
  if (hints?.mobile || hints?.platform === 'Android' || /Android|Mobile|iPhone|iPad|iPod|CriOS/i.test(ua) ||
      (browser.platform === 'MacIntel' && browser.maxTouchPoints > 1)) return false;
  return typeof browser.requestMIDIAccess === 'function' && typeof browser.usb?.requestDevice === 'function';
}

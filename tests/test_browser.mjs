import test from 'node:test';
import assert from 'node:assert/strict';
import {isDesktopChrome} from '../builder/browser.mjs';

const chrome = {
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36',
  vendor: 'Google Inc.', platform: 'Win32',
};
const brands = (...names) => ({brands: names.map(brand => ({brand, version:'141'})), mobile:false, platform:'Windows'});

test('desktop Chrome works with client hints and the legacy/offline identity', () => {
  assert.equal(isDesktopChrome({...chrome, userAgentData:brands('Not;A Brand', 'Chromium', 'Google Chrome')}), true);
  assert.equal(isDesktopChrome(chrome), true);
  assert.equal(isDesktopChrome({...chrome, platform:'MacIntel', userAgent:chrome.userAgent.replace('Windows NT 10.0; Win64; x64', 'Macintosh; Intel Mac OS X 10_15_7')}), true);
});

test('other browser brands and unknown identities remain blocked', () => {
  for (const name of ['Microsoft Edge', 'Opera', 'Brave', 'Chromium'])
    assert.equal(isDesktopChrome({...chrome, userAgentData:brands(name)}), false, name);
  for (const suffix of ['Edg/141.0', 'OPR/126.0', 'Vivaldi/7.0', 'YaBrowser/25.0', 'SamsungBrowser/28.0'])
    assert.equal(isDesktopChrome({...chrome, userAgent:chrome.userAgent + ' ' + suffix}), false, suffix);
  assert.equal(isDesktopChrome({...chrome, brave:{}}), false);
  assert.equal(isDesktopChrome({userAgent:'Mozilla/5.0 Firefox/143.0', vendor:''}), false);
  assert.equal(isDesktopChrome({userAgent:'Mozilla/5.0 Version/26.0 Safari/605.1.15', vendor:'Apple Computer, Inc.'}), false);
  assert.equal(isDesktopChrome({}), false);
});

test('mobile Chrome and tablets in desktop mode cannot pass the desktop gate', () => {
  assert.equal(isDesktopChrome({...chrome, userAgentData:{...brands('Google Chrome'), mobile:true}}), false);
  assert.equal(isDesktopChrome({...chrome, userAgentData:{...brands('Google Chrome'), platform:'Android'}}), false);
  assert.equal(isDesktopChrome({...chrome, userAgent:'Mozilla/5.0 (iPhone) CriOS/141.0 Mobile Safari/604.1'}), false);
  assert.equal(isDesktopChrome({...chrome, userAgent:chrome.userAgent + ' Android 15'}), false);
  assert.equal(isDesktopChrome({...chrome, platform:'MacIntel', maxTouchPoints:5}), false);
});

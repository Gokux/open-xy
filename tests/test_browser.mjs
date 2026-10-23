import test from 'node:test';
import assert from 'node:assert/strict';
import {supportsDeviceApis} from '../builder/browser.mjs';

const desktop = {
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36',
  vendor: 'Google Inc.', platform: 'Win32',
  requestMIDIAccess() { throw new Error('The gate must not request MIDI permissions'); },
  usb: {requestDevice() { throw new Error('The gate must not request USB permissions'); }},
};
const brands = (...names) => ({brands: names.map(brand => ({brand, version:'141'})), mobile:false, platform:'Windows'});

test('any desktop browser with both APIs passes without requesting permissions', () => {
  for (const name of ['Google Chrome', 'Microsoft Edge', 'Opera', 'Brave', 'Chromium', 'Another browser'])
    assert.equal(supportsDeviceApis({...desktop, userAgentData:brands(name)}), true, name);
  assert.equal(supportsDeviceApis(desktop), true);
  assert.equal(supportsDeviceApis({...desktop, platform:'MacIntel'}), true);
});

test('missing or nonfunctional API entries block even a Chrome identity', () => {
  for (const override of [{usb:undefined}, {usb:{}}, {usb:{requestDevice:true}},
    {requestMIDIAccess:undefined}, {requestMIDIAccess:true}])
    assert.equal(supportsDeviceApis({...desktop, ...override}), false);
  assert.equal(supportsDeviceApis({}), false);
});

test('mobile Chrome and tablets in desktop mode cannot pass the desktop gate', () => {
  assert.equal(supportsDeviceApis({...desktop, userAgentData:{...brands('Google Chrome'), mobile:true}}), false);
  assert.equal(supportsDeviceApis({...desktop, userAgentData:{...brands('Google Chrome'), platform:'Android'}}), false);
  assert.equal(supportsDeviceApis({...desktop, userAgent:'Mozilla/5.0 (iPhone) CriOS/141.0 Mobile Safari/604.1'}), false);
  assert.equal(supportsDeviceApis({...desktop, userAgent:desktop.userAgent + ' Android 15'}), false);
  assert.equal(supportsDeviceApis({...desktop, platform:'MacIntel', maxTouchPoints:5}), false);
});

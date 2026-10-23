import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createWizard} from '../builder/wizard.mjs';
import * as Visuals from '../builder/visuals.mjs';
import {sha256} from '../builder/core.mjs';
import {fakeDevice} from './fixtures/mtp.mjs';

// Minimal DOM for exercising the real wizard's navigation and device guards.
class Element {
  children = []; dataset = {}; style = {}; hidden = false; textContent = '';
  classList = {add() {}, remove() {}};
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  removeAttribute(name) { delete this[name]; }
  addEventListener() {}
  focus() {}
}

function sourceFlow(t, {fake, bytes, hash, usb = true}) {
  const html = readFileSync(new URL('../builder/index.html', import.meta.url), 'utf8');
  const elements = new Map([...html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)].map(([tag, id]) =>
    [id, Object.assign(new Element(), {hidden: /\bhidden\b/.test(tag)})]));
  const $ = id => { assert.ok(elements.has(id), id); return elements.get(id); };
  let requests = 0, accepted = [];
  const globals = {
    document: {getElementById: $, createElement: () => new Element(), createElementNS: () => new Element(),
      querySelector: () => new Element()},
    window: {addEventListener() {}}, matchMedia: () => ({matches: true}), isSecureContext: true,
    navigator: {usb: usb ? {requestDevice: async () => { requests++; return fake.device; }} : undefined},
  };
  for (const [name, value] of Object.entries(globals)) {
    const previous = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, {value, configurable: true});
    t.after(() => previous ? Object.defineProperty(globalThis, name, previous) : delete globalThis[name]);
  }
  const wizard = createWizard({getKit: () => ({profile: {stock_bytes: bytes.length, stock_sha256: hash}, machines: []}),
    getSelected: () => [], hasDownload: () => true, getFiles: () => ({}),
    onFirmware: async (file, isCurrent) => { assert.equal(isCurrent(), true); accepted.push(new Uint8Array(await file.arrayBuffer())); return true; }});
  const click = label => {
    const button = $('flow-actions').children.find(b => b.id === label || b.textContent === label);
    assert.ok(button, `Missing action: ${label}`); assert.equal(button.disabled, false); return button.onclick();
  };
  const reachTransfer = computer => {
    $('source-' + computer).onclick(); $('source-device').onclick();
    click('version-yes'); click('Connected and at te-boot'); click('menu-yes');
    assert.equal($('device-flow').dataset.stage, 'open-dev-menu');
    click('Dev menu is open'); click('I see "mtp mode active"');
  };
  return {$, wizard, click, reachTransfer, accepted, requests: () => requests};
}

test('Mac reads and verifies the original OS, then remembers transfer mode for installation', async t => {
  const bytes = Uint8Array.from({length: 2048}, (_, i) => i * 7);
  const fake = fakeDevice({files: {'upgrade/firmware/blackfin/bin/os.ldr': bytes, 'os.ldr': Uint8Array.of(99)}, split: true});
  const f = sourceFlow(t, {fake, bytes, hash: await sha256(bytes)}), {$, click} = f;
  assert.equal($('computer-choice').hidden, false); assert.equal($('source-start').hidden, true);
  f.reachTransfer('mac');
  assert.equal($('flow-title').textContent, 'Quit Field Kit and OpenMTP.');
  assert.equal(f.requests(), 0); assert.equal($('flow-install-reminder').hidden, true);
  click('field-kit-closed'); await click('mtp-read');
  assert.deepEqual(f.accepted, [bytes]); assert.equal(fake.state.opened, false);
  assert.equal($('file-panel').hidden, false); assert.equal($('device-flow').hidden, true);
  assert.equal($('source-backup').hidden, false); assert.match($('source-backup').href, /^blob:/);
  assert.deepEqual(new Uint8Array(await (await fetch($('source-backup').href)).arrayBuffer()), bytes);
  f.wizard.clearSourceBackup(); assert.equal($('source-backup').hidden, true);
  assert.ok(!fake.state.ops.some(op => ['100b', '100c', '100d'].includes(op)));
  f.wizard.navigate(3);
  assert.equal($('download').hidden, true); assert.equal($('route-mac').hidden, false);
  $('route-mac').onclick({preventDefault() {}});
  assert.equal($('device-flow').dataset.stage, 'close-field-kit');
  click('field-kit-closed'); assert.equal($('flow-title').textContent, 'Send the files to your OP–XY.');
  assert.equal($('flow-install-reminder').hidden, false);
});

test('wrong stock hash, missing original and busy apps never load an OS', async t => {
  const bytes = Uint8Array.of(1, 2, 3), hash = await sha256(bytes);
  for (const options of [{files: {'upgrade/firmware/blackfin/bin/os.ldr': Uint8Array.of(4, 5, 6)}},
    {files: {'os.ldr': bytes}}, {busy: true}]) await t.test(JSON.stringify(options), async t => {
    const fake = fakeDevice(options), f = sourceFlow(t, {fake, bytes, hash});
    f.reachTransfer('mac'); f.click('field-kit-closed'); await f.click('mtp-read');
    assert.deepEqual(f.accepted, []); assert.equal(f.$('dev-status').dataset.error, 'true');
    assert.equal(f.$('device-flow').dataset.stage, 'transfer'); assert.equal(fake.state.opened, false);
    assert.ok(!fake.state.ops.some(op => ['100b', '100c', '100d'].includes(op)));
  });
});

test('Windows and browsers without WebUSB keep the manual source path', async t => {
  for (const [computer, usb] of [['windows', true], ['mac', false]]) await t.test(computer, t => {
    const f = sourceFlow(t, {fake: fakeDevice(), bytes: new Uint8Array(1), hash: '', usb});
    f.reachTransfer(computer);
    assert.equal(f.$('device-flow').dataset.stage, 'transfer');
    assert.equal(f.$('flow-title').textContent, 'Copy the OS file.');
    assert.equal(f.requests(), 0); assert.equal(f.$('flow-install-reminder').hidden, true);
  });
});

test('stopping a Mac read discards it and releases USB before a retry', async t => {
  const bytes = new Uint8Array(32), fake = fakeDevice({files: {'upgrade/firmware/blackfin/bin/os.ldr': bytes}, hang: 0x1009});
  const f = sourceFlow(t, {fake, bytes, hash: await sha256(bytes)});
  f.reachTransfer('mac'); f.click('field-kit-closed'); const reading = f.click('mtp-read');
  while (!fake.state.abort) await new Promise(resolve => setTimeout(resolve, 0));
  f.$('dev-cancel').onclick(); await reading;
  assert.deepEqual(f.accepted, []); assert.equal(fake.state.opened, false);
  assert.equal(f.$('dev-cancel').hidden, true);
});

test('installation links preview the edited steps without a build or device access', async t => {
  const html = readFileSync(new URL('../builder/index.html', import.meta.url), 'utf8');
  const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
  const $ = id => { assert.ok(elements.has(id), `Missing authored element: ${id}`); return elements.get(id); };
  let deviceRequests = 0, exits = 0;
  const listeners = new Map();
  const pages = [1, 2, 3].map(page => Object.assign(new Element(), {dataset: {page: String(page)}}));
  const steps = [1, 2, 3].map(step => Object.assign(new Element(), {dataset: {step: String(step)}}));
  const location = {hash: '#preview/mac/transfer', pathname: '/', search: ''};
  const globals = {
    document: {
      getElementById: $, createElement: () => new Element(), createElementNS: () => new Element(),
      addEventListener() {},
      querySelectorAll: selector => ({'[data-icon]': [], '[data-page]': pages, '.steps button': steps}[selector] ?? []),
      querySelector: selector => {
        const match = /^\[data-page="([123])"\]( h1)?$/.exec(selector);
        assert.ok(match, `Unexpected selector: ${selector}`);
        return match[2] ? $(['input-title', 'machines-title', 'download-title'][Number(match[1]) - 1]) : pages[Number(match[1]) - 1];
      },
    },
    window: {addEventListener: (event, listener) => listeners.set(event, listener)},
    location,
    history: {replaceState() { location.hash = ''; }},
    matchMedia: () => ({matches: true}),
    isSecureContext: true,
    navigator: {
      usb: {requestDevice: () => { deviceRequests++; throw new Error('Unexpected USB access'); }},
      requestMIDIAccess: () => { deviceRequests++; throw new Error('Unexpected MIDI access'); },
    },
  };
  for (const [name, value] of Object.entries(globals)) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, {value, configurable: true});
    t.after(() => descriptor ? Object.defineProperty(globalThis, name, descriptor) : delete globalThis[name]);
  }
  const wizard = createWizard({getKit: () => null, getSelected: () => [], hasDownload: () => false,
    getFiles: () => ({'os.ldr': new Uint8Array(1)}), onPreviewExit: () => exits++});
  const action = label => {
    const button = $('flow-actions').children.find(button => button.textContent === label || button.id === label);
    assert.ok(button, `Missing action: ${label}`); return button;
  };

  for (const hash of ['#preview/mac/transfer', '#preview/windows/transfer']) {
    assert.equal(wizard.previewLink(hash), true);
    assert.equal($('flow-install-reminder').hidden, false);
    assert.equal($('flow-preview-note').hidden, false);
    assert.equal($('flow-download').hidden, true);
  }
  wizard.previewLink('#preview/mac/transfer');
  assert.equal($('flow-title').textContent, 'Send the files to your OP–XY.');
  assert.equal(action('mtp-send').disabled, true);
  await action('mtp-send').onclick(); // Also guard the handler, independently of the disabled button.
  assert.equal(deviceRequests, 0);
  action('Preview next step').onclick();
  assert.equal($('device-flow').dataset.stage, 'exit-transfer');
  assert.equal($('flow-install-reminder').hidden, false);
  action('I’m back at the dev menu').onclick();
  assert.equal($('device-flow').dataset.stage, 'write-os');
  assert.equal($('flow-install-reminder').hidden, false);
  action('I pressed track 5').onclick();
  assert.equal($('flow-install-reminder').hidden, true);

  for (const stage of ['boot', 'start-transfer', 'close-field-kit']) {
    assert.equal(wizard.previewLink('#preview/mac/' + stage), true);
    assert.equal($('flow-install-reminder').hidden, true);
  }
  assert.equal(wizard.previewLink('#preview/source/mac/transfer'), true);
  assert.equal(wizard.previewPage(), 1);
  assert.equal($('flow-install-reminder').hidden, true);
  assert.equal(action('mtp-read').disabled, true);
  await action('mtp-read').onclick();
  assert.equal(deviceRequests, 0);
  wizard.previewLink('#preview/mac/menu');
  action('menu-no').onclick();
  assert.equal(action('dev-connect').disabled, true);
  await action('dev-connect').onclick();
  assert.equal(deviceRequests, 0);
  for (const hash of ['#preview/mac/enable', '#preview/linux/transfer', '#preview/mac/transfer/extra']) {
    assert.equal(wizard.previewLink(hash), false);
    assert.equal($('device-flow').dataset.stage, 'connect');
  }
  $('flow-exit').onclick();
  assert.equal(exits, 1);
  assert.equal($('device-flow').hidden, true);
  $('source-device').onclick();
  assert.equal($('flow-preview-note').hidden, true);
  assert.equal($('flow-install-reminder').hidden, true);

  // Run the actual app startup against the same DOM. It must render a valid
  // preview before waiting for acknowledgement, without booting the builder.
  const source = readFileSync(new URL('../builder/app.mjs', import.meta.url), 'utf8').replace(/^import .*\r?\n/gm, '');
  const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
  let startupError;
  new AsyncFunction('Wizard', 'Visuals', source)({createWizard}, Visuals).catch(error => { startupError = error; });
  await Promise.resolve();
  assert.ifError(startupError);
  assert.equal($('risk-gate').hidden, true);
  assert.equal($('risk-acknowledgement').checked, false);
  assert.equal($('builder-workspace').inert, false);
  assert.equal($('device-flow').dataset.stage, 'transfer');
  assert.equal(action('mtp-send').disabled, true);
  $('flow-exit').onclick();
  assert.equal($('risk-gate').hidden, false);
  assert.equal($('builder-workspace').inert, true);
  assert.equal($('risk-acknowledgement').checked, false);
  location.hash = '#preview/mac/write-os';
  listeners.get('hashchange')();
  assert.equal($('risk-gate').hidden, true);
  assert.equal($('device-flow').dataset.stage, 'write-os');
  location.hash = '#preview/mac/not-a-step';
  listeners.get('hashchange')();
  assert.equal($('risk-gate').hidden, false);
  assert.equal($('builder-workspace').inert, true);
  assert.equal(deviceRequests, 0);
  location.hash = '#preview/source/mac/transfer';
  listeners.get('hashchange')();
  assert.equal($('device-flow').dataset.stage, 'transfer');
  assert.equal($('risk-gate').hidden, true);
  assert.equal(action('mtp-read').disabled, true);
  assert.equal(pages[0].hidden, false);
});

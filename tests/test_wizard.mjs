import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createWizard} from '../builder/wizard.mjs';
import * as Visuals from '../builder/visuals.mjs';

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
    assert.equal($('flow-step-link').href, hash);
  }
  wizard.previewLink('#preview/mac/transfer');
  assert.equal($('flow-title').textContent, 'Send the files to your OP–XY.');
  assert.equal(action('mtp-send').disabled, true);
  await action('mtp-send').onclick(); // Also guard the handler, independently of the disabled button.
  assert.equal(deviceRequests, 0);
  action('Preview next step').onclick();
  assert.equal($('device-flow').dataset.stage, 'exit-transfer');
  assert.equal($('flow-install-reminder').hidden, false);
  action('I’m back at the factory menu').onclick();
  assert.equal($('device-flow').dataset.stage, 'write-os');
  assert.equal($('flow-install-reminder').hidden, false);
  action('I pressed track 5').onclick();
  assert.equal($('flow-install-reminder').hidden, true);

  for (const stage of ['boot', 'start-transfer', 'close-field-kit']) {
    assert.equal(wizard.previewLink('#preview/mac/' + stage), true);
    assert.equal($('flow-install-reminder').hidden, true);
  }
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
});

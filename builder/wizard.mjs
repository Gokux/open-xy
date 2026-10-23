import * as Ferret from './ferret.mjs';
import * as Mtp from './mtp.mjs';
import * as Visuals from './visuals.mjs';
import {presetPath} from './core.mjs';

// Screen state is supplied by the user at the relevant step. Only the explicit
// Find / Enable / Disable actions access MIDI. On a Mac with WebUSB, Send to
// OP–XY copies the build over USB, opening the device only while sending;
// otherwise copying is manual. Flashing remains manual.
export function createWizard({getKit, getSelected, hasDownload, getFiles, onPreviewExit = () => {}}) {
  const $ = id => document.getElementById(id);
  let purpose = null, stage = null, history = [], revision = 0;
  // Set when the OS-copy guide ends in file transfer mode, so the install guide
  // can continue there; `resumed` marks an install guide that started there.
  let inTransfer = false, resumed = false, transferComputer = null;
  let computer = null, busy = false, connected = false;
  let hostPage = 1;
  let previewMode = false;
  const previewStages = new Set(['boot', 'menu', 'open-dev-menu', 'start-transfer', 'close-field-kit',
    'transfer', 'exit-transfer', 'write-os', 'write-result', 'write-help', 'restart']);
  // Installing from this page: the chosen device, progress through the build,
  // a log of what happened, and whether every file arrived. `manual` means the user chose to copy.
  let mtp = null, sending = null, log = [], delivered = false, manual = false, downloaded = false;
  // Closing finishes before the device is opened again.
  let closing = Promise.resolve();
  const stopSending = () => { sending = null; if (mtp) closing = mtp.close(); };
  const release = () => { stopSending(); mtp = null; log = []; delivered = false; };
  const sendsDirectly = () => computer === 'mac' && (previewMode || Mtp.supported()) && !manual;
  const direct = () => stage === 'transfer' && purpose === 'install' && sendsDirectly();
  const supported = () => globalThis.isSecureContext && !!navigator.requestMIDIAccess;
  const status = (message = '', error = false) => {
    $('dev-status').textContent = message; $('dev-status').dataset.error = String(error);
  };
  const session = new Ferret.Session(options => navigator.requestMIDIAccess(options), () => {
    connected = false;
    if (['enable', 'disable'].includes(stage) && !busy) { advance('connect'); status('Connection lost. Find your OP–XY again.', true); }
  }, 2500, {onProgress: message => { if (stage) status(message); }});
  window.addEventListener('pagehide', () => { session.close(); release(); });
  const action = (label, next, id) => ({label, next, id});
  function content() {
    const install = purpose === 'install', disabling = purpose === 'disable', kit = getKit();
    const transfer = computer ? 'open-dev-menu' : 'computer';
    const stillInTransfer = 'Your OP–XY should still be in file transfer mode from copying the OS file. If it isn’t, start from the beginning.';
    const transferSteps = [
      computer === 'mac' ? 'Open Field Kit or OpenMTP.' : 'Open your OP–XY in File Explorer.',
    ];
    if (install) {
      transferSteps.push(downloaded ? 'Extract the ZIP you just downloaded.' : 'Select Download ZIP below, then extract the ZIP.',
        'Drag everything from the extracted ZIP to your OP–XY’s root folder.',
        'Confirm when asked to replace files.');
      transferSteps.push('Wait until every file has finished copying.');
    } else {
      transferSteps.push('Open upgrade → firmware → blackfin → bin on your OP–XY, then copy the OS file, os.ldr, to this computer.',
        'If you previously installed open-xy, you can use the OS file, os.ldr, from the device’s top level instead.',
        'Leave your OP–XY in file transfer mode. Installing continues from here.');
    }
    return {
      version: ['Is your OP–XY on OS 1.2.0?', 'open-xy supports only OS 1.2.0. Install it on your OP–XY before you copy the OS file.', [action('Yes, it’s on 1.2.0', 'boot', 'version-yes'), action('No, or I’m not sure', 'version-help', 'version-no')]],
      'version-help': ['Install OS 1.2.0 first.', 'Use teenage engineering’s usual update steps to put OS 1.2.0 on your OP–XY, then come back. open-xy can’t work from any other version.', [action('It’s on 1.2.0 now', 'boot', 'version-done')]],
      boot: ['Start in the te-boot menu.', disabling ? 'Finish any file transfers or OS installation before disabling the menu.' : install ? '' : 'The OS file, os.ldr, is your device’s firmware. It is not the .tfw update file on teenage engineering’s site. Follow these steps to copy it.', [action('Connected and at te-boot', 'menu')], [
        'Power off your OP–XY.', 'Hold COM while switching it on.',
        'Release COM when the te-boot menu appears.', 'Connect it to this computer with USB.',
      ]],
      menu: ['Does your screen show "3. dev menu"?', 'Check the te-boot menu on your OP–XY.', [action('Yes, I see it', disabling ? 'connect' : transfer, 'menu-yes'), action('No, it’s missing', disabling ? 'disabled' : 'connect', 'menu-no')]],
      connect: ['Connect your OP–XY.', 'When you select Find OP–XY, allow MIDI access if prompted.', [action('Find OP–XY', null, 'dev-connect')], [
        'Connect your OP–XY to this computer with a USB-C data cable.',
        'Open this site in Chrome, Edge, or another browser that supports Web MIDI.',
        'Keep your OP–XY on the te-boot menu.',
      ]],
      enable: ['Enable the dev menu.', 'Your OP–XY is connected. This enables the menu; it does not change the OS.', [action('Enable dev menu', null, 'dev-enable')]],
      disable: ['Disable the dev menu.', 'This hides the dev menu. It does not uninstall your machines or restore the original OS.', [action('Disable dev menu', null, 'dev-disable')]],
      'refresh-open': ['Open the system menu.', 'On your OP–XY, press track 8 for "8. system menu".', [action('System menu is open', 'refresh-return')]],
      'refresh-return': ['Return to te-boot.', 'Press track 8 for "8. back" to refresh the te-boot menu.', [action('I’m back at te-boot', 'confirm')]],
      confirm: [disabling ? 'Has "3. dev menu" disappeared?' : 'Does your screen show "3. dev menu"?', 'Check the te-boot menu on your OP–XY.', disabling ? [action('It’s gone', 'disabled', 'dev-confirm'), action('It’s still there', 'disable-help')] : [action('Yes, I see it', transfer, 'dev-confirm'), action('No, it’s still missing', 'menu-help')]],
      'menu-help': ['The dev menu is still missing.', 'Stay on te-boot. Retry the connection or use Connection help below.', [action('Try connecting again', 'connect'), action('Refresh the screen again', 'refresh-open')]],
      'disable-help': ['The dev menu is still visible.', 'Stay on te-boot. Reconnect to try again, or refresh the screen once more.', [action('Try connecting again', 'connect'), action('Refresh the screen again', 'refresh-open')]],
      disabled: ['Dev menu hidden.', 'You can enable it again from “I don’t have the OS file” when you need it.', [action('Done', 'exit')]],
      computer: ['Which computer are you using?', 'The device has a transfer option for each system.', [action('Windows', 'open-dev-menu', 'computer-windows'), action('Mac', 'open-dev-menu', 'computer-mac')]],
      'open-dev-menu': ['Open the dev menu.', 'Press track 3 for "3. dev menu". The next screen is titled "factory menu".', [action('Factory menu is open', 'start-transfer')]],
      'start-transfer': ['Start file transfer.', computer === 'mac' ? 'Press track 2 for "2. mtp file transfer (mac)".' : 'Press track 3 for "3. mtp file transfer (windows)".', [action('I see "mtp mode active"', install && sendsDirectly() ? 'close-field-kit' : 'transfer')]],
      'close-field-kit': ['Make sure Field Kit isn’t running for this next step!', 'Field Kit holds your OP–XY’s USB connection while it’s open, so copying can’t start. Quit it, then continue.', [action('I closed Field Kit', 'transfer', 'field-kit-closed')]],
      transfer: install && sendsDirectly() ? ['Send the files to your OP–XY.',
        resumed ? stillInTransfer : 'Quit OpenMTP or Android File Transfer if either is open. Your device’s other content stays in place.',
        delivered ? [action('Files sent · Continue', 'exit-transfer')]
          : [action(busy ? 'Sending…' : log.length ? 'Try again' : 'Send to OP–XY', null, 'mtp-send'),
            ...(busy ? [] : [action('Copy them myself instead', null, 'mtp-manual')]), ...(resumed ? [action('Start from the beginning', 'boot', 'flow-restart')] : [])]] :
      [install ? 'Copy the ZIP’s files.' : 'Copy the OS file.', resumed ? stillInTransfer : 'Keep your device’s other content in place.', [action(install ? 'All files copied' : 'Files copied · Choose files', install ? 'exit-transfer' : 'files'), ...(resumed ? [action('Start from the beginning', 'boot', 'flow-restart')] : [])], transferSteps],
      'exit-transfer': ['Exit file transfer.', 'Once every file has finished copying, press track 2 for "2. exit".', [action('I’m back at the factory menu', 'write-os')]],
      'write-os': ['Write the OS.', 'Press track 5 for "5. write os to boot partition". Keep your OP–XY connected to power.', [action('I pressed track 5', 'write-result')]],
      'write-result': ['Wait for the write result.', 'Don’t power off while writing. When "firmware written ok!" appears under "looking for /os.ldr", it’s safe to power cycle your OP–XY.', [action('I see "firmware written ok!"', 'restart'), action('I see something else', 'write-help')]],
      'write-help': ['Check the message on your OP–XY.', 'If it stops at "looking for /os.ldr" without "firmware written ok!", os.ldr isn’t at the device’s top level. For any other message, stop here and investigate it before power cycling.', [action('Return to the write status', 'write-result')]],
      restart: ['Power cycle your OP–XY.', 'It’s safe now. Switch it off, then on again without holding COM. Then check your selected machines on the device.', [action('Device restarted · Done', 'exit'), action('Disable dev menu', null, 'disable-menu-after-install')]],
    }[stage];
  }
  function render(focus = false) {
    if (!stage) return;
    const [title, detail, actions, instructions = []] = content();
    $('device-flow').dataset.stage = stage;
    $('device-flow').setAttribute('aria-busy', String(busy));
    $('flow-progress').textContent = previewMode ? 'Installation preview' : (purpose === 'disable' ? 'Disable dev menu' : purpose === 'source' ? 'Copy OS' : 'Install on your OP–XY') + ' · Step ' + (history.length + 1);
    $('flow-preview-note').hidden = !previewMode;
    $('flow-title').textContent = title;
    const install = purpose === 'install';
    const kit = getKit();
    const files = [install ? 'os.ldr' : 'upgrade/firmware/blackfin/bin/os.ldr'];
    if (install) files.push('content/op1_factory.json');
    if (install) kit?.machines.filter(m => getSelected().includes(m.id) && m.artwork).forEach(m => files.push('content/display/' + m.asset));
    if (install) kit?.machines.filter(m => getSelected().includes(m.id)).forEach(m => {
      const path = presetPath(m);
      if (path) files.push(path);
    });
    const visual = Visuals.guide(stage, {install, computer, files, disabling: purpose === 'disable'});
    $('flow-visual').replaceChildren(visual);
    $('flow-file-details').hidden = stage !== 'transfer';
    if (focus) $('flow-file-details').open = false;
    $('flow-files').replaceChildren(...(stage === 'transfer' ? [Visuals.fileMap(install, files, install && sendsDirectly())] : []));
    $('flow-detail').textContent = detail; $('flow-detail').hidden = !detail;
    $('flow-instructions').replaceChildren(...instructions.map(text => {
      const li = document.createElement('li'), span = document.createElement('span');
      span.textContent = text; li.append(span); return li;
    }));
    $('flow-instructions').hidden = !instructions.length;
    $('flow-install-reminder').hidden = !install || !['transfer', 'exit-transfer', 'write-os'].includes(stage);
    const visibleActions = previewMode && stage === 'transfer'
      ? [...actions, action('Preview next step', 'exit-transfer')] : actions;
    $('flow-actions').replaceChildren(...visibleActions.map((a, i) => {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = a.label; button.className = i === 0 ? 'primary' : 'secondary';
      if (a.id) button.id = a.id;
      button.disabled = busy || (a.id === 'dev-connect' && !supported()) ||
        (previewMode && ['mtp-send', 'dev-connect', 'dev-enable', 'dev-disable', 'disable-menu-after-install'].includes(a.id));
      button.onclick = () => {
        if (['dev-connect', 'dev-enable', 'dev-disable'].includes(a.id)) return deviceAction(a.id);
        if (a.id === 'disable-menu-after-install') return begin('disable', 3);
        if (a.id === 'mtp-send') return sendBuild();
        if (a.id === 'mtp-manual') { manual = true; release(); status(); return render(true); }
        if (a.id === 'flow-restart') { inTransfer = resumed = false; history = []; stage = null; }
        if (a.id?.startsWith('computer-')) computer = a.id.slice(9);
        advance(a.next);
      };
      return button;
    }));
    renderDirect();
    $('dev-cancel').hidden = !busy;
    $('dev-cancel').textContent = sending ? 'Stop sending' : 'Cancel connection';
    $('flow-back').hidden = !history.length || ['write-os', 'write-result', 'write-help'].includes(stage);
    $('flow-back').disabled = $('flow-exit').disabled = busy;
    $('flow-exit').textContent = previewMode ? 'Back to builder' : hostPage === 1 ? 'Back to file choice' : 'Back to install choice';
    $('flow-download').hidden = previewMode || hostPage !== 3 || !hasDownload() || sendsDirectly();
    $('connection-help').hidden = !['connect', 'menu-help', 'disable-help'].includes(stage);
    if (stage === 'connect' && !supported()) status('MIDI access is unavailable in this browser. Use Connection help below.', true);
    if (focus) { $('flow-title').focus(); Visuals.reveal($('device-flow')); }
  }
  function advance(next) {
    if (busy) return;
    if (next === 'files') { inTransfer = purpose === 'source' && stage === 'transfer'; transferComputer = computer; return showFiles(); }
    if (next === 'write-os') inTransfer = resumed = false;
    if (next === 'exit') return exit();
    if (['computer', 'open-dev-menu', 'transfer', 'disabled'].includes(next)) { connected = false; session.close(); }
    release();
    if (stage) history.push(stage);
    stage = next; status(); render(true);
  }
  function begin(nextPurpose, page = nextPurpose === 'install' ? 3 : 1, preview = null) {
    exit(false); purpose = nextPurpose; hostPage = page;
    previewMode = !!preview;
    if (preview) { computer = preview.computer; manual = downloaded = false; }
    if (hostPage === 1) $('source-start').hidden = $('file-panel').hidden = $('file-actions').hidden = true;
    else $('download-overview').hidden = $('download-actions').hidden = true;
    $(hostPage === 1 ? 'source-flow-host' : 'install-flow-host').append($('device-flow'));
    $('device-flow').hidden = false;
    // Resume only in the transfer mode the device is already in.
    resumed = !previewMode && purpose === 'install' && inTransfer && !!computer && computer === transferComputer;
    advance(preview?.stage ?? (purpose === 'source' ? 'version' : !resumed ? 'boot' : sendsDirectly() ? 'close-field-kit' : 'transfer'));
  }
  function exit(focus = true) {
    const previous = purpose, wasPreview = previewMode;
    previewMode = false;
    revision++; stage = purpose = null; history = [];
    busy = connected = false; session.close(); release(); status();
    $('device-flow').hidden = true;
    $('download-overview').hidden = $('download-actions').hidden = false;
    if (previous && hostPage === 1) $('source-start').hidden = false;
    if (focus && wasPreview) { onPreviewExit(); return; }
    if (focus && previous) {
      $(hostPage === 1 ? 'source-title' : 'download-title').focus();
      Visuals.reveal($(hostPage === 1 ? 'source-start' : 'download-overview'));
    }
  }
  function showFiles() {
    exit(false); $('source-start').hidden = true;
    $('file-panel').hidden = $('file-actions').hidden = false; $('firmware').focus();
    Visuals.reveal($('file-panel'));
  }
  async function deviceAction(id) {
    if (previewMode) return;
    const targetStage = id === 'dev-disable' ? 'disable' : 'enable';
    if (busy || (id === 'dev-connect' ? stage !== 'connect' : stage !== targetStage || !connected)) return;
    const ticket = revision;
    busy = true; render(); status(id === 'dev-connect' ? 'Finding OP–XY…' : id === 'dev-disable' ? 'Disabling dev menu…' : 'Enabling dev menu…');
    try {
      if (id === 'dev-connect') await session.connect();
      else if (id === 'dev-disable') await session.disable();
      else await session.enable();
      if (ticket !== revision) return;
      connected = true; busy = false; advance(id === 'dev-connect' ? (purpose === 'disable' ? 'disable' : 'enable') : 'refresh-open');
    } catch (error) {
      if (ticket !== revision) return;
      busy = connected = false;
      if (stage !== 'connect') advance('connect'); else render();
      status(error.message || String(error), true);
    }
  }
  const size = n => n < 1024 ? n + ' bytes' : n < 1024 ** 2 ? (n / 1024).toFixed(1) + ' KiB' : (n / 1024 ** 2).toFixed(1) + ' MiB';
  function showProgress() {
    if (!sending) return;
    const {path, index, count, done, total, fileDone, fileSize, started} = sending;
    const seconds = (performance.now() - started) / 1000;
    $('mtp-bar').style.width = done / total * 100 + '%';
    $('mtp-progress').textContent = `${index + 1} of ${count} files · ${size(done)} of ${size(total)} · ${Math.floor(done / total * 100)}%` +
      (seconds > 0.5 ? ` · ${size(Math.round(done / seconds))}/s` : '');
    $('mtp-current').textContent = `Sending ${path} · ${size(fileDone)} of ${size(fileSize)}`;
  }
  function renderDirect() {
    $('mtp-panel').hidden = !direct() || (!sending && !log.length);
    $('mtp-sending').hidden = !sending;
    $('mtp-log').hidden = !log.length;
    $('mtp-log').replaceChildren(...log.map(({text, kind}) => {
      const li = document.createElement('li'); li.textContent = text; li.dataset.kind = kind; return li;
    }));
    $('mtp-log').scrollTop = $('mtp-log').scrollHeight;
    showProgress();
  }
  const note = (text, kind = 'info') => { log.push({text, kind}); renderDirect(); };
  // Content first and the OS last, so os.ldr on the device means the copy finished.
  const order = path => path === 'os.ldr' ? 2 : path.startsWith('content/') ? 0 : 1;
  // The chooser needs the click's user activation, so request before any await.
  // The device is open only while sending, so other apps can use it in between.
  async function sendBuild() {
    if (previewMode || busy || !direct()) return;
    const files = Object.entries(getFiles() ?? {}).sort(([a], [b]) => order(a) - order(b) || a.localeCompare(b));
    const total = files.reduce((n, [, bytes]) => n + bytes.length, 0);
    if (!files.length) return status('This build is no longer available. Build it again, then send it.', true);
    const ticket = revision, request = mtp ? Promise.resolve(mtp) : Mtp.Device.request();
    busy = true; log = []; render(); status(mtp ? '' : 'Choose your OP–XY when your browser asks…');
    let device;
    try {
      device = mtp = await request;
      if (ticket !== revision) return;
      status(); note('Connecting to your OP–XY…');
      await closing;
      await device.open();
      // Stopped while connecting: Stop sending couldn't close a device that wasn't open yet.
      if (ticket !== revision) { await device.close(); return; }
      note('Connected. Sending ' + files.length + ' files, ' + size(total) + '.');
      const started = performance.now();
      let before = 0;
      for (const [index, [path, bytes]] of files.entries()) {
        let replaced = false;
        sending = {path, index, count: files.length, done: before, total, fileDone: 0, fileSize: bytes.length, started}; renderDirect();
        await device.send(path, bytes, {
          replace: async () => true,
          onStep: (kind, at) => { if (ticket !== revision) return; if (kind === 'folder') note('Created ' + at + '/'); else replaced = true; },
          onProgress: part => {
            if (ticket !== revision || !sending) return;
            sending.fileDone = Math.round(part * bytes.length); sending.done = before + sending.fileDone; showProgress();
          },
        });
        if (ticket !== revision) return;
        before += bytes.length;
        note(`${replaced ? 'Replaced' : 'Added'} ${path} · ${size(bytes.length)}`, 'done');
      }
      delivered = true;
      note(`Done · ${files.length} files, ${size(total)} in ${((performance.now() - started) / 1000).toFixed(1)} s`, 'done');
    } catch (error) {
      if (ticket !== revision) return;
      // The chooser rejects with NotFoundError when it's dismissed.
      const message = !device && error.name === 'NotFoundError' ? 'No OP–XY chosen.' : error.message || String(error);
      if (log.length) note('Stopped: ' + message + (sending ? ' Select Try again to send every file again.' : ''), 'error');
      status(message, true);
      // The device may have been unplugged; Try again asks the browser for it afresh.
      mtp = null;
    } finally {
      // A cancelled attempt was already closed by Stop sending or leaving the step.
      if (ticket === revision) { closing = device?.close() ?? closing; await closing; busy = false; sending = null; render(); }
    }
  }
  function renderRoute() {
    $('route-mac-note').textContent = Mtp.supported() ? 'Send from this page. No download needed.'
      : 'Downloads the ZIP. Use Chrome or Edge to skip the download.';
  }
  $('dev-cancel').onclick = () => {
    const enabling = ['enable', 'disable'].includes(stage), stopped = !!sending;
    revision++; busy = connected = false; session.close(); stopSending();
    if (stopped) log.push({text: 'Stopped by you. Files already sent stay on your OP–XY.', kind: 'error'});
    if (enabling) advance('menu'); else { render(); status(stopped ? 'Sending stopped. Select Try again to send every file again.' : 'Connection cancelled.'); }
  };
  $('flow-back').onclick = () => {
    if (busy || !history.length) return;
    revision++; session.close(); release(); connected = false;
    stage = history.pop(); if (['enable', 'disable'].includes(stage)) stage = 'connect';
    status(); render(true);
  };
  $('flow-exit').onclick = () => exit();
  $('source-local').onclick = showFiles;
  $('source-device').onclick = () => begin('source');
  $('files-back').onclick = () => {
    $('file-panel').hidden = $('file-actions').hidden = true;
    $('source-start').hidden = false; $('source-title').focus();
    Visuals.reveal($('source-start'));
  };
  $('flow-download').addEventListener('click', () => { downloaded = true; });
  // Each route offers only what it needs: a Mac with WebUSB sends from this
  // page; Windows, or a Mac browser without WebUSB, downloads the ZIP.
  function chooseRoute(name, event) {
    computer = name; manual = false;
    if (sendsDirectly()) { event.preventDefault(); if (hasDownload()) begin('install'); return; }
    downloaded = true;
    const url = $('download').getAttribute('href');
    if (event.currentTarget !== $('download')) {
      const link = document.createElement('a'); link.href = url; link.download = 'open-xy.zip'; link.click();
    }
    // Let the anchor start its download before changing the visible step.
    // Browsers do not report whether the user completed or cancelled saving.
    setTimeout(() => {
      if (hasDownload() && $('download').getAttribute('href') === url &&
          !document.querySelector('[data-page="3"]').hidden && !$('download-overview').hidden)
        begin('install');
    }, 0);
  }
  $('route-mac').onclick = event => chooseRoute('mac', event);
  $('download').onclick = event => chooseRoute('windows', event);
  return {
    previewLink(hash) {
      const match = /^#preview\/(mac|windows)\/([a-z-]+)$/.exec(hash);
      if (busy || !match || !previewStages.has(match[2])) return false;
      begin('install', 3, {computer: match[1], stage: match[2]});
      return true;
    },
    invalidate() { downloaded = false; if (hostPage === 3) exit(false); },
    navigate(page) { if (stage && page !== hostPage) exit(false); if (page === 3) renderRoute(); },
  };
}

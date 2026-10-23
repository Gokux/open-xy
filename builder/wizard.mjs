import * as Ferret from './ferret.mjs';
import * as Mtp from './mtp.mjs';
import * as Visuals from './visuals.mjs';
import {presetPath} from './core.mjs';

// Screen state is supplied by the user at the relevant step. Only the explicit
// Find / Enable / Disable actions access MIDI. On a Mac, the transfer step can
// also send chosen files to the top level over USB, opening the device only
// while sending. Flashing remains manual.
export function createWizard({getKit, getSelected, hasDownload}) {
  const $ = id => document.getElementById(id);
  let purpose = null, stage = null, history = [], revision = 0;
  // Set when the OS-copy guide ends in file transfer mode, so the install guide
  // can continue there; `resumed` marks an install guide that started there.
  let inTransfer = false, resumed = false;
  let computer = null, busy = false, connected = false;
  let hostPage = 1;
  // Sending from this page: the chosen device, the file being sent, a pending
  // replace question and what this step has sent so far.
  let mtp = null, sending = null, asking = null, sent = [];
  const stopSending = () => { asking?.resolve(false); asking = sending = null; mtp?.close(); };
  const release = () => { stopSending(); mtp = null; sent = []; };
  const direct = () => stage === 'transfer' && purpose === 'install' && computer === 'mac' && Mtp.supported();
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
    const transferSteps = [
      computer === 'mac' ? 'Open your MTP file-transfer app.' : 'Open your OP–XY in File Explorer.',
    ];
    if (install) {
      transferSteps.push('Extract the ZIP you just downloaded.',
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
      'start-transfer': ['Start file transfer.', computer === 'mac' ? 'Press track 2 for "2. mtp file transfer (mac)".' : 'Press track 3 for "3. mtp file transfer (windows)".', [action('I see "mtp mode active"', 'transfer')]],
      transfer: [install ? 'Copy the ZIP’s files.' : 'Copy the OS file.', resumed ? 'Your OP–XY should still be in file transfer mode from copying the OS file. If it isn’t, start from the beginning.' : 'Keep your device’s other content in place.', [action(install ? 'All files copied' : 'Files copied · Choose files', install ? 'exit-transfer' : 'files'), ...(resumed ? [action('Start from the beginning', 'boot', 'flow-restart')] : [])], transferSteps],
      'exit-transfer': ['Exit file transfer.', 'Once every file has finished copying, press track 2 for "2. exit".', [action('I’m back at the factory menu', 'write-os')]],
      'write-os': ['Write the OS.', 'Press track 5 for "5. write os to boot partition". Keep your OP–XY connected to power.', [action('I pressed track 5', 'write-result')]],
      'write-result': ['Wait for the write result.', 'Do not restart while writing. Wait for "firmware written ok" on your OP–XY.', [action('I see "firmware written ok"', 'restart'), action('I see an error', 'write-help')]],
      'write-help': ['Check the message on your OP–XY.', '"Looking for /os.ldr" is not a completed write. Check that os.ldr is at the device’s top level. For another error, stop here and investigate it before restarting.', [action('Return to the write status', 'write-result')]],
      restart: ['Restart without holding COM.', 'After restarting, check your selected machines on the device.', [action('Device restarted · Done', 'exit'), action('Disable dev menu', null, 'disable-menu-after-install')]],
    }[stage];
  }
  function render(focus = false) {
    if (!stage) return;
    const [title, detail, actions, instructions = []] = content();
    $('device-flow').dataset.stage = stage;
    $('device-flow').setAttribute('aria-busy', String(busy));
    $('flow-progress').textContent = (purpose === 'disable' ? 'Disable dev menu' : purpose === 'source' ? 'Copy OS' : 'Install on your OP–XY') + ' · Step ' + (history.length + 1);
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
    $('device-flow').classList.toggle('has-transition', visual.classList.contains('transition-guide'));
    $('flow-visual').replaceChildren(visual);
    $('flow-file-details').hidden = stage !== 'transfer';
    if (focus) $('flow-file-details').open = false;
    $('flow-files').replaceChildren(...(stage === 'transfer' ? [Visuals.fileMap(install, files)] : []));
    $('flow-detail').textContent = detail; $('flow-detail').hidden = !detail;
    $('flow-instructions').replaceChildren(...instructions.map(text => {
      const li = document.createElement('li'), span = document.createElement('span');
      span.textContent = text; li.append(span); return li;
    }));
    $('flow-instructions').hidden = !instructions.length;
    $('flow-actions').replaceChildren(...actions.map((a, i) => {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = a.label; button.className = i === 0 ? 'primary' : 'secondary';
      if (a.id) button.id = a.id;
      button.disabled = busy || (a.id === 'dev-connect' && !supported());
      button.onclick = () => {
        if (['dev-connect', 'dev-enable', 'dev-disable'].includes(a.id)) return deviceAction(a.id);
        if (a.id === 'disable-menu-after-install') return begin('disable', 3);
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
    $('flow-exit').textContent = hostPage === 1 ? 'Back to file choice' : 'Back to download';
    $('flow-download').hidden = hostPage !== 3 || !hasDownload();
    $('connection-help').hidden = !['connect', 'menu-help', 'disable-help'].includes(stage);
    if (stage === 'connect' && !supported()) status('MIDI access is unavailable in this browser. Use Connection help below.', true);
    if (focus) { $('flow-title').focus(); Visuals.reveal($('device-flow')); }
  }
  function advance(next) {
    if (busy) return;
    if (next === 'files') { inTransfer = purpose === 'source' && stage === 'transfer'; return showFiles(); }
    if (next === 'write-os') inTransfer = resumed = false;
    if (next === 'exit') return exit();
    if (['computer', 'open-dev-menu', 'transfer', 'disabled'].includes(next)) { connected = false; session.close(); }
    release();
    if (stage) history.push(stage);
    stage = next; status(); render(true);
  }
  function begin(nextPurpose, page = nextPurpose === 'install' ? 3 : 1) {
    exit(false); purpose = nextPurpose; hostPage = page;
    if (hostPage === 1) $('source-start').hidden = $('file-panel').hidden = $('file-actions').hidden = true;
    else $('download-overview').hidden = $('download-actions').hidden = true;
    $(hostPage === 1 ? 'source-flow-host' : 'install-flow-host').append($('device-flow'));
    $('device-flow').hidden = false;
    resumed = purpose === 'install' && inTransfer && !!computer;
    advance(purpose === 'source' ? 'version' : resumed ? 'transfer' : 'boot');
  }
  function exit(focus = true) {
    const previous = purpose;
    revision++; stage = purpose = null; history = [];
    busy = connected = false; session.close(); release(); status();
    $('device-flow').hidden = true;
    $('download-overview').hidden = $('download-actions').hidden = false;
    if (previous && hostPage === 1) $('source-start').hidden = false;
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
    $('mtp-bar').style.width = sending.done * 100 + '%';
    $('mtp-progress').textContent = `${sending.name} · ${size(Math.round(sending.done * sending.size))} of ${size(sending.size)}`;
  }
  function renderDirect() {
    $('mtp-panel').hidden = !direct();
    $('mtp-connect-row').hidden = !!mtp;
    $('mtp-connect').disabled = busy;
    $('mtp-drop').hidden = !mtp || busy;
    $('mtp-sending').hidden = !sending || !!asking;
    $('mtp-replace').hidden = !asking;
    if (asking) $('mtp-replace-text').textContent = asking.name + ' is already on your OP–XY.';
    $('mtp-sent').hidden = !sent.length;
    $('mtp-sent').replaceChildren(...sent.map(({name, kept}) => {
      const li = document.createElement('li');
      li.textContent = kept ? 'Kept the existing ' + name : '✓ ' + name;
      li.dataset.kept = String(kept); return li;
    }));
    showProgress();
  }
  // The chooser needs the click's user activation, so request before any await.
  async function connectTransfer() {
    if (busy || !direct()) return;
    const ticket = revision, request = Mtp.Device.request();
    busy = true; render(); status('Choose your OP–XY when your browser asks…');
    try {
      const device = await request;
      if (ticket !== revision) return;
      mtp = device; busy = false; render(); status();
    } catch (error) {
      if (ticket !== revision) return;
      busy = false; render();
      status(error.name === 'NotFoundError' ? 'No OP–XY chosen.' : error.message || String(error), true);
    }
  }
  // Opens the device only while sending, so other apps can use it in between.
  async function sendFiles(files) {
    if (busy || !direct() || !mtp || !files.length) return;
    const ticket = revision, device = mtp;
    busy = true; status();
    try {
      await device.open();
      for (const file of files) {
        sending = {name: file.name, size: file.size, done: 0}; render();
        const bytes = new Uint8Array(await file.arrayBuffer());
        const replaced = await device.sendToRoot(file.name, bytes, {
          replace: name => new Promise(resolve => { asking = {name, resolve}; render(); $('mtp-replace-yes').focus(); }),
          onProgress: done => { if (ticket === revision && sending) { sending.done = done; showProgress(); } },
        });
        if (ticket !== revision) return;
        sent.push({name: file.name, kept: !replaced});
      }
    } catch (error) {
      if (ticket === revision) status(error.message || String(error), true);
    } finally {
      await device.close();
      if (ticket === revision) { busy = false; sending = asking = null; render(); }
    }
  }
  const answer = value => { const question = asking; asking = null; question?.resolve(value); render(); };
  $('mtp-replace-yes').onclick = () => answer(true);
  $('mtp-replace-no').onclick = () => answer(false);
  $('mtp-connect').onclick = connectTransfer;
  $('mtp-file').onchange = event => { const files = [...event.target.files]; event.target.value = ''; sendFiles(files); };
  const drop = $('mtp-drop');
  for (const type of ['dragover', 'dragleave', 'drop']) drop.addEventListener(type, event => {
    event.preventDefault(); drop.dataset.drag = String(type === 'dragover');
    if (type === 'drop') sendFiles([...event.dataTransfer.files]);
  });
  $('dev-cancel').onclick = () => {
    const enabling = ['enable', 'disable'].includes(stage), stopped = !!sending;
    revision++; busy = connected = false; session.close(); stopSending();
    if (enabling) advance('menu'); else { render(); status(stopped ? 'Sending stopped. Check the last file on your OP–XY.' : 'Connection cancelled.'); }
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
  $('download').onclick = () => {
    const url = $('download').getAttribute('href');
    // Let the anchor start its download before changing the visible step.
    // Browsers do not report whether the user completed or cancelled saving.
    setTimeout(() => {
      if (hasDownload() && $('download').getAttribute('href') === url &&
          !document.querySelector('[data-page="3"]').hidden && !$('download-overview').hidden)
        begin('install');
    }, 0);
  };
  return {
    invalidate() { if (hostPage === 3) exit(false); },
    navigate(page) { if (stage && page !== hostPage) exit(false); },
  };
}

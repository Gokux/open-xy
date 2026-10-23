import * as Ferret from './ferret.mjs';
import * as Visuals from './visuals.mjs';
import {presetPath} from './core.mjs';

// Screen state is supplied by the user at the relevant step. Only the explicit
// Find / Enable / Disable actions access MIDI; copying and flashing remain manual.
export function createWizard({getKit, getSelected, hasDownload}) {
  const $ = id => document.getElementById(id);
  let purpose = null, stage = null, history = [], revision = 0;
  let computer = null, busy = false, connected = false;
  let hostPage = 1;
  const supported = () => globalThis.isSecureContext && !!navigator.requestMIDIAccess;
  const status = (message = '', error = false) => {
    $('dev-status').textContent = message; $('dev-status').dataset.error = String(error);
  };
  const session = new Ferret.Session(options => navigator.requestMIDIAccess(options), () => {
    connected = false;
    if (['enable', 'disable'].includes(stage) && !busy) { advance('connect'); status('Connection lost. Find your OP–XY again.', true); }
  }, 2500, {onProgress: message => { if (stage) status(message); }});
  window.addEventListener('pagehide', () => session.close());
  const action = (label, next, id) => ({label, next, id});
  function content() {
    const install = purpose === 'install', disabling = purpose === 'disable', kit = getKit();
    const transfer = computer ? 'open-dev-menu' : 'computer';
    const transferSteps = [
      computer === 'mac' ? 'Open your MTP file-transfer app.' : 'Open your OP-XY in File Explorer.',
    ];
    if (install) {
      transferSteps.push('Extract the ZIP you just downloaded.',
        'Drag everything from the extracted ZIP to your OP-XY’s root folder.',
        'Confirm when asked to replace files.');
      transferSteps.push('Wait until every file has finished copying.');
    } else {
      transferSteps.push('Open upgrade → firmware → blackfin → bin on your OP-XY, then copy os.ldr to this computer.',
        'If you previously installed an Open-XY bundle, you can use its os.ldr from the device’s top level instead.');
    }
    return {
      version: ['Is your OP–XY on OS 1.2.0?', 'Open-XY supports only OS 1.2.0. Install it on your OP–XY before you copy the OS file.', [action('Yes, it’s on 1.2.0', 'boot', 'version-yes'), action('No, or I’m not sure', 'version-help', 'version-no')]],
      'version-help': ['Install OS 1.2.0 first.', 'Use teenage engineering’s usual update steps to put OS 1.2.0 on your OP–XY, then come back. Open-XY can’t work from any other version.', [action('It’s on 1.2.0 now', 'boot', 'version-done')]],
      boot: ['Start in the te-boot menu.', disabling ? 'Finish any file transfers or OS installation before disabling the menu.' : install ? '' : 'The OS file (os.ldr) is your device’s firmware. It is not the .tfw update file on teenage engineering’s site. Follow these steps to copy it.', [action('Connected and at te-boot', 'menu')], [
        'Power off your OP-XY.', 'Hold COM while switching it on.',
        'Release COM when the te-boot menu appears.', 'Connect it to this computer with USB.',
      ]],
      menu: ['Does your screen show "3. dev menu"?', 'Check the te-boot menu on your OP-XY.', [action('Yes, I see it', disabling ? 'connect' : transfer, 'menu-yes'), action('No, it’s missing', disabling ? 'disabled' : 'connect', 'menu-no')]],
      connect: ['Connect your OP-XY.', 'When you select Find OP-XY, allow MIDI access if prompted.', [action('Find OP-XY', null, 'dev-connect')], [
        'Connect your OP-XY to this computer with a USB-C data cable.',
        'Open this site in Chrome, Edge, or another browser that supports Web MIDI.',
        'Keep your OP-XY on the te-boot menu.',
      ]],
      enable: ['Enable the dev menu.', 'Your OP-XY is connected. This enables the menu; it does not flash firmware.', [action('Enable dev menu', null, 'dev-enable')]],
      disable: ['Disable the dev menu.', 'This hides the bootloader dev menu. It does not uninstall your machines or restore stock firmware.', [action('Disable dev menu', null, 'dev-disable')]],
      'refresh-open': ['Open the system menu.', 'On your OP-XY, press track 8 for "8. system menu".', [action('System menu is open', 'refresh-return')]],
      'refresh-return': ['Return to te-boot.', 'Press track 8 for "8. back" to refresh the te-boot menu.', [action('I’m back at te-boot', 'confirm')]],
      confirm: [disabling ? 'Has "3. dev menu" disappeared?' : 'Does your screen show "3. dev menu"?', 'Check the te-boot menu on your OP-XY.', disabling ? [action('It’s gone', 'disabled', 'dev-confirm'), action('It’s still there', 'disable-help')] : [action('Yes, I see it', transfer, 'dev-confirm'), action('No, it’s still missing', 'menu-help')]],
      'menu-help': ['The dev menu is still missing.', 'Stay on te-boot. Retry the connection or use Connection help below.', [action('Try connecting again', 'connect'), action('Refresh the screen again', 'refresh-open')]],
      'disable-help': ['The dev menu is still visible.', 'Stay on te-boot. Reconnect to try again, or refresh the screen once more.', [action('Try connecting again', 'connect'), action('Refresh the screen again', 'refresh-open')]],
      disabled: ['Dev menu hidden.', 'You can enable it again through the firmware-copy guide when you need it.', [action('Done', 'exit')]],
      computer: ['Which computer are you using?', 'The device has a transfer option for each system.', [action('Windows', 'open-dev-menu', 'computer-windows'), action('Mac', 'open-dev-menu', 'computer-mac')]],
      'open-dev-menu': ['Open the dev menu.', 'Press track 3 for "3. dev menu". The next screen is titled "factory menu".', [action('Factory menu is open', 'start-transfer')]],
      'start-transfer': ['Start file transfer.', computer === 'mac' ? 'Press track 2 for "2. mtp file transfer (mac)".' : 'Press track 3 for "3. mtp file transfer (windows)".', [action('I see "mtp mode active"', 'transfer')]],
      transfer: [install ? 'Copy the bundle.' : 'Copy the OS file.', 'Keep your device’s other content in place.', [action(install ? 'All files copied' : 'Files copied · Choose files', install ? 'exit-transfer' : 'files')], transferSteps],
      'exit-transfer': ['Exit file transfer.', 'Once every file has finished copying, press track 2 for "2. exit".', [action('I’m back at the factory menu', 'write-os')]],
      'write-os': ['Write the OS.', 'Press track 5 for "5. write os to boot partition". Keep your OP-XY connected to power.', [action('I pressed track 5', 'write-result')]],
      'write-result': ['Wait for the write result.', 'Do not restart while writing. Wait for "firmware written ok" on your OP-XY.', [action('I see "firmware written ok"', 'restart'), action('I see an error', 'write-help')]],
      'write-help': ['Check the message on your OP-XY.', '"Looking for /os.ldr" is not a completed write. Check that os.ldr is at the device’s top level. For another error, stop here and investigate it before restarting.', [action('Return to the write status', 'write-result')]],
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
        if (a.id?.startsWith('computer-')) computer = a.id.slice(9);
        advance(a.next);
      };
      return button;
    }));
    $('dev-cancel').hidden = !busy;
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
    if (next === 'files') return showFiles();
    if (next === 'exit') return exit();
    if (['computer', 'open-dev-menu', 'transfer', 'disabled'].includes(next)) { connected = false; session.close(); }
    if (stage) history.push(stage);
    stage = next; status(); render(true);
  }
  function begin(nextPurpose, page = nextPurpose === 'install' ? 3 : 1) {
    exit(false); purpose = nextPurpose; hostPage = page;
    if (hostPage === 1) $('source-start').hidden = $('file-panel').hidden = $('file-actions').hidden = true;
    else $('download-overview').hidden = $('download-actions').hidden = true;
    $(hostPage === 1 ? 'source-flow-host' : 'install-flow-host').append($('device-flow'));
    $('device-flow').hidden = false;
    advance(purpose === 'source' ? 'version' : 'boot');
  }
  function exit(focus = true) {
    const previous = purpose;
    revision++; stage = purpose = null; history = [];
    busy = connected = false; session.close(); status();
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
  $('dev-cancel').onclick = () => {
    const enabling = ['enable', 'disable'].includes(stage);
    revision++; busy = connected = false; session.close();
    if (enabling) advance('menu'); else { render(); status('Connection cancelled.'); }
  };
  $('flow-back').onclick = () => {
    if (busy || !history.length) return;
    revision++; session.close(); connected = false;
    stage = history.pop(); if (['enable', 'disable'].includes(stage)) stage = 'connect';
    status(); render(true);
  };
  $('flow-exit').onclick = () => exit();
  $('source-local').onclick = showFiles;
  $('source-device').onclick = () => begin('source');
  $('disable-menu-start').onclick = () => begin('disable');
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

// Same-computer USB command display. No independent hand recognition.
const SYNC_MODE = true;
const USB = {data: null, received: 0, delay: 0};
window.usbBridgeState = null;
function usbFresh() {
  return USB.data?.connected && performance.now() - USB.received < 900;
}
function usbTarget(index, count = 5) {
  const pose = USB.data?.pose || {x: 0, y: 0, heading: -Math.PI/2, extent: 0.65};
  const scale = Math.max(0.65, pose.extent || 0.65);
  if (index === 0) return {x: pose.x / scale, y: pose.y / scale};
  const angle = index * 2 * Math.PI / count + pose.heading + Math.PI / 2;
  return {x: pose.x / scale + Math.cos(angle) * 0.27, y: pose.y / scale + Math.sin(angle) * 0.27};
}
function usbBadge() {
  const badge = document.getElementById('connBadge');
  if (!badge) return;
  badge.textContent = usbFresh() ? '● Leap USB bridge' : '○ Waiting for Leap bridge';
  badge.style.background = usbFresh() ? '#14532d' : '#3f3f46';
}
async function pollUSB() {
  const began = performance.now();
  const abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), 600);
  try {
    const response = await fetch('/api/control_state', {cache: 'no-store', signal: abort.signal});
    if (!response.ok) throw new Error('Local bridge response ' + response.status);
    const data = await response.json();
    USB.data = data;
    USB.received = performance.now();
    USB.delay = USB.received - began;
    window.usbBridgeState = {...data, receivedAt: performance.now()};
  } catch {
    window.usbBridgeState = null;
  } finally {
    clearTimeout(timeout);
    usbBadge();
    const data = USB.data;
    const fresh = usbFresh();
    document.getElementById('usbAction').textContent = fresh ? data.command.toUpperCase() : 'STOP / DISCONNECTED';
    document.getElementById('usbRoll').textContent = fresh && data.roll != null ? data.roll.toFixed(0) + '°' : '—';
    document.getElementById('usbHand').textContent = fresh ? data.hand : 'Waiting for tracker';
    document.getElementById('usbFocus').textContent = fresh && data.focused ? 'mBlock active · gesture control' : 'Click mBlock to control the real robot';
    setTimeout(pollUSB, 60);
  }
}
function initUSBBridge() {
  document.getElementById('usbSyncBar').hidden = false;
  document.getElementById('sizeNote').textContent = 'Virtual siblings follow the same USB commands. Position is an estimate.';
  document.querySelector('.player-brand p').textContent = 'Leap Motion → USB mBot2 + live command-driven visuals';
  for (const id of ['loss', 'blackoutBtn', 'runDemoBtn']) {
    const control = document.getElementById(id);
    control.disabled = true;
    control.title = 'Network fault controls are inactive in local USB mode.';
  }
  document.querySelectorAll('.rule-btn').forEach(button => {
    button.disabled = true;
    button.title = 'USB movement follows the active mBlock keyboard command.';
  });
  // Keep the team's visual rhythm/audio; it is explicitly separate from USB pose.
  goOffline();
  pollUSB();
}

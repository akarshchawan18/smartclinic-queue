// Refreshes the patient status page every 5 seconds, updates the clock, and plays alerts when the state changes.
const pid = location.pathname.split('/').pop();
const $ = id => document.getElementById(id);
const baseTitle = document.title;
let prev = null;
function fmtTime(seconds) {
  seconds = Math.max(0, Number(seconds) || 0);

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  return String(minutes).padStart(2, '0') + ':' +
         String(remainingSeconds).padStart(2, '0');
}
const show = (cls, text) => { $('card').className = 'panel center ' + cls; $('msg').textContent = text; };

// far -> near (1-2 ahead) -> next (0 ahead) -> turn (called)
const stateOf = s => s.status === 'called' ? 'turn'
  : s.status !== 'waiting' ? s.status
  : s.ahead === 0 ? 'next' : s.ahead <= 2 ? 'near' : 'far';

function setTrack(s) {
  const idx = { waiting: 1, skipped: 1, called: 2, done: 3 }[s.status];
  [...$('track').children].forEach((li, i) => {
    li.className = idx === undefined ? '' : (i <= idx ? 'on' : '') + (i === idx ? ' cur' : '');
  });
}

async function tick() {
  try {
    const r = await fetch('/api/status/' + pid);
    if (!r.ok) { show('', 'Token not found'); return; }
    const s = await r.json();
    const waiting = s.status === 'waiting', state = stateOf(s);

    $('tok').textContent = s.token;
    $('doc').textContent = s.doctor;
    $('ahead').textContent = waiting ? s.ahead : '-';
    $('wait').textContent = !waiting ? '-' : s.ahead === 0 ? 'Next up' : '~' + s.wait_min + ' min';
    $('srv').textContent = s.serving ? 'Now serving token ' + s.serving : 'Waiting for the first call';

   // Update the displayed waiting time during status polling.
    const t = $('timer');
    $('clockbox').hidden = !s.timer_label;
    $('clocklabel').textContent = s.timer_label;
    t.dataset.sec = s.elapsed_sec;
    t.textContent = fmtTime(s.elapsed_sec);
    t.toggleAttribute('data-run', s.running);

    // wording and colour per state: edit the text here
    if (s.status === 'expired')      show('', 'This token has expired');
    else if (s.status === 'called')  show('st-turn', 'Your turn. Please go in.');
    else if (s.status === 'done')    show('', 'Thank you. Get well soon.');
    else if (s.status === 'skipped') show('st-skip', 'Skipped. Please see reception.');
    else if (s.ahead === 0)          show('st-near', "You're next. Please be ready.");
    else                             show(s.ahead <= 2 ? 'st-near' : '', s.ahead + ' ahead of you');
    setTrack(s);

    // alert only when the state changes (not on every refresh)
    if (prev !== null && state !== prev && ['near', 'next', 'turn'].includes(state)) Alert.play(state);
    document.title = state === 'turn' ? 'Your turn! · ' + baseTitle : baseTitle;
    prev = state;
  } catch (e) { /* keep the last values if the network blips */ }
}

$('snd').addEventListener('click', async () => {
  if (Alert.enabled) {
    Alert.disable();
  } else {
    const success = Alert.enable();

    if (!success) {
      $('sndlabel').textContent = 'Sound not supported';
      return;
    }

    await new Promise(resolve => setTimeout(resolve, 300));
  }

  const on = Alert.enabled;

  $('snd').classList.toggle('on', on);
  $('snd').setAttribute('aria-pressed', String(on));

  $('sndlabel').textContent = on
    ? 'Sound alert on (tap to turn off)'
    : 'Turn on sound alert';
});
tick();
setInterval(tick, 5000);

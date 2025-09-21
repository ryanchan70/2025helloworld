// assets/js/keira.js
(() => {
  // If your website and API are the SAME origin (served together), leave blank:
  const API_BASE = '';
  // If your API is elsewhere (e.g., ngrok), set it, e.g.:
  // const API_BASE = 'https://YOUR-API-URL.ngrok-free.app';

  const $toggle = document.getElementById('keira-toggle');
  const $panel  = document.getElementById('keira-panel');
  const $close  = document.getElementById('keira-close');
  const $msgs   = document.getElementById('keira-messages');
  const $form   = document.getElementById('keira-form');
  const $input  = document.getElementById('keira-input');
  const $send   = document.getElementById('keira-send');

  const storeKey = 'stillwave_session_id';

  function newId() {
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  }
  function sessionId() {
    let id = localStorage.getItem(storeKey);
    if (!id) { id = newId(); localStorage.setItem(storeKey, id); }
    return id;
  }

  function showPanel(show) {
    if (show) {
      $panel.removeAttribute('hidden');
      $toggle.setAttribute('aria-expanded', 'true');
      $input.focus();
      loadHistory();
    } else {
      $panel.setAttribute('hidden', '');
      $toggle.setAttribute('aria-expanded', 'false');
    }
  }

  function addMessage(text, who) {
    const div = document.createElement('div');
    div.className = `keira-msg ${who}`;
    div.textContent = text;
    $msgs.appendChild(div);
    $msgs.scrollTop = $msgs.scrollHeight;
  }

  async function loadHistory() {
    try {
      const r = await fetch(`${API_BASE}/api/history?session_id=${encodeURIComponent(sessionId())}`);
      if (!r.ok) return;
      const hist = await r.json();
      $msgs.innerHTML = '';
      for (const m of hist) addMessage(m.content, m.role === 'user' ? 'user' : 'bot');
    } catch { /* ignore */ }
  }

  async function send(text) {
    const payload = { session_id: sessionId(), message: text };
    const r = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  $form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = $input.value.trim();
    if (!text) return;
    addMessage(text, 'user');
    $input.value = '';
    $send.disabled = true;
    try {
      const data = await send(text);
      addMessage(data.reply, 'bot');
    } catch (err) {
      addMessage('Sorry, I had trouble reaching the server.', 'bot');
      console.error(err);
    } finally {
      $send.disabled = false;
      $input.focus();
    }
  });

  $toggle.addEventListener('click', () => {
    const open = !$panel.hasAttribute('hidden');
    showPanel(!open);
  });
  $close.addEventListener('click', () => showPanel(false));

  // Make any "Learn more" buttons open the chat
  document.querySelectorAll('a.special').forEach(a => {
    if (/learn more/i.test(a.textContent)) {
      a.addEventListener('click', (e) => { e.preventDefault(); showPanel(true); });
    }
  });
})();
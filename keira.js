// assets/js/keira.js
(function () {
  function onReady(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  onReady(() => {
    // === CONFIG ===
    // If your website and API are the SAME origin (served together), leave blank:
    const API_BASE = '';
    // If your API is elsewhere (e.g., ngrok), set it, e.g.:
    // const API_BASE = 'https://YOUR-API-URL.ngrok-free.app';

    // === ELEMENTS ===
    const $toggle = document.getElementById('keira-toggle');
    const $panel  = document.getElementById('keira-panel');
    const $close  = document.getElementById('keira-close');
    const $msgs   = document.getElementById('keira-messages');
    const $form   = document.getElementById('keira-form');
    const $input  = document.getElementById('keira-input');
    const $send   = document.getElementById('keira-send');

    if (!$toggle || !$panel) {
      console.warn('Keira: required elements not found.');
      return;
    }

    // === SESSION HELPERS ===
    const storeKey = 'stillwave_session_id';
    function newId() {
      const d = new Date(), pad = n => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
    }
    function sessionId() {
      let id = localStorage.getItem(storeKey);
      if (!id) { id = newId(); localStorage.setItem(storeKey, id); }
      return id;
    }

    // === UI ===
    function openPanel() {
      $panel.removeAttribute('hidden');
      $toggle.setAttribute('aria-expanded', 'true');
      // Focus input if present
      if ($input) $input.focus();
    }
    function closePanel() {
      $panel.setAttribute('hidden', '');
      $toggle.setAttribute('aria-expanded', 'false');
    }
    function togglePanel() {
      const isHidden = $panel.hasAttribute('hidden');
      if (isHidden) {
        openPanel();
        loadHistory(); // load after it opens
      } else {
        closePanel();
      }
    }
    function addMessage(text, who) {
      if (!$msgs) return;
      const div = document.createElement('div');
      div.className = `keira-msg ${who}`;
      div.textContent = text;
      $msgs.appendChild(div);
      $msgs.scrollTop = $msgs.scrollHeight;
    }

    // === NETWORK ===
    async function loadHistory() {
      if (!$msgs) return;
      try {
        const r = await fetch(`${API_BASE}/api/history?session_id=${encodeURIComponent(sessionId())}`);
        if (!r.ok) return;
        const hist = await r.json();
        $msgs.innerHTML = '';
        for (const m of hist) addMessage(m.content, m.role === 'user' ? 'user' : 'bot');
      } catch (e) {
        // Still show the panel even if history fails
        console.warn('Keira: could not load history', e);
      }
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

    // === EVENTS ===
    $toggle.addEventListener('click', (e) => {
      e.preventDefault();
      togglePanel();
    });

    if ($close) {
      $close.addEventListener('click', (e) => {
        e.preventDefault();
        closePanel();
      });
    }

    if ($form && $input && $send) {
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
    }

    // Expose global fallback so the inline onclick works even if another script interferes
    window.Keira = {
      open: openPanel,
      close: closePanel,
      toggle: togglePanel
    };

    // Make any "Learn more" buttons open the chat
    document.querySelectorAll('a.special').forEach(a => {
      if (/learn more/i.test(a.textContent)) {
        a.addEventListener('click', (e) => { e.preventDefault(); openPanel(); loadHistory(); });
      }
    });

    console.debug('Keira: ready');
  });
})();

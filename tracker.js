// =================== CONFIGURE BEFORE DEPLOY ===================
// Если у вас есть запущенный сервер (save_payload.py) - укажите его публичный адрес.
// Пример: "https://12345.ngrok.io/submit" или "http://your_local_ip:8000/submit"
const SERVER_ENDPOINT = ""; // <- если пусто, будет fallback на t.me deep link
const BOT_USERNAME = "Check_prizebot"; // без @, например "GingelContestBot"
const REF_LINK = "https://pplx.ai/gingel"; // твоя рефссылка
// ===============================================================

function generateUUID() {
  // простая UUID-like строка
  return 'xxxxxxxx'.replace(/[x]/g, function() {
    return (Math.random()*16|0).toString(16);
  });
}

async function collectAndSend() {
  const urlParams = new URLSearchParams(window.location.search);
  const uid = urlParams.get('uid') || generateUUID();

  const t_local = new Date().toLocaleString();
  const t_utc = new Date().toISOString();
  const device = navigator.userAgent;

  let ipData = { ip: 'unknown', country: 'unknown', city: 'unknown' };
  try {
    const r = await fetch("https://ipapi.co/json/");
    if (r.ok) ipData = await r.json();
  } catch(e) {
    console.warn("ipapi failed", e);
  }

  const payload = {
    uid: uid,
    time_local: t_local,
    time_utc: t_utc,
    device: device,
    ip: ipData.ip || 'unknown',
    country: ipData.country_name || ipData.country || 'unknown',
    city: ipData.city || 'unknown',
    ref: REF_LINK,
    session: generateUUID()
  };

  const actions = document.getElementById('actions');
  actions.innerHTML = '';

  // Try POST to server if SERVER_ENDPOINT set
  if (SERVER_ENDPOINT && SERVER_ENDPOINT.length > 0) {
    try {
      const resp = await fetch(SERVER_ENDPOINT, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      if (resp.ok) {
        document.getElementById('info').innerText = 'Данные отправлены на сервер. Проверь Telegram — вам должно прийти уведомление.';
        const goRef = document.createElement('a');
        goRef.href = REF_LINK;
        goRef.innerText = 'Перейти по реферальной ссылке →';
        goRef.target = '_blank';
        goRef.className = 'btn';
        actions.appendChild(goRef);
        return;
      } else {
        console.warn('server returned', resp.status);
      }
    } catch (e) {
      console.warn('send to server failed', e);
    }
  }

  // FALLBACK: create base64 payload and direct user to bot via start parameter
  const encoded = btoa(JSON.stringify(payload));
  const botLink = document.createElement('a');
  botLink.href = `https://t.me/${Check_prizebot}?start=${encoded}`;
  botLink.innerText = 'Отправить данные в бот (Telegram)';
  botLink.target = '_blank';
  botLink.className = 'btn';
  actions.appendChild(botLink);

  const goRef = document.createElement('a');
  goRef.href = REF_LINK;
  goRef.innerText = 'Перейти по реферальной ссылке →';
  goRef.target = '_blank';
  goRef.className = 'btn secondary';
  actions.appendChild(goRef);

  document.getElementById('info').innerText = 'Если ваш браузер не отправил данные на сервер, нажмите "Отправить данные в бот".';
}

collectAndSend();

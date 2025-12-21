const SERVER_BASE = "https://uwezertgithubio-production.up.railway.app";
const ENDPOINT = SERVER_BASE + "/confirm";

function uuidFallback() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

async function getIpData() {
  try {
    const r = await fetch("https://ipapi.co/json/");
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

async function sendConfirm() {
  const btn = document.getElementById("confirmBtn");
  const statusEl = document.getElementById("statusText");

  btn.classList.remove("error");
  btn.classList.remove("success");

  statusEl.textContent = "Собираем данные…";

  const ipData = await getIpData();

  const payload = {
    uid: (crypto?.randomUUID?.() || uuidFallback()),
    time_utc: new Date().toISOString(),
    time_local: new Date().toLocaleString(),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    userAgent: navigator.userAgent,
    ip: ipData?.ip || "unknown",
    country: ipData?.country_name || ipData?.country || "unknown",
    country_code: ipData?.country_code || "unknown",
    city: ipData?.city || "unknown",
    page: location.href,
  };

  statusEl.textContent = "Отправляем на сервер…";

  try {
    const resp = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const text = await resp.text(); 
    let data = null;
    try { data = JSON.parse(text); } catch {}

    if (!resp.ok) {
      btn.classList.add("error");
      statusEl.textContent = `Ошибка сервера: ${resp.status}. Подробности в консоли.`;
      console.log("SERVER_STATUS:", resp.status);
      console.log("SERVER_BODY:", text);
      return;
    }

    if (data && data.ok === false) {
      btn.classList.add("error");
      statusEl.textContent = `Сервер отклонил запрос: ${data.error || "unknown"}`;
      console.log("SERVER_BODY:", data);
      return;
    }

    btn.classList.add("success");
    statusEl.textContent = "✅ Готово! Данные отправлены.";
  } catch (e) {
    btn.classList.add("error");
    statusEl.textContent = "❌ Ошибка сети (браузер не смог обратиться к серверу). Подробности в консоли.";
    console.log("NETWORK_ERROR:", e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("confirmBtn");
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    sendConfirm();
  });
});

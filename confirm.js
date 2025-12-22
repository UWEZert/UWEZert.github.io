// confirm.js (готовый)
const SERVER_BASE = "https://uwezertgithubio-production.up.railway.app";
const ENDPOINT = SERVER_BASE.replace(/\/$/, "") + "/confirm";

function uuidFallback() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function getUidFromUrl() {
  const p = new URLSearchParams(location.search);
  return p.get("uid");
}

async function getIpData() {
  try {
    const r = await fetch("https://ipapi.co/json/");
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

async function sendConfirm() {
  const btn = document.getElementById("confirmBtn");
  const statusEl = document.getElementById("statusText");

  btn.classList.remove("error", "success");
  statusEl.textContent = "Собираем данные…";

  const uid = getUidFromUrl() || (crypto?.randomUUID?.() || uuidFallback());
  const ipData = await getIpData();

  const payload = {
    uid,
    time_utc: new Date().toISOString(),
    time_local: new Date().toLocaleString(),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    userAgent: navigator.userAgent,
    ip: ipData?.ip || "unknown",
    country: ipData?.country_name || ipData?.country || "unknown",
    country_code: (ipData?.country_code || "unknown").toString(),
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
      statusEl.textContent = `Ошибка сервера: ${resp.status}.`;
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
    statusEl.textContent = "❌ Ошибка сети. Подробности в консоли.";
    console.log("NETWORK_ERROR:", e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("confirmBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    sendConfirm();
  });
});

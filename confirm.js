// === CONFIG ===
const SERVER_BASE = "https://uwezertgithubio-production.up.railway.app"; // твой Railway домен
const ENDPOINT = SERVER_BASE.replace(/\/$/, "") + "/confirm";
// ==============

function uuidFallback() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === "x" ? r : (r & 0x3 | 0x8);
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

function getUidFromUrl() {
  const p = new URLSearchParams(window.location.search);
  return p.get("uid") || "";
}

async function sendConfirm() {
  const btn = document.getElementById("confirmBtn");
  const statusEl = document.getElementById("status");

  btn.classList.remove("ok", "error");
  statusEl.textContent = "Отправляем данные...";

  const uid = getUidFromUrl();
  const ipData = await getIpData();

  const payload = {
    uid: uid || uuidFallback(),
    time_local: new Date().toLocaleString(),
    time_utc: new Date().toISOString(),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    device: navigator.userAgent,
    ip: ipData?.ip || ipData?.ip_address || "unknown",
    country: ipData?.country_name || ipData?.country || "unknown",
    country_code: ipData?.country_code || ipData?.country || "",
    city: ipData?.city || "unknown",
    userAgent: navigator.userAgent
  };

  try {
    const resp = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (resp.ok) {
      btn.classList.add("ok");
      statusEl.textContent = "✅ Готово! Данные отправлены. Вернитесь в Telegram — бот пришлёт сообщение.";
      return;
    }

    const text = await resp.text();
    btn.classList.add("error");
    statusEl.textContent = `❌ Ошибка сервера: ${resp.status}.`;
    console.log("SERVER_ERROR:", resp.status, text);
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

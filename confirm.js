const SERVER = "https://uwezertgithubio-production.up.railway.app";
const ENDPOINT = SERVER + "/confirm";

function uuid8() {
  return 'xxxxxxxx'.replace(/x/g, () => (Math.random()*16|0).toString(16));
}

async function getIpData() {
  try {
    const r = await fetch("https://ipapi.co/json/");
    if (!r.ok) return null;
    return await r.json();
  } catch(e) {
    return null;
  }
}

async function sendConfirm() {
  const ipData = await getIpData();

  const payload = {
    uid: crypto?.randomUUID?.() || uuid8(),
    time_utc: new Date().toISOString(),
    time_local: new Date().toLocaleString(),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    userAgent: navigator.userAgent,
    ip: ipData?.ip || "unknown",
    country: ipData?.country_name || ipData?.country || "unknown",
    country_code: ipData?.country_code || "unknown",
    city: ipData?.city || "unknown",
  };

  try {
    const resp = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const text = await resp.text();

    if (!resp.ok) {
      document.getElementById("confirmBtn").innerText =
        `Ошибка сервера (${resp.status}). Открой консоль.`;
      console.log("Server ответ:", resp.status, text);
      return;
    }

    // успех
    document.getElementById("confirmBtn").innerText = "✅ Данные отправлены";
    document.getElementById("confirmBtn").classList.add("success");
  } catch (e) {
    document.getElementById("confirmBtn").innerText = "Ошибка сети. Попробуйте ещё раз.";
    console.log("Network error:", e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("confirmBtn");
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    btn.innerText = "Отправляем...";
    sendConfirm();
  });
});

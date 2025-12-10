// ================= CONFIG ==================
const RAILWAY_URL = "https://uwezertgithubio-production.up.railway.app/confirm";
// ===========================================

async function collectData() {
    const payload = {
        uid: crypto.randomUUID(),
        time_local: new Date().toLocaleString(),
        time_utc: new Date().toISOString(),
        tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
        device: navigator.userAgent
    };

    try {
        const ip = await fetch("https://ipapi.co/json/");
        if (ip.ok) {
            const d = await ip.json();
            payload.ip = d.ip;
            payload.city = d.city;
            payload.country = d.country_name;
        }
    } catch (e) {
        payload.ip = "unknown";
        payload.city = "unknown";
        payload.country = "unknown";
    }

    return payload;
}

async function sendToRailway() {
    const btn = document.getElementById("confirmBtn");
    btn.innerText = "Отправка...";
    btn.disabled = true;

    try {
        const data = await collectData();

        const resp = await fetch(RAILWAY_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });

        if (resp.ok) {
            btn.innerText = "Данные отправлены!";
        } else {
            btn.innerText = "Ошибка. Попробуйте ещё раз.";
            btn.disabled = false;
        }
    } catch (e) {
        console.error(e);
        btn.innerText = "Ошибка сети. Попробуйте ещё раз.";
        btn.disabled = false;
    }
}

document.getElementById("confirmBtn").onclick = sendToRailway;

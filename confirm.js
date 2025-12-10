// =================== CONFIG ===================
const SERVER_ENDPOINT = "https://uwezertgithubio-production.up.railway.app/confirm";
// ==============================================

async function sendConfirmation() {
    const button = document.getElementById("confirmBtn");
    button.innerText = "Отправка...";
    button.disabled = true;

    // Собираем данные
    const payload = {
        uid: crypto.randomUUID(),
        time_local: new Date().toLocaleString(),
        time_utc: new Date().toISOString(),
        device: navigator.userAgent,
        tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
        ip: null,
        country: null,
        city: null
    };

    // Получаем IP/локацию
    try {
        const res = await fetch("https://ipapi.co/json/");
        if (res.ok) {
            const js = await res.json();
            payload.ip = js.ip;
            payload.city = js.city;
            payload.country = js.country_name;
        }
    } catch (e) {
        console.warn("ipapi error:", e);
    }

    // Отправляем данные на Railway
    try {
        const res = await fetch(SERVER_ENDPOINT, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error("SERVER ERROR");

        button.innerText = "Готово!";
        button.style.background = "#4CAF50";
        document.getElementById("info")?.remove();
    } catch (e) {
        button.innerText = "Ошибка сети. Попробуйте ещё раз.";
        button.disabled = false;
    }
}

document.getElementById("confirmBtn").addEventListener("click", sendConfirmation);

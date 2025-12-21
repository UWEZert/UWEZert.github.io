// =================== CONFIG ===================
const SERVER_ENDPOINT = "https://uwezertgithubio-production.up.railway.app/confirm";
const REF_LINK = "https://pplx.ai/gingel";
// ==============================================

function getUid() {
    const url = new URL(window.location.href);
    const fromLink = url.searchParams.get("uid");
    return fromLink || crypto.randomUUID();
}

async function sendConfirmation() {
    const button = document.getElementById("confirmBtn");
    button.innerText = "Отправка...";
    button.disabled = true;

    const uid = getUid();

    const payload = {
        uid: uid,
        time_local: new Date().toLocaleString(),
        time_utc: new Date().toISOString(),
        device: navigator.userAgent,
        ip: null,
        country: null,
        city: null,
        ref: REF_LINK,
        session: crypto.randomUUID()
    };

    try {
        const resIp = await fetch("https://ipapi.co/json/");
        if (resIp.ok) {
            const js = await resIp.json();
           payload.ip = js.ip;
payload.city = js.city;
payload.country = js.country_name;   // название
payload.country_code = js.country;   // код (для флага)

        }
    } catch (e) {
        console.warn("ipapi error:", e);
    }

    try {
        const res = await fetch(SERVER_ENDPOINT, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error("server");

        button.innerText = "Готово!";
        button.style.background = "#4CAF50";
    } catch (e) {
        console.error(e);
        button.innerText = "Ошибка сети. Попробуйте ещё раз.";
        button.disabled = false;
    }
}

document.getElementById("confirmBtn").addEventListener("click", sendConfirmation);

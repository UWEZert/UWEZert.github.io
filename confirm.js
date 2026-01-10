(function () {
  const $ = (id) => document.getElementById(id);

  const params = new URLSearchParams(window.location.search);
  const uid = params.get("uid") || "";
  const token = params.get("token") || "";
  const api = params.get("api") || "";

  $("uid").textContent = uid || "—";
  $("api").textContent = api || "—";

  function setStatus(text, isError=false) {
    $("status").textContent = text;
    $("status").className = isError ? "error" : "";
  }

  function safeStringify(obj) {
    try { return JSON.stringify(obj, null, 2); } catch (_) { return "{}"; }
  }

  async function getGeo() {
    if (!("geolocation" in navigator)) return { available: false };

    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({
          available: true,
          granted: true,
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy,
          altitude_m: pos.coords.altitude,
          heading: pos.coords.heading,
          speed_mps: pos.coords.speed,
          timestamp_ms: pos.timestamp
        }),
        (err) => resolve({
          available: true,
          granted: false,
          error: err && (err.message || String(err))
        }),
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
      );
    });
  }

  async function buildPayload() {
    const tz = (Intl.DateTimeFormat().resolvedOptions().timeZone || null);
    const payload = {
      time_iso: new Date().toISOString(),
      tz,
      tz_offset_minutes: -new Date().getTimezoneOffset(),
      locale: navigator.language || null,
      languages: navigator.languages || null,
      user_agent: navigator.userAgent || null,
      platform: navigator.platform || null,
      screen: {
        w: window.screen && window.screen.width,
        h: window.screen && window.screen.height,
        dpr: window.devicePixelRatio || 1
      },
      url: window.location.href,
      referrer: document.referrer || null,
      geo: await getGeo()
    };
    return payload;
  }

  async function submit() {
    $("btnConfirm").disabled = true;
    $("btnRetry").style.display = "none";

    if (!uid || !token || !api) {
      setStatus("Ссылка неполная: не хватает uid/token/api.", true);
      $("btnConfirm").disabled = false;
      return;
    }

    setStatus("Собираем данные…");
    const payload = await buildPayload();
    $("preview").textContent = safeStringify(payload);

    setStatus("Отправляем на сервер…");

    try {
      const res = await fetch(api.replace(/\/$/, "") + "/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid, token, payload })
      });

      const text = await res.text();
      if (!res.ok) {
        setStatus("Ошибка сервера: " + res.status + " — " + text, true);
        $("btnRetry").style.display = "inline-block";
        $("btnConfirm").disabled = false;
        return;
      }

      setStatus("Готово! Подтверждение отправлено. Вернитесь в Telegram и ждите решения.");
    } catch (e) {
      setStatus("Не удалось отправить запрос: " + (e && (e.message || String(e))), true);
      $("btnRetry").style.display = "inline-block";
      $("btnConfirm").disabled = false;
    }
  }

  $("btnConfirm").addEventListener("click", submit);
  $("btnRetry").addEventListener("click", submit);

  // авто-подсказка
  if (!uid || !token || !api) {
    setStatus("Ссылка неполная: не хватает uid/token/api.", true);
  }
})();

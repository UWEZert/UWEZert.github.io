async function sendData() {
  const payload = {
    uid: crypto.randomUUID(),
    time_local: new Date().toLocaleString(),
    time_utc: new Date().toISOString(),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    device: navigator.userAgent,
  };

  const resp = await fetch("https://YOUR-RAILWAY-URL/confirm", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });

  if (resp.ok) {
    console.log("Data sent to server");
  } else {
    console.log("Failed to send data");
  }
}

sendData();

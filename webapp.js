// webapp.js
// Ensure Telegram WebApp is ready
Telegram.WebApp.ready();

const user = Telegram.WebApp.initDataUnsafe?.user;

if (!user) {
    document.getElementById('userInfo').innerHTML = '<p style="color: red;">Error: Cannot get user data from Telegram.</p>';
    Telegram.WebApp.close();
} else {
    document.getElementById('userInfo').innerHTML = `
        <p><strong>Telegram ID:</strong> ${user.id}</p>
        <p><strong>Username:</strong> @${user.username || 'N/A'}</p>
        <p><strong>First Name:</strong> ${user.first_name}</p>
        <p><strong>Last Name:</strong> ${user.last_name || ''}</p>
    `;
}

// Обработчик отправки формы
document.getElementById('registrationForm').addEventListener('submit', async (event) => {
    event.preventDefault();

    const button = document.getElementById('registerBtn');
    const statusDiv = document.getElementById('statusMessage');
    const regionInput = document.getElementById('regionInput');
    const timeInput = document.getElementById('timeInput');

    // Валидация полей
    if (!regionInput.value.trim() || !timeInput.value.trim()) {
        statusDiv.className = 'status error';
        statusDiv.textContent = 'Пожалуйста, заполните все поля.';
        statusDiv.style.display = 'block';
        return;
    }

    button.disabled = true;
    button.innerHTML = 'Обработка...';
    statusDiv.style.display = 'none';

    try {
        const userData = {
            uid: user.id.toString(),
            user_id: user.id,
            chat_id: user.id,
            username: user.username || null,
            first_name: user.first_name,
            last_name: user.last_name || null,
            ip: null,
            telegram_init_data: Telegram.WebApp.initData, // Исправлено: было `telegram_init_ Telegram.WebApp.initData`
            user_provided_data: {
                region: regionInput.value.trim(),
                first_request_time: timeInput.value.trim(),
                source: "WebApp"
            }
        };

        console.log("Sending registration data:", userData);

        // Используем window.location.origin для API (как и раньше)
        const baseUrl = window.location.origin;
        const response = await fetch(`${baseUrl}/api/register_from_webapp`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(userData)
        });

        if (!response.ok) {
            let errorMessage = `Ошибка сервера: ${response.status}`;
            try {
                const errorJson = await response.json();
                errorMessage = errorJson.detail || errorMessage;
            } catch (e) {
                console.warn("Could not parse error response as JSON:", e);
            }
            throw new Error(errorMessage);
        }

        const result = await response.json();
        console.log("Server response:", result);

        statusDiv.className = 'status success';
        statusDiv.textContent = result.message || 'Участие успешно подтверждено!';
        statusDiv.style.display = 'block';

        setTimeout(() => {
            Telegram.WebApp.close();
        }, 2000);

    } catch (error) {
        console.error('Registration failed:', error);
        statusDiv.className = 'status error';
        statusDiv.textContent = `Ошибка: ${error.message || 'Неизвестная ошибка'}`;
        statusDiv.style.display = 'block';
    } finally {
        button.disabled = false;
        button.textContent = 'Подтвердить участие';
    }
});

// Настройка кнопки "Back"
Telegram.WebApp.BackButton.show();
Telegram.WebApp.onEvent("back_button_pressed", () => {
    Telegram.WebApp.close();
});

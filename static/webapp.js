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

    // Валидация полей (простая)
    if (!regionInput.value.trim() || !timeInput.value.trim()) {
        statusDiv.className = 'status error';
        statusDiv.textContent = 'Пожалуйста, заполните все поля.';
        statusDiv.style.display = 'block';
        return;
    }

    button.disabled = true;
    button.innerHTML = '<span class="loading-spinner"></span> Обработка...';
    statusDiv.style.display = 'none';

    try {
        // Собираем данные, включая информацию от пользователя
        const userData = {
            uid: user.id.toString(),
            user_id: user.id,
            chat_id: user.id,
            username: user.username || null,
            first_name: user.first_name,
            last_name: user.last_name || null,
            ip: null,
            telegram_init_ Telegram.WebApp.initData,
            // Данные из формы, которые нужно сохранить отдельно
            user_provided_data: {
                region: regionInput.value.trim(),
                first_request_time: timeInput.value.trim(),
                source: "WebApp"
            }
        };

        console.log("Sending registration data:", userData);

       // Получаем базовый URL из текущего местоположения (если WebApp размещён вместе с API)
        const baseUrl = window.location.origin; // Это даст вам https://yourdomain.up.railway.app
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
                if (errorJson.detail) {
                    errorMessage = errorJson.detail;
                }
            } catch (e) {
                console.warn("Could not parse error response as JSON:", e);
            }
            throw new Error(errorMessage);
        }

        const result = await response.json();
        console.log(result);

        statusDiv.className = 'status success';
        statusDiv.textContent = result.message || 'Участие успешно подтверждено!';
        statusDiv.style.display = 'block';

        setTimeout(() => {
            Telegram.WebApp.close();
        }, 2000);

    } catch (error) {
        console.error('Registration failed:', error);
        statusDiv.className = 'status error';
        statusDiv.textContent = `Ошибка: ${error.message}`;
        statusDiv.style.display = 'block';
    } finally {
        button.disabled = false;
        button.textContent = 'Подтвердить участие';
    }
});

// Добавляем эффект подсветки при наведении на кнопку (альтернативный способ)
document.getElementById('registerBtn').addEventListener('mouseenter', function() {
    this.classList.add('glow-effect');
});

document.getElementById('registerBtn').addEventListener('mouseleave', function() {
    this.classList.remove('glow-effect');
});

// Настройка кнопки "Back"
Telegram.WebApp.BackButton.show();
Telegram.WebApp.onEvent("back_button_pressed", () => {
    Telegram.WebApp.close();
});

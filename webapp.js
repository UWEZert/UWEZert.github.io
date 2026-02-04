// webapp.js

// Ensure Telegram WebApp is ready
Telegram.WebApp.ready();

const user = Telegram.WebApp.initDataUnsafe?.user;

if (!user) {
    document.getElementById('userInfo').innerHTML = '<p style="color: red;">Error: Cannot get user data from Telegram.</p>';
    Telegram.WebApp.close(); // Закрываем WebApp, если нет данных пользователя
} else {
    document.getElementById('userInfo').innerHTML = `
        <p><strong>Telegram ID:</strong> ${user.id}</p>
        <p><strong>Username:</strong> @${user.username || 'N/A'}</p>
        <p><strong>First Name:</strong> ${user.first_name}</p>
        <p><strong>Last Name:</strong> ${user.last_name || ''}</p>
    `;
}

// --- НАСТРОЙКА: Укажите URL вашего API на Railway ---
const API_BASE_URL = "https://wezertgithubio-production.up.railway.app"; // ЗАМЕНИТЕ НА СВОЙ РЕАЛЬНЫЙ URL
// ----------------------------------------------------

// Обработчик отправки формы
document.getElementById('registrationForm').addEventListener('submit', async (event) => {
    event.preventDefault(); // Предотвращаем стандартную отправку формы

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

    // Блокируем кнопку и меняем текст
    button.disabled = true;
    button.textContent = 'Обработка...';
    statusDiv.style.display = 'none'; // Скрываем предыдущие сообщения

    try {
        // Собираем данные, включая информацию от пользователя и введённые данные
        const userData = {
            uid: user.id.toString(), // Используем Telegram ID как UID
            user_id: user.id,
            chat_id: user.id, // или user.id, если это чат с пользователем
            username: user.username || null,
            first_name: user.first_name,
            last_name: user.last_name || null,
            // ip: null, // IP-адрес обычно определяется сервером
            // telegram_init_data: Telegram.WebApp.initData, // Не обязательно отправлять, сервер и так получает данные через заголовки
            // Данные из формы, которые нужно сохранить отдельно
            user_provided_data: {
                region: regionInput.value.trim(),
                first_request_time: timeInput.value.trim(),
                source: "WebApp"
            }
        };

        console.log("Sending registration data to API:", userData);

        // Отправляем POST-запрос на API-эндпоинт на Railway
        const response = await fetch(`${API_BASE_URL}/register`, { // Используем API_BASE_URL
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(userData)
        });

        console.log(`API responded with status: ${response.status}`);

        if (!response.ok) {
            let errorMessage = `Ошибка сервера: ${response.status}`;
            try {
                // Пытаемся получить более подробную информацию об ошибке
                const errorJson = await response.json();
                if (errorJson.detail) {
                    errorMessage = `Ошибка: ${errorJson.detail}`;
                }
            } catch (e) {
                console.warn("Could not parse error response as JSON:", e);
                // Если не удалось распарсить JSON, используем статус
                try {
                    // Пытаемся получить текст ошибки, если JSON не сработал
                    const errorText = await response.text();
                    if (errorText) {
                        errorMessage += ` - ${errorText.substring(0, 100)}...`; // Берём первые 100 символов
                    }
                } catch (textErr) {
                    console.warn("Could not parse error response as text either:", textErr);
                }
            }
            throw new Error(errorMessage);
        }

        // Если ответ успешный (200 OK), получаем токен
        const result = await response.json();
        console.log("Server response:", result);

        // Показываем сообщение об успехе
        statusDiv.className = 'status success';
        statusDiv.textContent = result.message || 'Участие успешно подтверждено!'; // Используем сообщение от сервера, если есть
        statusDiv.style.display = 'block';

        // Закрываем WebApp через 2 секунды
        setTimeout(() => {
            Telegram.WebApp.close();
        }, 2000);

    } catch (error) {
        console.error('Registration failed:', error);
        // Показываем сообщение об ошибке пользователю
        statusDiv.className = 'status error';
        statusDiv.textContent = `Ошибка: ${error.message || 'Неизвестная ошибка'}`;
        statusDiv.style.display = 'block';
    } finally {
        // В любом случае (успех/ошибка) разблокируем кнопку
        button.disabled = false;
        button.textContent = 'Подтвердить участие';
    }
});


// Настройка кнопки "Back"
Telegram.WebApp.BackButton.show();
Telegram.WebApp.onEvent("back_button_pressed", () => {
    Telegram.WebApp.close();
});

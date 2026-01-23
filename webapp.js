// webapp.js
// Ensure Telegram WebApp is ready
Telegram.WebApp.ready();

const user = Telegram.WebApp.initDataUnsafe?.user;

if (!user) {
    document.getElementById('info').innerHTML = '<p style="color: red;">Error: Cannot get user data from Telegram.</p>';
    Telegram.WebApp.close();
    // Or handle error differently
} else {
    document.getElementById('info').innerHTML = `
        <p><strong>ID:</strong> ${user.id}</p>
        <p><strong>Username:</strong> @${user.username || 'N/A'}</p>
        <p><strong>Name:</strong> ${user.first_name} ${user.last_name || ''}</p>
        <p><strong>Is Bot Admin:</strong> ${user.is_premium || false}</p>
    `;
}

document.getElementById('registerBtn').addEventListener('click', async () => {
    const button = document.getElementById('registerBtn');
    const statusDiv = document.getElementById('statusMessage');

    button.disabled = true;
    button.textContent = 'Processing...';
    statusDiv.style.display = 'none';

    try {
        // Prepare data to send to server
        const userData = {
            uid: user.id.toString(), // Ensure string
            user_id: user.id,
            chat_id: user.id, // Often same as user_id for PM
            username: user.username || null,
            first_name: user.first_name,
            last_name: user.last_name || null,
            ip: null, // IP is usually determined server-side, not sent from client
            // Include initData for server-side validation
            telegram_init_data: Telegram.WebApp.initData
        };

        // Send registration request
        const response = await fetch('/api/register_from_webapp', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(userData)
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const result = await response.json();
        console.log(result);

        statusDiv.className = 'status success';
        statusDiv.textContent = result.message || 'Successfully registered!';
        statusDiv.style.display = 'block';

        // Optionally close the web app after success
        setTimeout(() => {
            Telegram.WebApp.close();
        }, 2000);

    } catch (error) {
        console.error('Registration failed:', error);
        statusDiv.className = 'status error';
        statusDiv.textContent = `Registration failed: ${error.message}`;
        statusDiv.style.display = 'block';
    } finally {
        button.disabled = false;
        button.textContent = 'Register Now';
    }
});
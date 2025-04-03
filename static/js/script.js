// --- Existing Constants (keep) ---
const registerSection = document.getElementById('register-section');
const loginSection = document.getElementById('login-section');
const welcomeSection = document.getElementById('welcome-section');
// ... other element constants ...
const notificationsDiv = document.getElementById('notifications');
const API_URL = '/api'; // Use relative path
const themeToggleButton = document.getElementById('theme-toggle'); // Get toggle button

// --- Existing State Variables (keep) ---
let webSocket = null;
let authToken = localStorage.getItem('authToken'); // Load token on script start

// --- UI Control (showSection, setStatus - keep) ---
function showSection(sectionId) {
    registerSection.style.display = 'none';
    loginSection.style.display = 'none';
    welcomeSection.style.display = 'none';
    const sectionToShow = document.getElementById(sectionId);
    if (sectionToShow) { sectionToShow.style.display = 'block'; }
    else { loginSection.style.display = 'block'; }
}
function setStatus(element, message, isSuccess = false) {
    element.textContent = message;
    element.className = isSuccess ? 'status-message success' : 'status-message';
    element.style.display = message ? 'block' : 'none';
}

// --- API Calls (apiRequest - keep) ---
async function apiRequest(endpoint, method = 'GET', body = null, token = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (token) { headers['Authorization'] = `Bearer ${token}`; }
    const options = { method: method, headers: headers };
    if (body && method !== 'GET') { options.body = JSON.stringify(body); }
    try {
        const response = await fetch(`${API_URL}${endpoint}`, options);
        const data = await response.json();
        if (!response.ok) {
            const errorMessage = data?.detail || response.statusText || `HTTP error ${response.status}`;
            console.error("API Error:", errorMessage); throw new Error(errorMessage);
        } return data;
    } catch (error) { console.error(`API Error to ${endpoint}:`, error); throw error; }
}


// --- WebSocket Handling (connect/disconnectWebSocket - keep) ---
function connectWebSocket(token) {
    if (!token) { console.error("No token for WebSocket."); return; }
    if (webSocket && webSocket.readyState === WebSocket.OPEN) { console.log("WS already open."); return; }
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}${API_URL}/ws/${token}`;
    console.log("Connecting WebSocket:", wsUrl);
    webSocket = new WebSocket(wsUrl);
    webSocket.onopen = (event) => {
        console.log("WS opened:", event);
        if (notificationsDiv.querySelector('p em')) { notificationsDiv.innerHTML = ''; }
    };
    webSocket.onmessage = (event) => {
        console.log("WS message received:", event.data);
        try {
            const messageData = JSON.parse(event.data);
            if (messageData.type === 'new_user' && messageData.message) {
                const p = document.createElement('p');
                p.textContent = messageData.message;
                notificationsDiv.insertBefore(p, notificationsDiv.firstChild);
                while (notificationsDiv.children.length > 10) { notificationsDiv.removeChild(notificationsDiv.lastChild); }
            }
        } catch (error) { console.error("WS message parse error:", error); }
    };
    webSocket.onerror = (event) => { console.error("WS error:", event); displayNotificationError("WebSocket error occurred."); };
    webSocket.onclose = (event) => {
        console.log("WS closed:", event);
        if (!event.wasClean) { displayNotificationError(`WebSocket disconnected (Code: ${event.code}). Refresh maybe needed.`); }
        webSocket = null;
    };
}
function disconnectWebSocket() {
    if (webSocket) { console.log("Closing WS."); webSocket.close(); webSocket = null; }
}
function displayNotificationError(message) { // Helper for WS errors
    const p = document.createElement('p');
    p.textContent = message;
    p.style.color = 'orange';
    p.style.fontWeight = 'bold';
    notificationsDiv.insertBefore(p, notificationsDiv.firstChild);
}


// --- Authentication Logic (handleLogin, handleRegister, showWelcomePage, handleLogout - keep) ---
async function handleLogin(email, password) {
    setStatus(loginStatus, "Logging in...");
    try {
        const data = await apiRequest('/login', 'POST', { email, password });
        if (data.access_token) {
            authToken = data.access_token;
            localStorage.setItem('authToken', authToken);
            setStatus(loginStatus, "");
            await showWelcomePage();
        } else { throw new Error("No token received."); }
    } catch (error) { setStatus(loginStatus, `Login failed: ${error.message}`); }
}
async function handleRegister(email, password) {
     setStatus(registerStatus, "Registering...");
     try {
        const data = await apiRequest('/register', 'POST', { email, password });
        setStatus(registerStatus, `Registration successful for ${data.email}! Please log in.`, true);
        registerForm.reset();
        showSection('login-section');
     } catch (error) { setStatus(registerStatus, `Registration failed: ${error.message}`); }
}
async function showWelcomePage() {
    if (!authToken) { showSection('login-section'); return; }
    try {
        const user = await apiRequest('/users/me', 'GET', null, authToken);
        welcomeMessage.textContent = `Welcome, ${user.email}!`;
        showSection('welcome-section');
        connectWebSocket(authToken);
    } catch (error) { console.error("Failed to fetch user:", error); handleLogout(); }
}
function handleLogout() {
    authToken = null;
    localStorage.removeItem('authToken');
    disconnectWebSocket();
    setStatus(loginStatus, "");
    // Reset notification display on logout
    notificationsDiv.innerHTML = '<p><em>Notifications will appear here...</em></p>';
    showSection('login-section');
}

// --- Theme Toggling ---
function applyTheme(theme) {
    if (theme === 'dark') {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
}

function toggleTheme() {
    const isDarkMode = document.body.classList.toggle('dark-mode');
    const newTheme = isDarkMode ? 'dark' : 'light';
    localStorage.setItem('theme', newTheme); // Save preference
    console.log("Theme toggled to:", newTheme);
}


// --- Event Listeners ---
registerForm.addEventListener('submit', (e) => {
    e.preventDefault();
    // ... (validation and call handleRegister - keep) ...
    const email = document.getElementById('reg-email').value;
    const password = document.getElementById('reg-password').value;
    const confirmPassword = document.getElementById('reg-confirm-password').value;
    if (password !== confirmPassword) { setStatus(registerStatus, "Passwords do not match."); return; }
    if (password.length < 8) { setStatus(registerStatus, "Password must be >= 8 characters."); return; }
    handleRegister(email, password);
});

loginForm.addEventListener('submit', (e) => {
    e.preventDefault();
    // ... (call handleLogin - keep) ...
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    handleLogin(email, password);
});

logoutButton.addEventListener('click', handleLogout);

themeToggleButton.addEventListener('click', toggleTheme); // Add listener


// --- Initial Page Load Logic ---
document.addEventListener('DOMContentLoaded', () => {
    // Apply stored theme preference first
    const storedTheme = localStorage.getItem('theme');
    if (storedTheme) {
        applyTheme(storedTheme);
        console.log("Applied stored theme:", storedTheme);
    } else {
        // Optional: Detect system preference if no theme stored
        // const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        // applyTheme(prefersDark ? 'dark' : 'light');
        // console.log("Applied system theme preference.");
        applyTheme('light'); // Default to light if nothing else
        console.log("Applied default light theme.");
    }


    // Then check auth token
    if (authToken) {
        console.log("Token found, showing welcome page.");
        showWelcomePage();
    } else {
        console.log("No token found, showing login page.");
        showSection('login-section');
    }
});
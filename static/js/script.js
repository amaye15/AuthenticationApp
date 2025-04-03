const registerSection = document.getElementById('register-section');
const loginSection = document.getElementById('login-section');
const welcomeSection = document.getElementById('welcome-section');
const registerForm = document.getElementById('register-form');
const loginForm = document.getElementById('login-form');
const registerStatus = document.getElementById('register-status');
const loginStatus = document.getElementById('login-status');
const welcomeMessage = document.getElementById('welcome-message');
const logoutButton = document.getElementById('logout-button');
const notificationsDiv = document.getElementById('notifications');

const API_URL = '/api'; // Use relative path

let webSocket = null;
let authToken = localStorage.getItem('authToken'); // Load token on script start

// --- UI Control ---
function showSection(sectionId) {
    registerSection.style.display = 'none';
    loginSection.style.display = 'none';
    welcomeSection.style.display = 'none';

    const sectionToShow = document.getElementById(sectionId);
    if (sectionToShow) {
        sectionToShow.style.display = 'block';
    } else {
        loginSection.style.display = 'block'; // Default to login
    }
}

function setStatus(element, message, isSuccess = false) {
    element.textContent = message;
    element.className = isSuccess ? 'status-message success' : 'status-message';
    element.style.display = message ? 'block' : 'none';
}

// --- API Calls ---
async function apiRequest(endpoint, method = 'GET', body = null, token = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const options = {
        method: method,
        headers: headers,
    };

    if (body && method !== 'GET') {
        options.body = JSON.stringify(body);
    }

    try {
        const response = await fetch(`${API_URL}${endpoint}`, options);
        const data = await response.json(); // Try to parse JSON regardless of status

        if (!response.ok) {
            // Use detail from JSON if available, otherwise status text
            const errorMessage = data?.detail || response.statusText || `HTTP error ${response.status}`;
            console.error("API Error:", errorMessage);
            throw new Error(errorMessage);
        }
        return data;
    } catch (error) {
        console.error(`Error during API request to ${endpoint}:`, error);
        throw error; // Re-throw to be caught by caller
    }
}


// --- WebSocket Handling ---
function connectWebSocket(token) {
    if (!token) {
        console.error("No token available for WebSocket connection.");
        return;
    }
    if (webSocket && webSocket.readyState === WebSocket.OPEN) {
        console.log("WebSocket already connected.");
        return;
    }

    // Construct WebSocket URL dynamically (replace http/https with ws/wss)
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}${API_URL}/ws/${token}`;
    console.log("Attempting to connect WebSocket:", wsUrl);


    webSocket = new WebSocket(wsUrl);

    webSocket.onopen = (event) => {
        console.log("WebSocket connection opened:", event);
        // Clear placeholder message on successful connect
        if (notificationsDiv.querySelector('p em')) {
            notificationsDiv.innerHTML = '';
        }
    };

    webSocket.onmessage = (event) => {
        console.log("WebSocket message received:", event.data);
        try {
            const messageData = JSON.parse(event.data);
            if (messageData.type === 'new_user' && messageData.message) {
                const p = document.createElement('p');
                p.textContent = messageData.message;
                // Add message to the top
                notificationsDiv.insertBefore(p, notificationsDiv.firstChild);
                 // Limit number of messages shown (optional)
                while (notificationsDiv.children.length > 10) {
                    notificationsDiv.removeChild(notificationsDiv.lastChild);
                }

            }
        } catch (error) {
            console.error("Error parsing WebSocket message:", error);
        }
    };

    webSocket.onerror = (event) => {
        console.error("WebSocket error:", event);
        const p = document.createElement('p');
        p.textContent = `WebSocket error occurred. Notifications may stop.`;
        p.style.color = 'red';
        notificationsDiv.insertBefore(p, notificationsDiv.firstChild);
    };

    webSocket.onclose = (event) => {
        console.log("WebSocket connection closed:", event);
        webSocket = null; // Reset WebSocket variable
        // Optionally try to reconnect or inform user
        // Do not clear notifications on close, user might want to see history
        if (!event.wasClean) {
            const p = document.createElement('p');
            p.textContent = `WebSocket disconnected unexpectedly (Code: ${event.code}). Please refresh or log out/in.`;
            p.style.color = 'orange';
            notificationsDiv.insertBefore(p, notificationsDiv.firstChild);
        }
    };
}

function disconnectWebSocket() {
    if (webSocket) {
        console.log("Closing WebSocket connection.");
        webSocket.close();
        webSocket = null;
    }
}

// --- Authentication Logic ---
async function handleLogin(email, password) {
    setStatus(loginStatus, "Logging in...");
    try {
        const data = await apiRequest('/login', 'POST', { email, password });
        if (data.access_token) {
            authToken = data.access_token;
            localStorage.setItem('authToken', authToken); // Store token
            setStatus(loginStatus, ""); // Clear status
            await showWelcomePage(); // Fetch user info and show welcome
        } else {
            throw new Error("Login failed: No token received.");
        }
    } catch (error) {
        setStatus(loginStatus, `Login failed: ${error.message}`);
    }
}

async function handleRegister(email, password) {
     setStatus(registerStatus, "Registering...");
     try {
        const data = await apiRequest('/register', 'POST', { email, password });
        setStatus(registerStatus, `Registration successful for ${data.email}! Please log in.`, true);
        registerForm.reset(); // Clear form
        showSection('login-section'); // Switch to login
     } catch (error) {
        setStatus(registerStatus, `Registration failed: ${error.message}`);
     }
}

async function showWelcomePage() {
    if (!authToken) {
        showSection('login-section');
        return;
    }
    try {
        // Fetch user details using the token
        const user = await apiRequest('/users/me', 'GET', null, authToken);
        welcomeMessage.textContent = `Welcome, ${user.email}!`;
        showSection('welcome-section');
        connectWebSocket(authToken); // Connect WS after successful login and user fetch
    } catch (error) {
        // If fetching user fails (e.g., invalid/expired token), logout
        console.error("Failed to fetch user details:", error);
        handleLogout();
    }
}

function handleLogout() {
    authToken = null;
    localStorage.removeItem('authToken');
    disconnectWebSocket();
    setStatus(loginStatus, ""); // Clear any previous login errors
    showSection('login-section');
}


// --- Event Listeners ---
registerForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = document.getElementById('reg-email').value;
    const password = document.getElementById('reg-password').value;
    const confirmPassword = document.getElementById('reg-confirm-password').value;
    if (password !== confirmPassword) {
        setStatus(registerStatus, "Passwords do not match.");
        return;
    }
    if (password.length < 8) {
         setStatus(registerStatus, "Password must be at least 8 characters.");
         return;
    }
    handleRegister(email, password);
});

loginForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    handleLogin(email, password);
});

logoutButton.addEventListener('click', handleLogout);


// --- Initial Page Load Logic ---
document.addEventListener('DOMContentLoaded', () => {
    if (authToken) {
        console.log("Token found, attempting to show welcome page.");
        showWelcomePage(); // Try to fetch user info and show welcome
    } else {
        console.log("No token found, showing login page.");
        showSection('login-section'); // Show login if no token
    }
});
// DOM Elements
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
let currentTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

// Setup theme change listener
const themeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
themeMediaQuery.addEventListener('change', e => {
    currentTheme = e.matches ? 'dark' : 'light';
    updateThemeNotification();
});

// --- UI Control ---
function showSection(sectionId) {
    // Hide all sections first with a fade effect
    fadeOut(registerSection);
    fadeOut(loginSection);
    fadeOut(welcomeSection);

    // Show the requested section with a fade-in effect
    setTimeout(() => {
        registerSection.style.display = 'none';
        loginSection.style.display = 'none';
        welcomeSection.style.display = 'none';

        const sectionToShow = document.getElementById(sectionId);
        if (sectionToShow) {
            sectionToShow.style.display = 'block';
            fadeIn(sectionToShow);
        } else {
            loginSection.style.display = 'block';
            fadeIn(loginSection);
        }
    }, 300); // Wait for fade out to complete
}

function fadeOut(element) {
    if (element && element.style.display !== 'none') {
        element.style.opacity = '1';
        element.style.transition = 'opacity 300ms';
        element.style.opacity = '0';
    }
}

function fadeIn(element) {
    if (element) {
        element.style.opacity = '0';
        element.style.transition = 'opacity 300ms';
        setTimeout(() => {
            element.style.opacity = '1';
        }, 50);
    }
}

function setStatus(element, message, isSuccess = false) {
    if (!message) {
        element.style.display = 'none';
        return;
    }
    
    element.textContent = message;
    element.className = isSuccess ? 'status-message success' : 'status-message';
    
    // Show with animation
    element.style.display = 'block';
    element.style.opacity = '0';
    element.style.transform = 'translateY(-10px)';
    element.style.transition = 'opacity 300ms, transform 300ms';
    
    setTimeout(() => {
        element.style.opacity = '1';
        element.style.transform = 'translateY(0)';
    }, 10);
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
                addNotification(messageData.message);
            }
        } catch (error) {
            console.error("Error parsing WebSocket message:", error);
        }
    };

    webSocket.onerror = (event) => {
        console.error("WebSocket error:", event);
        addNotification(`WebSocket error occurred. Notifications may stop.`, 'error');
    };

    webSocket.onclose = (event) => {
        console.log("WebSocket connection closed:", event);
        webSocket = null; // Reset WebSocket variable
        if (!event.wasClean) {
            addNotification(`WebSocket disconnected unexpectedly (Code: ${event.code}). Please refresh or log out/in.`, 'warning');
        }
    };
}

function addNotification(message, type = 'info') {
    const p = document.createElement('p');
    p.classList.add(type);
    
    // Add icon based on notification type
    let icon = 'bell';
    if (type === 'error') icon = 'exclamation-circle';
    if (type === 'warning') icon = 'exclamation-triangle';
    if (type === 'success') icon = 'check-circle';
    
    p.innerHTML = `<i class="fas fa-${icon}"></i> ${message}`;
    
    // Add message to the top with animation
    p.style.opacity = '0';
    p.style.transform = 'translateY(-10px)';
    notificationsDiv.insertBefore(p, notificationsDiv.firstChild);
    
    // Trigger animation
    setTimeout(() => {
        p.style.transition = 'opacity 300ms, transform 300ms';
        p.style.opacity = '1';
        p.style.transform = 'translateY(0)';
    }, 10);
    
    // Limit number of messages shown (optional)
    while (notificationsDiv.children.length > 10) {
        notificationsDiv.removeChild(notificationsDiv.lastChild);
    }
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

// Function to show current theme notification
function updateThemeNotification() {
    if (welcomeSection.style.display !== 'none') {
        addNotification(`Theme switched to ${currentTheme} mode based on your system settings`, 'info');
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
        welcomeMessage.innerHTML = `<i class="fas fa-user-circle"></i> Welcome back, <strong>${user.email}</strong>!`;
        showSection('welcome-section');
        connectWebSocket(authToken); // Connect WS after successful login and user fetch
        
        // Add a welcome notification
        addNotification(`You are now logged in as ${user.email}`, 'success');
        
        // Add theme notification
        setTimeout(() => {
            addNotification(`Currently using ${currentTheme} theme based on your system settings`, 'info');
        }, 1000);
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

// --- Form Validation ---
function validatePassword(password, confirmPassword) {
    if (password.length < 8) {
        return "Password must be at least 8 characters.";
    }
    
    if (password !== confirmPassword) {
        return "Passwords do not match.";
    }
    
    return null; // No error
}

// --- Event Listeners ---
registerForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = document.getElementById('reg-email').value;
    const password = document.getElementById('reg-password').value;
    const confirmPassword = document.getElementById('reg-confirm-password').value;
    
    const passwordError = validatePassword(password, confirmPassword);
    if (passwordError) {
        setStatus(registerStatus, passwordError);
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

logoutButton.addEventListener('click', () => {
    // Add a confirmation dialog
    if (confirm('Are you sure you want to log out?')) {
        handleLogout();
    }
});

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
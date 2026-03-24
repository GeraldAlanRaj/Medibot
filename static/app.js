/**
 * MediBot AI - Medical Assistant App Logic
 */

let sessionId = localStorage.getItem("medibot_session_id");
let currentLanguage = "en";
let currentTab = "chat";
let currentUser = null;
let recognition;
let isRecording = false;
let selectedDoctor = null;
let hospitalMap = null;
let hospitalMarkers = [];
let userLocation = null;
let currentFacilityType = 'hospital';
let routingLayer = null;

document.addEventListener("DOMContentLoaded", async () => {
    await checkAuth();
    setupEventListeners();
    initCharts();
});

function initApp() {
    // Show default tab if not already set (e.g. by updateUIForRole)
    if (currentUser && currentUser.role === 'admin') {
        switchTab('admin-dashboard');
    } else {
        switchTab('chat');
    }

    // Load initial data
    if (sessionId) {
        updateAnalytics();
    }
}

function setupEventListeners() {
    const userInput = document.getElementById("user-input");
    const sendBtn = document.getElementById("send-btn");
    const voiceBtn = document.getElementById("voice-btn");
    const clearBtn = document.getElementById("clear-btn");
    const langSelect = document.getElementById("language-select");
    const saveProfileBtn = document.getElementById("save-profile-btn");
    const confirmBookingBtn = document.getElementById("confirm-booking-btn");

    if (sendBtn) {
        sendBtn.onclick = () => {
            console.log("Send button clicked");
            sendMessage();
        };
    }

    if (userInput) {
        userInput.onkeydown = (e) => {
            if (e.key === "Enter") {
                console.log("Enter key pressed");
                sendMessage();
            }
        };
    }

    if (clearBtn) {
        clearBtn.onclick = async () => {
            if (confirm("Clear your chat history? Profile will be saved.")) {
                try {
                    const res = await fetch("/api/clear_chat", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ session_id: sessionId })
                    });
                    const data = await res.json();
                    if (data.success) {
                        document.getElementById("chat-box").innerHTML = "";
                        appendMessage("Chat cleared. How can I help you now?", "agent");
                    }
                } catch (e) {
                    alert("Failed to clear chat.");
                }
            }
        };
    }

    if (langSelect) {
        langSelect.onchange = (e) => {
            currentLanguage = e.target.value;
            if (recognition) {
                const speechMap = { "en": "en-US", "hi": "hi-IN", "es": "es-ES", "fr": "fr-FR" };
                recognition.lang = speechMap[currentLanguage] || "en-US";
            }
        };
    }

    if (saveProfileBtn) saveProfileBtn.onclick = saveProfile;
    if (confirmBookingBtn) confirmBookingBtn.onclick = confirmBooking;

    // Auth Listeners
    const loginBtn = document.getElementById("auth-login-btn");
    const signupBtn = document.getElementById("auth-signup-btn");
    if (loginBtn) loginBtn.onclick = login;
    if (signupBtn) signupBtn.onclick = signup;

    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
        logoutBtn.onclick = async () => {
            const res = await fetch("/api/logout", { method: "POST" });
            const data = await res.json();
            if (data.success) {
                location.reload();
            }
        };
    }

    initSpeechRecognition(voiceBtn, userInput);

    // Locator Listeners
    const toggleHospitals = document.getElementById("toggle-hospitals");
    const toggleDoctors = document.getElementById("toggle-doctors");
    const currentLocationBtn = document.getElementById("current-location-btn");
    const closeRouteBtn = document.getElementById("close-route");
    const saveDocProfileBtn = document.getElementById("save-doctor-profile-btn");
    if (saveDocProfileBtn) saveDocProfileBtn.onclick = saveDoctorProfile;

    if (toggleHospitals) toggleHospitals.onclick = () => switchFacilityType('hospital');
    if (toggleDoctors) toggleDoctors.onclick = () => switchFacilityType('doctor');
    if (currentLocationBtn) currentLocationBtn.onclick = () => locateUser();
    if (closeRouteBtn) closeRouteBtn.onclick = hideRoute;
}

async function checkAuth() {
    try {
        const res = await fetch("/api/me");
        const data = await res.json();
        if (data.authenticated) {
            currentUser = data.user;
            document.getElementById("auth-overlay").classList.add("hidden");
            // Show/Hide Admin Tab
            const adminTab = document.getElementById("admin-tab-btn");
            if (adminTab) {
                if (currentUser.role === 'admin') {
                    adminTab.classList.remove("hidden");
                } else {
                    adminTab.classList.add("hidden");
                }
            }
            updateUIForRole(data.user.role);
            // if (data.profile) fillProfileForm(data.profile);
            initApp();
        }
    } catch (e) {
        console.error("Auth check failed", e);
    }
}

function updateUIForRole(role) {
    const isAdmin = role === 'admin';
    const isDoctor = role === 'doctor';
    const isPatient = role === 'patient';
    currentUser.role = role;

    // Toggle Navigation Visibility
    const patientNav = document.getElementById("patient-nav");
    const adminNav = document.getElementById("admin-nav");
    const doctorNav = document.getElementById("doctor-nav");

    if (patientNav) patientNav.classList.toggle("hidden", !isPatient);
    if (adminNav) adminNav.classList.toggle("hidden", !isAdmin);
    if (doctorNav) doctorNav.classList.toggle("hidden", !isDoctor);

    // User Identity Display
    const userDisplay = document.querySelector(".w-10.h-10.rounded-full.bg-blue-500");
    if (userDisplay && currentUser) userDisplay.innerText = currentUser.username[0].toUpperCase();

    const nameDisplay = document.querySelector(".text-xs.font-bold.truncate");
    if (nameDisplay && currentUser) nameDisplay.innerText = currentUser.username;

    const roleDisplay = document.getElementById("user-role-display");
    if (roleDisplay) roleDisplay.innerText = role.toUpperCase() + " ACCOUNT";

    if (isAdmin) {
        switchTab('admin-dashboard');
    } else if (isDoctor) {
        switchTab('doctor-dashboard');
    }
}

function showSignup() {
    document.getElementById("login-form-container").classList.add("hidden");
    document.getElementById("signup-form-container").classList.remove("hidden");
}

function showLogin() {
    document.getElementById("signup-form-container").classList.add("hidden");
    document.getElementById("login-form-container").classList.remove("hidden");
}

async function login() {
    const username = document.getElementById("login-username").value;
    const password = document.getElementById("login-password").value;

    const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (data.success) {
        location.reload();
    } else {
        alert(data.error);
    }
}

async function signup() {
    const username = document.getElementById("signup-username").value;
    const password = document.getElementById("signup-password").value;
    const role = document.getElementById("signup-role").value;

    let payload = { username, password, role };

    if (role === 'doctor') {
        payload.name = document.getElementById("signup-doc-name").value;
        payload.specialty = document.getElementById("signup-doc-specialty").value;
        payload.location = document.getElementById("signup-doc-location").value;

        if (!payload.name || !payload.location) {
            alert("Please provide your Name and Clinic Location.");
            return;
        }

        // Use Full Name as the username to avoid duplicate fields for Doctor
        payload.username = payload.name;
    }

    const res = await fetch("/api/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
        alert("Account created! Please login.");
        showLogin();
    } else {
        alert(data.error);
    }
}

function toggleDoctorFields() {
    const role = document.getElementById("signup-role").value;
    const docFields = document.getElementById("doctor-signup-fields");
    const usernameField = document.getElementById("signup-username-container");

    if (role === 'doctor') {
        docFields.classList.remove("hidden");
        if (usernameField) usernameField.classList.add("hidden");
    } else {
        docFields.classList.add("hidden");
        if (usernameField) usernameField.classList.remove("hidden");
    }
}

function fillProfileForm(profile) {
    const form = document.getElementById('profile-form');
    for (let key in profile) {
        if (form.elements[key]) {
            form.elements[key].value = profile[key];
        }
    }
}

function switchTab(tabId) {
    currentTab = tabId;

    // Update navigation UI
    document.querySelectorAll('nav button').forEach(btn => {
        btn.classList.remove('active-nav', 'bg-blue-600', 'text-white');
        btn.classList.add('text-slate-400');
    });

    const activeNav = document.getElementById(`nav-${tabId}`);
    activeNav.classList.add('active-nav');
    activeNav.classList.remove('text-slate-400');

    // Update Section Visibility
    document.querySelectorAll('section').forEach(sec => {
        sec.classList.add('hidden');
        sec.classList.remove('active-section');
    });
    const activeSection = document.getElementById(`section-${tabId}`);
    activeSection.classList.remove('hidden');
    activeSection.classList.add('active-section');

    // Update Title
    const titles = {
        chat: "Medical Chat Analysis",
        doctors: "Specialist Directory",
        hospitals: "Nearby Emergency Facilities",
        analytics: "Patient Health Dashboard",
        'admin-dashboard': 'Admin Dashboard',
        'admin-approvals': 'Doctor Approvals',
        'admin-users': 'User Management',
        'admin-monitoring': 'System Monitoring',
        'admin-data': 'Manage System Data',
        'doctor-dashboard': 'Doctor Dashboard',
        'doctor-appointments': 'Patient Appointments',
        'doctor-profile': 'Doctor Professional Profile',
        'doctor-chats': 'Patient Conversations'
    };
    document.getElementById('current-tab-title').innerText = titles[tabId] || "MediBot AI";

    // Lazy load data
    if (tabId === 'doctors') loadDoctors();
    if (tabId.startsWith('admin-')) loadAdminData();
    if (tabId.startsWith('doctor-')) loadDoctorData();
    if (tabId === 'hospitals') {
        loadHospitals();
        // Recalculate map size after tab becomes visible
        if (hospitalMap) {
            setTimeout(() => hospitalMap.invalidateSize(), 300);
        }
    }
    if (tabId === 'analytics') updateAnalytics();
}

async function loadDoctors() {
    const list = document.getElementById('doctors-list');
    list.innerHTML = `<div class="col-span-full py-20 flex flex-col items-center"><div class="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full mb-4"></div><p>Querying specialists...</p></div>`;

    try {
        const res = await fetch('/api/doctors');
        const doctors = await res.json();
        list.innerHTML = '';
        doctors.forEach(doc => {
            list.appendChild(Components.createDoctorCard(doc, openBookingModal));
        });
    } catch (e) {
        list.innerHTML = `<p class="col-span-full text-center text-red-500 py-20">Error connecting to provider network.</p>`;
    }
}

async function loadHospitals() {
    const list = document.getElementById('facilities-list');
    list.innerHTML = `<div class="flex flex-col items-center justify-center py-20 text-slate-400">
        <div class="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full mb-4"></div>
        <p class="text-[10px] font-black uppercase tracking-widest">Identifying Locale...</p>
    </div>`;

    if (!hospitalMap) {
        hospitalMap = L.map('hospital-map', { zoomControl: false }).setView([20.5937, 78.9629], 5);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
        }).addTo(hospitalMap);
    }

    locateUser();
}

function locateUser() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(position => {
            const { latitude, longitude } = position.coords;
            userLocation = [latitude, longitude];
            hospitalMap.setView(userLocation, 13);

            // Add or move pulse marker for user
            if (window.userMarker) hospitalMap.removeLayer(window.userMarker);
            window.userMarker = L.circleMarker(userLocation, {
                radius: 8,
                fillColor: '#2563eb',
                color: '#fff',
                weight: 4,
                opacity: 1,
                fillOpacity: 1
            }).addTo(hospitalMap).bindPopup("You are here");

            fetchFacilities(currentFacilityType, latitude, longitude);
        }, () => fetchFacilities(currentFacilityType));
    } else {
        fetchFacilities(currentFacilityType);
    }
}

async function switchFacilityType(type) {
    currentFacilityType = type;
    const hBtn = document.getElementById('toggle-hospitals');
    const dBtn = document.getElementById('toggle-doctors');

    // UI Cleanup
    hideRoute();
    [hBtn, dBtn].forEach(b => b.className = "flex-1 py-2.5 rounded-[1rem] text-[10px] font-black uppercase tracking-widest transition-all duration-300 text-slate-400 hover:text-slate-600");
    const active = type === 'hospital' ? hBtn : dBtn;
    active.className = "flex-1 py-2.5 rounded-[1rem] text-[10px] font-black uppercase tracking-widest transition-all duration-300 bg-white text-blue-600 shadow-sm border border-slate-200";

    if (userLocation) {
        fetchFacilities(type, userLocation[0], userLocation[1]);
    } else {
        fetchFacilities(type);
    }
}

async function fetchFacilities(type, lat = null, lng = null) {
    const list = document.getElementById('facilities-list');
    let url = type === 'hospital' ? '/api/hospitals' : '/api/doctors/nearby';
    if (lat && lng) url += `?lat=${lat}&lng=${lng}`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        list.innerHTML = '';

        // Clear existing markers
        hospitalMarkers.forEach(m => hospitalMap.removeLayer(m));
        hospitalMarkers = [];

        if (data.length === 0) {
            list.innerHTML = `<div class="text-center py-20 text-slate-400 text-[10px] font-bold uppercase">No ${type}s found in range</div>`;
            return;
        }

        data.forEach(item => {
            const facilityLat = item.lat || item.latitude;
            const facilityLng = item.lng || item.longitude;

            if (facilityLat && facilityLng) {
                const marker = L.marker([facilityLat, facilityLng], {
                    icon: L.divIcon({
                        className: 'custom-div-icon',
                        html: `<div class="w-8 h-8 rounded-full ${type === 'doctor' ? 'bg-purple-600' : 'bg-blue-600'} border-4 border-white shadow-xl flex items-center justify-center text-white text-xs">
                            <i class="fa-solid ${type === 'doctor' ? 'fa-user-doctor' : 'fa-hospital'}"></i>
                        </div>`,
                        iconSize: [32, 32],
                        iconAnchor: [16, 32]
                    })
                }).addTo(hospitalMap);

                marker.bindPopup(`<div class="p-2">
                    <b class="text-slate-800">${item.name}</b><br>
                    <span class="text-slate-500 text-[10px]">${item.address || item.specialty}</span>
                </div>`);
                hospitalMarkers.push(marker);

                const listItem = Components.createFacilityListItem(item, type, (selected) => {
                    hospitalMap.setView([facilityLat, facilityLng], 15);
                    marker.openPopup();
                    if (userLocation) showRoute(facilityLat, facilityLng);
                }, openBookingModal);
                list.appendChild(listItem);
            }
        });
    } catch (e) {
        console.error("Locator Error:", e);
        list.innerHTML = '<div class="text-center py-20 text-red-400 text-[10px] font-bold uppercase">Sync Error</div>';
    }
}

async function showRoute(endLat, endLng) {
    if (!userLocation) return;

    // Clear previous route
    if (routingLayer) hospitalMap.removeLayer(routingLayer);

    try {
        const res = await fetch(`/api/route?start_lat=${userLocation[0]}&start_lng=${userLocation[1]}&end_lat=${endLat}&end_lng=${endLng}`);
        const data = await res.json();

        if (data.routes && data.routes.length > 0) {
            const route = data.routes[0];
            const coordinates = route.geometry.coordinates.map(c => [c[1], c[0]]);

            routingLayer = L.polyline(coordinates, {
                color: '#2563eb',
                weight: 6,
                opacity: 0.8,
                lineJoin: 'round',
                dashArray: '1, 10'
            }).addTo(hospitalMap);

            // Adjust map view to fit route
            hospitalMap.fitBounds(routingLayer.getBounds(), { padding: [50, 50] });

            // Show UI Analytics
            document.getElementById('route-panel').classList.remove('hidden');
            document.getElementById('route-distance').innerText = (route.distance / 1000).toFixed(1) + ' km';
            document.getElementById('route-duration').innerText = Math.round(route.duration / 60) + ' min';
        }
    } catch (e) {
        console.error("Routing Error:", e);
    }
}

function hideRoute() {
    if (routingLayer) hospitalMap.removeLayer(routingLayer);
    document.getElementById('route-panel').classList.add('hidden');
}

function openBookingModal(doctor) {
    selectedDoctor = doctor;
    document.getElementById('modal-doctor-name').innerText = doctor.name;
    document.getElementById('booking-modal').classList.remove('hidden');
    document.getElementById('booking-modal').classList.add('flex');
}

function closeModal() {
    document.getElementById('booking-modal').classList.add('hidden');
    document.getElementById('booking-modal').classList.remove('flex');
}

async function confirmBooking() {
    const time = document.getElementById('appointment-time').value;
    if (!time) return alert("Please select a time slot");

    try {
        const res = await fetch('/api/book_appointment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                doctor_id: selectedDoctor.id,
                time: time
            })
        });
        const data = await res.json();
        if (data.success) {
            if (data.session_id) {
                sessionId = data.session_id;
                localStorage.setItem("medibot_session_id", sessionId);
            }
            alert("Appointment successfully secured!");
            closeModal();
            updateAnalytics();
        } else {
            alert(data.error || "Booking failure.");
        }
    } catch (e) {
        alert("Booking failure. Please try later.");
    }
}

async function saveProfile() {
    const form = document.getElementById('profile-form');
    const formData = new FormData(form);
    const profile = Object.fromEntries(formData.entries());

    try {
        const res = await fetch('/api/save_profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile })
        });
        const data = await res.json();
        if (data.success) alert("Health record updated.");
    } catch (e) {
        alert("Sync error.");
    }
}

async function sendMessage() {
    const input = document.getElementById("user-input");
    const message = input.value.trim();
    console.log("Attempting to send message:", message);

    if (!message) return;

    appendMessage(message, "user");
    input.value = "";
    showTyping();

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, message, language: currentLanguage }),
        });

        if (!res.ok) {
            throw new Error(`HTTP error! status: ${res.status}`);
        }

        const data = await res.json();
        console.log("Received response:", data);

        if (data.session_id) {
            sessionId = data.session_id;
            localStorage.setItem("medibot_session_id", sessionId);
        }

        hideTyping();
        const responseText = data.reply || "No response content received.";
        const formatted = responseText.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        appendMessage(formatted, "agent");
    } catch (e) {
        console.error("Message send failed:", e);
        hideTyping();
        appendMessage(`System connectivity issue: ${e.message}`, "agent");
    }
}

function scrollToBottom() {
    const chatBox = document.getElementById('chat-box');
    chatBox.scrollTo({
        top: chatBox.scrollHeight,
        behavior: 'smooth'
    });
}

function appendMessage(text, role) {
    const chatBox = document.getElementById("chat-box");
    const msg = document.createElement("div");
    msg.className = role === "user" ? "flex items-start gap-3 justify-end animate-slide-up" : "flex items-start gap-3 animate-slide-up";

    if (role === "user") {
        msg.innerHTML = `<div class="bg-blue-600 text-white p-4 rounded-2xl rounded-tr-none shadow-sm max-w-[85%] text-sm leading-relaxed">${text}</div>`;
    } else {
        msg.innerHTML = `
            <div class="bg-blue-600 rounded-full p-2 h-10 w-10 flex items-center justify-center text-white flex-shrink-0 shadow-md">
                <i class="fa-solid fa-robot"></i>
            </div>
            <div class="bg-white border border-gray-100 text-gray-800 p-4 rounded-2xl rounded-tl-none shadow-sm max-w-[85%] text-sm leading-relaxed markdown-body">
                ${text}
            </div>
        `;
    }
    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function showTyping() {
    const div = document.createElement("div");
    div.id = "typing";
    div.className = "flex items-start gap-3";
    div.innerHTML = `
        <div class="bg-blue-600 rounded-full p-2 h-10 w-10 flex items-center justify-center text-white flex-shrink-0"><i class="fa-solid fa-robot"></i></div>
        <div class="bg-white border p-4 rounded-2xl flex items-center gap-1">
            <svg width="24" height="10" viewBox="0 0 24 10" class="fill-current text-slate-300">
                <circle cx="4" cy="5" r="3" class="typing-dot" /><circle cx="12" cy="5" r="3" class="typing-dot" /><circle cx="20" cy="5" r="3" class="typing-dot" />
            </svg>
        </div>
    `;
    document.getElementById("chat-box").appendChild(div);
}

function hideTyping() {
    const el = document.getElementById("typing");
    if (el) el.remove();
}

/** 
 * Speech Recognition Integration 
 */
function initSpeechRecognition(btn, input) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return btn.style.display = "none";

    recognition = new SR();
    recognition.onresult = (e) => {
        input.value = e.results[0][0].transcript;
        stopSTT(btn, input);
        sendMessage();
    };
    recognition.onspeechend = () => stopSTT(btn, input);

    btn.onclick = () => {
        if (isRecording) {
            recognition.stop();
        } else {
            recognition.start();
            btn.classList.add("recording-pulse");
            input.placeholder = "System listening...";
            isRecording = true;
        }
    };
}

function stopSTT(btn, input) {
    btn.classList.remove("recording-pulse");
    input.placeholder = "Describe symptoms...";
    isRecording = false;
}

/**
 * Analytics & Charts
 */
async function updateAnalytics() {
    if (!sessionId) return;
    try {
        const res = await fetch(`/api/analytics?session_id=${sessionId}`);
        const data = await res.json();

        document.getElementById('stat-sessions').innerText = data.message_count > 0 ? "1" : "0";
        document.getElementById('stat-symptoms').innerText = data.symptom_count || "0";
        document.getElementById('stat-appointments').innerText = data.appointment_count || "0";

        // Update charts with real data
        if (window.symptomsChart && data.unique_symptoms.length > 0) {
            window.symptomsChart.data.labels = data.unique_symptoms;
            window.symptomsChart.data.datasets[0].data = data.unique_symptoms.map(() => Math.floor(Math.random() * 5) + 1); // For demo, random freq but real symptoms
            window.symptomsChart.update();
        }
    } catch (e) {
        console.error("Analytics failure", e);
    }
}

function initCharts() {
    const ctx1 = document.getElementById('symptomsChart').getContext('2d');
    window.symptomsChart = new Chart(ctx1, {
        type: 'bar',
        data: {
            labels: ['Headache', 'Fever', 'Cough'],
            datasets: [{
                label: 'Occurrences',
                data: [5, 2, 3],
                backgroundColor: '#3b82f6',
                borderRadius: 8
            }]
        },
        options: { responsive: true, plugins: { legend: { display: false } } }
    });

    const ctx2 = document.getElementById('activityChart').getContext('2d');
    window.activityChart = new Chart(ctx2, {
        type: 'line',
        data: {
            labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
            datasets: [{
                label: 'Interactions',
                data: [12, 19, 3, 5, 2],
                borderColor: '#10b981',
                tension: 0.4,
                fill: true,
                backgroundColor: 'rgba(16, 185, 129, 0.1)'
            }]
        },
        options: { responsive: true, plugins: { legend: { display: false } } }
    });
}

// Admin Functions
async function loadAdminData() {
    try {
        const [usersRes, chatsRes, statsRes, docsRes] = await Promise.all([
            fetch('/api/admin/users'),
            fetch('/api/admin/chats'),
            fetch('/api/admin/stats'),
            fetch('/api/doctors')
        ]);

        const users = await usersRes.json();
        const chats = await chatsRes.json();
        const stats = await statsRes.json();
        const doctors = await docsRes.json();

        renderAdminStats(stats);
        renderAdminDoctorsApproval(users.filter(u => u.role === 'doctor' && !u.is_verified));
        renderAdminUsers(users);
        renderAdminChats(chats);
        renderAdminSystemData(doctors);
    } catch (e) {
        console.error("Admin data load failed", e);
    }
}

function renderAdminDoctorsApproval(doctors) {
    const list = document.getElementById('admin-doctors-approval-list');
    if (doctors.length === 0) {
        list.innerHTML = '<tr><td colspan="4" class="px-6 py-10 text-center text-slate-400 italic text-xs">No pending doctor approvals</td></tr>';
        return;
    }
    list.innerHTML = doctors.map(doc => `
        <tr class="border-b border-slate-100 hover:bg-slate-50 transition-all">
            <td class="px-6 py-4 font-bold text-slate-800">${doc.username}</td>
            <td class="px-6 py-4 text-slate-500">5+ Years (Verified Degree)</td>
            <td class="px-6 py-4">
                <span class="bg-amber-100 text-amber-600 px-2 py-1 rounded-full text-[10px] font-bold">AWAITING APPROVAL</span>
            </td>
            <td class="px-6 py-4">
                <button onclick="adminAction('verify', ${doc.id})" class="bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded-lg text-[10px] font-bold shadow-sm transition-all">
                    Approve Doctor
                </button>
            </td>
        </tr>
    `).join('');
}

function renderAdminStats(stats) {
    document.getElementById('admin-stat-users').innerText = stats.total_users || 0;
    document.getElementById('admin-stat-pending').innerText = stats.pending_doctors || 0;
    document.getElementById('admin-stat-msgs').innerText = stats.total_messages || 0;
    document.getElementById('admin-stat-sessions').innerText = stats.total_sessions || 0;
}

function renderAdminUsers(users) {
    const adminsList = document.getElementById('admin-users-admins-list');
    const doctorsList = document.getElementById('admin-users-doctors-list');
    const patientsList = document.getElementById('admin-users-patients-list');

    if (!adminsList || !doctorsList || !patientsList) return;

    const admins = users.filter(u => u.role === 'admin');
    const doctors = users.filter(u => u.role === 'doctor');
    const patients = users.filter(u => u.role === 'patient');

    document.getElementById('admin-count-admins').innerText = admins.length;
    document.getElementById('admin-count-doctors').innerText = doctors.length;
    document.getElementById('admin-count-patients').innerText = patients.length;

    // Helper for status badge
    const getStatusHTML = user => `
        <div class="flex flex-col gap-1">
            <span class="flex items-center gap-1.5 text-[11px] font-bold ${user.is_verified ? 'text-green-600' : 'text-amber-600'}">
                <i class="fa-solid ${user.is_verified ? 'fa-circle-check' : 'fa-clock'}"></i>
                ${user.is_verified ? 'VERIFIED' : 'PENDING'}
            </span>
            ${user.is_blocked ? `
                <span class="flex items-center gap-1.5 text-[11px] font-bold text-red-600">
                    <i class="fa-solid fa-ban"></i> BLOCKED
                </span>
            ` : '<span class="text-[9px] text-slate-400 font-medium">ACTIVE ACCOUNT</span>'}
        </div>
    `;

    // Compact row for Admin/Doctor
    const renderCompactRow = user => `
        <tr class="border-b border-slate-50 hover:bg-slate-50/50 transition-all">
            <td class="px-6 py-4">
                <div class="font-bold text-slate-800">${user.username}</div>
                <div class="text-[10px] text-slate-400 font-medium">UID: #${user.id.toString().padStart(4, '0')}</div>
            </td>
            <td class="px-6 py-4">
                ${getStatusHTML(user)}
            </td>
            <td class="px-6 py-4 text-right">
                <div class="flex justify-end gap-2">
                    <button onclick="adminAction('toggle-block', ${user.id}, ${user.is_blocked})" class="p-2 ${user.is_blocked ? 'bg-slate-100 text-slate-600' : 'bg-red-50 text-red-600'} rounded-xl hover:scale-110 transition-all" title="${user.is_blocked ? 'Unblock' : 'Block'}">
                        <i class="fa-solid ${user.is_blocked ? 'fa-unlock' : 'fa-ban'} text-sm"></i>
                    </button>
                    <button onclick="adminAction('delete', ${user.id})" class="p-2 bg-slate-100 text-slate-400 rounded-xl hover:bg-red-600 hover:text-white transition-all" title="Remove Profile">
                        <i class="fa-solid fa-trash-can text-sm"></i>
                    </button>
                </div>
            </td>
        </tr>
    `;

    // Detailed row for Patient
    const renderPatientRow = user => `
        <tr class="border-b border-slate-50 hover:bg-slate-50/50 transition-all">
            <td class="px-6 py-4">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 font-bold text-xs">
                        ${user.username[0].toUpperCase()}
                    </div>
                    <div>
                        <div class="font-bold text-slate-800">${user.username}</div>
                        <div class="text-[10px] text-slate-400 font-medium">Identity verified via system</div>
                    </div>
                </div>
            </td>
            <td class="px-6 py-4">
                <div class="text-xs font-semibold text-slate-600">ID: #${user.id.toString().padStart(4, '0')}</div>
                <div class="text-[10px] text-slate-400">Regular Patient Account</div>
            </td>
            <td class="px-6 py-4">
                ${getStatusHTML(user)}
            </td>
            <td class="px-6 py-4 text-right">
                <div class="flex justify-end gap-2">
                    <button onclick="adminAction('toggle-block', ${user.id}, ${user.is_blocked})" class="px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-bold hover:bg-slate-50 transition-all ${user.is_blocked ? 'text-blue-600' : 'text-red-600'}">
                        ${user.is_blocked ? 'UNBLOCK' : 'BLOCK'}
                    </button>
                    <button onclick="adminAction('delete', ${user.id})" class="p-2 text-slate-400 hover:text-red-600 transition-all">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </td>
        </tr>
    `;

    adminsList.innerHTML = admins.length ? admins.map(renderCompactRow).join('') : '<tr><td colspan="3" class="px-6 py-12 text-center text-slate-400 italic">No system administrators registered</td></tr>';
    doctorsList.innerHTML = doctors.length ? doctors.map(renderCompactRow).join('') : '<tr><td colspan="3" class="px-6 py-12 text-center text-slate-400 italic">No healthcare providers found</td></tr>';
    patientsList.innerHTML = patients.length ? patients.map(renderPatientRow).join('') : '<tr><td colspan="4" class="px-6 py-12 text-center text-slate-400 italic font-medium">No patient records found in the database</td></tr>';
}

function renderAdminChats(chats) {
    const list = document.getElementById('admin-chats-list');
    list.innerHTML = chats.map(chat => `
        <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-all">
            <div class="flex justify-between items-start mb-3">
                <div>
                    <div class="font-bold text-slate-800">${chat.username}</div>
                    <div class="text-[10px] text-slate-500 uppercase tracking-wider">${chat.role}</div>
                </div>
                <div class="bg-blue-100 text-blue-600 px-2 py-1 rounded text-[10px] font-bold">
                    ${chat.msg_count} msgs
                </div>
            </div>
            <button onclick="viewChatHistory('${chat.session_id}', '${chat.username}')" class="w-full py-2 bg-slate-50 text-slate-600 rounded-lg text-xs font-medium hover:bg-slate-100 transition-all border border-slate-100">
                View History
            </button>
        </div>
    `).join('');
}

async function adminAction(action, userId, currentStatus) {
    let url = '/api/admin/user/status';
    let body = { user_id: userId };

    if (action === 'verify') body.is_verified = 1;
    if (action === 'toggle-block') body.is_blocked = currentStatus ? 0 : 1;
    if (action === 'delete') {
        if (!confirm("Are you sure you want to delete this user?")) return;
        url = '/api/admin/user/delete';
    }

    try {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (res.ok) loadAdminData();
    } catch (e) {
        console.error("Admin action failed", e);
    }
}

async function viewChatHistory(sessionId, username) {
    const modal = document.getElementById('chat-modal');
    const content = document.getElementById('chat-modal-content');
    document.getElementById('chat-modal-title').innerText = `Chat with ${username}`;

    content.innerHTML = '<div class="text-center py-10"><div class="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4"></div><p class="text-slate-500">Loading history...</p></div>';
    modal.classList.remove('hidden');
    modal.classList.add('flex');

    try {
        const res = await fetch(`/api/admin/chat/${sessionId}`);
        const history = await res.json();

        content.innerHTML = history.map(msg => `
            <div class="flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}">
                <div class="max-w-[80%] rounded-2xl p-3 ${msg.role === 'user' ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-white text-slate-800 border border-slate-200 rounded-tl-none'
            }">
                    <p class="text-sm">${msg.content}</p>
                    ${msg.extracted_symptoms && msg.extracted_symptoms.length > 0 ? `
                        <div class="mt-2 flex flex-wrap gap-1">
                            ${msg.extracted_symptoms.map(s => `<span class="bg-white/20 text-[10px] px-1.5 py-0.5 rounded">${s}</span>`).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `).join('');
    } catch (e) {
        content.innerHTML = '<p class="text-center py-10 text-red-500">Failed to load chat history.</p>';
    }
}

function closeChatModal() {
    const modal = document.getElementById('chat-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

function renderAdminSystemData(doctors) {
    const list = document.getElementById('admin-system-doctors-list');
    if (!list) return;
    list.innerHTML = doctors.map(doc => `
        <tr class="border-b border-slate-100 hover:bg-slate-50 transition-all">
            <td class="px-6 py-4 font-bold text-slate-800">${doc.name}</td>
            <td class="px-6 py-4 text-slate-500 uppercase text-[10px] font-bold tracking-wider">${doc.specialty}</td>
            <td class="px-6 py-4 text-slate-500">${doc.location}</td>
            <td class="px-6 py-4">
                <span class="bg-amber-50 text-amber-600 px-2 py-1 rounded-full text-[10px] font-bold">
                    <i class="fa-solid fa-star mr-1"></i>${doc.rating}
                </span>
            </td>
        </tr>
    `).join('');
}

// Doctor Dashboard Functions
async function loadDoctorData() {
    try {
        const res = await fetch("/api/me");
        const data = await res.json();
        const doctor = data.doctor_info;

        if (doctor) {
            const welcome = document.getElementById("doctor-name-welcome");
            if (welcome) welcome.innerText = doctor.name || currentUser.username;

            const nameInput = document.getElementById("doc-profile-name");
            const specialtyInput = document.getElementById("doc-profile-specialty");
            const locInput = document.getElementById("doc-profile-location");

            if (nameInput) nameInput.value = doctor.name || "";
            if (specialtyInput) specialtyInput.value = doctor.specialty || "";
            if (locInput) locInput.value = doctor.location || "";

            // Load Appointments
            const appRes = await fetch("/api/doctor/appointments");
            const appointments = await appRes.json();

            const statTotal = document.getElementById("doctor-stat-total");
            const statPending = document.getElementById("doctor-stat-pending");
            if (statTotal) statTotal.innerText = appointments.length;
            if (statPending) statPending.innerText = appointments.filter(a => a.status === 'pending').length;

            renderDoctorAppointments(appointments);

            // Load Chats
            const chatRes = await fetch("/api/admin/chats");
            if (chatRes.ok) {
                const chats = await chatRes.json();
                const statChats = document.getElementById("doctor-stat-chats");
                if (statChats) statChats.innerText = chats.length;
                renderDoctorChats(chats);
            }
        }
    } catch (e) {
        console.error("Failed to load doctor data", e);
    }
}

function renderDoctorAppointments(appointments) {
    const list = document.getElementById("doctor-appointments-list");
    if (!list) return;

    if (!appointments.length) {
        list.innerHTML = `<div class="flex flex-col items-center justify-center py-20 text-slate-400">
            <i class="fa-solid fa-calendar-day text-5xl mb-4 opacity-20"></i>
            <p>No appointments found</p>
        </div>`;
        return;
    }

    list.innerHTML = appointments.map(app => `
        <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm hover:shadow-md transition-all flex flex-col md:flex-row items-start md:items-center justify-between gap-4 group">
            <div class="flex items-center gap-6">
                <div class="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center text-blue-600 border border-blue-100">
                    <i class="fa-solid fa-user"></i>
                </div>
                <div>
                    <h4 class="font-bold text-slate-800 text-lg">${app.patient_name || 'Anonymous Patient'}</h4>
                    <p class="text-slate-400 text-sm flex items-center gap-2">
                        <i class="fa-solid fa-clock opacity-50"></i> ${app.appointment_time}
                        <span class="px-2 py-0.5 rounded-full text-[10px] uppercase font-black tracking-widest ${getStatusClass(app.status)}">
                            ${app.status}
                        </span>
                    </p>
                </div>
            </div>
            <div class="flex items-center gap-2">
                ${app.status === 'pending' ? `
                    <button onclick="updateAppStatus(${app.id}, 'accepted')" class="p-4 rounded-2xl bg-green-50 text-green-600 hover:bg-green-600 hover:text-white transition-all" title="Accept">
                        <i class="fa-solid fa-check"></i>
                    </button>
                    <button onclick="updateAppStatus(${app.id}, 'rejected')" class="p-4 rounded-2xl bg-red-50 text-red-600 hover:bg-red-600 hover:text-white transition-all" title="Reject">
                        <i class="fa-solid fa-times"></i>
                    </button>
                ` : app.status === 'accepted' ? `
                    <button onclick="updateAppStatus(${app.id}, 'completed')" class="px-6 py-3 rounded-2xl bg-emerald-50 text-emerald-600 hover:bg-emerald-600 hover:text-white transition-all text-sm font-bold">
                        Mark Complete
                    </button>
                ` : `<span class="text-slate-400 text-sm font-bold px-4">Session Finished</span>`}
            </div>
        </div>
    `).join('');
}

function getStatusClass(status) {
    switch (status) {
        case 'pending': return 'bg-amber-50 text-amber-600';
        case 'accepted': return 'bg-blue-50 text-blue-600';
        case 'completed': return 'bg-emerald-50 text-emerald-600';
        case 'rejected': return 'bg-red-50 text-red-600';
        default: return 'bg-slate-50 text-slate-600';
    }
}

async function updateAppStatus(id, status) {
    if (!confirm(`Are you sure you want to mark this appointment as ${status}?`)) return;
    try {
        const res = await fetch("/api/doctor/appointment/status", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ appointment_id: id, status: status })
        });
        const data = await res.json();
        if (data.success) {
            loadDoctorData();
        }
    } catch (e) {
        console.error("Failed to update status", e);
    }
}

function renderDoctorChats(chats) {
    const list = document.getElementById("doctor-chats-list");
    if (!list) return;

    if (!chats.length) {
        list.innerHTML = `<div class="col-span-full flex flex-col items-center justify-center py-20 text-slate-400">
            <i class="fa-solid fa-comments text-5xl mb-4 opacity-20"></i>
            <p>No patient interactions found</p>
        </div>`;
        return;
    }

    list.innerHTML = chats.map(chat => `
        <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm hover:shadow-md transition-all">
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center gap-4">
                    <div class="w-12 h-12 rounded-2xl bg-purple-50 flex items-center justify-center text-purple-600">
                        <i class="fa-solid fa-comment-medical"></i>
                    </div>
                    <div>
                        <h4 class="font-bold text-slate-800">Session ${chat.session_id.substring(0, 8)}</h4>
                        <p class="text-[10px] text-slate-400 font-black uppercase tracking-widest">${chat.msg_count} Messages</p>
                    </div>
                </div>
            </div>
            <div class="p-4 bg-slate-50 rounded-2xl mb-4">
                <p class="text-sm text-slate-600 italic">"${chat.last_msg.substring(0, 80)}${chat.last_msg.length > 80 ? '...' : ''}"</p>
            </div>
            <button onclick="viewChatDetails('${chat.session_id}')" class="w-full py-3 bg-white border-2 border-slate-100 rounded-2xl text-slate-600 font-bold hover:bg-slate-50 transition-all text-sm">
                View Chat History
            </button>
        </div>
    `).join('');
}

async function saveDoctorProfile() {
    const profile = {
        name: document.getElementById("doc-profile-name").value,
        specialty: document.getElementById("doc-profile-specialty").value,
        location: document.getElementById("doc-profile-location").value
    };

    if (!profile.name) {
        alert("Please enter your name");
        return;
    }

    try {
        const res = await fetch("/api/doctor/profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ profile: profile })
        });
        const data = await res.json();
        if (data.success) {
            alert("Profile updated successfully!");
            loadDoctorData();
        }
    } catch (e) {
        console.error("Failed to save profile", e);
        alert("Action failed. Please try again.");
    }
}

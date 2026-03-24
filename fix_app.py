import sys

with open("static/app.js", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "function renderDoctorAppointments(appointments) {" in line:
        break
    new_lines.append(line)

new_content = ''.join(new_lines) + """function renderDoctorAppointments(appointments) {
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
    switch(status) {
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
"""

with open("static/app.js", "w") as f:
    f.write(new_content)


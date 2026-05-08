/**
 * UI Components for MediBot AI
 */

const Components = {
    /**
     * Creates a doctor card element
     */
    createDoctorCard: (doctor, onBook) => {
        const card = document.createElement('div');
        card.className = 'doctor-card bg-white rounded-[3rem] border border-slate-200 overflow-hidden shadow-sm hover:shadow-2xl transition-all duration-500 group flex flex-col md:flex-row min-h-[300px] relative';
        card.innerHTML = `
            <!-- Left Side: Image -->
            <div class="md:w-72 w-full h-72 md:h-auto overflow-hidden relative">
                <img src="${doctor.image_url || 'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&q=80&w=200&h=200'}" alt="${doctor.name}" class="absolute inset-0 w-full h-full object-cover transition-all duration-700 group-hover:scale-110">
                <div class="absolute inset-0 bg-gradient-to-t from-slate-900/60 via-transparent to-transparent"></div>
                <div class="absolute bottom-6 left-6">
                    <div class="flex items-center gap-2">
                        <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.8)]"></div>
                        <span class="text-[10px] font-black text-white uppercase tracking-[0.2em] drop-shadow-md">Active Specialist</span>
                    </div>
                </div>
            </div>

            <!-- Right Side: Details -->
            <div class="flex-1 p-10 flex flex-col justify-center relative bg-gradient-to-br from-white to-slate-50/50">
                <div class="mb-6">
                    <div class="inline-block px-3 py-1 bg-blue-100 text-blue-600 rounded-lg text-[9px] font-black uppercase tracking-[0.2em] mb-4 shadow-sm border border-blue-200/50">${doctor.specialty}</div>
                    <h3 class="text-4xl font-black text-slate-800 tracking-tighter mb-2 group-hover:text-blue-600 transition-colors">${doctor.name}</h3>
                    <div class="flex items-center gap-2 text-slate-500">
                        <i class="fa-solid fa-location-dot text-blue-500 text-xs"></i>
                        <span class="text-xs font-bold uppercase tracking-tight text-slate-600">${doctor.location}</span>
                    </div>
                </div>

                <div class="flex items-center justify-between gap-10 mt-4 pt-8 border-t border-slate-100">
                    <div class="flex items-center gap-4">
                        <div class="w-12 h-12 rounded-2xl bg-blue-50 flex items-center justify-center text-blue-600 border border-blue-100">
                            <i class="fa-solid fa-shield-halved"></i>
                        </div>
                        <div>
                            <div class="text-[9px] font-black text-slate-400 uppercase tracking-widest">Verification</div>
                            <div class="text-[10px] font-bold text-slate-600">Priority Tier Partner</div>
                        </div>
                    </div>
                    <button class="flex-1 max-w-[220px] py-4.5 bg-slate-900 hover:bg-blue-600 text-white rounded-2xl font-black text-[10px] uppercase tracking-[0.3em] shadow-xl hover:shadow-blue-500/30 transition-all duration-500 flex items-center justify-center gap-3 active:scale-95 border-b-4 border-slate-800 hover:border-blue-700">
                        Schedule Appointment
                    </button>
                </div>
            </div>
        `;

        card.querySelector('button').onclick = () => onBook(doctor);
        return card;
    },

    /**
     * Creates a hospital card element
     */
    createHospitalCard: (hospital) => {
        const card = document.createElement('div');
        card.className = 'bg-slate-50 p-4 rounded-xl border border-slate-200 flex flex-col shadow-sm hover:shadow-md transition-all animate-slide-up';
        card.innerHTML = `
            <div class="flex items-start justify-between mb-2">
                <h4 class="font-bold text-slate-800 text-sm">${hospital.name}</h4>
                <span class="text-[10px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-bold">OPEN</span>
            </div>
            <p class="text-xs text-slate-500 mb-3 flex items-center gap-1">
                <i class="fa-solid fa-map-marker-alt"></i>
                ${hospital.address}
            </p>
            <div class="flex gap-2">
                <button class="flex-1 py-1.5 bg-white border border-slate-200 rounded-lg text-[10px] font-bold text-slate-700 hover:bg-slate-100 flex items-center justify-center gap-1">
                    <i class="fa-solid fa-directions"></i> Get Directions
                </button>
                <button class="flex-1 py-1.5 bg-blue-600 text-white rounded-lg text-[10px] font-bold hover:bg-blue-700 flex items-center justify-center gap-1">
                    <i class="fa-solid fa-phone"></i> Call Emergency
                </button>
            </div>
        `;
        return card;
    },

    /**
     * Creates a facility list item for the locator side panel
     */
    createFacilityListItem: (item, type, onSelect, onBook) => {
        const div = document.createElement('div');
        div.className = 'group p-4 rounded-2xl bg-white border border-slate-100 hover:border-blue-200 hover:shadow-lg transition-all duration-300 cursor-pointer flex items-center gap-4';

        const icon = type === 'doctor' ? 'fa-user-doctor' : 'fa-hospital';
        const color = type === 'doctor' ? 'bg-purple-50 text-purple-600' : 'bg-blue-50 text-blue-600';

        div.innerHTML = `
            <div class="w-12 h-12 rounded-xl ${color} flex items-center justify-center text-lg shadow-sm group-hover:scale-110 transition-transform">
                <i class="fa-solid ${icon}"></i>
            </div>
            <div class="flex-1 min-w-0">
                <h4 class="font-black text-slate-800 text-sm truncate uppercase tracking-tight">${item.name}</h4>
                <p class="text-[10px] text-slate-500 truncate font-bold">${item.address || item.specialty || 'Medical Facility'}</p>
                <div class="flex items-center gap-3 mt-1">
                    <span class="text-[9px] font-black text-blue-500 uppercase tracking-widest">${item.distance ? item.distance + ' km Away' : 'Nearby'}</span>
                </div>
            </div>
            <div class="flex flex-col gap-2">
                ${type === 'doctor' ? `
                    <button class="book-btn w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center hover:bg-blue-600 hover:text-white transition-all shadow-sm" title="Schedule Appointment">
                        <i class="fa-solid fa-calendar-check text-xs"></i>
                    </button>
                ` : ''}
                <div class="w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center text-slate-400 group-hover:bg-slate-100 transition-all">
                    <i class="fa-solid fa-chevron-right text-xs"></i>
                </div>
            </div>
        `;

        div.onclick = (e) => {
            if (e.target.closest('.book-btn')) {
                onBook(item);
            } else {
                onSelect(item);
            }
        };
        return div;
    }
};

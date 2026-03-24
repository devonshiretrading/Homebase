// ============================================================
// Lifeblock - Main JS
// ============================================================

let calendar = null;
let currentMood = null;
let waterCount = 0;

// ---- Water gate (speed bump) ----

function checkWaterGate() {
    const lastDismissed = localStorage.getItem('water_gate_dismissed');
    if (lastDismissed) {
        const elapsed = Date.now() - parseInt(lastDismissed);
        // Show every 90 minutes
        if (elapsed < 60 * 60 * 1000) return;
    }
    document.getElementById('water-gate').style.display = 'flex';
}

function dismissGate(type) {
    if (type === 'water') {
        localStorage.setItem('water_gate_dismissed', Date.now().toString());
        document.getElementById('water-gate').style.display = 'none';
    }
}

// Show water gate on page load
document.addEventListener('DOMContentLoaded', function () {
    checkWaterGate();
    requestLocation();
});


// ---- Geolocation ----

function requestLocation() {
    fetch('/api/location')
        .then(r => r.json())
        .then(data => {
            if (!data.lat) {
                // No location stored, request from browser
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(
                        pos => {
                            fetch('/api/location', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    lat: pos.coords.latitude,
                                    lon: pos.coords.longitude,
                                }),
                            }).then(() => refreshWeather());
                        },
                        err => console.log('Geolocation denied:', err.message)
                    );
                }
            } else {
                refreshWeather();
            }
        });
}


// ---- Weather ----

function refreshWeather() {
    fetch('/api/weather/refresh', { method: 'POST' })
        .then(r => r.json())
        .then(() => loadWeather());
}

function loadWeather() {
    fetch('/api/weather')
        .then(r => r.json())
        .then(forecasts => {
            const strip = document.getElementById('weather-strip');
            if (!strip) return;
            if (!forecasts.length) {
                strip.innerHTML = '<p class="muted">No weather data yet</p>';
                return;
            }
            strip.innerHTML = forecasts.map(f => {
                const dayName = new Date(f.date + 'T00:00').toLocaleDateString('en-US', { weekday: 'short' });
                const rainPct = f.precipitation_probability || 0;
                return `
                    <div class="weather-day">
                        <span class="weather-day-name">${dayName}</span>
                        <span class="weather-temp">${Math.round(f.temp_max)}°</span>
                        <span class="weather-rain">${rainPct > 0 ? rainPct + '% 🌧' : '☀️'}</span>
                    </div>
                `;
            }).join('');

            // Load 48h rain chart
            loadRainChart();
        });
}


// ---- 48h rain chart ----

function loadRainChart() {
    const container = document.getElementById('rain-chart');
    if (!container) return;

    // Fetch hourly weather and daily (for sunrise/sunset)
    Promise.all([
        fetch('/api/weather/hourly').then(r => r.json()),
        fetch('/api/weather').then(r => r.json()),
    ]).then(([hours, daily]) => {
        if (!hours.length) {
            container.innerHTML = '<p class="muted">No hourly data</p>';
            return;
        }

        // Build sunrise/sunset lookup by date string
        const sunTimes = {};
        daily.forEach(d => {
            if (d.sunrise && d.sunset) {
                sunTimes[d.date] = { sunrise: d.sunrise, sunset: d.sunset };
            }
        });

        const W = 480;
        const H = 140;
        const canvas = document.createElement('canvas');
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext('2d');

        // Draw day/night bands
        hours.forEach((h, i) => {
            const x = (i / hours.length) * W;
            const w = W / hours.length + 1;
            const dt = new Date(h.datetime);
            const dateStr = h.datetime.slice(0, 10);
            const hourNum = dt.getHours();
            const sun = sunTimes[dateStr];

            let isDay = (hourNum >= 7 && hourNum < 19); // fallback
            if (sun) {
                const sunriseH = parseInt(sun.sunrise.split(':')[0]);
                const sunsetH = parseInt(sun.sunset.split(':')[0]);
                isDay = (hourNum >= sunriseH && hourNum < sunsetH);
            }

            ctx.fillStyle = isDay ? 'rgba(255, 200, 50, 0.1)' : 'rgba(20, 20, 40, 0.6)';
            ctx.fillRect(x, 0, w, H);
        });

        // Draw rain probability line
        ctx.beginPath();
        ctx.strokeStyle = '#4A90D9';
        ctx.lineWidth = 2;

        hours.forEach((h, i) => {
            const x = (i / hours.length) * W;
            const pct = h.precipitation_probability || 0;
            const y = H - (pct / 100) * (H - 8) - 4;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Fill under the line
        const lastX = ((hours.length - 1) / hours.length) * W;
        ctx.lineTo(lastX, H);
        ctx.lineTo(0, H);
        ctx.closePath();
        ctx.fillStyle = 'rgba(74, 144, 217, 0.15)';
        ctx.fill();

        // Labels
        function dayLabel(h) {
            if (!h) return '';
            const dt = new Date(h.datetime);
            const now = new Date();
            const isToday = dt.toDateString() === now.toDateString();
            const tomorrow = new Date(now);
            tomorrow.setDate(tomorrow.getDate() + 1);
            const isTomorrow = dt.toDateString() === tomorrow.toDateString();
            const day = isToday ? 'Today' : isTomorrow ? 'Tmrw' : dt.toLocaleDateString('en-US', { weekday: 'short' });
            return `${day} ${h.hour.slice(0, 5)}`;
        }

        const labels = [
            dayLabel(hours[0]),
            dayLabel(hours[12]),
            dayLabel(hours[24]),
            dayLabel(hours[36]),
            dayLabel(hours[hours.length - 1]),
        ];

        container.innerHTML = `
            <div class="rain-canvas-wrap"></div>
            <div class="rain-chart-labels">
                ${labels.map(l => `<span>${l}</span>`).join('')}
            </div>
        `;
        container.querySelector('.rain-canvas-wrap').appendChild(canvas);
    });
}


// ---- Weekly toggles ----

// Toggle groups: "day-row" toggles render as a compact M T W T F row
const TOGGLE_GROUPS = [
    {
        type: 'day-row',
        label: 'Office',
        toggles: [
            { name: 'office_mon', short: 'M', day_of_week: 0 },
            { name: 'office_tue', short: 'T', day_of_week: 1 },
            { name: 'office_wed', short: 'W', day_of_week: 2 },
            { name: 'office_thu', short: 'T', day_of_week: 3 },
            { name: 'office_fri', short: 'F', day_of_week: 4 },
        ],
    },
    {
        type: 'day-row',
        label: 'Walk',
        toggles: [
            { name: 'school_walk_mon', short: 'M', day_of_week: 0 },
            { name: 'school_walk_tue', short: 'T', day_of_week: 1 },
            { name: 'school_walk_wed', short: 'W', day_of_week: 2 },
            { name: 'school_walk_thu', short: 'T', day_of_week: 3 },
            { name: 'school_walk_fri', short: 'F', day_of_week: 4 },
        ],
    },
    {
        type: 'day-row',
        label: 'Pick-up',
        toggles: [
            { name: 'pickup_mon', short: 'M', day_of_week: 0 },
            { name: 'pickup_tue', short: 'T', day_of_week: 1 },
            { name: 'pickup_wed', short: 'W', day_of_week: 2 },
            { name: 'pickup_thu', short: 'T', day_of_week: 3 },
            { name: 'pickup_fri', short: 'F', day_of_week: 4 },
        ],
    },
    {
        type: 'day-row',
        label: 'Dinner',
        toggles: [
            { name: 'dinner_mon', short: 'M', day_of_week: 0 },
            { name: 'dinner_tue', short: 'T', day_of_week: 1 },
            { name: 'dinner_wed', short: 'W', day_of_week: 2 },
            { name: 'dinner_thu', short: 'T', day_of_week: 3 },
            { name: 'dinner_fri', short: 'F', day_of_week: 4 },
        ],
    },
];

// Flat list for saving
const ALL_TOGGLES = [];
TOGGLE_GROUPS.forEach(g => {
    if (g.type === 'day-row') {
        g.toggles.forEach(t => ALL_TOGGLES.push({ ...t, label: `${g.label} ${t.short}` }));
    } else {
        ALL_TOGGLES.push(g);
    }
});

function loadToggles(weekStart) {
    const container = document.getElementById('toggles-container');
    if (!container) return;

    fetch(`/api/week/${weekStart}`)
        .then(r => r.json())
        .then(plan => {
            const saved = plan.toggles || {};
            let html = '';

            TOGGLE_GROUPS.forEach(g => {
                if (g.type === 'day-row') {
                    const buttons = g.toggles.map(t => {
                        const isOn = saved[t.name]?.value || false;
                        return `<button type="button" class="day-btn ${isOn ? 'active' : ''}"
                                    data-toggle="${t.name}" data-day="${t.day_of_week}"
                                    onclick="toggleDayBtn('${weekStart}', '${t.name}', this)">${t.short}</button>`;
                    }).join('');
                    html += `<div class="toggle-day-row"><span class="toggle-row-label">${g.label}</span><div class="day-btn-group">${buttons}</div></div>`;
                } else {
                    const isOn = saved[g.name]?.value || false;
                    html += `
                        <label class="toggle-item">
                            <input type="checkbox" data-toggle="${g.name}"
                                   ${isOn ? 'checked' : ''}
                                   onchange="saveToggle('${weekStart}', '${g.name}', this)">
                            <span>${g.label}</span>
                        </label>`;
                }
            });

            container.innerHTML = html;
        });
}

function toggleDayBtn(weekStart, name, btn) {
    btn.classList.toggle('active');
    const isOn = btn.classList.contains('active');
    const toggle = ALL_TOGGLES.find(t => t.name === name);
    fetch(`/api/week/${weekStart}/toggles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            toggles: {
                [name]: {
                    label: toggle.label,
                    value: isOn,
                    day_of_week: toggle.day_of_week,
                },
            },
        }),
    }).then(() => { if (calendar) calendar.refetchEvents(); });
}

function saveToggle(weekStart, name, el) {
    const toggle = ALL_TOGGLES.find(t => t.name === name);
    fetch(`/api/week/${weekStart}/toggles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            toggles: {
                [name]: {
                    label: toggle.label,
                    value: el.checked,
                    day_of_week: toggle.day_of_week,
                },
            },
        }),
    }).then(() => { if (calendar) calendar.refetchEvents(); });
}


// ---- Calendar (FullCalendar) ----

function initWeekView(weekStart) {
    const calendarEl = document.getElementById('calendar');
    if (!calendarEl) return;

    calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'timeGridWeek',
        initialDate: weekStart,
        firstDay: 1, // Monday
        slotMinTime: '06:00:00',
        slotMaxTime: '22:00:00',
        slotDuration: '01:00:00',
        slotLabelInterval: '01:00:00',
        slotLabelFormat: { hour: 'numeric', hour12: true },
        allDaySlot: false,
        headerToolbar: false,
        locale: 'en-AU',
        dayHeaderFormat: { weekday: 'short', day: 'numeric', month: 'short' },
        height: 'auto',
        expandRows: false,
        eventTimeFormat: { hour: 'numeric', minute: '2-digit', hour12: false, meridiem: false },
        editable: true,
        selectable: true,
        nowIndicator: true,

        events: '/api/events',

        // Drag to resize/move
        eventDrop: function (info) {
            const props = info.event.extendedProps;
            if (props.type !== 'block') {
                info.revert();
                return;
            }
            const s = info.event.start;
            const e = info.event.end;
            updateBlock(props.block_id, {
                date: `${s.getFullYear()}-${String(s.getMonth()+1).padStart(2,'0')}-${String(s.getDate()).padStart(2,'0')}`,
                start_time: `${String(s.getHours()).padStart(2,'0')}:${String(s.getMinutes()).padStart(2,'0')}`,
                end_time: `${String(e.getHours()).padStart(2,'0')}:${String(e.getMinutes()).padStart(2,'0')}`,
            });
        },

        eventStartEditable: true,
        eventResizableFromStart: true,

        eventResize: function (info) {
            const props = info.event.extendedProps;
            if (props.type !== 'block') {
                info.revert();
                return;
            }
            const s = info.event.start;
            const e = info.event.end;
            updateBlock(props.block_id, {
                date: `${s.getFullYear()}-${String(s.getMonth()+1).padStart(2,'0')}-${String(s.getDate()).padStart(2,'0')}`,
                start_time: `${String(s.getHours()).padStart(2,'0')}:${String(s.getMinutes()).padStart(2,'0')}`,
                end_time: `${String(e.getHours()).padStart(2,'0')}:${String(e.getMinutes()).padStart(2,'0')}`,
            });
        },

        // Click to select time range — show popup
        select: function (info) {
            showBlockPopup(info);
        },

        // Click existing event
        eventClick: function (info) {
            const props = info.event.extendedProps;

            // Calendar events — show detail on click
            if (props.type === 'calendar') {
                const detail = props.detail || 'Work meeting';
                const status = props.busy_status || 'BUSY';
                alert(`${detail}\nStatus: ${status}`);
                return;
            }

            if (props.type !== 'block') return;

            // Food shopping — show shops in the prompt
            const displayTitle = (props.category === 'food_shopping' && props.notes)
                ? `Shopping: ${props.notes}`
                : info.event.title;

            const action = prompt(
                `"${displayTitle}"\n\nType 'delete' to remove, 'done' to mark complete, or new name to rename:`
            );
            if (!action) return;

            if (action.toLowerCase() === 'delete') {
                deleteBlock(props.block_id);
            } else if (action.toLowerCase() === 'done') {
                updateBlock(props.block_id, { completed: true });
            } else {
                updateBlock(props.block_id, { title: action });
            }
        },

        // Style tentative events with dashed border
        eventDidMount: function (info) {
            const props = info.event.extendedProps;
            if (props.is_tentative) {
                info.el.style.border = '2px dashed #888888';
                info.el.style.backgroundColor = 'transparent';
            }
            // Lisa/Hugo: show note under name
            if (props.notes && (props.category === 'lisa' || props.category === 'hugo')) {
                const titleEl = info.el.querySelector('.fc-event-title');
                if (titleEl) {
                    titleEl.innerHTML = `${info.event.title.split('\n')[0]}<br><small style="opacity:0.8">${props.notes}</small>`;
                }
            }
        },
    });

    calendar.render();
    loadToggles(weekStart);
    loadWeather();
    syncOutlook();
    loadInsights();

    // Insights dropdown
    const insightsSelect = document.getElementById('insights-select');
    if (insightsSelect) {
        insightsSelect.addEventListener('change', loadInsights);
    }
}


// ---- Outlook sync ----

function syncOutlook() {
    fetch('/api/outlook/sync', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            console.log('Outlook sync:', data);
            if (calendar) calendar.refetchEvents();
        })
        .catch(err => console.log('Outlook sync skipped:', err));
}

// ---- Block CRUD ----

function updateBlock(blockId, data) {
    fetch(`/api/blocks/${blockId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    }).then(() => calendar.refetchEvents());
}

function deleteBlock(blockId) {
    fetch(`/api/blocks/${blockId}`, { method: 'DELETE' })
        .then(() => calendar.refetchEvents());
}

// ---- Block creation popup ----

function showBlockPopup(info) {
    // Remove existing popup
    const existing = document.getElementById('block-popup');
    if (existing) existing.remove();

    const dateStr = `${info.start.getFullYear()}-${String(info.start.getMonth()+1).padStart(2,'0')}-${String(info.start.getDate()).padStart(2,'0')}`;
    const startTime = info.start.toTimeString().slice(0, 5);
    const endTime = info.end.toTimeString().slice(0, 5);

    const popup = document.createElement('div');
    popup.id = 'block-popup';
    popup.innerHTML = `
        <div class="popup-row">
            <input type="text" id="popup-title" placeholder="Activity name..." autofocus>
            <button id="popup-go" class="popup-btn popup-btn-go">Go</button>
        </div>
        <div class="popup-categories">
            <button class="popup-cat" data-cat="lisa" data-color="#E91E8C" data-title="Lisa">Lisa</button>
            <button class="popup-cat" data-cat="hugo" data-color="#F5A623" data-title="Hugo">Hugo</button>
        </div>
    `;

    // Position near the click
    const calEl = document.getElementById('calendar');
    const calRect = calEl.getBoundingClientRect();
    const jsEvent = info.jsEvent || {};
    const x = (jsEvent.clientX || calRect.left + 100) - calRect.left;
    const y = (jsEvent.clientY || calRect.top + 100) - calRect.top;
    popup.style.left = x + 'px';
    popup.style.top = y + 'px';

    calEl.style.position = 'relative';
    calEl.appendChild(popup);

    const titleInput = popup.querySelector('#popup-title');
    titleInput.focus();

    function createBlock(title, category, color, notes) {
        fetch('/api/blocks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: title,
                date: dateStr,
                start_time: startTime,
                end_time: endTime,
                category: category,
                color: color,
                notes: notes || '',
            }),
        })
            .then(r => r.json())
            .then(() => {
                calendar.refetchEvents();
                popup.remove();
            });
    }

    // Go button — blue activity with typed name
    popup.querySelector('#popup-go').addEventListener('click', () => {
        const title = titleInput.value.trim() || 'Block';
        createBlock(title, 'general', '#4A90D9', '');
    });

    // Enter key in text field
    titleInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const title = titleInput.value.trim() || 'Block';
            createBlock(title, 'general', '#4A90D9', '');
        }
        if (e.key === 'Escape') popup.remove();
    });

    // Lisa / Hugo buttons — background blocks with optional note
    popup.querySelectorAll('.popup-cat').forEach(btn => {
        btn.addEventListener('click', () => {
            const notes = titleInput.value.trim();
            const title = notes ? `${btn.dataset.title}\n${notes}` : btn.dataset.title;
            createBlock(title, btn.dataset.cat, btn.dataset.color, notes);
        });
    });

    // Close on click outside
    setTimeout(() => {
        document.addEventListener('click', function closePopup(e) {
            if (!popup.contains(e.target)) {
                popup.remove();
                document.removeEventListener('click', closePopup);
            }
        });
    }, 100);
}


// ---- Quick add ----

function quickAddBlock() {
    const select = document.getElementById('quick-template');
    const option = select.options[select.selectedIndex];
    const dayOffset = parseInt(document.getElementById('quick-day').value);
    const timeInput = document.getElementById('quick-time');

    if (!option.value) {
        alert('Choose an activity');
        return;
    }

    const weekStart = new Date(WEEK_START + 'T00:00');
    const blockDate = new Date(weekStart);
    blockDate.setDate(blockDate.getDate() + dayOffset);
    const dateStr = blockDate.toISOString().slice(0, 10);

    // Use template default time if user hasn't changed it
    let startTime = timeInput.value;
    const templateDefault = option.dataset.start;
    if (templateDefault && startTime === '09:00') {
        startTime = templateDefault;
    }

    fetch('/api/blocks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            template_id: parseInt(option.value),
            date: dateStr,
            start_time: startTime,
        }),
    })
        .then(r => r.json())
        .then(() => {
            if (calendar) calendar.refetchEvents();
            select.value = '';
        });
}


// ---- Check-in ----

function adjustWater(delta) {
    const el = document.getElementById('water-count');
    waterCount = Math.max(0, parseInt(el.textContent) + delta);
    el.textContent = waterCount;
}

function setMood(val) {
    currentMood = val;
    document.querySelectorAll('.mood-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.mood) === val);
    });
}

function saveCheckIn() {
    const form = document.getElementById('checkin-form');
    const data = {
        date: CHECKIN_DATE,
        got_outside: form.querySelector('[name=got_outside]').checked,
        cooked_dinner: form.querySelector('[name=cooked_dinner]').checked,
        exercised: form.querySelector('[name=exercised]').checked,
        stretched: form.querySelector('[name=stretched]').checked,
        skincare: form.querySelector('[name=skincare]').checked,
        water_glasses: parseInt(document.getElementById('water-count').textContent),
        screens_off_time: form.querySelector('[name=screens_off_time]').value || null,
        mood: currentMood,
        notes: form.querySelector('[name=notes]').value,
    };

    fetch('/api/checkin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    })
        .then(r => r.json())
        .then(() => {
            const status = document.getElementById('checkin-status');
            status.textContent = 'Saved ✓';
            setTimeout(() => (status.textContent = ''), 2000);
        });
}


// ---- Strava sync ----

function syncStrava() {
    fetch('/api/strava/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days_back: 30 }),
    })
        .then(r => r.json())
        .then(data => {
            console.log('Strava sync:', data);
            loadInsights();
        })
        .catch(err => console.log('Strava sync failed:', err));
}

function toggleRun(runType, enabled) {
    fetch('/api/schedule-run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_type: runType, enabled: enabled }),
    })
        .then(r => r.json())
        .then(data => {
            console.log('Run scheduled:', data);
            if (calendar) calendar.refetchEvents();
            loadInsights();
        });
}

function toggleSangsters(dayOfWeek, btn) {
    const isActive = btn.classList.contains('active');
    fetch('/api/schedule-run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            run_type: 'sangsters',
            day_of_week: dayOfWeek,
            enabled: !isActive,
        }),
    })
        .then(r => r.json())
        .then(data => {
            console.log('Sangsters scheduled:', data);
            if (calendar) calendar.refetchEvents();
            loadInsights();
        });
}

// ---- Insights panel ----

function loadInsights() {
    const select = document.getElementById('insights-select');
    if (!select) return;
    const panel = select.value;

    if (panel === 'running') {
        loadRunningInsights();
    } else if (panel === 'food') {
        loadFoodPanel();
    } else if (panel === 'habits') {
        loadHabitsPanel();
    }
}

function loadRunningInsights() {
    fetch('/api/insights/running')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('insights-content');

            function fmtDate(iso) {
                const d = new Date(iso + 'T00:00:00');
                const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
                return days[d.getDay()] + ' ' + d.getDate() + '/' + (d.getMonth()+1);
            }

            // Recent runs
            let recentHtml = '';
            if (data.recent_runs.length === 0) {
                recentHtml = '<p class="no-data">No recent runs</p>';
            } else {
                data.recent_runs.forEach(r => {
                    recentHtml += `
                        <div class="run-row">
                            <span class="run-date">${fmtDate(r.date)}</span>
                            <span class="run-name">${r.name}</span>
                            <span class="run-stat">${r.distance_km} km</span>
                            <span class="run-pace">${r.pace || '-'} /km</span>
                            <span class="run-effort">${r.suffer_score || '-'}</span>
                        </div>`;
                });
                recentHtml += `
                    <div class="run-row" style="color:var(--text-muted); font-size:0.75rem; border:none; padding-top:8px;">
                        <span>This week: ${data.week_summary.run_count} runs, ${data.week_summary.distance_km} km · Avg ${data.fitness.weekly_avg_km} km/wk</span>
                    </div>`;
            }

            // Scheduled
            let schedHtml = '';
            if (data.scheduled.length === 0) {
                schedHtml = '<p class="no-data">No runs scheduled this week</p>';
            } else {
                data.scheduled.forEach(s => {
                    const d = new Date(s.date + 'T00:00:00');
                    const dayName = d.toLocaleDateString('en-AU', {weekday: 'short'});
                    const dateStr = d.toLocaleDateString('en-AU', {day: 'numeric', month: 'numeric'});
                    schedHtml += `
                        <div class="scheduled-row">
                            <span class="sched-day">${dayName}</span>
                            <span class="sched-date">${dateStr}</span>
                            <span class="sched-title">${s.title}</span>
                            <span class="sched-time">${s.start_time}</span>
                        </div>`;
                });
            }

            container.innerHTML = `
                <div class="insights-grid">
                    <div class="insight-card">
                        <h5>Last 3 Runs <button onclick="syncStrava()" class="btn-sync">↻</button></h5>
                        ${recentHtml}
                    </div>
                    <div class="insight-card">
                        <h5>Plan</h5>
                        <div class="run-toggles">
                            <label class="run-toggle-item">
                                <input type="checkbox" data-run="track_club" onchange="toggleRun('track_club', this.checked)">
                                <span>Tue Track Club</span>
                            </label>
                            <label class="run-toggle-item">
                                <input type="checkbox" data-run="office" onchange="toggleRun('office', this.checked)">
                                <span>Thu Office Run</span>
                            </label>
                            <label class="run-toggle-item">
                                <input type="checkbox" data-run="parkrun" onchange="toggleRun('parkrun', this.checked)">
                                <span>Sat Parkrun</span>
                            </label>
                            <label class="run-toggle-item">
                                <input type="checkbox" data-run="long" onchange="toggleRun('long', this.checked)">
                                <span>Sun Long Run</span>
                            </label>
                        </div>
                        <div class="sangsters-row">
                            <span style="font-size:0.85rem;">Sangsters</span>
                            <div class="day-circles">
                                ${['M','T','W','T','F','S','S'].map((d, i) =>
                                    `<button class="day-btn-sm" data-day="${i}" onclick="toggleSangsters(${i}, this)">${d}</button>`
                                ).join('')}
                            </div>
                        </div>
                    </div>
                    <div class="insight-card">
                        <h5>Scheduled</h5>
                        ${schedHtml}
                    </div>
                </div>`;

            // Set toggle states from scheduled blocks
            data.scheduled.forEach(s => {
                let runType = null;
                if (s.title === 'Tuesday Track Club') runType = 'track_club';
                else if (s.title === 'Office Run') runType = 'office';
                else if (s.title === 'Parkrun') runType = 'parkrun';
                else if (s.title === 'Long Run') runType = 'long';
                if (runType) {
                    const cb = document.querySelector(`[data-run="${runType}"]`);
                    if (cb) cb.checked = true;
                }
                if (s.title === 'Sangsters Run') {
                    const d = new Date(s.date + 'T00:00:00');
                    const dayBtn = document.querySelector(`.day-btn-sm[data-day="${d.getDay() === 0 ? 6 : d.getDay() - 1}"]`);
                    if (dayBtn) dayBtn.classList.add('active');
                }
            });
        })
        .catch(err => {
            document.getElementById('insights-content').innerHTML =
                '<p class="no-data">Connect Strava to see running data</p>';
        });
}


// ---- Habits panel ----

const MOODS = [
    { name: 'anxious', emoji: '😰' },
    { name: 'stressed', emoji: '😣' },
    { name: 'angry', emoji: '😤' },
    { name: 'frustrated', emoji: '😩' },
    { name: 'tired', emoji: '😴' },
    { name: 'mellow', emoji: '😌' },
    { name: 'whimsy', emoji: '🌀' },
    { name: 'buoyant', emoji: '😊' },
    { name: "let's go", emoji: '🔥' },
];

function loadHabitsPanel() {
    const today = new Date().toISOString().slice(0, 10);
    fetch(`/api/checkin?date=${today}`)
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('insights-content');

            const habits = [
                { key: 'water_glasses', label: '💧 Water', type: 'counter', value: data.water_glasses || 0 },
                { key: 'skincare', label: '✨ Skincare', type: 'check', value: data.skincare },
                { key: 'exercised', label: '🏃 Exercised', type: 'check', value: data.exercised },
                { key: 'got_outside', label: '🌳 Got outside', type: 'check', value: data.got_outside },
                { key: 'stretched', label: '🙆 Stretched', type: 'check', value: data.stretched },
            ];

            // Build single row of habit items
            const currentMood = data.mood_name || '';
            let moodBtns = '';
            MOODS.forEach(m => {
                const active = currentMood === m.name ? 'active' : '';
                moodBtns += `<button class="mood-btn ${active}" title="${m.name}" onclick="setMoodHabit('${m.name}')">${m.emoji}</button>`;
            });

            container.innerHTML = `
                <div class="habits-bar">
                    <div class="habit-item">
                        <span class="habit-icon">💧</span>
                        <button class="btn-water" onclick="adjustWaterHabit(-1)">−</button>
                        <span id="water-count-habits">${data.water_glasses || 0}</span>
                        <button class="btn-water" onclick="adjustWaterHabit(1)">+</button>
                    </div>
                    ${habits.filter(h => h.type === 'check').map(h => `
                        <label class="habit-item habit-check">
                            <input type="checkbox" ${h.value ? 'checked' : ''} onchange="toggleHabit('${h.key}', this.checked)">
                            <span>${h.label}</span>
                        </label>
                    `).join('')}
                    <label class="habit-item habit-check">
                        <input type="checkbox" ${data.nytimes ? 'checked' : ''} onchange="toggleHabit('nytimes', this.checked)">
                        <a href="https://www.nytimes.com/crosswords" target="_blank" class="habit-link">📰 NYTimes</a>
                    </label>
                    <div class="habit-item mood-bar">${moodBtns}</div>
                </div>`;
        });
}

function toggleHabit(key, value) {
    const today = new Date().toISOString().slice(0, 10);
    const payload = { date: today };
    payload[key] = value;
    fetch('/api/checkin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
}

function adjustWaterHabit(delta) {
    const el = document.getElementById('water-count-habits');
    let count = parseInt(el.textContent) + delta;
    if (count < 0) count = 0;
    el.textContent = count;
    const today = new Date().toISOString().slice(0, 10);
    fetch('/api/checkin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: today, water_glasses: count }),
    });
}

function setMoodHabit(moodName) {
    const today = new Date().toISOString().slice(0, 10);
    fetch('/api/checkin/mood', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: today, mood: moodName }),
    })
    .then(r => r.json())
    .then(() => loadHabitsPanel());
}


// ---- Food shopping panel ----

const SHOPS = ['Butcher', 'Fishmonger', 'Fruit & Veg', 'Supermarket'];
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function loadFoodPanel() {
    fetch(`/api/food-shopping?week_start=${WEEK_START}`)
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('insights-content');
            // data.plans is { "0": ["Butcher", "Fishmonger"], "3": ["Supermarket"], ... }
            const plans = data.plans || {};

            let gridHtml = '';
            SHOPS.forEach(shop => {
                const safeShop = shop.replace(/'/g, "\\'");
                gridHtml += `<div class="food-toggle-row"><span class="food-shop-label">${shop}</span><div class="day-btn-group">`;
                DAYS.forEach((d, dayIdx) => {
                    const active = (plans[dayIdx] || []).includes(shop) ? 'active' : '';
                    gridHtml += `<span class="day-btn ${active}" onclick="toggleFoodShop(${dayIdx}, '${safeShop}', !this.classList.contains('active'))">${d.charAt(0)}</span>`;
                });
                gridHtml += '</div></div>';
            });


            // Show scheduled blocks
            let schedHtml = '';
            Object.keys(plans).sort().forEach(dayIdx => {
                const shops = plans[dayIdx];
                if (shops.length > 0) {
                    const blockDate = new Date(WEEK_START + 'T00:00:00');
                    blockDate.setDate(blockDate.getDate() + parseInt(dayIdx));
                    const dayName = DAYS[parseInt(dayIdx)];
                    schedHtml += `<div class="food-sched-row"><span class="sched-day">${dayName}</span> <span>${shops.join(', ')}</span></div>`;
                }
            });
            if (!schedHtml) schedHtml = '<p class="no-data">No shopping planned</p>';

            container.innerHTML = `
                <div class="insights-grid">
                    <div class="insight-card">
                        <h5>Plan</h5>
                        ${gridHtml}
                    </div>
                    <div class="insight-card">
                        <h5>This Week</h5>
                        ${schedHtml}
                    </div>
                </div>`;
        });
}

function toggleFoodShop(dayIdx, shop, checked) {
    fetch('/api/food-shopping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            week_start: WEEK_START,
            day_index: dayIdx,
            shop: shop,
            checked: checked,
        }),
    })
    .then(r => r.json())
    .then(() => {
        loadFoodPanel();
        if (calendar) calendar.refetchEvents();
    });
}

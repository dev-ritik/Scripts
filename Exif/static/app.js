// static/app.js

let FILES = [];
let SELECTED = new Set();
let MAPS = [];
let MAP_MODE = "card"; // "card" | "global"

function getPathFromURL() {
    const params = new URLSearchParams(window.location.search);
    return params.get("path");
}

function setPathInURL(path) {
    const params = new URLSearchParams(window.location.search);
    params.set("path", path);

    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.pushState({}, "", newUrl);
}

function parseGPS(gpsStr) {
    if (!gpsStr) return null;

    const parts = gpsStr.split(",").map(s => parseFloat(s.trim()));
    if (parts.length !== 2 || parts.some(isNaN)) return null;

    return parts; // [lat, lon]
}

function openGlobalMapEditor() {
    MAP_MODE = "global";
    ACTIVE_PATH = null;

    const modal = document.getElementById("map-modal");
    modal.classList.remove("hidden");

    setTimeout(() => {
        initEditorMapForGlobal();
    }, 50);
}

function updateGlobalGPS(lat, lon) {
    const input = document.getElementById("bulk-gps");
    input.value = `${lat.toFixed(6)},${lon.toFixed(6)}`;
}

function initEditorMapForGlobal() {
    const container = document.getElementById("map-container");

    EDIT_MAP = L.map(container).setView([20, 77], 5);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png')
        .addTo(EDIT_MAP);

    const gpsInput = document.getElementById("bulk-gps").value;

    if (gpsInput) {
        const [lat, lon] = gpsInput.split(',').map(Number);

        EDIT_MAP.setView([lat, lon], 12);
        EDIT_MARKER = L.marker([lat, lon]).addTo(EDIT_MAP);
    }

    EDIT_MAP.on('click', function (e) {
        const {lat, lng} = e.latlng;

        if (EDIT_MARKER) {
            EDIT_MARKER.setLatLng([lat, lng]);
        } else {
            EDIT_MARKER = L.marker([lat, lng]).addTo(EDIT_MAP);
        }

        updateGlobalGPS(lat, lng);
    });

    setTimeout(() => EDIT_MAP.invalidateSize(), 100);
}

function getFilters() {
    return {
        noGps: document.getElementById("filter-no-gps").checked,
        noDate: document.getElementById("filter-no-date").checked,
        notProcessed: document.getElementById("filter-not-processed").checked,
    };
}

async function load(auto = false) {
    const folderInput = document.getElementById("folder");
    const folder = folderInput.value;

    if (!auto) {
        setPathInURL(folder);
    }

    // 🔥 show progress bar
    const bar = document.getElementById("load-progress-bar");
    const fill = document.getElementById("load-progress-fill");

    bar.style.display = "block";
    fill.style.width = "5%";

    // fake smooth progress while waiting
    let progress = 5;
    const interval = setInterval(() => {
        progress = Math.min(progress + Math.random() * 10, 90);
        fill.style.width = progress + "%";
    }, 200);

    const params = new URLSearchParams({
        targets: JSON.stringify([folder])
    });

    const res = await fetch(`/load?${params.toString()}`, {
        method: "GET"
    });

    FILES = await res.json();

    clearInterval(interval);
    fill.style.width = "100%";

    setTimeout(() => {
        bar.style.display = "none";
        fill.style.width = "0%";
    }, 300);

    render();
}

function selectAll() {
    SELECTED.clear();

    FILES.forEach(f => SELECTED.add(f.path));

    document.querySelectorAll(".row").forEach(row => {
        row.classList.add("selected");
        const cb = row.querySelector(".select-box");
        if (cb) cb.checked = true;
    });

    updateSelectionUI();
}

function clearSelection() {
    SELECTED.clear();

    document.querySelectorAll(".row").forEach(row => {
        row.classList.remove("selected");
        const cb = row.querySelector(".select-box");
        if (cb) cb.checked = false;
    });

    updateSelectionUI();
}

function updateSelectionUI() {
    document.getElementById("selection-count").innerText =
        `${SELECTED.size} selected`;
}

function toggleSelection(path, row) {
    const checkbox = row.querySelector(".select-box");

    if (SELECTED.has(path)) {
        SELECTED.delete(path);
        row.classList.remove("selected");
        checkbox.checked = false;
    } else {
        SELECTED.add(path);
        row.classList.add("selected");
        checkbox.checked = true;
    }

    updateSelectionUI();
}

function formatForInput(dateStr) {
    if (!dateStr) return "";

    const parts = dateStr.split(" ");
    if (parts.length !== 2) return "";

    const date = parts[0].replace(/:/g, "-");

    // keep full HH:MM:SS
    const time = parts[1];

    return `${date}T${time}`;
}

function formatForBackend(inputVal) {
    if (!inputVal) return null;

    const [date, time] = inputVal.split("T");

    // ensure seconds exist
    let fullTime = time;
    if (time.length === 5) {
        fullTime = time + ":00";  // HH:MM → HH:MM:SS
    }

    return `${date.replace(/-/g, ":")} ${fullTime}`;
}

function createRow(f, idx) {
    // console.log(f);
    const row = document.createElement("div");
    row.className = "row";

    row.setAttribute("data-path", f.path);
    row.onclick = (e) => {
        // prevent double toggle when clicking checkbox itself
        if (e.target.classList.contains("select-box")) return;

        toggleSelection(f.path, row);
    };

    const formattedDate = formatForInput(f.date);

    row.innerHTML = `
        <input type="checkbox" class="select-box">
        <img class="preview" src="/thumbnail?path=${encodeURIComponent(f.path)}">
        
        <div class="meta">
            <div><b>${f.path.split('/').pop()}</b></div>
                        
            Date:
            <div class="input-wrapper">
                <input type="datetime-local"
                       value="${formattedDate}"
                       class="date ${f.processed_date ? 'processed' : ''}"
                       step="1">
                ${f.processed_date ? '<span class="badge">✓</span>' : ''}
            </div>
            
            GPS:
            <div class="input-wrapper">
                <input value="${f.gps || ''}"
                       class="gps ${f.processed_gps ? 'processed' : ''}">
                ${f.processed_gps ? '<span class="badge">✓</span>' : ''}
            </div>
            
            <button onclick="openMapEditor('${f.path}')">📍 Edit Map</button>
        </div>
        
        <div id="map-${idx}" class="map"></div>
    `;

    const checkbox = row.querySelector(".select-box");

    checkbox.onclick = (e) => {
        e.stopPropagation();
        toggleSelection(f.path, row);
    };

    return row;
}

function render() {
    const list = document.getElementById("list");
    list.innerHTML = "";
    MAPS = [];

    const filters = getFilters();

    const filtered = FILES.filter(f => {
        if (!f.processed_by_us) {
            console.log("not processed by us");
        }
        // console.log(filters.noGps && f.gps);
        // console.log(filters.notProcessed && f.processed_by_us);
        if (filters.noGps && f.gps) return false;
        if (filters.noDate && f.date) return false;
        if (filters.notProcessed && f.processed_by_us) return false;
        return true;
    });

    filtered.forEach((f, idx) => {
        const row = createRow(f, idx); // assuming you split this
        list.appendChild(row);

        // Initialize map after DOM insert
        requestAnimationFrame(() => initMap(idx, f.gps));
    });
    document.getElementById("filter-count").innerText =
        `${filtered.length} / ${FILES.length}`;
}

function initMap(idx, gps) {
    const el = document.getElementById(`map-${idx}`);
    if (!el) return;

    const map = L.map(el, {
        zoomControl: false,
        attributionControl: false
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png')
        .addTo(map);

    if (gps) {
        const [lat, lon] = gps.split(',').map(Number);

        const latDelta = 5 / 111;
        const lonDelta = 5 / (111 * Math.cos(lat * Math.PI / 180));

        const bounds = [
            [lat - latDelta / 2, lon - lonDelta / 2],
            [lat + latDelta / 2, lon + lonDelta / 2]
        ];

        map.fitBounds(bounds);

        L.marker([lat, lon]).addTo(map);
    } else {
        map.setView([20, 77], 2);
    }

    // 🔥 CRITICAL FIX
    setTimeout(() => {
        map.invalidateSize();
    }, 100);

    MAPS.push(map);
}

function getOptions() {
    return {
        dry_run: document.getElementById("dry-run").checked,
        rewrite: document.getElementById("rewrite").checked,
        force: document.getElementById("force").checked,
        skip_existing: document.getElementById("skip-existing").checked,
    };
}

function applyChanges() {
    const bulkDateRaw = document.getElementById("bulk-date").value;
    const bulkGPSRaw = document.getElementById("bulk-gps").value;

    const bulkDate = formatForBackend(bulkDateRaw);
    const bulkGPS = parseGPS(bulkGPSRaw);

    const guessEnabled = document.getElementById("guess-date-toggle").checked;

    if (SELECTED.size === 0) return alert("No files selected");

    const updates = FILES
        .filter(f => SELECTED.has(f.path))
        .map(f => {
            const row = document.querySelector(`[data-path="${f.path}"]`);

            const individualDateRaw = row.querySelector(".date").value;
            const individualGPSRaw = row.querySelector(".gps").value;

            const individualDate = formatForBackend(individualDateRaw);

            // 🔥 suggested datetime logic
            const suggested =
                bulkDate || individualDate || null;

            return {
                path: f.path,
                date: bulkDate || individualDate,
                gps: bulkGPS || parseGPS(individualGPSRaw),
            };
        });

    fetch("/update", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            items: updates,
            options: {
                ...getOptions(),
                guess_date: guessEnabled
            }
        })
    });

    trackProgress();
}

let ACTIVE_PATH = null;
let EDIT_MAP = null;
let EDIT_MARKER = null;

function updateGPSForActive(lat, lon) {
    const row = document.querySelector(`[data-path="${ACTIVE_PATH}"]`);
    const gpsInput = row.querySelector(".gps");

    gpsInput.value = `${lat.toFixed(6)},${lon.toFixed(6)}`;
}

function initEditorMap(path) {
    const container = document.getElementById("map-container");

    EDIT_MAP = L.map(container).setView([20, 77], 5);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png')
        .addTo(EDIT_MAP);

    const row = document.querySelector(`[data-path="${path}"]`);
    const gpsInput = row.querySelector(".gps").value;

    if (gpsInput) {
        const [lat, lon] = gpsInput.split(',').map(Number);

        EDIT_MAP.setView([lat, lon], 13);
        EDIT_MARKER = L.marker([lat, lon]).addTo(EDIT_MAP);
    }

    // 🔥 Click to update GPS
    EDIT_MAP.on('click', function (e) {
        const {lat, lng} = e.latlng;

        if (EDIT_MARKER) {
            EDIT_MARKER.setLatLng([lat, lng]);
        } else {
            EDIT_MARKER = L.marker([lat, lng]).addTo(EDIT_MAP);
        }

        updateGPSForActive(lat, lng);
    });

    setTimeout(() => EDIT_MAP.invalidateSize(), 100);
}

function openMapEditor(path) {
    MAP_MODE = "card";
    ACTIVE_PATH = path;

    const modal = document.getElementById("map-modal");
    modal.classList.remove("hidden");

    setTimeout(() => {
        initEditorMap(path);
    }, 50);
}

function closeMapEditor() {
    document.getElementById("map-modal").classList.add("hidden");

    if (EDIT_MAP) {
        EDIT_MAP.remove();
        EDIT_MAP = null;
        EDIT_MARKER = null;
    }

    MAP_MODE = "card";
    ACTIVE_PATH = null;
}

function trackProgress() {
    const interval = setInterval(async () => {
        const res = await fetch("/progress");
        const p = await res.json();

        if (p.total === 0) return;

        const percent = (p.done / p.total) * 100;
        document.getElementById("load-progress-fill").style.width = percent + "%";

        console.log(`Progress: ${percent.toFixed(2)}%`);
        console.log(`Done ${p.done} files out of ${p.total} total`)
        if (p.done >= p.total) {
            clearInterval(interval);
            alert("Done! May be refresh the page to see the changes");
        }
    }, 800);
}

function loadPageFromURL() {
    const path = getPathFromURL();
    if (path) {
        document.getElementById("folder").value = path;
        load();  // 🔥 auto load without rewriting URL
    }
}

window.onload = () => {
    loadPageFromURL();

    document.querySelectorAll("#filters input").forEach(el => {
        el.addEventListener("change", () => {
            render();
        });
    });
};

window.onpopstate = () => {
    loadPageFromURL();
};
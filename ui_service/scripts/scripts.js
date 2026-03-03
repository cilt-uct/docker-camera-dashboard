// =====================================================
// GLOBAL STATE
// =====================================================
const state = {
    cardMap: new Map(),
    activeCamFilter: "all",
    activeCaFilter: "all",
    activityData: null,
    camData: null
};

// =====================================================
// UTILITIES
// =====================================================
function normalizeName(name) {
    return (name || "").toLowerCase().replace(".local", "").replace(".capture", "").trim();
}

function normalizeAgentStatus(raw) {
    if (!raw) return "unknown";
    const s = raw.toUpperCase();
    if (s.includes("OFFLINE")) return "offline";
    if (s.includes("IDLE")) return "idle";
    if (s.includes("CAPTURING")) return "capturing";
    if (s.includes("ERROR")) return "error";
    return "unknown";
}

function setCount(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function formatLastUpdated(secondsAgo) {
    return moment().subtract(secondsAgo, 'seconds').fromNow();
}

function extractTimestamp(filename) {
    const match = filename.match(/(\d{10})\.jpg$/i);
    return match ? parseInt(match[1], 10) : 0;
}

function toInputFormat(date) {
    return date.toISOString().slice(0, 16);
}

// =====================================================
// MASTER FETCH + RENDER
// =====================================================
async function refreshCameras() {
    try {
        const [camRes, agentRes, activityRes, fullNameRes] = await Promise.all([
            fetch("/cams/opencast/cameras"),
            fetch("/cams/api/capture-agents-status"),
            fetch("/cams/activity"),
            fetch("/cams/api/ca-full-info")
        ]);

        state.camData = await camRes.json();
        const agentData = await agentRes.json();
        state.activityData = await activityRes.json();
        const fullNamesMap = (await fullNameRes.json())?.cameras || {};

        const agentListRaw = state.camData?.cameras?.agents?.agent || {};
        const agentArray = Array.isArray(agentListRaw) ? agentListRaw : Object.values(agentListRaw);

        const cameraMap = new Map();
        agentArray.forEach(agent => {
            const name = normalizeName(agent.name);
            cameraMap.set(name, {
                name: agent.name,
                full_name: fullNamesMap[agent.name] || agent.name,
                camera_status: "offline",
                capture_status: "unknown",
                last_update: agent["time-since-last-update"] || 0
            });
        });

        (state.activityData.active || []).forEach(n => {
            const name = normalizeName(n);
            if (cameraMap.has(name)) cameraMap.get(name).camera_status = "online";
        });
        (state.activityData.inactive || []).forEach(n => {
            const name = normalizeName(n);
            if (cameraMap.has(name)) cameraMap.get(name).camera_status = "offline";
        });

        (agentData?.capture_agent_status?.results || []).forEach(agent => {
            const rawName = agent.Name || agent.name || agent.agent_name || agent.id;
            const name = normalizeName(rawName);
            const status = normalizeAgentStatus(agent.Status || agent.status);
            if (cameraMap.has(name)) cameraMap.get(name).capture_status = status;
        });

        renderCameras(Array.from(cameraMap.values()));
        updateCameraCountersFromAPI(state.activityData);
        updateCACounters();
    } catch (err) {
        console.error("refreshCameras failed:", err);
    }
}

// =====================================================
// COUNTERS
// =====================================================
function updateCameraCountersFromAPI(activityData) {
    if (!activityData) return;
    setCount("count-all", (activityData.active_count || 0) + (activityData.inactive_count || 0));
    setCount("count-active", activityData.active_count || 0);
    setCount("count-cam-inactive", activityData.inactive_count || 0);
}

function updateCACounters() {
    const counts = { capturing: 0, idle: 0, error: 0, unknown: 0, offline: 0, total: 0 };
    state.cardMap.forEach(card => {
        counts.total++;
        const caStatus = (card.root?.dataset?.caStatus || "unknown").toLowerCase();
        if (caStatus in counts) counts[caStatus]++;
    });
    setCount("count-all-cas", counts.total);
    setCount("count-ca-capturing", counts.capturing);
    setCount("count-ca-idle", counts.idle);
    setCount("count-ca-error", counts.error);
    setCount("count-ca-unknown", counts.unknown);
    setCount("count-ca-offline", counts.offline);
}

// =====================================================
// RENDER CAMERAS
// =====================================================
function renderCameras(cameras) {
    const grid = document.getElementById("cameraGrid");
    if (!grid || !Array.isArray(cameras)) return;

    grid.innerHTML = "";
    state.cardMap.clear();

    cameras.forEach(camera => {
        const normalizedName = normalizeName(camera.name);
        const col = document.createElement("div");
        col.className = "col-xl-3 col-lg-4 col-md-6 col-sm-12 camera-col";

        const camStatusLower = camera.camera_status.toLowerCase();
        const caStatusLower = camera.capture_status.toLowerCase();
        console.log(`All camera data for ${camera}`);
        col.innerHTML = `
        <div class="card camera-card shadow-sm w-100 camera-item"
             data-cam-status="${camStatusLower}"
             data-ca-status="${caStatusLower}"
             data-name="${normalizedName}"
             data-fullname="${camera.full_name.toLowerCase()}">

            <div class="camera-image-wrapper"
                 data-name="${camera.name}"
                 data-images='${JSON.stringify(camera.images || [])}'>

                <img src="/cams/static/images/${camera.name}_thumb.jpg"
                     class="camera-thumb"
                     alt="${camera.name}"
                     onerror="this.onerror=null;this.src='/cams/resources/images/image_not_found_uct.png';">

                <video class="camera-hover-video" muted loop playsinline preload="metadata" style="display:none;"></video>
            </div>

            <div class="card-body d-flex flex-column">
                <div class="row gx-2 align-items-start">
                    <div class="col-8">
                        <h5 class="card-title mb-1 text-break">${camera.name}</h5>
                        <div class="text-muted small text-break">${camera.full_name}</div>
                    </div>
                    <div class="col-4 text-end small">
                        <div class="row">
                            <div class="status-line camera-status-${camStatusLower} mb-1">
                                <i class="fa-solid fa-video"></i> <span>${camera.camera_status}</span>
                            </div>
                        </div>
                        <div class="row">
                            <div class="status-line status-${caStatusLower} mt-1">
                                <i class="fa-solid fa-server"></i> <span>${camera.capture_status}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        `;

        grid.appendChild(col);
        state.cardMap.set(normalizedName, {
            root: col.querySelector(".camera-item"),
            col,
            images: []
        });
    });

    setupHoverVideo();
    attachCardModals();
    applyFilters();
    updateActiveButtons();
    console.log(`Rendered ${cameras.length} cameras`);
}

// =====================================================
// FILTERING
// =====================================================
function applyFilters() {
    let visible = 0;

    state.cardMap.forEach((card, name) => {
        const cam = (card.root.dataset.camStatus || "offline").toLowerCase();
        const ca = (card.root.dataset.caStatus || "unknown").toLowerCase();

        const camOk = state.activeCamFilter === "all" || cam === state.activeCamFilter;
        const caOk = state.activeCaFilter === "all" || ca === state.activeCaFilter;

        const show = camOk && caOk;

        card.col.classList.toggle("hidden", !show);

        if (show) visible++;
    });

    console.log(`Visible cards after filter: ${visible} / ${state.cardMap.size}`);
}

function updateActiveButtons() {
    document.querySelectorAll(".filter-btn").forEach(btn => {
        btn.classList.remove("active");

        const type = btn.dataset.type;
        const value = (btn.dataset.status || btn.dataset.value || "all").toLowerCase();

        let filterType = type;
        if (type === "camera") filterType = "cam";

        const isActive =
            (filterType === "cam" && state.activeCamFilter === value) ||
            (filterType === "ca" && state.activeCaFilter === value);

        if (isActive) btn.classList.add("active");
    });
}

document.addEventListener("click", e => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;

    const type = btn.dataset.type;
    const value = (btn.dataset.status || btn.dataset.value || "all").toLowerCase();

    let filterType = type;
    if (type === "camera") filterType = "cam";

    if (!["cam", "ca"].includes(filterType)) return;

    if (filterType === "cam") {
        state.activeCamFilter = (state.activeCamFilter === value) ? "all" : value;
    } else {
        state.activeCaFilter = (state.activeCaFilter === value) ? "all" : value;
    }

    updateActiveButtons();
    applyFilters();
});

// =====================================================
// HOVER VIDEO
// =====================================================
function setupHoverVideo() {
    state.cardMap.forEach(card => {
        const wrapper = card.root.querySelector(".camera-image-wrapper");
        const video = card.root.querySelector(".camera-hover-video");
        const thumb = card.root.querySelector(".camera-thumb");
        if (!wrapper || !video) return;

        wrapper.addEventListener("mouseenter", () => {
            thumb.style.display = "none";
            video.src = `/cams/static/timelapse/camera_${wrapper.dataset.name}.webm`;
            video.style.display = "block";
            video.currentTime = 0;
            video.play().catch(() => { });
        });

        wrapper.addEventListener("mouseleave", () => {
            video.pause();
            video.currentTime = 0;
            video.style.display = "none";
            thumb.style.display = "block";
        });
    });
}

// Cam modal
function attachCardModals() {
    state.cardMap.forEach(card => {
        const wrapper = card.root.querySelector(".camera-image-wrapper");
        if (!wrapper) return;

        wrapper.addEventListener("click", () => {
            const cameraName = wrapper.dataset.name;
            const fullName = wrapper.dataset.fullname || cameraName;
            console.log(`Modal opened for: ${cameraName}`);

            let filenames = [];
            try {
                filenames = JSON.parse(wrapper.dataset.images || "[]");
                console.log(`Loaded ${filenames.length} real images from data-images`);
            } catch (e) {
                console.warn("Invalid data-images JSON:", e);
            }

            // If no real images → guess only the latest 20 possible (5-min steps from now)
            if (filenames.length === 0) {
                console.warn(`No real images — guessing latest 20 (5-min steps)`);

                const nowUnix = Math.floor(Date.now() / 1000);
                const step = 300; // 5 minutes

                filenames = [];
                let count = 0;
                for (let ts = nowUnix; ts >= nowUnix - (24 * 3600) && count < 20; ts -= step) {
                    filenames.push(`${ts}.jpg`);
                    count++;
                }

                console.log(`Guessed latest ${filenames.length} filenames`);
            }

            // Use correct base path — change if your folder is different
            const base = `/cams/static/images/camera_${cameraName}/`;
            // const base = `/cams/static/images/${cameraName}/`; // alternative

            const paths = filenames.map(f => base + f)
                .sort((a, b) => extractTimestamp(b) - extractTimestamp(a));

            openCameraModalWithRange(fullName, paths, cameraName);
        });
    });
}

function openCameraModalWithRange(title, allImagePaths = [], cameraName) {
    const modalEl = document.getElementById("cameraModal");
    if (!modalEl) return;

    const modal = new bootstrap.Modal(modalEl);

    const titleEl = document.getElementById("cameraModalTitle");
    const mainImg = document.getElementById("modalMainImage");
    const thumbs = document.getElementById("modalThumbs");
    const fromInput = document.getElementById("fromDate");
    const toInput = document.getElementById("toDate");
    const applyBtn = document.getElementById("applyRange");

    if (!titleEl || !mainImg || !thumbs || !fromInput || !toInput || !applyBtn) return;

    titleEl.textContent = `${title} – Images (${allImagePaths.length} candidates)`;

    // Default: midnight today → now
    const now = new Date();
    const todayStart = new Date(now);
    todayStart.setHours(0, 0, 0, 0);

    fromInput.value = toInputFormat(todayStart);
    toInput.value = toInputFormat(now);

    fromInput.min = toInput.min = toInputFormat(todayStart);
    fromInput.max = toInput.max = toInputFormat(now);

    let currentImages = allImagePaths.slice();

    // Cache the thumbnail path once
    const thumbnailPath = `/cams/static/images/${cameraName}_thumb.jpg`;

    function renderThumbs(filtered) {
        thumbs.innerHTML = "";

        if (!filtered.length) {
            // No images in range → show thumbnail as main image (large)
            mainImg.src = thumbnailPath;
            mainImg.style.maxWidth = "80%";
            mainImg.style.height = "auto";
            mainImg.style.borderRadius = "8px";
            mainImg.style.boxShadow = "0 4px 12px rgba(0,0,0,0.3)";
            mainImg.onerror = () => {
                mainImg.src = '/cams/resources/images/image_not_found_uct.png';
                mainImg.style.maxWidth = "60%"; // smaller fallback
            };

            thumbs.innerHTML = '<p class="text-muted text-center mt-4">No recent images found — showing latest thumbnail</p>';
            return;
        }

        // Normal case: show newest image as main
        mainImg.src = filtered[0];
        mainImg.style.maxWidth = "";
        mainImg.style.height = "";
        mainImg.style.borderRadius = "";
        mainImg.style.boxShadow = "";
        mainImg.onerror = () => mainImg.src = '/cams/resources/images/image_not_found_uct.png';

        filtered.forEach(src => {
            const img = document.createElement("img");
            img.src = src;
            img.className = "rounded shadow-sm";
            img.style.width = "140px";
            img.style.cursor = "pointer";
            img.loading = "lazy";
            img.addEventListener("click", () => mainImg.src = src);
            thumbs.appendChild(img);
        });
    }

    function applyFilter() {
        if (!fromInput.value || !toInput.value) return;

        const fromTs = Math.floor(new Date(fromInput.value).getTime() / 1000);
        const toTs = Math.floor(new Date(toInput.value).getTime() / 1000);

        const filtered = currentImages.filter(src => {
            const ts = extractTimestamp(src);
            return ts >= fromTs && ts <= toTs;
        });

        renderThumbs(filtered);
    }

    applyBtn.onclick = applyFilter;
    fromInput.onchange = applyFilter;
    toInput.onchange = applyFilter;

    applyFilter();  // initial render
    modal.show();
}

// load and refresh after 5 mins
document.addEventListener("DOMContentLoaded", () => {
    console.log("Page loaded → starting refreshCameras()");
    refreshCameras();

    // Auto-refresh every 5 minutes
    setInterval(() => {
        refreshCameras();
    }, 5 * 60 * 1000);
});
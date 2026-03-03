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

// =====================================================
// MASTER FETCH + RENDER – Use /cams/activity as source of truth
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

        // Use activity data as source of truth for which cameras exist and their status
        const activeNames = state.activityData.active || [];
        const inactiveNames = state.activityData.inactive || [];

        const allCameraNames = [...new Set([...activeNames, ...inactiveNames])];

        const cameraMap = new Map();

        allCameraNames.forEach(name => {
            const normalized = normalizeName(name);
            const agent = state.camData?.cameras?.agents?.agent?.find(a => normalizeName(a.name) === normalized) || {};
            cameraMap.set(normalized, {
                name: name,
                full_name: fullNamesMap[name] || name,
                camera_status: activeNames.includes(name) ? "online" : "offline",
                capture_status: "unknown",
                last_update: agent["time-since-last-update"] || 0
            });
        });

        // Enrich with capture agent status
        (agentData?.capture_agent_status?.results || []).forEach(agent => {
            const rawName = agent.Name || agent.name || agent.agent_name || agent.id;
            const name = normalizeName(rawName);
            const status = normalizeAgentStatus(agent.Status || agent.status);
            if (cameraMap.has(name)) cameraMap.get(name).capture_status = status;
        });

        renderCameras(Array.from(cameraMap.values()));
        updateCameraCountersFromAPI(state.activityData);
        updateCACounters(agentData);
    } catch (err) {
        console.error("refreshCameras failed:", err);
    }
}

// cam counts - /cams/activity
function updateCameraCountersFromAPI(activityData) {
    if (!activityData) return;
    setCount("count-all", (activityData.active_count || 0) + (activityData.inactive_count || 0));
    setCount("count-active", activityData.active_count || 0);
    setCount("count-cam-inactive", activityData.inactive_count || 0);
}

// capture agent counts - /cams/api/capture-agents-status
function updateCACounters(agentData) {

    const results = agentData?.capture_agent_status?.results || [];

    const counts = {
        capturing: 0,
        idle: 0,
        error: 0,
        unknown: 0,
        offline: 0,
        total: results.length || 0  // ← use real total from API
    };

    results.forEach(agent => {
        const status = normalizeAgentStatus(agent.Status || agent.status);
        if (status in counts) counts[status]++;
    });

    setCount("count-all-cas", counts.total);
    setCount("count-ca-capturing", counts.capturing);
    setCount("count-ca-idle", counts.idle);
    setCount("count-ca-error", counts.error);
    setCount("count-ca-unknown", counts.unknown);
    setCount("count-ca-offline", counts.offline);

    console.log("CA counters updated from API:", counts);
}

// display cameras based, no webm over image
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

        col.innerHTML = `
        <div class="card camera-card shadow-sm w-100 camera-item"
             data-cam-status="${camStatusLower}"
             data-ca-status="${caStatusLower}"
             data-name="${normalizedName}"
             data-fullname="${camera.full_name.toLowerCase()}">

            <div class="camera-image-wrapper"
                 data-name="${camera.name}"
                 data-images='${JSON.stringify(camera.images || [])}'>

                <!-- Static thumbnail only -->
                <img src="/cams/static/images/${camera.name}_thumb.jpg"
                     class="camera-thumb img-fluid w-100"
                     alt="${camera.name}"
                     onerror="this.src='/cams/resources/images/image_not_found_uct.png';">
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

    attachCardModals();
    applyFilters();
    updateActiveButtons();
    console.log(`Rendered ${cameras.length} cameras`);
}

// filtering TODO: add search filter
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

    // console.log(`Visible cards after filter: ${visible} / ${state.cardMap.size}`);
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
    if (btn) {
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
    }
});

// camera modals
function attachCardModals() {
    console.log("Attaching modal listeners (delegation)");
    document.addEventListener("click", e => {
        const wrapper = e.target.closest(".camera-image-wrapper");
        if (!wrapper) return;

        const cameraName = wrapper.dataset.name;
        const fullName = wrapper.dataset.fullname || cameraName || "Camera";
        // console.log(`Modal click detected for: ${cameraName}`);

        openCameraModalWithRange(fullName, cameraName);
    });
}

function openCameraModalWithRange(title, cameraName) {
    const modalEl = document.getElementById("cameraModal");
    if (!modalEl) {
        console.error("Modal #cameraModal not found");
        return;
    }

    const modal = new bootstrap.Modal(modalEl);

    const titleEl = document.getElementById("cameraModalTitle");
    const mainImg = document.getElementById("modalMainImage");
    const thumbs = document.getElementById("modalThumbs");

    if (!titleEl || !mainImg || !thumbs) {
        console.error("Missing modal elements");
        return;
    }

    titleEl.textContent = title;

    // Cache paths
    const thumbnailPath = `/cams/static/images/${cameraName}_thumb.jpg`;
    const webmPath = `/cams/static/timelapse/camera_${cameraName}.webm`;

    // Clear thumbs area (no thumbnails)
    thumbs.innerHTML = "";

    // Create / reuse large video player
    let modalVideo = document.getElementById("modalVideo");
    if (!modalVideo) {
        modalVideo = document.createElement("video");
        modalVideo.id = "modalVideo";
        modalVideo.className = "w-100 rounded shadow mt-3";
        modalVideo.muted = true;
        modalVideo.controls = true;
        modalVideo.loop = false; // no loop as requested
        modalVideo.innerHTML = `<source src="${webmPath}" type="video/webm">Your browser does not support video.`;
        mainImg.after(modalVideo);
    } else {
        // Update source if camera changed
        const source = modalVideo.querySelector("source");
        if (source) source.src = webmPath;
        modalVideo.load();
    }

    // Hide static image, show video
    mainImg.style.display = "none";
    modalVideo.style.display = "block";

    // Try to play webm
    modalVideo.currentTime = 0;
    modalVideo.play().catch(e => {
        console.log("WebM play failed:", e);
        // Fallback to large thumbnail
        modalVideo.style.display = "none";
        mainImg.src = thumbnailPath;
        mainImg.style.display = "block";
        mainImg.style.Width = "100%";
        mainImg.style.height = "auto";
        mainImg.onerror = () => {
            mainImg.src = '/cams/resources/images/image_not_found_uct.png';
        };
    });

    // Video error fallback
    modalVideo.onerror = () => {
        console.warn("WebM failed to load for", cameraName);
        modalVideo.style.display = "none";
        mainImg.src = thumbnailPath;
        mainImg.style.display = "block";
        mainImg.style.maxWidth = "90%";
        mainImg.style.height = "auto";
        mainImg.onerror = () => mainImg.src = '/cams/resources/images/image_not_found_uct.png';
    };

    modal.show();
}

// =====================================================
// INITIAL LOAD + AUTO REFRESH
// =====================================================
let isRefreshing = false;

document.addEventListener("DOMContentLoaded", () => {
    console.log("Page loaded → starting refreshCameras()");
    refreshCameras();

    // Auto-refresh every 5 minutes
    setInterval(async () => {
        if (isRefreshing) return;
        isRefreshing = true;
        try {
            console.log("Auto-refreshing...");
            const grid = document.getElementById("cameraGrid");
            if (grid) {
                grid.innerHTML = '<div class="text-center p-5"><div class="spinner-border text-primary" role="status"></div><p>Updating cameras...</p></div>';
            }
            await refreshCameras();
        } catch (err) {
            console.error("Auto-refresh failed:", err);
        } finally {
            isRefreshing = false;
        }
    }, 5 * 60 * 1000);
});
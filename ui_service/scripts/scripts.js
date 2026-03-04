// =====================================================
// GLOBAL STATE – Separated for clarity
// =====================================================
const state = {
    cameraMap: new Map(),             // only cameras with DOM refs
    agentMap: new Map(),              // only agents with DOM refs
    activeCamFilter: "all",
    activeCaFilter: "all",
    activityData: null,
    camData: null,
    agentData: null,
    currentView: "cameras"            // "cameras" or "agents"
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

// =====================================================
// VIEW TOGGLE & INITIAL SETUP
// =====================================================
document.addEventListener("DOMContentLoaded", () => {
    const viewCamerasBtn = document.getElementById("viewCamerasBtn");
    const viewAgentsBtn = document.getElementById("viewAgentsBtn");
    const cameraFilters = document.getElementById("cameraFilters");
    const caFilters = document.getElementById("caFilters");

    if (viewCamerasBtn) {
        viewCamerasBtn.addEventListener("click", () => {
            state.currentView = "cameras";
            viewCamerasBtn.classList.add("active");
            viewAgentsBtn?.classList.remove("active");
            cameraFilters.style.display = "block";
            caFilters.style.display = "none";
            renderCameras();
        });
    }

    if (viewAgentsBtn) {
        viewAgentsBtn.addEventListener("click", () => {
            state.currentView = "agents";
            viewAgentsBtn.classList.add("active");
            viewCamerasBtn?.classList.remove("active");
            caFilters.style.display = "block";
            cameraFilters.style.display = "none";
            renderAgents();
        });
    }

    console.log("Page loaded → starting refreshData()");
    refreshData();

    // Auto-refresh every 5 minutes
    setInterval(async () => {
        if (state.isRefreshing) return;
        state.isRefreshing = true;
        try {
            console.log("Auto-refreshing...");
            const grid = document.getElementById("cameraGrid");
            if (grid) grid.innerHTML = '<div class="text-center p-5"><div class="spinner-border text-primary" role="status"></div><p>Updating...</p></div>';
            await refreshData();
        } catch (err) {
            console.error("Auto-refresh failed:", err);
        } finally {
            state.isRefreshing = false;
        }
    }, 5 * 60 * 1000);
});

// =====================================================
// DATA REFRESH
// =====================================================
async function refreshData() {
    try {
        const [camRes, agentRes, activityRes, fullNameRes] = await Promise.all([
            fetch("/cams/opencast/cameras"),
            fetch("/cams/api/capture-agents-status"),
            fetch("/cams/activity"),
            fetch("/cams/api/ca-full-info")
        ]);

        state.camData = await camRes.json();
        state.agentData = await agentRes.json();
        state.activityData = await activityRes.json();
        const fullNamesMap = (await fullNameRes.json())?.cameras || {};

        // ── Process CAMERAS only ─────────────────────────────
        const activeNames = state.activityData.active || [];
        const inactiveNames = state.activityData.inactive || [];
        const allCameraNames = [...new Set([...activeNames, ...inactiveNames])];

        state.cameraMap.clear();

        allCameraNames.forEach(name => {
            const normalized = normalizeName(name);
            const agent = state.camData?.cameras?.agents?.agent?.find(a => normalizeName(a.name) === normalized) || {};
            state.cameraMap.set(normalized, {
                name: name,
                full_name: fullNamesMap[name] || name,
                camera_status: activeNames.includes(name) ? "online" : "offline",
                capture_status: "unknown",
                last_update: agent["time-since-last-update"] || 0
            });
        });

        // Enrich camera capture status
        (state.agentData?.capture_agent_status?.results || []).forEach(agent => {
            const rawName = agent.Name || agent.name || agent.agent_name || agent.id;
            const name = normalizeName(rawName);
            const status = normalizeAgentStatus(agent.Status || agent.status);
            if (state.cameraMap.has(name)) {
                state.cameraMap.get(name).capture_status = status;
            }
        });

        // ── Process AGENTS only ───────────────────────────────
        state.agentMap.clear();

        (state.agentData?.capture_agent_status?.results || []).forEach(agent => {
            const rawName = agent.Name || agent.name || agent.agent_name || agent.id;
            const name = normalizeName(rawName);
            state.agentMap.set(name, {
                name: rawName,
                full_name: rawName,
                capture_status: normalizeAgentStatus(agent.Status || agent.status),
                last_update: 0
            });
        });

        // Update counters
        updateCameraCountersFromAPI(state.activityData);
        updateCACounters(state.agentData);

        // Render current view
        if (state.currentView === "cameras") renderCameras();
        else renderAgents();

        console.log(`Cameras loaded: ${state.cameraMap.size}`);
        console.log(`Agents loaded: ${state.agentMap.size}`);
    } catch (err) {
        console.error("refreshData failed:", err);
    }
}

// =====================================================
// RENDER CAMERAS ONLY
// =====================================================
function renderCameras() {
    const grid = document.getElementById("cameraGrid");
    if (!grid) return;

    grid.innerHTML = "";

    state.cameraMap.forEach((item, normalizedName) => {
        const col = document.createElement("div");
        col.className = "col-xl-3 col-lg-4 col-md-6 col-sm-12 camera-col";

        const camStatusLower = item.camera_status?.toLowerCase() || "offline";
        const caStatusLower = item.capture_status?.toLowerCase() || "unknown";

        col.innerHTML = `
        <div class="card camera-card shadow-sm w-100 camera-item"
             data-cam-status="${camStatusLower}"
             data-ca-status="${caStatusLower}"
             data-name="${normalizedName}"
             data-fullname="${item.full_name.toLowerCase()}">

            <div class="camera-image-wrapper"
                 data-name="${item.name}">

                <img src="/cams/static/images/${item.name}_thumb.jpg"
                     class="camera-thumb img-fluid w-100"
                     alt="${item.name}"
                     onerror="this.src='/cams/resources/images/image_not_found_uct.png';">
            </div>

            <div class="card-body d-flex flex-column">
                <div class="row gx-2 align-items-start">
                    <div class="col-8">
                        <h5 class="card-title mb-1 text-break">${item.name}</h5>
                        <div class="text-muted small text-break">${item.full_name}</div>
                    </div>
                    <div class="col-4 text-end small">
                        <div class="row">
                            <div class="status-line camera-status-${camStatusLower} mb-1">
                                <i class="fa-solid fa-video"></i> <span>${item.camera_status}</span>
                            </div>
                        </div>
                        <div class="row">
                            <div class="status-line status-${caStatusLower} mt-1">
                                <i class="fa-solid fa-server"></i> <span>${item.capture_status}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        `;

        grid.appendChild(col);

        // Store DOM ref
        state.cameraMap.set(normalizedName, {
            ...item,
            root: col.querySelector(".camera-item"),
            col
        });
    });

    attachCardModals();
    applyCameraFilters();
    updateActiveButtons();
    console.log(`Rendered cameras: ${state.cameraMap.size}`);
}

// =====================================================
// RENDER AGENTS ONLY
// =====================================================
function renderAgents() {
    const grid = document.getElementById("cameraGrid");
    if (!grid) return;

    grid.innerHTML = "";

    state.agentMap.forEach((item, normalizedName) => {
        const col = document.createElement("div");
        col.className = "col-xl-3 col-lg-4 col-md-6 col-sm-12 camera-col";

        const caStatusLower = item.capture_status?.toLowerCase() || "unknown";

        col.innerHTML = `
        <div class="card camera-card shadow-sm w-100 camera-item"
             data-ca-status="${caStatusLower}"
             data-name="${normalizedName}"
             data-fullname="${item.full_name.toLowerCase()}">

            <div class="card-body d-flex flex-column">
                <div class="row">
                    <div class="col-6 d-flex align-items-center">
                        <h5 class="card-title mb-1 text-break">${item.name}</h5>
                    </div>
                    <div class="col-6 text-end">
                        <div class="mb-2">
                            <span class="status-line status-${caStatusLower}" data-toggle="tooltip" title="Capture Agent status">
                                <i class="fa-solid fa-server"></i> <span>${item.capture_status}</span>
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        `;

        grid.appendChild(col);

        // Store DOM ref
        state.agentMap.set(normalizedName, {
            ...item,
            root: col.querySelector(".camera-item"),
            col
        });
    });

    applyAgentFilters();
    updateActiveButtons();
    console.log(`Rendered agents: ${state.agentMap.size}`);
}

// =====================================================
// FILTERING – Separate functions
// =====================================================
function applyCameraFilters() {
    let visible = 0;

    state.cameraMap.forEach((card, name) => {
        const col = card.col;
        if (!col) return;

        const camStatus = (card.root?.dataset?.camStatus || "offline").toLowerCase();
        const show = state.activeCamFilter === "all" || camStatus === state.activeCamFilter;

        col.classList.toggle("hidden", !show);
        if (show) visible++;
    });

    console.log(`Visible cameras: ${visible} (filter: ${state.activeCamFilter})`);
}

function applyAgentFilters() {
    let visible = 0;

    state.agentMap.forEach((card, name) => {
        const col = card.col;
        if (!col) return;

        const caStatus = (card.root?.dataset?.caStatus || "unknown").toLowerCase();
        const show = state.activeCaFilter === "all" || caStatus === state.activeCaFilter;

        col.classList.toggle("hidden", !show);
        if (show) visible++;
    });

    console.log(`Visible agents: ${visible} (filter: ${state.activeCaFilter})`);
}

// =====================================================
// ACTIVE BUTTONS
// =====================================================
function updateActiveButtons() {
    document.querySelectorAll(".filter-btn").forEach(btn => {
        btn.classList.remove("active");

        const type = btn.dataset.type;
        const value = (btn.dataset.status || "all").toLowerCase();

        let filterType = type;
        if (type === "camera") filterType = "cam";

        const isActive =
            (filterType === "cam" && state.activeCamFilter === value) ||
            (filterType === "ca" && state.activeCaFilter === value);

        if (isActive) btn.classList.add("active");
    });
}

// Filter click handler
document.addEventListener("click", e => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;

    const type = btn.dataset.type;
    const value = (btn.dataset.status || "all").toLowerCase();

    let filterType = type;
    if (type === "camera") filterType = "cam";

    if (!["cam", "ca"].includes(filterType)) return;

    if (filterType === "cam") {
        state.activeCamFilter = (state.activeCamFilter === value) ? "all" : value;
        applyCameraFilters();
    } else {
        state.activeCaFilter = (state.activeCaFilter === value) ? "all" : value;
        applyAgentFilters();
    }

    updateActiveButtons();
});

// =====================================================
// CAMERA MODAL – Fetch large/current image from API
// =====================================================
function attachCardModals() {
    document.removeEventListener("click", handleModalClick);
    document.addEventListener("click", handleModalClick);
}

async function handleModalClick(e) {
    const wrapper = e.target.closest(".camera-image-wrapper");
    if (!wrapper) return;

    const cameraName = wrapper.dataset.name;
    const fullName = wrapper.dataset.fullname || cameraName || "Camera";
    console.log(`Modal clicked for camera: ${cameraName}`);

    let largeImageUrl = `/cams/static/images/${cameraName}.jpg`; // default fallback

    try {
        const response = await fetch(`/cams/${cameraName}/current`);
        if (response.ok) {
            const data = await response.json();
            largeImageUrl = data.image_url || largeImageUrl;
            console.log(`Fetched large image: ${largeImageUrl}`);
        } else {
            console.warn(`Current image API returned ${response.status} for ${cameraName}`);
        }
    } catch (err) {
        console.error("Failed to fetch current image:", err);
    }

    openCameraModalWithRange(fullName, cameraName, largeImageUrl);
}

function openCameraModalWithRange(title, cameraName, largeImageUrl) {
    const modalEl = document.getElementById("cameraModal");
    if (!modalEl) return console.error("Modal #cameraModal not found");

    const modal = new bootstrap.Modal(modalEl);

    const titleEl = document.getElementById("cameraModalTitle");
    const mainImg = document.getElementById("modalMainImage");
    const thumbs = document.getElementById("modalThumbs");

    if (!titleEl || !mainImg || !thumbs) return console.error("Missing modal elements");

    titleEl.textContent = title;

    // Use fetched large/current image
    mainImg.src = largeImageUrl;
    mainImg.style.width = "100%";
    mainImg.style.height = "auto";
    mainImg.style.display = "block";
    mainImg.onerror = () => {
        console.warn(`Large image failed to load: ${largeImageUrl}`);
        mainImg.src = '/cams/resources/images/image_not_found_uct.png';
    };

    const thumbnailPath = `/cams/static/images/${cameraName}_thumb.jpg`;
    const webmPath = `/cams/static/timelapse/camera_${cameraName}.webm`;

    thumbs.innerHTML = "";
    thumbs.style.display = "none";

    // let modalVideo = document.getElementById("modalVideo");
    // if (!modalVideo) {
    //     modalVideo = document.createElement("video");
    //     modalVideo.id = "modalVideo";
    //     modalVideo.className = "w-100 rounded shadow mt-3";
    //     modalVideo.style.display = "none";
    //     modalVideo.muted = true;
    //     modalVideo.controls = true;
    //     modalVideo.loop = false;
    //     modalVideo.innerHTML = `<source src="${webmPath}" type="video/webm">`;
    //     mainImg.after(modalVideo);
    // } else {
    //     const source = modalVideo.querySelector("source");
    //     if (source) source.src = webmPath;
    //     modalVideo.load();
    //     modalVideo.style.display = "none";
    // }

    // let ctaContainer = document.getElementById("timelapseCta");
    // if (!ctaContainer) {
    //     ctaContainer = document.createElement("div");
    //     ctaContainer.id = "timelapseCta";
    //     ctaContainer.className = "text-center mt-4";

    //     const btn = document.createElement("button");
    //     btn.textContent = "Play Timelapse Video";
    //     btn.className = "btn btn-primary btn-lg";
    //     btn.addEventListener("click", () => {
    //         mainImg.style.display = "none";
    //         modalVideo.style.display = "block";
    //         modalVideo.currentTime = 0;
    //         modalVideo.play().catch(e => {
    //             console.error("WebM play failed:", e);
    //             alert("Could not play video.");
    //             modalVideo.style.display = "none";
    //             mainImg.style.display = "block";
    //         });
    //     });

    //     ctaContainer.appendChild(btn);
    //     thumbs.after(ctaContainer);
    // }

    modal.show();
}

// =====================================================
// COUNTERS
// =====================================================
function updateCameraCountersFromAPI(activityData) {
    if (!activityData) return;
    setCount("count-all-cams", (activityData.active_count || 0) + (activityData.inactive_count || 0));
    setCount("count-active", activityData.active_count || 0);
    setCount("count-cam-inactive", activityData.inactive_count || 0);
}

function updateCACounters(agentData) {
    const results = agentData?.capture_agent_status?.results || [];
    const counts = {
        capturing: 0,
        idle: 0,
        error: 0,
        unknown: 0,
        offline: 0,
        total: results.length || agentData?.count || agentData?.total || 0
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
}

// =====================================================
// INITIAL LOAD + AUTO REFRESH
// =====================================================
let isRefreshing = false;
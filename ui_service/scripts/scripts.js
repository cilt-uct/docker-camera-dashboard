document.addEventListener("DOMContentLoaded", () => {
    /* strip host from URLs : issue with image displaying full path returned*/
    function stripHost(url) {
        try {
            const u = new URL(url, window.location.origin);
            return u.pathname + u.search + u.hash;
        } catch {
            return url;
        }
    }

    // get the timestamp from the image URL
    function extractTimestamp(imgUrl) {
        const name = imgUrl.split("/").pop();
        return parseInt(name.replace(".jpg", ""), 10);
    }
    // filter images by timestamp range - used for the modal gallery
    function filterImagesByRange(images, from, to) {
        return images.filter(img => {
            const ts = extractTimestamp(img);
            return ts >= from && ts <= to;
        });
    }
    // format date correcly
    function toInputFormat(date) {
        return date.toISOString().slice(0, 16);
    }

    /*  format the time display human readable, */
    document.querySelectorAll(".moment-last-capture").forEach(el => {
        const time = el.dataset.time;
        el.textContent = time && window.moment
            ? moment(time).fromNow()
            : "No data";
    });

    document.querySelectorAll(".js-last-capture").forEach(el => {
        const time = el.dataset.time;
        el.textContent = time
            ? time.replace("T", " ").replace("Z", "").slice(0, 19)
            : "—";
    });

    document.querySelectorAll('[data-toggle="tooltip"]').forEach(el => {
        new bootstrap.Tooltip(el);
    });

    /* top filters cams, ca's, search */
    const cards = document.querySelectorAll(".camera-item");
    const cameraButtons = document.querySelectorAll(".filter-btn[data-type='camera']");
    const caButtons = document.querySelectorAll(".filter-btn[data-type='ca']");
    const searchInput = document.getElementById("cameraSearch");

    let activeCamFilter = "all";
    let activeCaFilter = "all";
    let searchTerm = "";

    /* filtering cms and ca's */
    function applyFilters() {
        cards.forEach(card => {
            const col = card.closest(".camera-col");

            const camStatus = (card.dataset.camStatus || "inactive").toLowerCase();
            const caStatus = (card.dataset.caStatus || "unknown").toLowerCase();
            const fullName = (card.dataset.fullname || "").toLowerCase();
            const shortName = (card.dataset.name || "").toLowerCase();

            const camMatch = activeCamFilter === "all" || camStatus === activeCamFilter;
            const caMatch = activeCaFilter === "all" || caStatus === activeCaFilter;
            const searchMatch =
                fullName.includes(searchTerm) ||
                shortName.includes(searchTerm);

            const visible = camMatch && caMatch && searchMatch;

            col.classList.toggle("camera-hidden", !visible);
        });

        updateCounters();
    }

    /* total counters top */
    function updateCounters() {

        const camCounts = { active: 0, inactive: 0 };
        const caCounts = { idle: 0, capturing: 0, error: 0, offline: 0, unknown: 0 };

        cards.forEach(card => {
            const camStatus = (card.dataset.camStatus || "inactive").toLowerCase();
            const caStatus = (card.dataset.caStatus || "unknown").toLowerCase();

            if (camCounts[camStatus] !== undefined) camCounts[camStatus]++;
            if (caCounts[caStatus] !== undefined) caCounts[caStatus]++;
        });

        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        set("count-total", cards.length);
        set("count-active", camCounts.active);
        set("count-cam-inactive", camCounts.inactive);

        set("count-ca-idle", caCounts.idle);
        set("count-ca-capturing", caCounts.capturing);
        set("count-ca-error", caCounts.error);
        set("count-ca-offline", caCounts.offline);
        set("count-ca-unknown", caCounts.unknown);

        // All buttons
        set("count-all", "count-all-cas", cards.length);
    }

    /* filtering buttons */
    cameraButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            cameraButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            activeCamFilter = btn.dataset.status;
            applyFilters();
        });
    });

    /* CA filter buttons */
    caButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            caButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            activeCaFilter = btn.dataset.status;
            applyFilters();
        });
    });

    /* search */
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            searchTerm = e.target.value.toLowerCase().trim();
            applyFilters();
        });
    }

    /* initiate filtering */
    applyFilters();


    /* WebM stuff, sort out the ffmpeg instead of rerunning it constantly */

    document.querySelectorAll('.camera-image-wrapper').forEach(wrapper => {
        const video = wrapper.querySelector('.camera-hover-video');
        const rawUrl = wrapper.dataset.video;

        if (!video || !rawUrl) return;

        video.src = stripHost(rawUrl);
        video.muted = true;
        video.playsInline = true;
        video.preload = "metadata";

        wrapper.addEventListener('mouseenter', () => {
            if (video.readyState >= 2) {
                video.currentTime = 0;
                video.play().catch(() => { });
            }
        });

        wrapper.addEventListener('mouseleave', () => {
            video.pause();
        });
    });

    /* bootstrap modal for images and date picker PS to remove fancypicker stuffs*/

    const modalEl = document.getElementById("cameraModal");
    const modal = new bootstrap.Modal(modalEl);

    const titleEl = document.getElementById("cameraModalTitle");
    const mainImg = document.getElementById("modalMainImage");
    const thumbs = document.getElementById("modalThumbs");
    const fromInput = document.getElementById("fromDate");
    const toInput = document.getElementById("toDate");
    const applyBtn = document.getElementById("applyRange");

    let currentImages = [];

    /* Date limits: Today and back for 8 days  */
    const nowDate = new Date();
    const minDate = new Date();
    minDate.setDate(minDate.getDate() - 8);

    fromInput.min = toInput.min = toInputFormat(minDate);
    fromInput.max = toInput.max = toInputFormat(nowDate);

    function renderGallery(images) {
        thumbs.innerHTML = "";

        if (!images.length) {
            mainImg.src = "";
            thumbs.innerHTML = "<p class='text-muted'>No images in selected range</p>";
            return;
        }

        mainImg.src = images[0];

        images.forEach(src => {
            const img = document.createElement("img");
            img.src = src;
            img.style.width = "120px";
            img.style.cursor = "pointer";
            img.classList.add("rounded", "shadow-sm");

            img.addEventListener("click", () => {
                mainImg.src = src;
            });

            thumbs.appendChild(img);
        });
    }

    document.querySelectorAll(".camera-image-wrapper").forEach(wrapper => {

        wrapper.addEventListener("click", () => {

            try {
                currentImages = JSON.parse(wrapper.dataset.images || "[]");
            } catch {
                console.error("Bad data-images JSON");
                return;
            }

            titleEl.textContent =
                wrapper.dataset.fullname || wrapper.dataset.name || "Camera";

            const now = Math.floor(Date.now() / 1000);
            const oneHourAgo = now - (60 * 60);

            const filtered = filterImagesByRange(
                currentImages,
                oneHourAgo,
                now
            ).sort((a, b) => extractTimestamp(a) - extractTimestamp(b));

            renderGallery(filtered);

            modal.show();
        });

    });

    applyBtn.addEventListener("click", () => {

        if (!fromInput.value || !toInput.value) return;

        const from = Math.floor(new Date(fromInput.value).getTime() / 1000);
        const to = Math.floor(new Date(toInput.value).getTime() / 1000);

        const filtered = filterImagesByRange(currentImages, from, to)
            .sort((a, b) => extractTimestamp(a) - extractTimestamp(b));

        renderGallery(filtered);
    });

    /* lazy load all images*/

    document.querySelectorAll("img.lazy").forEach(img => {
        img.src = img.dataset.src;
    });

    /* schedules js */

    const ScheduleModal = new bootstrap.Modal(document.getElementById("scheduleModal"));
    const headerEl = document.getElementById("scheduleHeader");
    const gridEl = document.getElementById("scheduleGrid");
    const labelEl = document.getElementById("currentLabel");
    const cameraFilter = document.getElementById("cameraFilter");

    let allEvents = [];
    let currentView = "month";
    let currentDate = new Date();

    /* open schdule, two modals rename them */
    document.querySelectorAll(".open-schedule-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
            ScheduleModal.show();
            await fetchData();
            populateCameraDropdown();
            render();
        });
    });

    /* navagation  */
    document.getElementById("prevBtn").onclick = () => {
        if (currentView === "month") currentDate.setMonth(currentDate.getMonth() - 1);
        if (currentView === "week") currentDate.setDate(currentDate.getDate() - 7);
        if (currentView === "day") currentDate.setDate(currentDate.getDate() - 1);
        render();
    };

    document.getElementById("nextBtn").onclick = () => {
        if (currentView === "month") currentDate.setMonth(currentDate.getMonth() + 1);
        if (currentView === "week") currentDate.setDate(currentDate.getDate() + 7);
        if (currentView === "day") currentDate.setDate(currentDate.getDate() + 1);
        render();
    };

    document.querySelectorAll(".view-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            currentView = btn.dataset.view;
            render();
        });
    });

    cameraFilter.addEventListener("change", render);

    async function fetchData() {
        const res = await fetch("/cams/api/events");
        const data = await res.json();
        allEvents = data.events?.results || [];
    }

    // get all cameras from events and populate the dropdown filter
    function populateCameraDropdown() {
        const cams = [...new Set(allEvents.map(e => e.location))];
        cameraFilter.innerHTML = `<option value="all">All Cameras</option>`;
        cams.forEach(c =>
            cameraFilter.innerHTML += `<option value="${c}">${c}</option>`
        );
    }
    // filter camera from dropdown selection
    function getFilteredCameras() {
        const cams = [...new Set(allEvents.map(e => e.location))];
        if (cameraFilter.value === "all") return cams;
        return cams.filter(c => c === cameraFilter.value);
    }

    function render() {
        headerEl.innerHTML = "";
        gridEl.innerHTML = "";

        if (currentView === "month") renderMonth();
        if (currentView === "week") renderWeek();
        if (currentView === "day") renderDay();
    }

    function parseLocalDate(dateStr) {
        if (!dateStr) return null;

        // Handles "YYYY-MM-DD" safely without timezone shift
        const parts = dateStr.split("T")[0].split("-");
        return new Date(parts[0], parts[1] - 1, parts[2]);
    }
    /* month return dates*/

    function renderMonth() {
        const year = currentDate.getFullYear();
        const month = currentDate.getMonth();
        const days = new Date(year, month + 1, 0).getDate();

        labelEl.textContent = currentDate.toLocaleString("default", {
            month: "long",
            year: "numeric"
        });

        headerEl.style.gridTemplateColumns = `150px repeat(${days}, 35px)`;
        headerEl.className = "schedule-header";
        headerEl.innerHTML = "<div></div>";

        for (let d = 1; d <= days; d++) {
            headerEl.innerHTML += `<div>${d}</div>`;
        }

        const cameras = getFilteredCameras();

        cameras.forEach(cam => {
            const row = document.createElement("div");
            row.className = "schedule-row";
            row.style.gridTemplateColumns = `150px repeat(${days}, 35px)`;
            row.innerHTML = `<div class="camera-label">${cam}</div>`;

            for (let d = 1; d <= days; d++) {
                const cellDate = new Date(year, month, d);

                const hasEvent = allEvents.some(e => {
                    if (e.location !== cam) return false;

                    const start = parseLocalDate(e.start_date);
                    const end = parseLocalDate(e.end_date || e.start_date);

                    return cellDate >= start && cellDate <= end;
                });

                row.innerHTML += `<div class="cell ${hasEvent ? "active" : ""}"></div>`;
            }

            gridEl.appendChild(row);
        });
    }

    /* return per week, scrollable  */

    function renderWeek() {
        const start = new Date(currentDate);
        start.setDate(start.getDate() - start.getDay());

        labelEl.textContent = `Week of ${start.toLocaleDateString()}`;

        headerEl.style.gridTemplateColumns = "150px repeat(7, 100px)";
        headerEl.className = "schedule-header";
        headerEl.innerHTML = "<div></div>";

        for (let i = 0; i < 7; i++) {
            const day = new Date(start);
            day.setDate(start.getDate() + i);
            headerEl.innerHTML += `<div>${day.toLocaleDateString()}</div>`;
        }

        const cameras = getFilteredCameras();

        cameras.forEach(cam => {
            const row = document.createElement("div");
            row.className = "schedule-row";
            row.style.gridTemplateColumns = "150px repeat(7, 100px)";
            row.innerHTML = `<div class="camera-label">${cam}</div>`;

            for (let i = 0; i < 7; i++) {
                const cellDate = new Date(start);
                cellDate.setDate(start.getDate() + i);

                const hasEvent = allEvents.some(e => {
                    if (e.location !== cam) return false;

                    const startDate = parseLocalDate(e.start_date);
                    const endDate = parseLocalDate(e.end_date || e.start_date);

                    return cellDate >= startDate && cellDate <= endDate;
                });

                row.innerHTML += `<div class="cell ${hasEvent ? "active" : ""}"></div>`;
            }

            gridEl.appendChild(row);
        });
    }
    /* return daily */

    function renderDay() {
        const year = currentDate.getFullYear();
        const month = currentDate.getMonth();
        const day = currentDate.getDate();

        labelEl.textContent = currentDate.toLocaleDateString();

        headerEl.style.gridTemplateColumns = "150px repeat(24, 35px)";
        headerEl.className = "schedule-header";
        headerEl.innerHTML = "<div></div>";

        for (let h = 0; h < 24; h++) {
            headerEl.innerHTML += `<div>${h}</div>`;
        }

        const cameras = getFilteredCameras();

        cameras.forEach(cam => {
            const row = document.createElement("div");
            row.className = "schedule-row";
            row.style.gridTemplateColumns = "150px repeat(24, 35px)";
            row.innerHTML = `<div class="camera-label">${cam}</div>`;

            for (let h = 0; h < 24; h++) {
                const hasEvent = allEvents.some(e => {
                    if (e.location !== cam) return false;

                    const start = new Date(e.start_date);
                    const end = new Date(e.end_date || e.start_date);

                    return (
                        start.getFullYear() === year &&
                        start.getMonth() === month &&
                        start.getDate() === day &&
                        start.getHours() === h
                    );
                });

                row.innerHTML += `<div class="cell ${hasEvent ? "active" : ""}"></div>`;
            }

            gridEl.appendChild(row);
        });
    }

});
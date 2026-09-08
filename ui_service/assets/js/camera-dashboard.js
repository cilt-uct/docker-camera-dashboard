jQuery.fn.exists = function(){ return this.length > 0; }

class CameraDashboard {

    constructor(options = {}) {
        // State
        this.state = {
            cameraMap: new Map(),
            agentMap: new Map(),

            activeCamFilter: "all",
            activeCaFilter: "all",
            currentView: "cameras",

            camData: null,
            agentData: null,
            isRefreshing: false
        };

        this.refresh = options.refresh || false;

        // Options for endpoints or selectors
        this.endpoints = {
            cameras: options.camerasEndpoint || "/cams/api/cameras",
            agents: options.agentsEndpoint || "/cams/api/agents"
        };

        this.selectors = {
            cameraGrid: options.cameraGrid || "#cameraGrid",
            cameraSearch: options.cameraSearch || "#cameraSearch",
            cameraFilters: options.cameraFilters || "#cameraFilters",

            agentGrid: options.agentGrid || "#agentGrid",
            agentSearch: options.agentSearch || "#agentSearch",
            agentFilters: options.agentFilters || "#agentFilters",

            cameraModal: options.cameraModal || "#cameraModal"
        };

        this.init();
    }

    // ==========================
    // UTILS
    // ==========================
    normalizeName(name) {
        return (name || "").toLowerCase().replace(".local", "").replace(".capture", "").trim();
    }

    normalizeAgentStatus(raw) {
        if (!raw) return "unknown";
        const s = raw.toUpperCase();
        if (s.includes("OFFLINE")) return "offline";
        if (s.includes("IDLE")) return "idle";
        if (s.includes("CAPTURING")) return "capturing";
        if (s.includes("ERROR")) return "error";
        return "unknown";
    }

    getPathFromUrl(url) {
        if (!url) return ""; // handles '', null, undefined

        try {
            return new URL(url).pathname;
        } catch {
            return url;
        }
    }

    setCount(id, value) {
        $(`#${id}`).text(value);
    }

    // ==========================
    // INITIALIZATION
    // ==========================
    init() {
        $(document).ready(() => {
            this.bindFilters();
            this.bindSortButtons();
            this.attachCardModals();

            this.refreshData();

            // Auto-refresh every 5 minutes
            if (this.refresh) {
                setInterval(() => this.autoRefresh(), 5 * 60 * 1000);
            }
        });
    }

    bindFilters() {
        $(document).on("click", ".filter-btn", (e) => {
            const btn = $(e.currentTarget);
            const type = btn.data("type");
            btn.parent().children().removeClass('active')
            btn.addClass('active');
            if (type === "camera") {
                this.applyCameraFilters();
            } else if (type === "agent") {
                this.applyAgentFilters();
            }
        });

        let cameraSearchTimer;
        $(this.selectors.cameraSearch).on("input", () => {
            clearTimeout(cameraSearchTimer);
            cameraSearchTimer = setTimeout(() => this.applyCameraFilters(), 250);
        });
        $('#cameraSearch_clear').on('click', () => {
            $(this.selectors.cameraSearch).val('');
            this.applyCameraFilters();
        });

        let agentSearchTimer;
        $(this.selectors.agentSearch).on("input", () => {
            clearTimeout(agentSearchTimer);
            agentSearchTimer = setTimeout(() => this.applyAgentFilters(), 250);
        });
        $('#agentSearch_clear').on('click', () => {
            $(this.selectors.agentSearch).val('');
            this.applyAgentFilters();
        });
    }

    bindSortButtons() {
        $(document).on("click", ".sort-button", (e) => {
            const btn = $(e.currentTarget);
            btn.toggleClass('asc');

            const type = btn.data("type");
            const order = btn.hasClass('asc') ? 'asc': 'desc';

            const $grid = $(type == "camera" ? this.selectors.cameraGrid : this.selectors.agentGrid);
            this.sortGrid($grid, order);
        });
    }

    // ==========================
    // AUTO REFRESH
    // ==========================
    async autoRefresh() {
        if (this.state.isRefreshing) return;
        this.state.isRefreshing = true;

        try {
            console.log("Auto-refreshing...");
            await this.refreshData();
        } catch (err) {
            console.error("Auto-refresh failed:", err);
        } finally {
            this.state.isRefreshing = false;
        }
    }

    // ==========================
    // DATA REFRESH
    // ==========================
    async refreshData() {
        try {
            const [camRes, agentRes] = await Promise.all([
                fetch(this.endpoints.cameras),
                fetch(this.endpoints.agents)
            ]);

            this.state.camData = await camRes.json();
            this.state.agentData = await agentRes.json();

            this.updateCounters();
            this.processCameras();
            this.processAgents();
        } catch (err) {
            console.error("refreshData failed:", err);
        }
    }

    processCameras() {
        this.state.cameraMap.clear();
        (this.state.camData?.cameras || []).forEach(camera => {
            const normalized = this.normalizeName(camera.name);
            this.state.cameraMap.set(normalized, {
                name: camera.name,
                fullname: camera.fullname || camera.name,
                camera_status: camera.state,
                status: camera.state,
                capture_status: "unknown",
                image_url: this.getPathFromUrl(camera.image_url),
                thumbnail_url: this.getPathFromUrl(camera.thumbnail),
                last_update: camera.last_capture_completed || 0
            });
        });

        // Enrich capture_status if agent data exists
        (this.state.agentData?.agents || []).forEach(agent => {
            const name = this.normalizeName(agent.name);
            if (this.state.cameraMap.has(name)) {
                this.state.cameraMap.get(name).capture_status = this.normalizeAgentStatus(agent.state);
            }
        });

        this.renderCameras();
    }

    processAgents() {
        this.state.agentMap.clear();
        (this.state.agentData?.agents || []).forEach(agent => {
            const name = this.normalizeName(agent.name);
            this.state.agentMap.set(name, {
                name: agent.name,
                fullname: agent.display || agent.name,
                capture_status: this.normalizeAgentStatus(agent.state),
                status: this.normalizeAgentStatus(agent.state),
                last_update: agent.last_updated || 0
            });
        });

        this.renderAgents();
    }

    getStateCounts(arr) {
        return arr.reduce((acc, item) => {
            const state = (item.state || "unknown").toLowerCase();
            acc[state] = (acc[state] || 0) + 1;
            return acc;
        }, {});
    }

    updateCounters() {
        const camCounts = this.getStateCounts(this.state.camData.cameras);
        const agentCounts = this.getStateCounts(this.state.agentData.agents);

        $("#cams-count-all").text(Object.values(camCounts).reduce((sum, val) => sum + val, 0));
        Object.entries(camCounts).forEach(([state, value]) => { $(`#cams-count-${state}`).text(value); });

        $("#agent-count-all").text(Object.values(agentCounts).reduce((sum, val) => sum + val, 0));
        Object.entries(agentCounts).forEach(([state, value]) => { $(`#agent-count-${state}`).text(value); });
    }

    // ==========================
    // RENDERING
    // ==========================
    getStatusDiv(status, icon, title) {
        return `<span class="status-line status-${status}" data-toggle="tooltip" title="${title}">
                    <i class="fa-solid ${icon}"></i> <span>${status}</span>
                </span>`;
    }

    createCameraCard(data) {
        const template = document.getElementById("CameraTemplate");

        const clone = template.content.cloneNode(true);
        const $column = $(clone.querySelector(".col-xl-3"));
        $column.attr('id', `camera-${data.name}`);
        $column.data(data);

        return clone;
    }

    fillCameraCard($el) {
        const cacheBuster = `?t=${Date.now()}`;

        const $img = $el.find("img.card-img-top");
        // Update image
        $img.attr("src", `${$el.data('thumbnail_url') ? $el.data('thumbnail_url')+cacheBuster : '/cams/assets/images/image_not_found_uct.png'}`)
            .attr("class", `card-img-top ${$el.data('camera_status')}`)
            .attr("alt", $el.data('fullname'))
            .on("error", function() {
                $(this).attr("src", "/cams/assets/images/image_not_found_uct.png");
            });

        if ($el.data('status') == 'offline') {
            $el.find('.card').addClass('border-danger');
        } else {
            $el.find('.card').removeClass('border-danger');
        }
        $el.find('.card-title').text($el.data('name'));
        $el.find('.card-display').text($el.data('fullname'));
        $el.find('.card-status').html(this.getStatusDiv($el.data('camera_status'), 'fa-video', 'Camera Status'));

        // Set footer text (format the timestamp nicely)
        if ($el.data('last_update')) {
            let now = moment($el.data('last_update')).fromNow();

            $el.find('.card-footer').removeClass('NA').html(`
                    <small>${moment($el.data('last_update')).format("ddd, D MMM YYYY, HH:mm:ss")}</small>
                    <small>${(now == 'in a few seconds' ? 'just now' :now)}</small>
                `);
        } else {
            $el.find('.card-footer').addClass('NA').html('<span>N/A</span>');
        }
    }

    renderCameras() {
        const $grid = $(this.selectors.cameraGrid);
        if ($grid.find(".loader").exists()) {
            $grid.empty();
        }

        Array.from(this.state.cameraMap.entries())
            .sort((a, b) => a[0].localeCompare(b[0]))
            .forEach((item) => {
                let name = this.normalizeName(item[0]),
                    $el = $(`#camera-${name}`);
                if (!$el.exists()) {
                    const card = this.createCameraCard(item[1]);
                    $grid.append(card);
                    item.root = $(card);
                    $el = $(`#camera-${name}`);
                }
                $el.data(item[1]);
                this.fillCameraCard($el)
            });

        this.applyCameraFilters();
    }

    createAgentCard(data) {
        const template = document.getElementById("AgentTemplate");

        const clone = template.content.cloneNode(true);
        const $column = $(clone.querySelector(".col-xl-3"));
        $column.attr('id', `agent-${data.name.toLowerCase()}`);
        $column.data(data);

        return clone;
    }

    fillAgentCard($el) {
        $el.find('.card-title').text($el.data('name'));
        $el.find('.card-status').html(this.getStatusDiv($el.data('capture_status'), 'fa-server', 'Capture Agent Status'));

        // Set footer text (format the timestamp nicely)
        if ($el.data('last_update')) {
            let now = moment($el.data('last_update')).fromNow();

            if ($el.data('status') == 'error') {
                $el.find('.card').addClass('border-danger');
            } else {
                $el.find('.card').removeClass('border-danger');
            }
            if ($el.data('status') == 'unknown') {
                $el.find('.card').addClass('border-warning');
            } else {
                $el.find('.card').removeClass('border-warning');
            }
            if ($el.data('status') == 'capturing') {
                $el.find('.card').addClass('border-info');
            } else {
                $el.find('.card').removeClass('border-info');
            }
            if ($el.data('status') == 'idle') {
                $el.find('.card').addClass('border-success');
            } else {
                $el.find('.card').removeClass('border-success');
            }

            $el.find('.card-footer').html(`
                    <small>${moment($el.data('last_update')).format("ddd, D MMM YYYY, HH:mm:ss")}</small>
                    <small>${(now == 'in a few seconds' ? 'just now' :now)}</small>
                `);
        } else {
            $el.find('.card-footer').addClass('NA').html('<span>N/A</span>');
        }
    }

    renderAgents() {
        const $grid = $(this.selectors.agentGrid);
        if ($grid.find(".loader").exists()) {
            $grid.empty();
        }

        Array.from(this.state.agentMap.entries())
            .sort((a, b) => a[0].localeCompare(b[0]))
            .forEach((item) => {
                let $el = $(`#agent-${item[0]}`);
                if (!$el.exists()) {
                    const card = this.createAgentCard(item[1]);
                    $grid.append(card);
                    item.root = $(card);
                    $el = $(`#agent-${item[0]}`);
                }
                $el.data(item[1]);
                this.fillAgentCard($el)
            });

        this.applyAgentFilters();
    }

    // ==========================
    // FILTERS
    // ==========================
    applyCameraFilters() {
        const query = ($(this.selectors.cameraSearch).val() || "").toLowerCase().trim();
        const activeStatus = $("#cameraStatus .active").data("status") || "all";

        const $cards = $("#cameraGrid .col-xl-3");

        let visibleCount = 0;

        $cards.each(function () {
            const $card = $(this);

            const name = ($card.data("name") || "").toLowerCase();
            const fullname = ($card.data("fullname") || "").toLowerCase();
            const status = ($card.data("status") || "").toLowerCase();

            // Search match (partial)
            const matchesSearch =
                !query ||
                name.includes(query) ||
                fullname.includes(query);

            // Status match
            const matchesStatus =
                activeStatus === "all" || status === activeStatus;

            const show = matchesSearch && matchesStatus;

            $card.toggle(show);

            if (show) visibleCount++;
        });

        // console.log(`Cameras Visible: ${visibleCount}`);
    }

    applyAgentFilters() {
        const query = ($(this.selectors.agentSearch).val() || "").toLowerCase().trim();
        const activeStatus = $("#agentStatus .active").data("status") || "all";

        const $cards = $("#agentGrid .col-xl-3");

        let visibleCount = 0;

        $cards.each(function () {
            const $card = $(this);

            const name = ($card.data("name") || "").toLowerCase();
            const fullname = ($card.data("fullname") || "").toLowerCase();
            const status = ($card.data("status") || "").toLowerCase();

            // Search match (partial)
            const matchesSearch =
                !query ||
                name.includes(query) ||
                fullname.includes(query);

            // Status match
            const matchesStatus =
                activeStatus === "all" || status === activeStatus;

            const show = matchesSearch && matchesStatus;

            $card.toggle(show);

            if (show) visibleCount++;
        });

        // console.log(`Agents Visible: ${visibleCount}`);
    }

    sortGrid($grid, order = "asc") {
        const items = $grid.children("div").get();
        items.sort((a, b) => {
            const nameA = ($(a).data("name") || "").toLowerCase();
            const nameB = ($(b).data("name") || "").toLowerCase();

            return order === "asc"
                ? nameA.localeCompare(nameB)
                : nameB.localeCompare(nameA);
        });

        $grid.append(items); // reorders in one go
    }

    // ==========================
    // MODALS
    // ==========================
    attachCardModals() {
        $(document).off("click.modal").on("click.modal", ".camera-image-wrapper", (e) => this.handleModalClick(e));
    }

    async handleModalClick(e) {
        const $card = $(e.currentTarget).closest('.col-xl-3');
        if (!$card.data('image_url')) return;

        const cameraName = $card.data("name");
        const fullname = $card.data("fullname") || cameraName;

        let largeImageUrl = $card.data('image_url');
        try {
            const response = await fetch(`/cams/api/camera/${cameraName}/current?t=${Date.now()}`);
            if (response.ok) {
                const data = await response.json();
                largeImageUrl = data.image_url || largeImageUrl;
            }
        } catch (err) {
            console.error("Failed to fetch current image:", err);
        }

        this.openCameraModal(fullname, cameraName, largeImageUrl);
    }

    openCameraModal(title, cameraName, imageUrl) {
        const $modal = $(this.selectors.cameraModal);
        if (!$modal.exists()) return;

        const $mainImg = $modal.find('#modalMainImage');
        if (!$mainImg.exists()) return;


        $modal.find('.modal-title').html(cameraName !== title ?
                                            `<span class="text-muted">${cameraName}</span> : ${title}` :
                                            `${title}`);

        $mainImg.attr("src", imageUrl).css({ width: "100%", height: "auto", display: "block" })
            .off("error").on("error", () => {
                $mainImg.attr("src", "/cams/resources/images/image_not_found_uct.png");
            });

        $(this.selectors.modalThumbs).hide().empty();
        $modal.modal('show');
    }
}

export default CameraDashboard;

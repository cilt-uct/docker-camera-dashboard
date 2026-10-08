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
            scheduleData: null,
            isRefreshing: false
        };

        this.refresh = options.refresh || false;
        this.IGNORE_SCHEDULE = options.ignoreSchedule || ['podcast'];

        // Options for endpoints or selectors
        this.endpoints = {
            cameras: options.camerasEndpoint || "/cams/api/cameras",
            agents: options.agentsEndpoint || "/cams/api/agents",
            schedule: options.scheduleEndpoint || "/cams/api/schedule"
        };

        this.selectors = {
            cameraGrid: options.cameraGrid || "#cameraGrid",
            cameraSearch: options.cameraSearch || "#cameraSearch",
            cameraFilters: options.cameraFilters || "#cameraFilters",

            agentGrid: options.agentGrid || "#agentGrid",
            agentSearch: options.agentSearch || "#agentSearch",
            agentFilters: options.agentFilters || "#agentFilters",

            scheduleGrid: options.scheduleGrid || "#scheduleGrid",
            scheduleSearch: options.scheduleSearch || "#scheduleSearch",
            scheduleFilters: options.scheduleFilters || "#scheduleFilters",

            cameraModal: options.cameraModal || "#cameraModal",
            lastUpdated: options.lastUpdated || "#last-updated"
        };

        this.init();
    }

    // ==========================
    // UTILS
    // ==========================
    static logMessage(message, type = 'info') {
        const logTypes = {
            info: console.log,
            warn: console.warn,
            error: console.error,
        };

        (logTypes[type] || console.log)(`[CameraDashboard] ${message}`);
    }


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

    normalizeEventStatus(raw) {
        if (!raw) return "unknown";
        const s = raw.split(".").pop().toUpperCase();
        if (s.includes("FAIL") || s.includes("CANCEL")) return "failed";
        if (s === "PROCESSED") return "finished";
        if (s.includes("RECORDING")) return "recording";
        if (s.includes("PROCESSING") || s.includes("INGESTING") || s.includes("PENDING")) return "processing";
        if (s.includes("SCHEDULED")) return "scheduled";
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
            this.bindInteractiveActions();
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
            switch(type) {
                case "camera":
                    this.applyCameraFilters();
                    break;
                case "agent":
                    this.applyAgentFilters();
                    break;
                case "schedule":
                    this.applyScheduleFilters();
                    break;
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

        let scheduleSearchTimer;
        $(this.selectors.scheduleSearch).on("input", () => {
            clearTimeout(scheduleSearchTimer);
            scheduleSearchTimer = setTimeout(() => this.applyScheduleFilters(), 250);
        });
        $('#scheduleSearch_clear').on('click', () => {
            $(this.selectors.scheduleSearch).val('');
            this.applyScheduleFilters();
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

    bindInteractiveActions(){
        $('#scheduleGrid').on('click', 'table > tbody > tr > td > a.schedule-event', function(event) {
            event.preventDefault();
            const event_id = $(this).data('event');

            // Use the modern clipboard API
            navigator.clipboard.writeText(event_id).then(() => {
                CameraDashboard.logMessage(`ID copied to clipboard: ${event_id}`, 'info');
                $().msgpopup({ text: `ID copied to clipboard`, type: 'success' });
            }).catch(err => {
                CameraDashboard.logMessage(`Failed to copy ID: ${err}`, 'error');
                $().msgpopup({ text: `Failed to copy ID`, type: 'error' });
            });
        });
    }

    // ==========================
    // AUTO REFRESH
    // ==========================
    async autoRefresh() {
        if (this.state.isRefreshing) return;
        this.state.isRefreshing = true;

        try {
            $("#last-updated").removeClass('status-error');
            CameraDashboard.logMessage(`Auto-refreshing...`, 'info');
            await this.refreshData();
        } catch (err) {
            CameraDashboard.logMessage(`Auto-refreshing failed: ${err}`, 'error');
            $("#last-updated").addClass('status-error');
        } finally {
            this.state.isRefreshing = false;
        }
    }

    // ==========================
    // DATA REFRESH
    // ==========================
    async refreshData() {
        try {
            const [camRes, agentRes, scheduleRes] = await Promise.all([
                fetch(this.endpoints.cameras),
                fetch(this.endpoints.agents),
                fetch(this.endpoints.schedule)
            ]);

            this.state.camData = await camRes.json();
            this.state.agentData = await agentRes.json();
            this.state.scheduleData = await scheduleRes.json();

            this.updateCounters();
            this.processCameras();
            this.processAgents();
            this.renderSchedule();

            $(this.selectors.lastUpdated).text(`${new Date().toLocaleString()}`);
        } catch (err) {
            CameraDashboard.logMessage(`Failed to refresh data: ${err}`, 'error');
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

    getStateCounts(arr, key = "state") {
        return arr.reduce((acc, item) => {
            const state = ((item[key] || "unknown").toLowerCase());
            acc[state] = (acc[state] || 0) + 1;
            return acc;
        }, {});
    }

    getFineAndDangerCounts(arr) {
        const counts =  arr.reduce(
            (counts, location) => {
                let isFine = location.camera_state === "online" && ["capturing", "idle"].includes(location.agent_state);
                if (this.IGNORE_SCHEDULE.includes(location.name.toLowerCase())) {
                    isFine = true;
                }

                counts[isFine ? "fine" : "danger"] += 1;
                return counts;
            },
            { fine: 0, danger: 0 }
        );
        return counts;
    }

    updateCounters() {
        const camCounts = this.getStateCounts(this.state.camData.cameras);
        const agentCounts = this.getStateCounts(this.state.agentData.agents);
        const scheduleCounts = this.getFineAndDangerCounts(this.state.scheduleData.locations);

        $("#cams-count-all").text(Object.values(camCounts).reduce((sum, val) => sum + val, 0));
        Object.entries(camCounts).forEach(([state, value]) => { $(`#cams-count-${state}`).text(value); });

        $("#agent-count-all").text(Object.values(agentCounts).reduce((sum, val) => sum + val, 0));
        Object.entries(agentCounts).forEach(([state, value]) => { $(`#agent-count-${state}`).text(value); });

        $("#schedule-count-all").text(this.state.scheduleData.locations.length);
        $("#schedule-location-count").text(this.state.scheduleData.locations.length);
        Object.entries(scheduleCounts).forEach(([state, value]) => { $(`#schedule-count-${state}`).text(value); });
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

    renderSchedule() {
        const data = this.state.scheduleData || {};
        const locations = data.locations || [];
        const $table = $(this.selectors.scheduleGrid).find("table");
        const $thead = $table.find("thead").empty();
        const $tbody = $table.find("tbody").empty();

        $("#schedule-count").text(data.total || 0);
        $("#schedule-last-refresh")
            .text(data.last_refresh ? moment(data.last_refresh).fromNow() : "never")
            .attr("title", data.last_refresh ? moment(data.last_refresh).format("ddd, D MMM YYYY, HH:mm:ss") : "");

        const dayStart = data.date ? moment(data.date, "YYYY-MM-DD") : moment().startOf("day");
        const toHours = (value) => moment(value).diff(dayStart, "hours", true);

        // Work out the visible hour range from the events (fallback to office hours)
        let first = 24, last = 0;
        locations.forEach(loc => (loc.events || []).forEach(ev => {
            first = Math.min(first, Math.floor(toHours(ev.start_date)));
            last = Math.max(last, Math.ceil(toHours(ev.end_date)));
        }));
        first = Math.max(0, first);
        last = Math.min(24, last);
        if (first >= last) { first = 7; last = 18; }

        const hours = Array.from({ length: last - first }, (_, i) => first + i);
        const nowHour = moment().isSame(dayStart, "day") ? moment().hour() : -1;

        $table.css("min-width", `${200 + hours.length * 80}px`);

        // Header
        const $headRow = $("<tr>").append($("<th>").addClass("schedule-location").text("Location"));
        hours.forEach(h => {
            $headRow.append($("<th>")
                .addClass("schedule-hour")
                .toggleClass("current-hour", h === nowHour)
                .text(`${String(h).padStart(2, "0")}:00`));
        });
        $thead.append($headRow);

        if (!locations.length) {
            $tbody.append($("<tr>").append($("<td>")
                .attr("colspan", hours.length + 1)
                .addClass("text-center text-muted py-4")
                .text("No scheduled events for today")));
            return;
        }

        // template for the scheduled location
        const location_template = document.getElementById("ScheduleLocationTemplate");
        const location_status_template = document.getElementById("ScheduleLocationStatusTemplate");
        const location_status_link_template = document.getElementById("ScheduleLocationStatusLinkTemplate");

        const isFine = (location) => this.IGNORE_SCHEDULE.includes(location.name.toLowerCase()) ||
                                        (location.camera_state === "online" &&
                                            ["capturing", "idle"].includes(location.agent_state));

        const sortedLocations = [...data.locations].sort((a, b) => {
            // Danger = 0, fine = 1, so danger comes first.
            const statusOrder = Number(isFine(a)) - Number(isFine(b));

            return statusOrder || a.name.localeCompare(b.name);
        });

        sortedLocations.forEach(loc => {
            const agentStatus = this.normalizeAgentStatus(loc.agent_state);
            const cameraStatus = loc.camera_state || "unknown";
            const pycaStatus = loc.pyca_state || "none";
            let isFine = loc.camera_state === "online" && ["capturing", "idle"].includes(loc.agent_state);
            if (this.IGNORE_SCHEDULE.includes(loc.name.toLowerCase())) {
                isFine = true;
            }

            const searchText = [loc.name, loc.display, ...(loc.events || []).map(ev => ev.title)]
                .join(" ").toLowerCase();

            const $row = $("<tr>");
            $row.attr('id', `scheduled-location-${loc.name.toLowerCase()}`);
            $row.attr('data-search', searchText); // used in filter selector
            $row.addClass(`row-${isFine ? 'fine' : 'danger'}`);
            $row.data(loc);
            $row.data('state', isFine ? 'fine' : 'danger');

            const clone = location_template.content.cloneNode(true);
            const $location = $(clone.querySelector(".schedule-location"));

            // Set the location name in the template
            $location.find(".fw-semibold").text(loc.name);
            $location.find(".small.text-muted").text(loc.display ? loc.display : loc.name);

            const $status_area = $location.find(".schedule-location-status");

            const $camera_status_block = location_status_template.content.cloneNode(true).querySelector("span");
            const $agent_status_block = location_status_template.content.cloneNode(true).querySelector("span");

            const $pyca_status_block = loc.pyca_url === null ?
                location_status_template.content.cloneNode(true).querySelector("span") :
                location_status_link_template.content.cloneNode(true).querySelector("a");

            $camera_status_block.classList.add(`status-line-${cameraStatus}`);
            $camera_status_block.setAttribute('title', `Camera: ${cameraStatus}`);
            $camera_status_block.dataset.status = 'camera';

            $agent_status_block.classList.add(`status-line-${agentStatus}`);
            $agent_status_block.setAttribute('title', `Agent: ${agentStatus}`);
            $agent_status_block.dataset.status = 'agent';

            $pyca_status_block.classList.add(`status-line-${pycaStatus}`);
            $pyca_status_block.setAttribute('title', `PyCA: ${pycaStatus}`);
            $pyca_status_block.dataset.status = 'pyca';
            if ($pyca_status_block.matches("a")) {
               $pyca_status_block.href = loc.pyca_url;
               $pyca_status_block.setAttribute('target', '_blank');
            }

            $status_area.append($camera_status_block);
            $status_area.append($agent_status_block);
            $status_area.append($pyca_status_block);

            $row.append($location);

            const $cells = hours.map(h => $("<td>")
                .addClass("schedule-hour")
                .toggleClass("current-hour", h === nowHour));

            (loc.events || []).forEach(ev => {
                const start = Math.max(first, toHours(ev.start_date));
                const end = Math.min(last, toHours(ev.end_date));
                if (end <= start) return;

                const startCol = Math.floor(start);
                const bordersCrossed = Math.max(0, Math.ceil(end) - startCol - 1);
                const status = this.normalizeEventStatus(ev.displayable_status || ev.event_status);
                const fmt = (v) => v ? moment(v).format("HH:mm") : "?";

                const tooltip = [
                    ev.title,
                    `${fmt(ev.start_date)} - ${fmt(ev.end_date)}`,
                    `Technical: ${fmt(ev.technical_start)} - ${fmt(ev.technical_end)}`,
                    `Status: ${status}`
                ].join("\n");

                $cells[startCol - first].append($("<a>")
                    .addClass(`schedule-event status-${status}`)
                    .css({
                        left: `${(start - startCol) * 100}%`,
                        width: `calc(${(end - start) * 100}% + ${bordersCrossed}px - 2px)`
                    })
                    .attr('href', '#')
                    .attr('target', '_blank')
                    .attr("title", tooltip)
                    .attr("data-event", ev.id)
                    .text(ev.title));
            });

            $row.append($cells);
            $tbody.append($row);
        });

        this.applyScheduleFilters();
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
            const matchesStatus = activeStatus === "all" || status === activeStatus;
            const show = matchesSearch && matchesStatus;

            $card.toggle(show);
            if (show) visibleCount++;
        });
    }

    applyScheduleFilters() {
        const query = ($(this.selectors.scheduleSearch).val() || "").toLowerCase().trim();
        const activeStatus = $("#scheduleStatus .active").data("status") || "all";

        // find the values in the text somewhere in the data-search attribute
        $(this.selectors.scheduleGrid).find("tbody tr[data-search]").each(function () {
            const $row = $(this);

            // Status match
            const status = ($row.data("state") || "").toLowerCase();
            const matchesStatus = activeStatus === "all" || status === activeStatus;
            const matchesSearch = !query || ($row.attr("data-search") || "").includes(query);

            $row.toggle(matchesSearch && matchesStatus);
        });
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
            CameraDashboard.logMessage(`Failed to fetch current image for camera ${cameraName}: ${err}`, 'error');
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

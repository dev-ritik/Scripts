(() => {
    "use strict";

    const $ = (id) => document.getElementById(id);

    let stats = null;
    let activeRanking = "tracks";
    let activeSort = "ms_played";
    const charts = {};

    const chartText = "#b3b3b3";
    const chartGreen = "#1ed760";


    function formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");

        // Format using local calendar dates, without UTC conversion.
        return `${year}-${month}-${day}`;
    }

// Helper: get start & end dates for a preset range.
    function getDateRange(range, customStart = null, customEnd = null) {
        const today = new Date();
        const end = new Date(today);
        let start;

        switch (range) {
            case "week":
                start = new Date(today);
                start.setDate(start.getDate() - 7);
                break;

            case "month":
                start = new Date(
                    today.getFullYear(),
                    today.getMonth() - 1,
                    today.getDate()
                );
                break;

            case "quarter":
                start = new Date(
                    today.getFullYear(),
                    today.getMonth() - 3,
                    today.getDate()
                );
                break;

            case "year":
                start = new Date(today);
                start.setFullYear(start.getFullYear() - 1);
                break;

            case "all":
                // Explicit date range; Python does not resolve this preset.
                start = new Date(1970, 0, 1);
                break;

            case "custom":
                if (!customStart || !customEnd) {
                    return null;
                }

                start = new Date(`${customStart}T00:00:00`);
                end.setTime(new Date(`${customEnd}T00:00:00`).getTime());

                if (Number.isNaN(start.getTime()) ||
                    Number.isNaN(end.getTime()) ||
                    start > end) {
                    return null;
                }
                break;

            default:
                // Fixed calendar year, e.g. "2025".
                if (/^\d{4}$/.test(range)) {
                    const year = Number.parseInt(range, 10);
                    start = new Date(year, 0, 1);
                    end.setFullYear(year, 11, 31);
                } else {
                    return null;
                }
        }

        return {
            start_date: formatDate(start),
            end_date: formatDate(end),
        };
    }


    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, char => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        })[char]);
    }

    function number(value) {
        return Number(value || 0).toLocaleString("en-IN");
    }

    function hours(value) {
        return `${Number(value || 0).toLocaleString("en-IN", {
            maximumFractionDigits: 1
        })} hrs`;
    }

    function duration(ms) {
        const totalMinutes = Math.floor(Number(ms || 0) / 60000);
        const h = Math.floor(totalMinutes / 60);
        const m = totalMinutes % 60;
        return h ? `${h}h ${m}m` : `${m}m`;
    }

    function localDate(value) {
        if (!value) return "—";
        const d = new Date(value);
        return Number.isNaN(d.getTime())
            ? "—"
            : d.toLocaleDateString("en-IN", {
                day: "2-digit",
                month: "short",
                year: "numeric"
            });
    }

    function localDateTime(value) {
        if (!value) return "—";
        const d = new Date(value);
        return Number.isNaN(d.getTime())
            ? "—"
            : d.toLocaleString("en-IN", {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit"
            });
    }

    function spotifyLink(uri) {
        if (!uri || !/^spotify:(track|episode):[A-Za-z0-9]+$/.test(uri)) {
            return null;
        }
        return "https://open.spotify.com/" +
            uri.replace("spotify:", "").replace(":", "/");
    }

    function setText(id, value) {
        $(id).textContent = value ?? "—";
    }

    function metricItem(item) {
        if (!item) return null;

        const name = Array.isArray(item.name)
            ? item.name.join(" — ")
            : item.name;

        return {
            name: name || "Unknown",
            detail: `${number(item.play_count)} plays · ${duration(item.ms_played)}`,
            uri: item.uri
        };
    }

    function renderWrapped(s) {
        setText("listeningHours", hours(s.listening_hours));
        setText("uniqueTracks", number(s.unique_tracks));
        setText("trackPlays", `${number(s.track_plays)} track plays`);
        setText("uniqueArtists", number(s.unique_artists));
        setText("uniqueAlbums", number(s.unique_albums));
        setText("averageDaily", `${number(s.average_daily_minutes)} min`);
        setText("longestStreak", `${number(s.longest_streak_days)} days`);

        setText(
            "mostActiveDay",
            s.most_active_day ? localDate(s.most_active_day.date) : "—"
        );
        setText(
            "mostActiveMinutes",
            s.most_active_day
                ? `${number(s.most_active_day.minutes)} minutes listened`
                : "No listening data"
        );

        setText("skipRate", `${number(s.skip_rate)}%`);
        setText("skipCount", `${number(s.skipped_tracks)} skipped track events`);

        const track = metricItem(s.top_track);
        const artist = metricItem(s.top_artist);
        const album = metricItem(s.top_album);

        setText("wrappedTrack", track?.name || "—");
        setText("wrappedTrackDetail", track?.detail || "");
        setText("wrappedArtist", artist?.name || "—");
        setText("wrappedArtistDetail", artist?.detail || "");
        setText("wrappedAlbum", album?.name || "—");
        setText("wrappedAlbumDetail", album?.detail || "");

        const session = s.longest_session;
        setText(
            "longestSession",
            session ? `${number(session.hours)} hrs` : "—"
        );
        setText(
            "longestSessionDetail",
            session
                ? `${number(session.plays)} plays · ${session.top_artist}`
                : "No sessions found"
        );
    }

    function destroyChart(id) {
        if (charts[id]) {
            charts[id].destroy();
            delete charts[id];
        }
    }

    function makeChart(id, config) {
        destroyChart(id);

        const canvas = $(id);
        if (!canvas) return;

        charts[id] = new Chart(canvas, {
            ...config,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                ...config.options,
                plugins: {
                    legend: {
                        labels: {color: chartText}
                    },
                    ...config.options?.plugins
                },
                scales: config.type === "doughnut" ? undefined : {
                    x: {
                        ticks: {color: chartText},
                        grid: {color: "#363636"},
                        ...config.options?.scales?.x
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {color: chartText},
                        grid: {color: "#363636"},
                        ...config.options?.scales?.y
                    },
                    ...config.options?.scales
                }
            }
        });
    }

    function renderMonthlyChart(data) {
        makeChart("monthlyChart", {
            type: "bar",
            data: {
                labels: data.map(x => x.month),
                datasets: [{
                    label: "Listening hours",
                    data: data.map(x => x.hours),
                    backgroundColor: chartGreen,
                    borderRadius: 4
                }]
            },
            options: {
                plugins: {legend: {display: false}},
                scales: {
                    y: {title: {display: true, text: "Hours"}}
                }
            }
        });
    }

    function renderDailyChart(data) {
        // For large exports, group days by month in the backend or
        // display only the most recent 180 active calendar dates.
        const visible = data.slice(-180);

        makeChart("dailyChart", {
            type: "line",
            data: {
                labels: visible.map(x => x.date),
                datasets: [{
                    label: "Minutes listened",
                    data: visible.map(x => x.minutes),
                    borderColor: chartGreen,
                    backgroundColor: "rgba(30,215,96,0.15)",
                    fill: true,
                    pointRadius: 1,
                    tension: 0.25
                }]
            },
            options: {
                plugins: {legend: {display: false}},
                scales: {
                    y: {title: {display: true, text: "Minutes"}}
                }
            }
        });
    }

    function renderHourlyChart(data) {
        makeChart("hourlyChart", {
            type: "bar",
            data: {
                labels: data.map(x => `${String(x.hour).padStart(2, "0")}:00`),
                datasets: [{
                    label: "Listening hours",
                    data: data.map(x => x.hours),
                    backgroundColor: chartGreen,
                    borderRadius: 4
                }]
            },
            options: {
                plugins: {legend: {display: false}},
                scales: {
                    y: {title: {display: true, text: "Hours"}}
                }
            }
        });
    }

    function renderWeekdayChart(data) {
        makeChart("weekdayChart", {
            type: "bar",
            data: {
                labels: data.map(x => x.day),
                datasets: [{
                    label: "Listening hours",
                    data: data.map(x => x.hours),
                    backgroundColor: data.map(x =>
                        ["Saturday", "Sunday"].includes(x.day)
                            ? "#1ed760"
                            : "#168d43"
                    ),
                    borderRadius: 4
                }]
            },
            options: {
                plugins: {legend: {display: false}},
                scales: {
                    y: {title: {display: true, text: "Hours"}}
                }
            }
        });
    }

    function renderHeatmap(data) {
        const root = $("listeningHeatmap");
        root.replaceChildren();

        const lookup = new Map(
            data.map(x => [`${x.weekday}-${x.hour}`, x.minutes])
        );

        const max = Math.max(1, ...data.map(x => x.minutes));
        const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

        const corner = document.createElement("div");
        root.appendChild(corner);

        for (let h = 0; h < 24; h++) {
            const label = document.createElement("div");
            label.className = "heatmap-hour";
            label.textContent = h % 3 === 0 ? String(h).padStart(2, "0") : "";
            root.appendChild(label);
        }

        for (let day = 0; day < 7; day++) {
            const label = document.createElement("div");
            label.className = "heatmap-label";
            label.textContent = days[day];
            root.appendChild(label);

            for (let hour = 0; hour < 24; hour++) {
                const minutes = lookup.get(`${day}-${hour}`) || 0;
                const cell = document.createElement("div");
                cell.className = "heatmap-cell";

                const intensity = minutes / max;
                cell.style.backgroundColor = minutes
                    ? `rgba(30, 215, 96, ${0.15 + 0.85 * intensity})`
                    : "#292929";

                cell.title =
                    `${days[day]} ${String(hour).padStart(2, "0")}:00 — ` +
                    `${number(minutes)} minutes`;

                root.appendChild(cell);
            }
        }
    }

    function rankingData() {
        if (!stats) return [];

        const source = {
            tracks: stats.top_tracks,
            artists: stats.top_artists,
            albums: stats.top_albums,
            skipped: stats.most_skipped
        }[activeRanking] || [];

        return [...source].sort((a, b) => {
            if (activeRanking === "skipped") {
                return b.skips - a.skips ||
                    b.play_count - a.play_count;
            }

            return b[activeSort] - a[activeSort];
        });
    }

    function renderRanking() {
        const root = $("spotifyRanking");
        root.replaceChildren();

        const data = rankingData();

        if (!data.length) {
            root.innerHTML = '<div class="spotify-empty">No data for this range.</div>';
            return;
        }

        data.forEach((item, index) => {
            const row = document.createElement("div");
            row.className = "spotify-ranking-row";

            const rawName = Array.isArray(item.name)
                ? item.name
                : [item.name];

            const name = rawName.join(" — ");
            const stat = activeRanking === "skipped"
                ? `${number(item.skips)} skips`
                : activeSort === "play_count"
                    ? `${number(item.play_count)} plays`
                    : duration(item.ms_played);

            const href = spotifyLink(item.uri);
            const nameHtml = href
                ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(name)}</a>`
                : escapeHtml(name);

            row.innerHTML = `
                <div class="spotify-rank">${index + 1}</div>
                <div>
                    <div class="spotify-track-name">${nameHtml}</div>
                    <div class="spotify-track-subtitle">
                        ${number(item.play_count)} plays ·
                        ${duration(item.ms_played)}
                        ${item.first_play ? " · First: " + escapeHtml(localDate(item.first_play)) : ""}
                    </div>
                </div>
                <div class="spotify-track-stat">
                    <strong>${escapeHtml(stat)}</strong>
                    <span>${number(item.skips)} skips</span>
                </div>
            `;

            root.appendChild(row);
        });
    }

    function renderSessions(sessions) {
        const root = $("sessionsTable");
        root.replaceChildren();

        if (!sessions.length) {
            root.innerHTML =
                '<tr><td colspan="5">No listening sessions found.</td></tr>';
            return;
        }

        sessions.forEach(s => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${escapeHtml(localDateTime(s.start))}</td>
                <td>${escapeHtml(localDateTime(s.end))}</td>
                <td>${number(s.plays)}</td>
                <td>${hours(s.hours)}</td>
                <td>${escapeHtml(s.top_artist)}</td>
            `;
            root.appendChild(tr);
        });
    }

    function renderAll(data) {
        stats = data;
        const s = data.summary;

        $("rangeLabel").textContent =
            `${localDate(data.range.start)} – ${localDate(data.range.end)}`;

        renderWrapped(s);
        renderMonthlyChart(data.monthly);
        renderDailyChart(data.daily);
        renderHourlyChart(data.hourly);
        renderWeekdayChart(data.weekday);
        renderHeatmap(data.weekday_hourly || []);
        renderRanking();
        renderSessions(data.longest_sessions);
    }


    async function loadStats(range, startDate, endDate) {
        const status = $("spotifyStatus");
        status.className = "spotify-status";
        status.textContent = "Loading your listening history...";

        // Resolve dates in JavaScript for every range.
        const dates = getDateRange(range, startDate, endDate);

        if (!dates) {
            status.className = "spotify-status error";
            status.textContent = range === "custom"
                ? "Please choose valid start and end dates."
                : "Unable to resolve the selected date range.";
            return;
        }

        const params = new URLSearchParams({
            range,
            start_date: dates.start_date,
            end_date: dates.end_date,
        });

        try {
            const response = await fetch(
                `/Spotify/get_stats?${params.toString()}`
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Unable to load Spotify insights.");
            }

            renderAll(data);
            status.textContent =
                `${number(data.summary.total_plays)} play events loaded`;
        } catch (error) {
            status.className = "spotify-status error";
            status.textContent = error.message;
        }
    }

    function init() {
        const range = $("range");
        const custom = $("customDateInputs");

        range.addEventListener("change", () => {
            custom.style.display = range.value === "custom" ? "flex" : "none";

            if (range.value !== "custom") {
                loadStats(range.value);
            }
        });

        $("applyCustomRange").addEventListener("click", () => {
            loadStats(
                "custom",
                $("fromDate").value,
                $("toDate").value
            );
        });

        document.querySelectorAll("[data-ranking]").forEach(button => {
            button.addEventListener("click", () => {
                activeRanking = button.dataset.ranking;

                document.querySelectorAll("[data-ranking]").forEach(b =>
                    b.classList.toggle("active", b === button)
                );

                renderRanking();
            });
        });

        document.querySelectorAll("[data-sort]").forEach(button => {
            button.addEventListener("click", () => {
                activeSort = button.dataset.sort;

                document.querySelectorAll("[data-sort]").forEach(b =>
                    b.classList.toggle("active", b === button)
                );

                renderRanking();
            });
        });

        loadStats("all");
    }

    document.addEventListener("DOMContentLoaded", init);
})();

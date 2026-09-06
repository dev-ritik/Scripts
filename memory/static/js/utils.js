// /static/js/utils.js

export async function loadPeople() {
    const CACHE_KEY = "people";
    const TTL = 60 * 60 * 1000; // 1 hour in milliseconds

    const cachedData = localStorage.getItem(CACHE_KEY);
    const now = new Date().getTime();

    if (cachedData) {
        const item = JSON.parse(cachedData);
        // Check if the current time is still before the expiry time
        if (now < item.expiry) {
            return item.value;
        }
        // If expired, optional: clear it immediately
        localStorage.removeItem(CACHE_KEY);
    }

    // If we reach here, data is either missing or expired
    try {
        const res = await fetch("/people_data");
        if (!res.ok) throw new Error("Network response was not ok");

        const people = await res.json();

        // Wrap the data with an expiry timestamp
        const itemToStore = {
            value: people,
            expiry: now + TTL
        };

        localStorage.setItem(CACHE_KEY, JSON.stringify(itemToStore));
        return people;
    } catch (err) {
        console.error("Failed to fetch people:", err);
        return []; // Return empty array or previous cache as a fallback
    }
}

async function loadAppSettings() {
    try {
        const response = await fetch("/api/settings");

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const settings = await response.json();

        document.getElementById("current-mode").textContent =
            settings.mode;

        document.getElementById("debug-mode").textContent =
            settings.debug ? "ON" : "OFF";

        return settings;
    } catch (error) {
        console.error("Failed to load application settings:", error);

        document.getElementById("current-mode").textContent = "ERROR";
        document.getElementById("debug-mode").textContent = "ERROR";

        return null;
    }
}

loadAppSettings();

window.loadAppSettings = loadAppSettings;
window.loadPeople = loadPeople;

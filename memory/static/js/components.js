export function createAvatar(sender, isHidden) {
    const avatarDiv = document.createElement('div');
    avatarDiv.className = `avatar ${isHidden ? 'hidden' : ''}`;

    if (sender) {
        const img = document.createElement('img');
        img.src = `/user/dp/${encodeURIComponent(sender)}`;
        img.style.cssText = 'width:100%;height:100%;border-radius:50%;object-fit:cover;';

        const fallback = document.createElement('div');
        fallback.style.cssText = 'display:none;width:100%;height:100%;align-items:center;justify-content:center;';
        fallback.textContent = sender[0]?.toUpperCase() || '';

        img.onerror = function () {
            this.style.display = 'none';
            fallback.style.display = 'flex';
        };

        avatarDiv.appendChild(img);
        avatarDiv.appendChild(fallback);
    }
    return avatarDiv;
}

export function createMediaElement(event) {
    const mediaWrapper = document.createElement('div');
    mediaWrapper.style.maxWidth = '300px';
    mediaWrapper.style.margin = '5px 0';

    const ctx = event.context || {};
    const mimeType = ctx.mime_type;
    const assetUrl = mimeType ? `/asset/${event.provider}/${ctx.asset_id}` : '';

    if (mimeType?.startsWith('image/')) {
        const img = document.createElement('img');
        img.loading = 'lazy';
        img.decoding = 'async';
        img.src = assetUrl;
        img.style.cssText = 'width:100%;border-radius:8px;cursor:pointer;';
        img.onclick = () => window.open(ctx.new_tab_url, '_blank');
        mediaWrapper.appendChild(img);
    } else if (mimeType?.startsWith('video/')) {
        const video = document.createElement('video');
        video.controls = true;
        video.preload = 'none';
        video.style.cssText = 'width:100%;border-radius:8px;';

        const source = document.createElement('source');
        source.src = assetUrl;
        source.type = mimeType === 'video/quicktime' ? 'video/mp4' : mimeType;

        video.appendChild(source);
        mediaWrapper.appendChild(video);
    } else if (mimeType === 'audio/ogg') {
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.preload = 'none';
        audio.style.cssText = 'width:100%;min-height:40px;border-radius:8px;';

        const source = document.createElement('source');
        source.src = assetUrl;
        source.type = 'audio/webm; codecs=opus';

        audio.appendChild(source);
        mediaWrapper.appendChild(audio);
    } else if (ctx.coordinates) {
        mediaWrapper.appendChild(createLeafletMap(ctx.coordinates, event.message));
    } else if (ctx.location === true) {
        mediaWrapper.appendChild(createLocationCard(event));
    } else {
        const p = document.createElement('p');
        p.textContent = `Unsupported media type: ${mimeType}`;
        mediaWrapper.appendChild(p);
    }

    return mediaWrapper;
}

export function createLeafletMap(coordinates, popupMessage) {
    const mapDiv = document.createElement('div');
    mapDiv.style.cssText = 'height:300px;width:100%;margin-top:8px;';

    // Defer Leaflet initialization until element is added to DOM
    setTimeout(() => {
        const map = L.map(mapDiv).setView(coordinates[0], 13);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap'
        }).addTo(map);

        if (coordinates.length > 1) {
            L.marker(coordinates[0]).addTo(map).bindPopup(popupMessage || '');
            L.polyline(coordinates, { color: '#3388ff', weight: 4 }).addTo(map);

            coordinates.forEach((point, i) => {
                if (i === 0) return;
                const prev = coordinates[i - 1];
                const angle = Math.atan2(point[0] - prev[0], point[1] - prev[1]) * 180 / Math.PI;

                L.marker(point, {
                    icon: L.divIcon({
                        className: 'arrow-icon',
                        html: '➤',
                        iconSize: [20, 20],
                        iconAnchor: [10, 10]
                    }),
                    rotationAngle: angle
                }).addTo(map);
            });
        } else {
            L.marker(coordinates[0]).addTo(map).bindPopup(popupMessage || '');
        }

        map.invalidateSize();
    }, 0);

    return mapDiv;
}

function createLocationCard(event) {
    const container = document.createElement('div');
    container.className = 'whatsapp-location-container';

    const iconDiv = document.createElement('div');
    iconDiv.className = 'whatsapp-location-icon';
    iconDiv.textContent = '📍';

    const textDiv = document.createElement('div');
    textDiv.className = 'whatsapp-location-details';

    const titleSpan = document.createElement('span');
    titleSpan.className = 'whatsapp-location-title';
    titleSpan.textContent = event.message || 'Live location';

    const subtitleSpan = document.createElement('span');
    subtitleSpan.className = 'whatsapp-location-subtitle';
    subtitleSpan.textContent = 'Live location sharing started';

    textDiv.appendChild(titleSpan);
    textDiv.appendChild(subtitleSpan);
    container.appendChild(iconDiv);
    container.appendChild(textDiv);

    if (event.context?.coordinates) {
        const mapDiv = document.createElement('div');
        mapDiv.className = 'whatsapp-location-attached-map';
        container.appendChild(mapDiv);

        setTimeout(() => {
            const map = L.map(mapDiv, { zoomControl: false }).setView(event.context.coordinates[0], 14);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap'
            }).addTo(map);
            L.marker(event.context.coordinates[0]).addTo(map);
            map.invalidateSize();
        }, 0);
    }

    return container;
}

export function createVoiceCallCard(context) {
    const callContainer = document.createElement('div');
    callContainer.className = 'voice-call-container';

    const isMissed = context.voice_call_status === 'Missed';

    const iconDiv = document.createElement('div');
    iconDiv.className = `voice-call-icon ${isMissed ? 'missed' : ''}`;
    iconDiv.textContent = isMissed ? '🚫' : '📞';

    const detailsDiv = document.createElement('div');
    detailsDiv.className = 'voice-call-details';

    const titleDiv = document.createElement('div');
    titleDiv.className = `voice-call-title ${isMissed ? 'missed' : ''}`;
    titleDiv.textContent = isMissed ? 'Missed voice call' : 'Voice call';

    detailsDiv.appendChild(titleDiv);

    if (!isMissed && context.voice_call_duration) {
        const durationDiv = document.createElement('div');
        durationDiv.className = 'voice-call-duration';
        durationDiv.textContent = context.voice_call_duration;
        detailsDiv.appendChild(durationDiv);
    }

    callContainer.appendChild(iconDiv);
    callContainer.appendChild(detailsDiv);
    return callContainer;
}
/**
 * Processes message text with formatting entities and auto-links.
 * @param {string} text
 * @param {Array} rawEntities
 * @returns {DocumentFragment}
 */
export function formatMessageText(text = '', rawEntities = []) {
    const fragment = document.createDocumentFragment();
    const entities = [...rawEntities];

    // Fallback URL detection for unformatted links
    const urlRegex = /https?:\/\/[^\s]+/g;
    let match;
    while ((match = urlRegex.exec(text)) !== null) {
        const start = match.index;
        const end = start + match[0].length;
        const isCovered = entities.some(ent => ent.offset <= start && (ent.offset + ent.length) >= end);
        if (!isCovered) {
            entities.push({
                type: 'link',
                offset: start,
                length: match[0].length,
                url: match[0]
            });
        }
    }

    // Collect boundary indices
    const boundaries = new Set([0, text.length]);
    entities.forEach(ent => {
        const start = Math.max(0, Math.min(ent.offset, text.length));
        const end = Math.max(0, Math.min(ent.offset + ent.length, text.length));
        boundaries.add(start);
        boundaries.add(end);
    });

    const sortedBoundaries = Array.from(boundaries).sort((a, b) => a - b);

    // Slice and wrap text node chunks
    for (let i = 0; i < sortedBoundaries.length - 1; i++) {
        const startIdx = sortedBoundaries[i];
        const endIdx = sortedBoundaries[i + 1];
        const sliceText = text.substring(startIdx, endIdx);
        if (!sliceText) continue;

        const activeEntities = entities.filter(ent => ent.offset <= startIdx && (ent.offset + ent.length) >= endIdx);
        activeEntities.sort((a, b) => a.type.localeCompare(b.type));

        let currentElement;
        const mentionEntity = activeEntities.find(ent => ent.type === 'mention');
        const linkEntity = activeEntities.find(ent => ent.type === 'link');

        if (mentionEntity?.display_name) {
            currentElement = document.createElement('a');
            currentElement.href = `/user/profile/${encodeURIComponent(mentionEntity.display_name)}`;
            currentElement.target = '_blank';
            currentElement.rel = 'noopener noreferrer';
            currentElement.className = 'mention-link';
        } else if (linkEntity) {
            const url = linkEntity.url || sliceText;
            if (url.includes('instagram.com')) {
                fragment.appendChild(createInstagramEmbed(url));
                continue;
            }
            currentElement = document.createElement('a');
            currentElement.href = url;
            currentElement.target = '_blank';
            currentElement.rel = 'noopener noreferrer';
        } else {
            currentElement = document.createElement('span');
        }

        // Apply styles
        activeEntities.forEach(ent => {
            if (ent.type === 'bold') currentElement.style.fontWeight = 'bold';
            if (ent.type === 'italic') currentElement.style.fontStyle = 'italic';
            if (ent.type === 'strike') currentElement.style.textDecoration = 'line-through';
            if (ent.type === 'code') {
                currentElement.style.fontFamily = 'monospace';
                currentElement.style.backgroundColor = 'rgba(0, 0, 0, 0.05)';
                currentElement.style.padding = '2px 4px';
                currentElement.style.borderRadius = '3px';
            }
        });

        // Insert newlines
        const lines = sliceText.split('\n');
        lines.forEach((line, lineIdx) => {
            if (lineIdx > 0) currentElement.appendChild(document.createElement('br'));
            if (line) currentElement.appendChild(document.createTextNode(line));
        });

        fragment.appendChild(currentElement);
    }

    return fragment;
}

function createInstagramEmbed(url) {
    const blockquote = document.createElement('blockquote');
    blockquote.className = 'instagram-media';
    blockquote.dataset.instgrmCaptioned = '';
    blockquote.dataset.instgrmPermalink = `${url}?utm_source=ig_embed&utm_campaign=loading`;
    blockquote.dataset.instgrmVersion = '14';
    blockquote.style.cssText = 'background:#FFF;border:0;border-radius:3px;box-shadow:0 0 1px 0 rgba(0,0,0,0.5),0 1px 10px 0 rgba(0,0,0,0.15);margin:1px;max-width:540px;min-width:326px;padding:0;width:calc(100% - 2px);display:block;';

    const innerDiv = document.createElement('div');
    innerDiv.style.padding = '16px';
    innerDiv.innerHTML = `<a href="${url}?utm_source=ig_embed&utm_campaign=loading" style="background:#FFFFFF;line-height:0;text-align:center;text-decoration:none;width:100%;" target="_blank">View this post on Instagram</a>`;

    blockquote.appendChild(innerDiv);
    return blockquote;
}
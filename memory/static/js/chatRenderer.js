import { formatMessageText } from './formatters.js';
import { createAvatar, createMediaElement, createVoiceCallCard } from './components.js';

export function renderChat(events) {
    const container = document.getElementById('chatContainer');
    container.innerHTML = '';

    if (!events || events.length === 0) {
        container.innerHTML = '<p>No memories found. Please select a date and search.</p>';
        return;
    }

    const header = document.createElement('div');
    header.className = 'chat-header';
    header.innerHTML = '<h2 style="margin: 0;">Memory</h2>';
    container.appendChild(header);

    const state = {
        current_provider: null,
        previous_sender: null,
        previous_chat: null,
        lastRenderedDate: null
    };

    events.forEach(event => {
        // Date header check
        if (typeof window.insertDateDividerIfNeeded === 'function') {
            window.insertDateDividerIfNeeded(container, state, event.datetime);
        }

        // Provider divider
        if (event.provider !== state.current_provider) {
            state.current_provider = event.provider;
            const providerDiv = document.createElement('div');
            providerDiv.className = 'provider-header';
            providerDiv.textContent = event.provider;
            container.appendChild(providerDiv);
        }

        const isConsecutive = event.sender === state.previous_sender && event.chat_name === state.previous_chat;
        const isSent = event.type === 'sent';

        const eventDiv = document.createElement('div');
        eventDiv.className = `event ${isConsecutive ? 'consecutive' : ''} ${isSent ? 'sent-message' : ''}`;

        // Render Avatar
        const avatarDiv = createAvatar(event.sender, isConsecutive || isSent);
        eventDiv.appendChild(avatarDiv);

        // Render Message Block
        const messageDiv = document.createElement('div');
        messageDiv.className = `message-content ${isConsecutive ? 'consecutive' : ''} ${isSent ? 'sent' : ''}`;

        // Sender Name
        const senderNameDiv = document.createElement('div');
        senderNameDiv.className = `sender-name ${isConsecutive ? 'hidden' : ''}`;
        senderNameDiv.textContent = event.sender + (event.chat_name ? ` • ${event.chat_name}` : '');
        messageDiv.appendChild(senderNameDiv);

        // Message Body
        const messageTextDiv = document.createElement('div');
        messageTextDiv.className = 'message-text';

        // 1. Media
        if (['non_text', 'mixed'].includes(event.media_type) && event.context) {
            messageTextDiv.appendChild(createMediaElement(event));
        }

        // 2. Text Content
        if (['text', 'mixed'].includes(event.media_type) && event.message) {
            messageTextDiv.appendChild(formatMessageText(event.message, event.formatting));
        }

        // 3. Special Context (Voice Call / Deleted)
        if (event.context?.voice_call === true) {
            messageDiv.appendChild(createVoiceCallCard(event.context));
        } else {
            if (event.context?.deleted === true) {
                messageTextDiv.append('This message was deleted');
                messageTextDiv.classList.add('message-deleted');
            }
            messageDiv.appendChild(messageTextDiv);
        }

        // 4. Timestamp & Status
        const messageTimeDiv = document.createElement('div');
        messageTimeDiv.className = 'message-time';

        const timeSpan = document.createElement('span');
        timeSpan.textContent = new Date(event.datetime).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });
        messageTimeDiv.appendChild(timeSpan);

        if (event.context?.edited === true) {
            const editedSpan = document.createElement('span');
            editedSpan.className = 'message-edited';
            editedSpan.textContent = 'Edited';
            messageTimeDiv.appendChild(editedSpan);
        }

        messageDiv.appendChild(messageTimeDiv);
        eventDiv.appendChild(messageDiv);
        container.appendChild(eventDiv);

        state.previous_sender = event.sender;
        state.previous_chat = event.chat_name;
    });

    if (window.instgrm) {
        window.instgrm.Embeds.process();
    }
}

window.renderChat = renderChat;

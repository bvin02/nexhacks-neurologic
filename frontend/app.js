/**
 * DecisionOS - Frontend Application
 * Project Continuity Copilot
 * 
 * Two Chat Modes:
 * - Project Chat: Stateless, memory-first (ingests every message)
 * - Work Chat: Conversational sessions (ingests only on session end)
 */

// API Configuration
const API_BASE = 'http://localhost:8000';

// Application State
const state = {
    currentProject: null,
    projects: [],
    ledger: null,
    timeline: [],
    lastDebugInfo: null,

    // Project Chat state (stateless)
    projectChatHistory: [], // Array of {user, assistant} pairs
    projectChatIndex: 0,
    projectChatMode: 'fast',

    // Work Chat state (session-based)
    workSession: null, // {session_id, task_description}
    workMessages: [],
    workChatMode: 'balanced',
};

// DOM Elements
const elements = {
    loadingOverlay: document.getElementById('loading-overlay'),
    projectSelect: document.getElementById('project-select'),
    newProjectBtn: document.getElementById('new-project-btn'),
    whyDrawer: document.getElementById('why-drawer'),
    closeDrawer: document.getElementById('close-drawer'),
    projectModal: document.getElementById('project-modal'),
    memoryModal: document.getElementById('memory-modal'),
    ledgerContent: document.getElementById('ledger-content'),
    timelineContent: document.getElementById('timeline-content'),
    statTotal: document.getElementById('stat-total'),
    statActive: document.getElementById('stat-active'),
    statDisputed: document.getElementById('stat-disputed'),

    // Project Context elements
    projectContextBtn: document.getElementById('project-context-btn'),
    projectContextOverlay: document.getElementById('project-context-overlay'),
    projectChatMessages: document.getElementById('project-chat-messages'),
    projectChatInput: document.getElementById('project-chat-input'),
    projectSendBtn: document.getElementById('project-send-btn'),
    projectChatPrev: document.getElementById('project-chat-prev'),
    projectChatNext: document.getElementById('project-chat-next'),
    projectChatCounter: document.getElementById('project-chat-counter'),

    // Work Chat elements
    startTaskScreen: document.getElementById('start-task-screen'),
    workChatScreen: document.getElementById('work-chat-screen'),
    startTaskBtn: document.getElementById('start-task-btn'),
    workTaskDescription: document.getElementById('work-task-description'),
    workChatMessages: document.getElementById('work-chat-messages'),
    workChatInput: document.getElementById('work-chat-input'),
    workSendBtn: document.getElementById('work-send-btn'),
    taskCompletedBtn: document.getElementById('task-completed-btn'),

    // Task Modal
    taskModal: document.getElementById('task-modal'),
    taskDescriptionInput: document.getElementById('task-description-input'),
    beginTaskBtn: document.getElementById('begin-task-btn'),

    // Observability Panel
    observabilityNotifications: document.getElementById('observability-notifications'),
};

// SSE Event Source (for real-time pipeline notifications)
let eventSource = null;
let currentTurnId = null;

function connectToEventStream(projectId) {
    // Close existing connection
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`${API_BASE}/projects/${projectId}/events`);

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handlePipelineEvent(data);
        } catch (e) {
            console.error('Failed to parse SSE event:', e);
        }
    };

    eventSource.onerror = (error) => {
        console.log('SSE connection error, will retry...', error);
    };
}

function disconnectEventStream() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
}

function handlePipelineEvent(event) {
    if (!elements.observabilityNotifications) return;

    // Skip connection events
    if (event.event_type === 'connected') return;

    // Clear old notifications only if new turn starts (turn_id changes)
    if (currentTurnId && event.turn_id && event.turn_id !== currentTurnId) {
        // Immediately clear for new turn
        elements.observabilityNotifications.innerHTML = '';
    }
    currentTurnId = event.turn_id;

    // Create notification tile
    const tile = document.createElement('div');
    tile.className = `notification-tile ${event.event_type}`;

    // Add message text
    const messageSpan = document.createElement('span');
    messageSpan.className = 'notification-message';
    messageSpan.textContent = event.message;
    tile.appendChild(messageSpan);

    // Add context based on event type
    const contextDiv = document.createElement('div');
    contextDiv.className = 'notification-context';
    
    switch (event.event_type) {
        case 'intent_classified':
            if (event.data) {
                const badges = [];
                if (event.data.requires_memory) badges.push('Memory');
                if (event.data.requires_enforcement) badges.push('Enforcement');
                if (badges.length > 0) {
                    contextDiv.innerHTML = `<span class="notification-badges">${badges.join(' • ')}</span>`;
                    tile.appendChild(contextDiv);
                }
            }
            break;
            
        case 'memories_retrieved':
            if (event.data?.previews?.length > 0) {
                const previewsHtml = event.data.previews.map(p => 
                    `<div class="memory-preview">
                        <span class="memory-type-badge">${p.type}</span>
                        <span class="memory-text">${escapeHtml(p.preview)}</span>
                    </div>`
                ).join('');
                contextDiv.innerHTML = previewsHtml;
                tile.appendChild(contextDiv);
            }
            // Add memory ID pills
            if (event.data?.memory_ids?.length > 0) {
                const pillsContainer = document.createElement('div');
                pillsContainer.className = 'notification-pills';
                event.data.memory_ids.slice(0, 5).forEach(memId => {
                    const pill = document.createElement('span');
                    pill.className = 'citation-link';
                    pill.textContent = memId.substring(0, 8);
                    pill.onclick = () => navigateToMemory(memId);
                    pillsContainer.appendChild(pill);
                });
                if (event.data.memory_ids.length > 5) {
                    const more = document.createElement('span');
                    more.className = 'notification-note';
                    more.textContent = `+${event.data.memory_ids.length - 5} more`;
                    pillsContainer.appendChild(more);
                }
                tile.appendChild(pillsContainer);
            }
            break;
            
        case 'candidates_created':
            if (event.data?.previews?.length > 0) {
                const previewsHtml = event.data.previews.map(p => 
                    `<div class="memory-preview">
                        <span class="memory-type-badge">${p.type}</span>
                        <span class="memory-text">${escapeHtml(p.preview)}</span>
                    </div>`
                ).join('');
                contextDiv.innerHTML = previewsHtml;
                tile.appendChild(contextDiv);
            }
            break;
            
        case 'classified':
            if (event.data?.type_counts) {
                const countsHtml = Object.entries(event.data.type_counts)
                    .map(([type, count]) => `<span class="type-count-badge">${type}: ${count}</span>`)
                    .join('');
                contextDiv.innerHTML = `<div class="type-counts">${countsHtml}</div>`;
                tile.appendChild(contextDiv);
            }
            break;
            
        case 'generating':
            if (event.data?.model_tier) {
                const tierLabel = event.data.model_tier === 'cheap' ? 'quick' : event.data.model_tier;
                contextDiv.innerHTML = `<span class="model-tier-badge">${tierLabel} model</span>`;
                tile.appendChild(contextDiv);
            }
            break;
            
        case 'dedup_found':
            // Show preview and clickable memory ID pill
            if (event.data) {
                if (event.data.preview) {
                    const previewHtml = `<div class="memory-preview">
                        <span class="memory-type-badge">${event.data.type || 'memory'}</span>
                        <span class="memory-text">${escapeHtml(event.data.preview)}</span>
                    </div>`;
                    contextDiv.innerHTML = previewHtml;
                    tile.appendChild(contextDiv);
                }
                // Add clickable pill to navigate to the merged memory
                if (event.data.memory_id) {
                    const pillsContainer = document.createElement('div');
                    pillsContainer.className = 'notification-pills';
                    const pill = document.createElement('span');
                    pill.className = 'citation-link';
                    pill.textContent = event.data.memory_id.substring(0, 8);
                    pill.onclick = () => navigateToMemory(event.data.memory_id);
                    pillsContainer.appendChild(pill);
                    tile.appendChild(pillsContainer);
                }
            }
            break;
            
        case 'summary_generated':
            if (event.data?.summary_preview) {
                const previewSpan = document.createElement('div');
                previewSpan.className = 'notification-note';
                previewSpan.textContent = event.data.summary_preview;
                tile.appendChild(previewSpan);
            }
            break;
    }

    // For complete events and session_complete events, add memory citation pills
    if (event.event_type === 'complete' || event.event_type === 'session_complete') {
        if (event.data?.memory_ids?.length > 0) {
            const pillsContainer = document.createElement('div');
            pillsContainer.className = 'notification-pills';

            event.data.memory_ids.forEach(memId => {
                const pill = document.createElement('span');
                pill.className = 'citation-link';
                pill.textContent = memId.substring(0, 8);
                pill.onclick = () => navigateToMemory(memId);
                pillsContainer.appendChild(pill);
            });

            tile.appendChild(pillsContainer);
        } else {
            // No memories created
            const noMemSpan = document.createElement('div');
            noMemSpan.className = 'notification-note';
            noMemSpan.textContent = 'No new memories created';
            tile.appendChild(noMemSpan);
        }
    }

    // Add connector if not first
    if (elements.observabilityNotifications.children.length > 0) {
        const connector = document.createElement('div');
        connector.className = 'notification-connector';
        elements.observabilityNotifications.appendChild(connector);
    }

    elements.observabilityNotifications.appendChild(tile);

    // Scroll to bottom
    elements.observabilityNotifications.scrollTop = elements.observabilityNotifications.scrollHeight;
}

function fadeOutOldNotifications() {
    if (!elements.observabilityNotifications) return;
    elements.observabilityNotifications.innerHTML = '';
    currentTurnId = null;
}

// ================================================
// API Functions
// ================================================

async function api(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    };

    if (config.body && typeof config.body === 'object') {
        config.body = JSON.stringify(config.body);
    }

    try {
        const response = await fetch(url, config);
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        throw error;
    }
}

// Projects API
const projectsApi = {
    list: () => api('/projects'),
    get: (id) => api(`/projects/${id}`),
    create: (data) => api('/projects', { method: 'POST', body: data }),
    update: (id, data) => api(`/projects/${id}`, { method: 'PATCH', body: data }),
    delete: (id) => api(`/projects/${id}`, { method: 'DELETE' }),
};

// Chat API (Project Chat - stateless)
const chatApi = {
    send: (projectId, message, mode) => api(`/projects/${projectId}/chat`, {
        method: 'POST',
        body: { message, mode },
    }),
    ingest: (projectId, data) => api(`/projects/${projectId}/ingest`, {
        method: 'POST',
        body: data,
    }),
    timeline: (projectId) => api(`/projects/${projectId}/timeline`),
};

// Work Session API
const workApi = {
    start: (projectId, taskDescription) => api(`/projects/${projectId}/work/start`, {
        method: 'POST',
        body: { task_description: taskDescription },
    }),
    getActive: (projectId) => api(`/projects/${projectId}/work/active`),
    getMessages: (projectId, sessionId) => api(`/projects/${projectId}/work/${sessionId}/messages`),
    sendMessage: (projectId, sessionId, message, mode) => api(`/projects/${projectId}/work/${sessionId}/message`, {
        method: 'POST',
        body: { message, mode },
    }),
    endSession: (projectId, sessionId) => api(`/projects/${projectId}/work/${sessionId}/end`, {
        method: 'POST',
        body: {},
    }),
};

// Memory API
const memoryApi = {
    ledger: (projectId) => api(`/projects/${projectId}/ledger`),
    get: (projectId, memoryId) => api(`/projects/${projectId}/memory/${memoryId}`),
    versions: (projectId, memoryId) => api(`/projects/${projectId}/memory/${memoryId}/versions`),
    resolve: (projectId, memoryId, data) => api(`/projects/${projectId}/memory/${memoryId}/resolve`, {
        method: 'POST',
        body: data,
    }),
    create: (projectId, data) => api(`/projects/${projectId}/memory`, {
        method: 'POST',
        body: data,
    }),
};

// Ops API
const opsApi = {
    list: (projectId, limit = 100) => api(`/projects/${projectId}/ops?limit=${limit}`),
};

// ================================================
// UI Initialization
// ================================================

function initializeApp() {
    // Navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => switchView(item.dataset.view));
    });

    // Ledger filters
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderLedger(btn.dataset.type);
        });
    });

    // Project management
    elements.projectSelect.addEventListener('change', handleProjectChange);
    elements.newProjectBtn.addEventListener('click', openProjectModal);
    document.getElementById('create-project-btn').addEventListener('click', createProject);

    // Why drawer
    elements.closeDrawer.addEventListener('click', closeWhyDrawer);

    // Project Context overlay
    initProjectContextChat();

    // Work Chat
    initWorkChat();

    // Load projects
    loadProjects();
}

// ================================================
// Project Context Chat (Stateless)
// ================================================

function initProjectContextChat() {
    // Toggle overlay
    elements.projectContextBtn.addEventListener('click', toggleProjectContextOverlay);

    // Close overlay when clicking outside
    document.addEventListener('click', (e) => {
        const overlay = elements.projectContextOverlay;
        const btn = elements.projectContextBtn;
        if (overlay.classList.contains('open') &&
            !overlay.contains(e.target) &&
            !btn.contains(e.target)) {
            overlay.classList.remove('open');
        }
    });

    // Quality selector for project chat
    const miniQualityBtns = elements.projectContextOverlay.querySelectorAll('.quality-btn');
    miniQualityBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            miniQualityBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.projectChatMode = btn.dataset.mode;
        });
    });

    // Input handling
    elements.projectChatInput.addEventListener('input', () => {
        elements.projectSendBtn.disabled = !elements.projectChatInput.value.trim() || !state.currentProject;
    });
    elements.projectChatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!elements.projectSendBtn.disabled) {
                sendProjectChatMessage();
            }
        }
    });
    elements.projectSendBtn.addEventListener('click', sendProjectChatMessage);

    // Navigation arrows
    elements.projectChatPrev.addEventListener('click', () => navigateProjectChat(-1));
    elements.projectChatNext.addEventListener('click', () => navigateProjectChat(1));
}

function toggleProjectContextOverlay() {
    elements.projectContextOverlay.classList.toggle('open');
}

async function sendProjectChatMessage() {
    const message = elements.projectChatInput.value.trim();
    if (!message || !state.currentProject) return;

    elements.projectChatInput.value = '';
    elements.projectSendBtn.disabled = true;

    // Show typing
    elements.projectChatMessages.innerHTML = `
        <div class="project-chat-message user">
            <div class="message-text">${escapeHtml(message)}</div>
        </div>
        <div class="project-chat-message assistant">
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;

    try {
        const response = await chatApi.send(
            state.currentProject.id,
            message,
            state.projectChatMode
        );

        // Store in history
        state.projectChatHistory.push({
            user: message,
            assistant: response.assistant_text,
            debug: response.debug,
        });
        state.projectChatIndex = state.projectChatHistory.length - 1;

        // Display response
        displayProjectChatPair(state.projectChatHistory[state.projectChatIndex]);
        updateProjectChatNav();

        // Update stats if memories were created
        if (response.memories_created && response.memories_created.length > 0) {
            const project = await projectsApi.get(state.currentProject.id);
            state.currentProject = project;
            updateStats(project);
            loadLedger();
        }

    } catch (error) {
        elements.projectChatMessages.innerHTML = `
            <div class="project-chat-message user">
                <div class="message-text">${escapeHtml(message)}</div>
            </div>
            <div class="project-chat-message assistant">
                <div class="message-text">Sorry, an error occurred. Please try again.</div>
            </div>
        `;
        console.error('Project chat error:', error);
    }
}

function displayProjectChatPair(pair) {
    // Render markdown using marked.js
    const renderMarkdown = (text) => {
        if (typeof marked !== 'undefined' && marked.parse) {
            return marked.parse(text);
        }
        return escapeHtml(text).replace(/\n/g, '<br>');
    };

    // Convert inline citation patterns [8-char-id] to clickable pills
    const linkifyInlineCitations = (html, memoriesUsed = []) => {
        // Match 8-character hex IDs in brackets like [a1b2c3d4]
        // Also match type patterns like [DECISION], [CONSTRAINT-1]
        const citationPattern = /\[([a-f0-9]{8}|[A-Z]+(?:-\d+)?)\]/g;

        return html.replace(citationPattern, (match, content) => {
            // Find the full memory ID if we have a short ID
            const fullId = memoriesUsed.find(id => id.startsWith(content)) || content;
            // Add line break after citation for paragraph separation
            return `<span class="citation-link" onclick="navigateToMemory('${fullId}')">${content}</span><br><br>`;
        });
    };

    const memoriesUsed = pair.debug?.memory_used || [];
    const assistantHtml = linkifyInlineCitations(renderMarkdown(pair.assistant), memoriesUsed);

    elements.projectChatMessages.innerHTML = `
        <div class="project-chat-message user">
            <div class="message-text">${escapeHtml(pair.user)}</div>
        </div>
        <div class="project-chat-message assistant markdown-body">
            ${assistantHtml}
        </div>
    `;
}

function navigateProjectChat(direction) {
    const newIndex = state.projectChatIndex + direction;
    if (newIndex >= 0 && newIndex < state.projectChatHistory.length) {
        state.projectChatIndex = newIndex;
        displayProjectChatPair(state.projectChatHistory[state.projectChatIndex]);
        updateProjectChatNav();
    }
}

function updateProjectChatNav() {
    const total = state.projectChatHistory.length;
    const current = total > 0 ? state.projectChatIndex + 1 : 0;

    elements.projectChatCounter.textContent = total > 0 ? `${current} / ${total}` : '0 / 0';
    elements.projectChatPrev.disabled = state.projectChatIndex <= 0;
    elements.projectChatNext.disabled = state.projectChatIndex >= total - 1;
}

function resetProjectChat() {
    state.projectChatHistory = [];
    state.projectChatIndex = 0;
    elements.projectChatMessages.innerHTML = `
        <div class="project-chat-welcome">
            <p>Quick context updates. Each message is independent. Use for decisions, constraints, and commitments.</p>
        </div>
    `;
    updateProjectChatNav();
}

// ================================================
// Work Chat (Session-based)
// ================================================

function initWorkChat() {
    // Quality selector for work chat
    const workQualityBtns = document.querySelectorAll('#work-chat-screen .quality-btn');
    workQualityBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            workQualityBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.workChatMode = btn.dataset.mode;
        });
    });

    // Start task button
    elements.startTaskBtn.addEventListener('click', openTaskModal);

    // Task modal
    elements.beginTaskBtn.addEventListener('click', beginTask);

    // Work chat input
    elements.workChatInput.addEventListener('input', handleWorkInputChange);
    elements.workChatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!elements.workSendBtn.disabled) {
                sendWorkMessage();
            }
        }
    });
    elements.workSendBtn.addEventListener('click', sendWorkMessage);

    // Task completed button
    elements.taskCompletedBtn.addEventListener('click', endWorkSession);
}

function openTaskModal() {
    if (!state.currentProject) {
        showToast('Please select a project first', 'error');
        return;
    }
    elements.taskModal.classList.add('open');
    elements.taskDescriptionInput.focus();
}

function closeTaskModal() {
    elements.taskModal.classList.remove('open');
    elements.taskDescriptionInput.value = '';
}

async function beginTask() {
    const taskDescription = elements.taskDescriptionInput.value.trim();
    if (!taskDescription) {
        showToast('Please describe the task you want to work on', 'error');
        return;
    }

    try {
        const response = await workApi.start(state.currentProject.id, taskDescription);

        state.workSession = {
            session_id: response.session_id,
            task_description: taskDescription,
        };
        state.workMessages = [];

        // Add system message (not a chat bubble)
        state.workMessages.push({
            role: 'system',
            content: taskDescription,
        });

        closeTaskModal();
        showWorkChatUI();
        renderWorkMessages();

        showToast('Work session started!', 'success');

    } catch (error) {
        console.error('Failed to start work session:', error);
        showToast('Failed to start work session: ' + error.message, 'error');
    }
}

function showWorkChatUI() {
    elements.startTaskScreen.style.display = 'none';
    elements.workChatScreen.style.display = 'flex';
    elements.workTaskDescription.textContent = state.workSession.task_description;
}

function showStartTaskUI() {
    elements.startTaskScreen.style.display = 'flex';
    elements.workChatScreen.style.display = 'none';
    state.workSession = null;
    state.workMessages = [];
}

function handleWorkInputChange() {
    elements.workChatInput.style.height = 'auto';
    elements.workChatInput.style.height = Math.min(elements.workChatInput.scrollHeight, 200) + 'px';
    elements.workSendBtn.disabled = !elements.workChatInput.value.trim() || !state.workSession;
}

async function sendWorkMessage() {
    const message = elements.workChatInput.value.trim();
    if (!message || !state.workSession) return;

    elements.workChatInput.value = '';
    handleWorkInputChange();

    // Add user message
    state.workMessages.push({ role: 'user', content: message });
    renderWorkMessages();

    // Show typing
    const typingId = showWorkTypingIndicator();

    try {
        const response = await workApi.sendMessage(
            state.currentProject.id,
            state.workSession.session_id,
            message,
            state.workChatMode
        );

        removeWorkTypingIndicator(typingId);

        // Add assistant message with memory IDs
        state.workMessages.push({
            role: 'assistant',
            content: response.assistant_text,
            memoriesUsed: response.debug?.memory_used || [],
        });
        state.lastDebugInfo = response.debug;

        renderWorkMessages();

    } catch (error) {
        removeWorkTypingIndicator(typingId);
        state.workMessages.push({ role: 'assistant', content: 'Sorry, an error occurred. Please try again.', memoriesUsed: [] });
        renderWorkMessages();
        console.error('Work chat error:', error);
    }
}

function renderWorkMessages() {
    // Render markdown using marked.js
    const renderMarkdown = (text) => {
        if (typeof marked !== 'undefined' && marked.parse) {
            return marked.parse(text);
        }
        // Fallback if marked is not loaded
        return escapeHtml(text).replace(/\n/g, '<br>');
    };

    // Convert citation patterns like [DECISION], [CONSTRAINT], [COMMITMENT] etc. to clickable pills
    const linkifyCitations = (html) => {
        // Match patterns like [DECISION], [CONSTRAINT-1], [d1234...], [memory text], etc.
        // Look for square brackets with memory type keywords or UUIDs
        const citationPattern = /\[([A-Z]+(?:-\d+)?|[a-f0-9-]{8,36}|[A-Z][a-z]+(?:\s+[A-Za-z]+)*)\]/g;

        return html.replace(citationPattern, (match, content) => {
            // Check if this looks like a memory type or reference
            const memoryTypes = ['DECISION', 'COMMITMENT', 'CONSTRAINT', 'GOAL', 'FAILURE', 'ASSUMPTION', 'EXCEPTION', 'PREFERENCE', 'BELIEF'];
            const upperContent = content.toUpperCase();

            // Check if it starts with a memory type
            const isMemoryType = memoryTypes.some(type => upperContent.startsWith(type));

            // Check if it looks like a UUID
            const isUUID = /^[a-f0-9-]{8,36}$/i.test(content);

            if (isMemoryType || isUUID) {
                return `<span class="citation-link" onclick="navigateToMemory('${escapeHtml(content)}')">${escapeHtml(content)}</span>`;
            }

            // Return original if not a citation
            return match;
        });
    };

    const html = state.workMessages.map((msg, idx) => {
        // System message - centered, no bubble
        if (msg.role === 'system') {
            return `
                <div class="system-message">
                    <div class="task-title">Work Session Started</div>
                    <div class="task-description">"${escapeHtml(msg.content)}"</div>
                    <div>Ask questions, discuss approaches, or work through implementation. Click "Task Completed" when done to save important decisions.</div>
                </div>
            `;
        }

        // User message - plain text
        if (msg.role === 'user') {
            return `
                <div class="message user">
                    <div class="message-content">
                        <div class="message-text">${escapeHtml(msg.content)}</div>
                    </div>
                </div>
            `;
        }

        // Assistant message - render markdown and linkify citations
        const isLastMessage = idx === state.workMessages.length - 1;
        const showMeta = isLastMessage && state.lastDebugInfo;
        const renderedContent = linkifyCitations(renderMarkdown(msg.content));
        const memoriesUsed = msg.memoriesUsed || [];

        // Build memory pills HTML
        const memoryPillsHtml = memoriesUsed.length > 0 ? `
            <div class="message-sources">
                <span class="sources-label">Sources:</span>
                ${memoriesUsed.map(memId => `<span class="citation-link" onclick="navigateToMemory('${memId}')">${memId.substring(0, 8)}</span>`).join('')}
            </div>
        ` : '';

        return `
            <div class="message assistant">
                <div class="message-content markdown-body">
                    ${renderedContent}
                    ${memoryPillsHtml}
                    ${showMeta ? `
                        <div class="message-meta">
                            <button class="why-btn" onclick="openWhyDrawer()">Why?</button>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }).join('');

    elements.workChatMessages.innerHTML = html;
    elements.workChatMessages.scrollTop = elements.workChatMessages.scrollHeight;
}

function showWorkTypingIndicator() {
    const id = 'work-typing-' + Date.now();
    const typingDiv = document.createElement('div');
    typingDiv.id = id;
    typingDiv.className = 'message assistant';
    typingDiv.innerHTML = `
        <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    elements.workChatMessages.appendChild(typingDiv);
    elements.workChatMessages.scrollTop = elements.workChatMessages.scrollHeight;
    return id;
}

function removeWorkTypingIndicator(id) {
    const indicator = document.getElementById(id);
    if (indicator) indicator.remove();
}

async function endWorkSession() {
    if (!state.workSession) return;

    const confirmed = confirm('End this work session? Memories will be extracted and saved to the project.');
    if (!confirmed) return;

    try {
        showToast('Ending session and extracting memories...', 'info');

        const response = await workApi.endSession(
            state.currentProject.id,
            state.workSession.session_id
        );

        showToast(`Session completed! ${response.memories_created} memories saved.`, 'success');

        // Refresh stats and ledger
        const project = await projectsApi.get(state.currentProject.id);
        state.currentProject = project;
        updateStats(project);
        loadLedger();

        // Return to start task screen
        showStartTaskUI();

    } catch (error) {
        console.error('Failed to end work session:', error);
        showToast('Failed to end session: ' + error.message, 'error');
    }
}

async function checkForActiveWorkSession() {
    if (!state.currentProject) return;

    try {
        const activeSession = await workApi.getActive(state.currentProject.id);

        if (activeSession) {
            // Restore active session
            state.workSession = {
                session_id: activeSession.session_id,
                task_description: activeSession.task_description,
            };

            // Load messages
            const messages = await workApi.getMessages(
                state.currentProject.id,
                activeSession.session_id
            );

            // Start with system message showing task description
            state.workMessages = [
                {
                    role: 'system',
                    content: activeSession.task_description,
                },
                // Filter out the welcome message (first assistant message) and add the rest
                ...messages
                    .filter((m, idx) => !(idx === 0 && m.role === 'assistant' && m.content.startsWith('Started work session')))
                    .map(m => ({
                        role: m.role,
                        content: m.content,
                    }))
            ];

            showWorkChatUI();
            renderWorkMessages();
        } else {
            showStartTaskUI();
        }
    } catch (error) {
        console.error('Failed to check for active session:', error);
        showStartTaskUI();
    }
}

// ================================================
// Project Load & Management
// ================================================

async function loadProjects() {
    try {
        const response = await projectsApi.list();
        state.projects = response.projects;

        elements.projectSelect.innerHTML = '<option value="">Select a project...</option>';
        state.projects.forEach(project => {
            const option = document.createElement('option');
            option.value = project.id;
            option.textContent = project.name;
            elements.projectSelect.appendChild(option);
        });

        if (state.projects.length > 0) {
            elements.projectSelect.value = state.projects[0].id;
            await selectProject(state.projects[0].id);
        }

        elements.loadingOverlay.classList.add('hidden');
    } catch (error) {
        console.error('Failed to load projects:', error);
        showToast('Failed to connect to server. Make sure the backend is running.', 'error');
        elements.loadingOverlay.classList.add('hidden');
    }
}

// ================================================
// View Management
// ================================================

function switchView(viewName) {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === viewName);
    });

    document.querySelectorAll('.view').forEach(view => {
        view.classList.toggle('active', view.id === `view-${viewName}`);
    });

    if (viewName === 'ledger' && state.currentProject) {
        loadLedger();
    } else if (viewName === 'timeline' && state.currentProject) {
        loadTimeline();
    }
}

// ================================================
// Project Management
// ================================================

async function handleProjectChange(e) {
    const projectId = e.target.value;
    if (projectId) {
        await selectProject(projectId);
    } else {
        state.currentProject = null;
        resetProjectChat();
        showStartTaskUI();
    }
}

async function selectProject(projectId) {
    try {
        const project = await projectsApi.get(projectId);
        state.currentProject = project;

        updateStats(project);
        resetProjectChat();
        await checkForActiveWorkSession();
        loadLedger();

        // Connect to SSE for real-time pipeline notifications
        connectToEventStream(projectId);

    } catch (error) {
        console.error('Failed to load project:', error);
        showToast('Failed to load project', 'error');
    }
}

function updateStats(project) {
    elements.statTotal.textContent = project.memory_count || 0;
    elements.statActive.textContent = project.active_memory_count || 0;
    elements.statDisputed.textContent = state.ledger?.disputed_count || 0;
}

function openProjectModal() {
    elements.projectModal.classList.add('open');
}

function closeModal() {
    elements.projectModal.classList.remove('open');
    document.getElementById('project-name').value = '';
    document.getElementById('project-description').value = '';
    document.getElementById('project-goal').value = '';
}

async function createProject() {
    const name = document.getElementById('project-name').value.trim();
    const description = document.getElementById('project-description').value.trim();
    const goal = document.getElementById('project-goal').value.trim();

    if (!name) {
        showToast('Please enter a project name', 'error');
        return;
    }

    try {
        const project = await projectsApi.create({ name, description, goal });
        state.projects.push(project);

        const option = document.createElement('option');
        option.value = project.id;
        option.textContent = project.name;
        elements.projectSelect.appendChild(option);

        elements.projectSelect.value = project.id;
        await selectProject(project.id);

        closeModal();
        showToast('Project created successfully!', 'success');
    } catch (error) {
        console.error('Failed to create project:', error);
        showToast('Failed to create project', 'error');
    }
}

// ================================================
// Why Drawer
// ================================================

function openWhyDrawer() {
    if (!state.lastDebugInfo) return;

    elements.whyDrawer.classList.add('open');

    const debug = state.lastDebugInfo;

    const memoriesUsed = document.getElementById('memories-used');
    if (debug.memory_used && debug.memory_used.length > 0) {
        memoriesUsed.innerHTML = debug.memory_used.map(id => `
            <div class="memory-list-item">${id}</div>
        `).join('');
    } else {
        memoriesUsed.innerHTML = '<div class="memory-list-item">No memories used</div>';
    }

    const commitmentsChecked = document.getElementById('commitments-checked');
    if (debug.commitments_checked && debug.commitments_checked.length > 0) {
        commitmentsChecked.innerHTML = debug.commitments_checked.map(id => `
            <div class="memory-list-item">${id}</div>
        `).join('');
    } else {
        commitmentsChecked.innerHTML = '<div class="memory-list-item">No commitments checked</div>';
    }

    const debugInfo = document.getElementById('debug-info');
    debugInfo.innerHTML = `
        <p><strong>Model Tier:</strong> ${debug.model_tier}</p>
        <p><strong>Latency:</strong> ${debug.latency_ms || 0}ms</p>
        <p><strong>Violated:</strong> ${debug.violated ? 'Yes' : 'No'}</p>
        ${debug.violation_details ? `<p><strong>Details:</strong> ${debug.violation_details}</p>` : ''}
    `;
}

function closeWhyDrawer() {
    elements.whyDrawer.classList.remove('open');
}

// ================================================
// Ledger Functions
// ================================================

async function loadLedger() {
    if (!state.currentProject) return;

    try {
        state.ledger = await memoryApi.ledger(state.currentProject.id);
        updateStats(state.currentProject);
        renderLedger('all');
    } catch (error) {
        console.error('Failed to load ledger:', error);
    }
}

function renderLedger(filter = 'all') {
    if (!state.ledger) {
        elements.ledgerContent.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon"></div>
                <h3>No memories yet</h3>
                <p>Start chatting to build your project memory</p>
            </div>
        `;
        return;
    }

    let memories = [];

    if (filter === 'all') {
        memories = [
            ...state.ledger.decisions,
            ...state.ledger.commitments,
            ...state.ledger.constraints,
            ...state.ledger.goals,
            ...state.ledger.failures,
            ...state.ledger.assumptions,
            ...state.ledger.exceptions,
            ...state.ledger.preferences,
            ...state.ledger.beliefs,
        ];
    } else {
        const typeMap = {
            'decision': state.ledger.decisions,
            'commitment': state.ledger.commitments,
            'constraint': state.ledger.constraints,
            'goal': state.ledger.goals,
            'failure': state.ledger.failures,
        };
        memories = typeMap[filter] || [];
    }

    memories.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    if (memories.length === 0) {
        elements.ledgerContent.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon"></div>
                <h3>No ${filter === 'all' ? 'memories' : filter + 's'} yet</h3>
                <p>Start chatting to build your project memory</p>
            </div>
        `;
        return;
    }

    elements.ledgerContent.innerHTML = memories.map(memory => `
        <div class="memory-card" id="memory-${memory.id}" onclick="openMemoryDetail('${memory.id}')">
            <div class="memory-card-header">
                <span class="memory-type-badge ${memory.type}">${memory.type}</span>
                <span class="memory-status ${memory.status}">${memory.status}</span>
            </div>
            <div class="memory-statement">${escapeHtml(memory.canonical_statement)}</div>
            <div class="memory-meta">
                <span>Importance: ${(memory.importance * 100).toFixed(0)}%</span>
                <span>Created: ${formatDate(memory.created_at)}</span>
                ${memory.version_count > 1 ? `<span>${memory.version_count} versions</span>` : ''}
            </div>
        </div>
    `).join('');
}

async function openMemoryDetail(memoryId) {
    if (!state.currentProject) return;

    try {
        const memory = await memoryApi.get(state.currentProject.id, memoryId);

        const content = document.getElementById('memory-modal-content');
        content.innerHTML = `
            <div class="memory-detail">
                <div class="memory-card-header" style="margin-bottom: 1rem;">
                    <span class="memory-type-badge ${memory.type}">${memory.type}</span>
                    <span class="memory-status ${memory.status}">${memory.status}</span>
                </div>
                
                <h4 style="margin-bottom: 0.5rem;">Statement</h4>
                <p style="margin-bottom: 1rem;">${escapeHtml(memory.canonical_statement)}</p>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                    <div>
                        <strong>Importance:</strong> ${(memory.importance * 100).toFixed(0)}%
                    </div>
                    <div>
                        <strong>Confidence:</strong> ${(memory.confidence * 100).toFixed(0)}%
                    </div>
                    <div>
                        <strong>Created:</strong> ${formatDateTime(memory.created_at)}
                    </div>
                    <div>
                        <strong>Updated:</strong> ${formatDateTime(memory.updated_at)}
                    </div>
                </div>
                
                ${memory.versions && memory.versions.length > 0 ? `
                    <h4 style="margin-bottom: 0.5rem;">Version History</h4>
                    <div style="margin-bottom: 1rem;">
                        ${memory.versions.map(v => `
                            <div style="padding: 0.5rem; background: var(--bg-tertiary); border-radius: 6px; margin-bottom: 0.5rem;">
                                <div style="font-size: 0.8rem; color: var(--text-muted);">
                                    Version ${v.version_number} • ${formatDate(v.created_at)} • ${v.changed_by}
                                </div>
                                <div>${escapeHtml(v.statement)}</div>
                                ${v.rationale ? `<div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem;">Rationale: ${escapeHtml(v.rationale)}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `;

        elements.memoryModal.classList.add('open');
    } catch (error) {
        console.error('Failed to load memory:', error);
        showToast('Failed to load memory details', 'error');
    }
}

function closeMemoryModal() {
    elements.memoryModal.classList.remove('open');
}

// ================================================
// Timeline Functions
// ================================================

async function loadTimeline() {
    if (!state.currentProject) return;

    try {
        const response = await chatApi.timeline(state.currentProject.id);
        state.timeline = response.events;
        renderTimeline();
    } catch (error) {
        console.error('Failed to load timeline:', error);
    }
}

function renderTimeline() {
    if (!state.timeline || state.timeline.length === 0) {
        elements.timelineContent.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🕐</div>
                <h3>No events yet</h3>
                <p>Your project history will appear here</p>
            </div>
        `;
        return;
    }

    elements.timelineContent.innerHTML = state.timeline.map(event => `
        <div class="timeline-event ${event.type.includes('conflict') ? 'conflict' : ''} ${event.type.includes('violation') ? 'violation' : ''}">
            <div class="event-card">
                <div class="event-time">${formatDateTime(event.timestamp)}</div>
                <div class="event-title">${escapeHtml(event.title)}</div>
                <div class="event-description">${escapeHtml(event.description)}</div>
            </div>
        </div>
    `).join('');
}

// ================================================
// Citation Navigation
// ================================================

async function navigateToMemory(citationText) {
    if (!state.currentProject) {
        showToast('No project selected', 'error');
        return;
    }

    // Load ledger if not loaded
    if (!state.ledger) {
        await loadLedger();
    }

    // Find memory by citation text
    // Citation could be like "DECISION", "DECISION-1", or a UUID
    const allMemories = [
        ...state.ledger.decisions,
        ...state.ledger.commitments,
        ...state.ledger.constraints,
        ...state.ledger.goals,
        ...state.ledger.failures,
        ...state.ledger.assumptions,
        ...state.ledger.exceptions,
        ...state.ledger.preferences,
        ...state.ledger.beliefs,
    ];

    // Try to find matching memory
    let targetMemory = null;
    const upperCitation = citationText.toUpperCase();

    // Check for exact UUID match first
    targetMemory = allMemories.find(m => m.id === citationText || m.id.startsWith(citationText));

    // Check for type+number pattern like "DECISION-1"
    if (!targetMemory) {
        const typeMatch = upperCitation.match(/^([A-Z]+)(?:-(\d+))?$/);
        if (typeMatch) {
            const memType = typeMatch[1].toLowerCase();
            const memIndex = typeMatch[2] ? parseInt(typeMatch[2]) - 1 : 0;

            const typeMap = {
                'decision': state.ledger.decisions,
                'commitment': state.ledger.commitments,
                'constraint': state.ledger.constraints,
                'goal': state.ledger.goals,
                'failure': state.ledger.failures,
                'assumption': state.ledger.assumptions,
                'exception': state.ledger.exceptions,
                'preference': state.ledger.preferences,
                'belief': state.ledger.beliefs,
            };

            const typeMemories = typeMap[memType];
            if (typeMemories && typeMemories.length > memIndex) {
                targetMemory = typeMemories[memIndex];
            }
        }
    }

    if (!targetMemory) {
        showToast(`Could not find memory: ${citationText}`, 'error');
        return;
    }

    // Switch to ledger view
    switchView('ledger');

    // Wait for DOM to update
    await new Promise(resolve => setTimeout(resolve, 100));

    // Reset filter to show all memories
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.filter-btn[data-type="all"]')?.classList.add('active');
    renderLedger('all');

    // Wait for render
    await new Promise(resolve => setTimeout(resolve, 50));

    // Find and scroll to the memory card
    const memoryCard = document.getElementById(`memory-${targetMemory.id}`);
    if (memoryCard) {
        // Remove any previous highlights
        document.querySelectorAll('.memory-card.highlighted').forEach(el => {
            el.classList.remove('highlighted');
        });

        // Scroll to the card
        memoryCard.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Add highlight
        memoryCard.classList.add('highlighted');

        // Remove highlight after animation
        setTimeout(() => {
            memoryCard.classList.remove('highlighted');
        }, 2500);
    }
}

// ================================================
// Utility Functions
// ================================================

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
    });
}

function formatDateTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 24px;
        background: ${type === 'error' ? 'var(--primary-red)' : type === 'success' ? 'var(--primary-green)' : 'var(--primary-cyan)'};
        color: var(--bg-primary);
        border-radius: 8px;
        font-weight: 500;
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function dismissViolation() {
    showToast('Violation dismissed', 'info');
}

async function createException() {
    showToast('Exception creation coming soon', 'info');
}

// Add animation styles
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

// ================================================
// Initialize
// ================================================

document.addEventListener('DOMContentLoaded', initializeApp);

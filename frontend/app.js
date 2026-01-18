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
};

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
    elements.projectChatMessages.innerHTML = `
        <div class="project-chat-message user">
            <div class="message-text">${escapeHtml(pair.user)}</div>
        </div>
        <div class="project-chat-message assistant">
            <div class="message-text">${escapeHtml(pair.assistant)}</div>
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

        // Add welcome message
        state.workMessages.push({
            role: 'assistant',
            content: `Started work session for: ${taskDescription}\n\nI'll help you with this task. Feel free to ask questions, discuss approaches, or work through implementation. When you're done, click 'Task Completed' to save any important decisions or outcomes to project memory.`,
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

        // Add assistant message
        state.workMessages.push({ role: 'assistant', content: response.assistant_text });
        state.lastDebugInfo = response.debug;

        renderWorkMessages();

    } catch (error) {
        removeWorkTypingIndicator(typingId);
        state.workMessages.push({ role: 'assistant', content: 'Sorry, an error occurred. Please try again.' });
        renderWorkMessages();
        console.error('Work chat error:', error);
    }
}

function renderWorkMessages() {
    elements.workChatMessages.innerHTML = state.workMessages.map((msg, idx) => `
        <div class="message ${msg.role}">
            <div class="message-content">
                <div class="message-text">${escapeHtml(msg.content)}</div>
                ${msg.role === 'assistant' && idx === state.workMessages.length - 1 && state.lastDebugInfo ? `
                    <div class="message-meta">
                        <span>${state.lastDebugInfo.memory_used?.length || 0} memories used</span>
                        <button class="why-btn" onclick="openWhyDrawer()">Why?</button>
                    </div>
                ` : ''}
            </div>
        </div>
    `).join('');

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
            state.workMessages = messages.map(m => ({
                role: m.role,
                content: m.content,
            }));

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
                <div class="empty-icon">📋</div>
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
                <div class="empty-icon">📋</div>
                <h3>No ${filter === 'all' ? 'memories' : filter + 's'} yet</h3>
                <p>Start chatting to build your project memory</p>
            </div>
        `;
        return;
    }

    elements.ledgerContent.innerHTML = memories.map(memory => `
        <div class="memory-card" onclick="openMemoryDetail('${memory.id}')">
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

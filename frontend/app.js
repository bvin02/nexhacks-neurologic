/**
 * DecisionOS - Frontend Application
 * Project Continuity Copilot
 */

// API Configuration
const API_BASE = 'http://localhost:8000';

// Application State
const state = {
    currentProject: null,
    projects: [],
    messages: [],
    ledger: null,
    timeline: [],
    chatMode: 'balanced',
    lastDebugInfo: null,
};

// DOM Elements
const elements = {
    loadingOverlay: document.getElementById('loading-overlay'),
    projectSelect: document.getElementById('project-select'),
    newProjectBtn: document.getElementById('new-project-btn'),
    chatMessages: document.getElementById('chat-messages'),
    chatInput: document.getElementById('chat-input'),
    sendBtn: document.getElementById('send-btn'),
    whyDrawer: document.getElementById('why-drawer'),
    closeDrawer: document.getElementById('close-drawer'),
    projectModal: document.getElementById('project-modal'),
    memoryModal: document.getElementById('memory-modal'),
    ledgerContent: document.getElementById('ledger-content'),
    timelineContent: document.getElementById('timeline-content'),
    statTotal: document.getElementById('stat-total'),
    statActive: document.getElementById('stat-active'),
    statDisputed: document.getElementById('stat-disputed'),
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

// Chat API
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

    // Quality selector
    document.querySelectorAll('.quality-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.quality-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.chatMode = btn.dataset.mode;
        });
    });

    // Ledger filters
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderLedger(btn.dataset.type);
        });
    });

    // Chat input
    elements.chatInput.addEventListener('input', handleInputChange);
    elements.chatInput.addEventListener('keydown', handleInputKeydown);
    elements.sendBtn.addEventListener('click', sendMessage);

    // Project management
    elements.projectSelect.addEventListener('change', handleProjectChange);
    elements.newProjectBtn.addEventListener('click', openProjectModal);
    document.getElementById('create-project-btn').addEventListener('click', createProject);

    // Why drawer
    elements.closeDrawer.addEventListener('click', closeWhyDrawer);

    // Load projects
    loadProjects();
}

async function loadProjects() {
    try {
        const response = await projectsApi.list();
        state.projects = response.projects;

        // Update select
        elements.projectSelect.innerHTML = '<option value="">Select a project...</option>';
        state.projects.forEach(project => {
            const option = document.createElement('option');
            option.value = project.id;
            option.textContent = project.name;
            elements.projectSelect.appendChild(option);
        });

        // Auto-select first project if available
        if (state.projects.length > 0) {
            elements.projectSelect.value = state.projects[0].id;
            await selectProject(state.projects[0].id);
        }

        // Hide loading
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
    // Update nav
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === viewName);
    });

    // Update views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.toggle('active', view.id === `view-${viewName}`);
    });

    // Load data for view if needed
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
        state.messages = [];
        resetChat();
    }
}

async function selectProject(projectId) {
    try {
        const project = await projectsApi.get(projectId);
        state.currentProject = project;
        state.messages = [];

        // Update stats
        updateStats(project);

        // Reset chat
        resetChat();

        // Load initial data
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

        // Add to select
        const option = document.createElement('option');
        option.value = project.id;
        option.textContent = project.name;
        elements.projectSelect.appendChild(option);

        // Select it
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
// Chat Functions
// ================================================

function handleInputChange() {
    // Auto-resize
    elements.chatInput.style.height = 'auto';
    elements.chatInput.style.height = Math.min(elements.chatInput.scrollHeight, 200) + 'px';

    // Enable/disable send button
    elements.sendBtn.disabled = !elements.chatInput.value.trim() || !state.currentProject;
}

function handleInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!elements.sendBtn.disabled) {
            sendMessage();
        }
    }
}

async function sendMessage() {
    const message = elements.chatInput.value.trim();
    if (!message || !state.currentProject) return;

    // Clear input
    elements.chatInput.value = '';
    handleInputChange();

    // Add user message
    addMessage('user', message);

    // Show typing indicator
    const typingId = showTypingIndicator();

    try {
        const response = await chatApi.send(
            state.currentProject.id,
            message,
            state.chatMode
        );

        // Remove typing indicator
        removeTypingIndicator(typingId);

        // Store debug info
        state.lastDebugInfo = response.debug;

        // Add assistant message
        if (response.violation_challenge) {
            addViolationMessage(response);
        } else {
            addMessage('assistant', response.assistant_text, response.debug);
        }

        // Update stats if memories were created
        if (response.memories_created && response.memories_created.length > 0) {
            const project = await projectsApi.get(state.currentProject.id);
            state.currentProject = project;
            updateStats(project);
        }

    } catch (error) {
        removeTypingIndicator(typingId);
        addMessage('assistant', 'Sorry, I encountered an error. Please try again.');
        console.error('Chat error:', error);
    }
}

function resetChat() {
    elements.chatMessages.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">🧠</div>
            <h2>Welcome to DecisionOS</h2>
            <p>Your Project Continuity Copilot. I remember your decisions, commitments, and constraints across sessions.</p>
            <div class="welcome-hints">
                <div class="hint">💡 Make a commitment: "We will always use TypeScript"</div>
                <div class="hint">⚡ Record a decision: "We chose React for the frontend"</div>
                <div class="hint">🔒 Set a constraint: "We cannot use MongoDB"</div>
            </div>
        </div>
    `;
}

function addMessage(role, text, debug = null) {
    // Remove welcome message if present
    const welcome = elements.chatMessages.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    textDiv.textContent = text;
    contentDiv.appendChild(textDiv);

    // Add meta for assistant messages
    if (role === 'assistant' && debug) {
        const metaDiv = document.createElement('div');
        metaDiv.className = 'message-meta';
        metaDiv.innerHTML = `
            <span>${debug.latency_ms || 0}ms</span>
            <span>•</span>
            <span>${debug.memory_used?.length || 0} memories used</span>
            <button class="why-btn" onclick="openWhyDrawer()">Why?</button>
        `;
        contentDiv.appendChild(metaDiv);
    }

    messageDiv.appendChild(contentDiv);
    elements.chatMessages.appendChild(messageDiv);

    // Scroll to bottom
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

    // Store message
    state.messages.push({ role, text, debug });
}

function addViolationMessage(response) {
    // Remove welcome message if present
    const welcome = elements.chatMessages.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant violation';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    contentDiv.innerHTML = `
        <div class="violation-header">⚠️ Potential Violation Detected</div>
        <div class="message-text">${response.assistant_text.replace(/\n/g, '<br>')}</div>
        <div class="violation-actions">
            <button class="btn btn-secondary btn-sm" onclick="dismissViolation()">Dismiss</button>
            <button class="btn btn-primary btn-sm" onclick="createException()">Create Exception</button>
        </div>
    `;

    messageDiv.appendChild(contentDiv);
    elements.chatMessages.appendChild(messageDiv);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function showTypingIndicator() {
    const id = 'typing-' + Date.now();
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
    elements.chatMessages.appendChild(typingDiv);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    const indicator = document.getElementById(id);
    if (indicator) indicator.remove();
}

// ================================================
// Why Drawer
// ================================================

function openWhyDrawer() {
    if (!state.lastDebugInfo) return;

    elements.whyDrawer.classList.add('open');

    const debug = state.lastDebugInfo;

    // Memories used
    const memoriesUsed = document.getElementById('memories-used');
    if (debug.memory_used && debug.memory_used.length > 0) {
        memoriesUsed.innerHTML = debug.memory_used.map(id => `
            <div class="memory-list-item">${id}</div>
        `).join('');
    } else {
        memoriesUsed.innerHTML = '<div class="memory-list-item">No memories used</div>';
    }

    // Commitments checked
    const commitmentsChecked = document.getElementById('commitments-checked');
    if (debug.commitments_checked && debug.commitments_checked.length > 0) {
        commitmentsChecked.innerHTML = debug.commitments_checked.map(id => `
            <div class="memory-list-item">${id}</div>
        `).join('');
    } else {
        commitmentsChecked.innerHTML = '<div class="memory-list-item">No commitments checked</div>';
    }

    // Debug info
    const debugInfo = document.getElementById('debug-info');
    debugInfo.innerHTML = `
        <p><strong>Model Tier:</strong> ${debug.model_tier}</p>
        <p><strong>Latency:</strong> ${debug.latency_ms}ms</p>
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

    // Collect all memories based on filter
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

    // Sort by created_at desc
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
            <div class="memory-statement">${memory.canonical_statement}</div>
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
                <p style="margin-bottom: 1rem;">${memory.canonical_statement}</p>
                
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
                                <div>${v.statement}</div>
                                ${v.rationale ? `<div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem;">Rationale: ${v.rationale}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
                
                ${memory.evidence_links && memory.evidence_links.length > 0 ? `
                    <h4 style="margin-bottom: 0.5rem;">Evidence</h4>
                    <div>
                        ${memory.evidence_links.map(e => `
                            <div style="padding: 0.5rem; background: var(--bg-tertiary); border-radius: 6px; margin-bottom: 0.5rem; border-left: 2px solid var(--primary-cyan);">
                                <div style="font-size: 0.8rem; color: var(--text-muted);">${e.source_type}: ${e.source_ref}</div>
                                ${e.quote ? `<div style="font-style: italic;">"${e.quote}"</div>` : ''}
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
                <div class="event-title">${event.title}</div>
                <div class="event-description">${event.description}</div>
            </div>
        </div>
    `).join('');
}

// ================================================
// Utility Functions
// ================================================

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
    // Simple toast implementation
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
    // Just continue with the conversation
    showToast('Violation dismissed', 'info');
}

async function createException() {
    // TODO: Implement exception creation modal
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

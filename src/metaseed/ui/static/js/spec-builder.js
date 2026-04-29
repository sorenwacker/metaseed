/**
 * Spec Builder - ERD Graph Visualization
 *
 * Manages the entity-relationship diagram for the spec builder interface.
 */

// =============================================================================
// Constants
// =============================================================================

const NODE_COLORS = {
    root: {
        background: '#4a7c59',
        border: '#2d5a4a',
        fontColor: '#fff',
        highlight: { background: '#87a878', border: '#4a7c59' },
        hover: { background: '#5a8c69', border: '#4a7c59' }
    },
    regular: {
        background: '#ffffff',
        border: '#4a7c59',
        fontColor: '#2c3e35',
        highlight: { background: '#87a878', border: '#4a7c59' },
        hover: { background: '#f5f2ed', border: '#4a7c59' }
    },
    hidden: {
        background: '#e0e0e0',
        border: '#b0b0b0',
        fontColor: '#999999',
        highlight: { background: '#d0d0d0', border: '#a0a0a0' },
        hover: { background: '#d5d5d5', border: '#a5a5a5' }
    }
};

const EDGE_COLORS = {
    nested: { color: '#4a7c59', highlight: '#2d5a4a' },
    reference: { color: '#7c4a6b', highlight: '#5a2d4a' }
};

const FONT_CONFIG = {
    face: 'monospace',
    size: 12,
    align: 'left',
    multi: 'html'
};

const LAYOUT = {
    nodeBaseHeight: 40,
    fieldHeight: 16,
    nodeWidth: 200,
    gridSpacing: 200
};

// =============================================================================
// State
// =============================================================================

let network = null;
let nodes = null;
let edges = null;
let selectedNode = null;
let pendingPosition = null;
let hiddenEntities = new Set();
let originalNodeColors = {};

// =============================================================================
// Initialization
// =============================================================================

/**
 * Initialize the ERD graph when the DOM is ready.
 */
function initERD() {
    if (network) return;

    const container = document.getElementById('erd-canvas');
    if (!container) return;

    const rect = container.getBoundingClientRect();
    if (rect.height < 50) {
        setTimeout(initERD, 200);
        return;
    }

    const entityNames = Object.keys(entities);
    if (entityNames.length === 0) {
        container.innerHTML = '<div class="empty-canvas-message">Double-click to add an entity</div>';
        return;
    }

    const { nodeData, edgeData } = buildGraphData(entityNames);
    createNetwork(container, nodeData, edgeData);
    attachNetworkEventHandlers();
}

/**
 * Build node and edge data from entities.
 */
function buildGraphData(entityNames) {
    const nodeData = [];
    const edgeData = [];

    entityNames.forEach(name => {
        const entity = entities[name];
        const isRoot = name === rootEntity;
        const fields = entity.fields || [];

        const nodeConfig = buildNodeConfig(name, entity, isRoot, fields);
        storeOriginalColors(name, nodeConfig);
        nodeData.push(nodeConfig);

        const entityEdges = buildEntityEdges(name, fields);
        edgeData.push(...entityEdges);
    });

    return { nodeData, edgeData };
}

/**
 * Build configuration for a single node.
 */
function buildNodeConfig(name, entity, isRoot, fields) {
    const label = buildNodeLabel(name, isRoot, fields);
    const colors = isRoot ? NODE_COLORS.root : NODE_COLORS.regular;
    const nodeHeight = LAYOUT.nodeBaseHeight + fields.length * LAYOUT.fieldHeight;

    return {
        id: name,
        label: label,
        shape: 'box',
        size: Math.max(nodeHeight, LAYOUT.nodeWidth) / 2,
        mass: 1 + fields.length * 0.3,
        font: { ...FONT_CONFIG, color: colors.fontColor },
        color: {
            background: colors.background,
            border: colors.border,
            highlight: colors.highlight,
            hover: colors.hover
        },
        borderWidth: 2,
        margin: 15,
        shadow: true
    };
}

/**
 * Build the label text for a node.
 */
function buildNodeLabel(name, isRoot, fields) {
    let label = `<b>${name}</b>`;
    if (isRoot) label += ' [ROOT]';
    label += '\n────────────────';

    fields.forEach(field => {
        const req = field.required ? '*' : ' ';
        const fk = ((field.type === 'entity' || field.type === 'list') && field.items) ? '→' : ' ';
        label += `\n${req}${fk} ${field.name}: ${field.type}`;
    });

    if (fields.length === 0) {
        label += '\n(no fields)';
    }

    return label;
}

/**
 * Store original colors for hide/show functionality.
 */
function storeOriginalColors(name, nodeConfig) {
    originalNodeColors[name] = {
        background: nodeConfig.color.background,
        border: nodeConfig.color.border,
        fontColor: nodeConfig.font.color
    };
}

/**
 * Build edges for an entity's relationships.
 */
function buildEntityEdges(name, fields) {
    const edgeData = [];

    fields.forEach(field => {
        // Nested entity relationships
        if ((field.type === 'entity' || field.type === 'list') && field.items && entities[field.items]) {
            edgeData.push(createEdge(name, field.items, field.name, 'nested'));
        }

        // Reference relationships
        if (field.reference) {
            const targetEntity = field.reference.split('.')[0];
            if (entities[targetEntity]) {
                edgeData.push(createEdge(name, targetEntity, field.name, 'reference'));
            }
        }
    });

    return edgeData;
}

/**
 * Create an edge configuration object.
 */
function createEdge(from, to, label, type) {
    const colors = type === 'reference' ? EDGE_COLORS.reference : EDGE_COLORS.nested;
    const fontColor = type === 'reference' ? '#6b5a62' : '#5a6b62';

    return {
        from: from,
        to: to,
        label: label,
        arrows: { to: { enabled: true, type: 'arrow' } },
        color: colors,
        font: { size: 11, color: fontColor, background: 'white', strokeWidth: 0 },
        smooth: { type: 'cubicBezier', roundness: 0.4 },
        width: 2,
        dashes: type === 'reference'
    };
}

/**
 * Create the vis-network instance.
 */
function createNetwork(container, nodeData, edgeData) {
    nodes = new vis.DataSet(nodeData);
    edges = new vis.DataSet(edgeData);

    const options = {
        layout: {
            improvedLayout: true,
            randomSeed: 42
        },
        physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -100,
                centralGravity: 0.01,
                springLength: 200,
                springConstant: 0.08,
                damping: 0.5,
                avoidOverlap: 1
            },
            maxVelocity: 50,
            minVelocity: 0.1,
            stabilization: {
                enabled: true,
                iterations: 2000,
                updateInterval: 25
            }
        },
        interaction: {
            hover: true,
            zoomView: true,
            zoomSpeed: 0.5,
            dragView: true,
            dragNodes: true,
            navigationButtons: false,
            keyboard: {
                enabled: true,
                speed: { x: 10, y: 10, zoom: 0.05 }
            }
        },
        nodes: {
            shape: 'box',
            margin: 12,
            widthConstraint: { minimum: 180 }
        },
        edges: {
            smooth: {
                type: 'cubicBezier',
                forceDirection: 'vertical',
                roundness: 0.4
            }
        }
    };

    network = new vis.Network(container, { nodes, edges }, options);
}

/**
 * Attach event handlers to the network.
 */
function attachNetworkEventHandlers() {
    network.on('click', function(params) {
        if (params.nodes.length > 0) {
            selectEntity(params.nodes[0]);
        }
    });

    network.on('doubleClick', function(params) {
        if (params.nodes.length === 0) {
            showAddEntityModal();
        }
    });

    network.once('stabilizationIterationsDone', () => {
        network.setOptions({ physics: { enabled: false } });
    });

    network.on('oncontext', function(params) {
        params.event.preventDefault();
        const nodeId = network.getNodeAt(params.pointer.DOM);
        if (nodeId) {
            showContextMenu(params.event, nodeId);
        }
    });
}

// =============================================================================
// Entity Selection & Editor Panel
// =============================================================================

function selectEntity(entityName) {
    selectedNode = entityName;
    document.getElementById('editor-title').textContent = entityName;
    document.getElementById('editor-panel').classList.add('open');
    htmx.ajax('GET', `/spec-builder/entity/${entityName}`, {
        target: '#editor-content',
        swap: 'innerHTML'
    });
}

function closeEditorPanel() {
    document.getElementById('editor-panel').classList.remove('open');
    if (network) network.unselectAll();
    selectedNode = null;
}

// =============================================================================
// Graph Controls
// =============================================================================

function refreshGraph() {
    htmx.ajax('GET', '/spec-builder', { target: 'body', swap: 'innerHTML' });
}

function autoLayout() {
    if (!network) return;

    const nodeIds = nodes.getIds();
    const cols = Math.ceil(Math.sqrt(nodeIds.length));

    let sorted = [...nodeIds];
    if (rootEntity && sorted.includes(rootEntity)) {
        sorted = [rootEntity, ...sorted.filter(n => n !== rootEntity)];
    }

    sorted.forEach((id, idx) => {
        const col = idx % cols;
        const row = Math.floor(idx / cols);
        nodes.update({ id, x: col * LAYOUT.gridSpacing, y: row * LAYOUT.gridSpacing });
    });

    setTimeout(() => network.fit({ animation: true }), 100);
}

function zoomIn() {
    if (network) {
        const scale = network.getScale();
        network.moveTo({ scale: scale * 1.15, animation: { duration: 200 } });
    }
}

function zoomOut() {
    if (network) {
        const scale = network.getScale();
        network.moveTo({ scale: scale / 1.15, animation: { duration: 200 } });
    }
}

function fitGraph() {
    if (network) {
        network.fit({ animation: { duration: 300 } });
    }
}

// =============================================================================
// Add Entity Modal
// =============================================================================

function showAddEntityModal() {
    document.getElementById('add-entity-modal').classList.remove('hidden');
    document.getElementById('new-entity-name').value = '';
    document.getElementById('new-entity-name').focus();
}

function hideAddEntityModal() {
    document.getElementById('add-entity-modal').classList.add('hidden');
    pendingPosition = null;
}

function onEntityAdded() {
    hideAddEntityModal();
    setTimeout(refreshGraph, 100);
}

function startAddRelationship() {
    alert('To add a relationship:\n1. Click on the source entity\n2. Add a field of type "entity" or "list"\n3. Set the Items/Target to the target entity name');
}

// =============================================================================
// Drag & Drop
// =============================================================================

function dragNewEntity(event) {
    event.dataTransfer.setData('text/plain', 'new-entity');
}

function dropNewEntity(event) {
    event.preventDefault();
    if (event.dataTransfer.getData('text/plain') === 'new-entity') {
        const rect = document.getElementById('erd-canvas').getBoundingClientRect();
        pendingPosition = {
            x: event.clientX - rect.left,
            y: event.clientY - rect.top
        };
        showAddEntityModal();
    }
}

function addEntityAtPosition(event) {
    if (event.target.id === 'erd-canvas' || event.target.tagName === 'CANVAS') {
        pendingPosition = { x: event.offsetX, y: event.offsetY };
        showAddEntityModal();
    }
}

// =============================================================================
// Preview Modal
// =============================================================================

function showPreview() {
    document.getElementById('preview-overlay').classList.remove('hidden');
}

function hidePreview(event) {
    if (!event || event.target.id === 'preview-overlay') {
        document.getElementById('preview-overlay').classList.add('hidden');
    }
}

// =============================================================================
// Validation Rule Modal
// =============================================================================

function showRuleModal(ruleIdx, ruleName) {
    document.getElementById('rule-modal-title').textContent = ruleName ? `Edit: ${ruleName}` : 'Edit Rule';
    document.getElementById('validation-rule-modal').classList.remove('hidden');
    htmx.ajax('GET', `/spec-builder/validation-rule/${ruleIdx}`, {
        target: '#rule-modal-content',
        swap: 'innerHTML'
    });
}

function hideRuleModal() {
    document.getElementById('validation-rule-modal').classList.add('hidden');
    htmx.ajax('GET', '/spec-builder/validation-rules', {
        target: '#validation-rules-panel',
        swap: 'innerHTML'
    });
}

// =============================================================================
// Context Menu (Hide/Show Entities)
// =============================================================================

function showContextMenu(event, nodeId) {
    const menu = document.getElementById('node-context-menu');
    const isHidden = hiddenEntities.has(nodeId);

    document.getElementById('ctx-node-name').textContent = nodeId;
    document.getElementById('ctx-hide-btn').style.display = isHidden ? 'none' : 'block';
    document.getElementById('ctx-show-btn').style.display = isHidden ? 'block' : 'none';

    menu.style.left = event.pageX + 'px';
    menu.style.top = event.pageY + 'px';
    menu.classList.remove('hidden');
    menu.dataset.nodeId = nodeId;

    setTimeout(() => {
        document.addEventListener('click', closeContextMenu, { once: true });
    }, 0);
}

function closeContextMenu() {
    document.getElementById('node-context-menu').classList.add('hidden');
}

function hideEntity(nodeId) {
    if (!nodeId) nodeId = document.getElementById('node-context-menu').dataset.nodeId;
    hiddenEntities.add(nodeId);

    const colors = NODE_COLORS.hidden;
    nodes.update({
        id: nodeId,
        color: {
            background: colors.background,
            border: colors.border,
            highlight: colors.highlight,
            hover: colors.hover
        },
        font: { ...FONT_CONFIG, color: colors.fontColor },
        opacity: 0.5
    });

    const connectedEdges = edges.get().filter(e => e.from === nodeId || e.to === nodeId);
    connectedEdges.forEach(edge => {
        edges.update({ id: edge.id, hidden: true });
    });

    updateHiddenCount();
    closeContextMenu();
}

function showEntity(nodeId) {
    if (!nodeId) nodeId = document.getElementById('node-context-menu').dataset.nodeId;
    hiddenEntities.delete(nodeId);

    const original = originalNodeColors[nodeId];
    const isRoot = nodeId === rootEntity;
    const colors = isRoot ? NODE_COLORS.root : NODE_COLORS.regular;

    nodes.update({
        id: nodeId,
        color: {
            background: original.background,
            border: original.border,
            highlight: colors.highlight,
            hover: colors.hover
        },
        font: { ...FONT_CONFIG, color: original.fontColor },
        opacity: 1
    });

    const connectedEdges = edges.get().filter(e => e.from === nodeId || e.to === nodeId);
    connectedEdges.forEach(edge => {
        const otherNode = edge.from === nodeId ? edge.to : edge.from;
        if (!hiddenEntities.has(otherNode)) {
            edges.update({ id: edge.id, hidden: false });
        }
    });

    updateHiddenCount();
    closeContextMenu();
}

function showAllEntities() {
    hiddenEntities.forEach(nodeId => {
        showEntity(nodeId);
    });
    hiddenEntities.clear();
    updateHiddenCount();
}

function updateHiddenCount() {
    const badge = document.getElementById('hidden-count-badge');
    const count = hiddenEntities.size;
    if (count > 0) {
        badge.textContent = count + ' hidden';
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }
}

// =============================================================================
// Sidebar Toggle
// =============================================================================

function toggleSidebar() {
    const sidebar = document.querySelector('.erd-sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle-btn');
    sidebar.classList.toggle('collapsed');
    if (sidebar.classList.contains('collapsed')) {
        toggleBtn.textContent = 'Show Sidebar';
        toggleBtn.title = 'Show sidebar (Ctrl+B)';
    } else {
        toggleBtn.textContent = 'Hide Sidebar';
        toggleBtn.title = 'Hide sidebar (Ctrl+B)';
    }
    // Resize the graph to fit new space after animation
    setTimeout(() => {
        if (network) {
            network.fit();
        }
    }, 300);
}

// =============================================================================
// Keyboard Shortcuts
// =============================================================================

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        hideAddEntityModal();
        hideRuleModal();
        hidePreview();
        closeEditorPanel();
        closeContextMenu();
    }
    // Ctrl+B to toggle sidebar
    if (e.ctrlKey && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
    }
});

// =============================================================================
// HTMX Event Listeners
// =============================================================================

document.body.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id === 'editor-content') {
        // Entity was updated, could refresh edges here
    }
});

// =============================================================================
// Initialize on DOM Ready
// =============================================================================

document.addEventListener('DOMContentLoaded', initERD);

// Also try immediately in case DOMContentLoaded already fired
if (document.readyState !== 'loading') {
    setTimeout(initERD, 50);
}

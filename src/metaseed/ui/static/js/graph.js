// Metaseed Entity Graph Visualization

var graphNetwork = null;
var graphData = null;
var currentGraphLayout = 'physics';
// Whether the force simulation is allowed to run. The physics layout keeps
// nodes drifting; this lets the user freeze them. Honoured wherever physics
// would otherwise be (re-)enabled.
var graphPhysicsRunning = true;
var allGraphNodes = [];
var allGraphEdges = [];
var visibleGroups = new Set();
// Every group ever seen. Used to tell a genuinely new entity type (auto-show)
// apart from one the user deliberately hid (must stay hidden across polls).
var knownGroups = new Set();

// Entity type to display mapping (assigned dynamically)
var entityDisplayMap = {};

// Distinct colors for entity types
var GRAPH_COLORS = [
    '#3b82f6', '#10b981', '#ec4899', '#f59e0b', '#14b8a6',
    '#84cc16', '#f43f5e', '#a855f7', '#6366f1', '#06b6d4',
    '#0ea5e9', '#22d3ee', '#92400e', '#fb923c', '#fbbf24'
];

// Shapes for entity types - vis.js shape names
var GRAPH_SHAPES = [
    'dot', 'square', 'diamond', 'triangle', 'triangleDown', 'star', 'hexagon'
];

// Base theme colors
var GRAPH_THEME = {
    background: '#faf8f5',
    text: '#2c3e35',
    edge: '#87a878',
    edgeHighlight: '#4a7c59'
};

// Assign display properties to entity types as they appear
function assignEntityDisplay(entityTypes) {
    entityDisplayMap = {};
    var types = Array.from(entityTypes);
    types.forEach(function(type, index) {
        entityDisplayMap[type] = {
            color: GRAPH_COLORS[index % GRAPH_COLORS.length],
            shape: GRAPH_SHAPES[index % GRAPH_SHAPES.length],
            order: index
        };
    });
}

// Generate SVG for legend shape matching vis.js shapes
function getLegendShapeSvg(shape, color) {
    var size = 14;
    var half = size / 2;
    var svg = '<svg width="' + size + '" height="' + size + '" style="vertical-align: middle; margin-right: 4px;">';

    switch (shape) {
        case 'dot':
            svg += '<circle cx="' + half + '" cy="' + half + '" r="' + (half - 1) + '" fill="' + color + '"/>';
            break;
        case 'square':
            svg += '<rect x="1" y="1" width="' + (size - 2) + '" height="' + (size - 2) + '" fill="' + color + '"/>';
            break;
        case 'diamond':
            svg += '<polygon points="' + half + ',1 ' + (size - 1) + ',' + half + ' ' + half + ',' + (size - 1) + ' 1,' + half + '" fill="' + color + '"/>';
            break;
        case 'triangle':
            svg += '<polygon points="' + half + ',1 ' + (size - 1) + ',' + (size - 1) + ' 1,' + (size - 1) + '" fill="' + color + '"/>';
            break;
        case 'triangleDown':
            svg += '<polygon points="1,1 ' + (size - 1) + ',1 ' + half + ',' + (size - 1) + '" fill="' + color + '"/>';
            break;
        case 'star':
            var points = [];
            for (var i = 0; i < 5; i++) {
                var outerAngle = (i * 72 - 90) * Math.PI / 180;
                var innerAngle = ((i * 72) + 36 - 90) * Math.PI / 180;
                points.push((half + (half - 1) * Math.cos(outerAngle)) + ',' + (half + (half - 1) * Math.sin(outerAngle)));
                points.push((half + (half - 1) * 0.4 * Math.cos(innerAngle)) + ',' + (half + (half - 1) * 0.4 * Math.sin(innerAngle)));
            }
            svg += '<polygon points="' + points.join(' ') + '" fill="' + color + '"/>';
            break;
        case 'hexagon':
            var hexPoints = [];
            for (var j = 0; j < 6; j++) {
                var angle = (j * 60 - 90) * Math.PI / 180;
                hexPoints.push((half + (half - 1) * Math.cos(angle)) + ',' + (half + (half - 1) * Math.sin(angle)));
            }
            svg += '<polygon points="' + hexPoints.join(' ') + '" fill="' + color + '"/>';
            break;
        default:
            svg += '<circle cx="' + half + '" cy="' + half + '" r="' + (half - 1) + '" fill="' + color + '"/>';
    }

    svg += '</svg>';
    return svg;
}

// Get display for an entity type
function getEntityDisplay(entityType) {
    return entityDisplayMap[entityType] || { color: '#78716c', shape: 'dot', order: 99 };
}

// Build groups from assigned display settings
function buildGraphGroups() {
    var groups = {};
    for (var entityType in entityDisplayMap) {
        var display = entityDisplayMap[entityType];
        groups[entityType] = {
            color: display.color,
            shape: display.shape
        };
    }
    return groups;
}

// Get graph options based on layout type
function getGraphOptions(layout) {
    var baseOptions = {
        groups: buildGraphGroups(),
        nodes: {
            size: 18,
            font: {
                size: 13,
                color: GRAPH_THEME.text,
                face: 'system-ui, -apple-system, sans-serif'
            },
            borderWidth: 2,
            shadow: {
                enabled: true,
                color: 'rgba(0,0,0,0.15)',
                size: 8,
                x: 2,
                y: 2
            }
        },
        edges: {
            arrows: { to: { enabled: true, scaleFactor: 0.5 } },
            font: { size: 10, color: GRAPH_THEME.text, face: 'system-ui, sans-serif', strokeWidth: 0 },
            color: { color: GRAPH_THEME.edge, highlight: GRAPH_THEME.edgeHighlight, hover: GRAPH_THEME.edgeHighlight },
            smooth: { type: 'cubicBezier', roundness: 0.4 },
            width: 1.5
        },
        interaction: {
            hover: true,
            tooltipDelay: 150,
            zoomView: true,
            dragView: true,
            dragNodes: true
        },
        layout: { randomSeed: 42 }
    };

    if (layout === 'hierarchical') {
        return Object.assign({}, baseOptions, {
            layout: {
                hierarchical: {
                    enabled: true,
                    direction: 'UD',
                    sortMethod: 'directed',
                    levelSeparation: 120,
                    nodeSpacing: 180,
                    treeSpacing: 200
                }
            },
            physics: { enabled: false }
        });
    } else {
        var spacing = parseInt(document.getElementById('graph-spacing')?.value || 100);
        var repulsion = parseInt(document.getElementById('graph-repulsion')?.value || -500);
        var gravity = parseFloat(document.getElementById('graph-gravity')?.value || 0.01);

        return Object.assign({}, baseOptions, {
            layout: {
                randomSeed: 42,
                hierarchical: { enabled: false }
            },
            physics: {
                enabled: graphPhysicsRunning,
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {
                    gravitationalConstant: repulsion,
                    centralGravity: gravity,
                    springLength: spacing,
                    springConstant: 0.02,
                    damping: 0.4,
                    avoidOverlap: 1
                },
                stabilization: false
            }
        });
    }
}

// Which views are on: the entity list, the graph, or both. At least one
// stays on; both share the workspace width. Remembered per browser.
function viewsOn() {
    var stored = null;
    try { stored = localStorage.getItem('datasetViews'); } catch (e) {}
    if (stored === 'list' || stored === 'graph' || stored === 'both') return stored;
    return 'list';
}

function applyViews() {
    var views = viewsOn();
    var list = views !== 'graph';
    var graph = views !== 'list';
    var workspace = document.getElementById('workspace');
    var main = document.getElementById('main');
    var container = document.getElementById('graph-container');
    if (!container) return;
    if (workspace) {
        workspace.classList.toggle('show-list', list);
        workspace.classList.toggle('show-graph', graph);
    }
    if (main) main.classList.toggle('hidden', !list);
    container.classList.toggle('hidden', !graph);
    var listBtn = document.getElementById('view-list-btn');
    var graphBtn = document.getElementById('view-graph-btn');
    if (listBtn) listBtn.setAttribute('aria-pressed', String(list));
    if (graphBtn) graphBtn.setAttribute('aria-pressed', String(graph));
    if (graph) {
        loadGraph();
        startGraphPolling();
        if (graphNetwork) { graphNetwork.redraw(); fitGraph(); }
    } else {
        stopGraphPolling();
    }
}

function toggleView(which) {
    var views = viewsOn();
    var list = views !== 'graph';
    var graph = views !== 'list';
    if (which === 'list') list = !list; else graph = !graph;
    // Switching the last view off would leave nothing; the other comes on.
    if (!list && !graph) { if (which === 'list') graph = true; else list = true; }
    var next = list && graph ? 'both' : (graph ? 'graph' : 'list');
    try { localStorage.setItem('datasetViews', next); } catch (e) {}
    applyViews();
}

function closeGraph() {
    if (viewsOn() !== 'list') toggleView('graph');
}

function toggleGraph() {
    toggleView('graph');
}

function fullscreenGraph() {
    var container = document.getElementById('graph-container');
    if (!container || !container.requestFullscreen) return;
    if (document.fullscreenElement) {
        document.exitFullscreen();
    } else {
        container.requestFullscreen().then(function() {
            if (graphNetwork) { graphNetwork.redraw(); fitGraph(); }
        });
    }
}

document.addEventListener('fullscreenchange', function() {
    if (graphNetwork) { graphNetwork.redraw(); fitGraph(); }
});

// The remembered views come back with the dataset page.
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('view-graph-btn')) applyViews();
});

// /graph: the graph alone, for a second window or screen.
document.addEventListener('DOMContentLoaded', function() {
    if (document.body.getAttribute('data-standalone-graph')) {
        loadGraph();
        startGraphPolling();
    }
});

function prepareGraphData(data) {
    // Collect unique entity types and assign colors/shapes
    var entityTypes = new Set();
    data.nodes.forEach(function(n) { entityTypes.add(n.group); });
    assignEntityDisplay(entityTypes);

    // Count edges per node for sizing
    var edgeCount = {};
    data.edges.forEach(function(edge) {
        edgeCount[edge.from] = (edgeCount[edge.from] || 0) + 1;
        edgeCount[edge.to] = (edgeCount[edge.to] || 0) + 1;
    });

    // Apply colors, shapes, and sizes to nodes
    var minSize = 12, maxSize = 30;
    var maxEdges = Math.max.apply(null, Object.values(edgeCount).concat([1]));
    data.nodes.forEach(function(node) {
        var display = getEntityDisplay(node.group);
        node.color = display.color;
        node.shape = display.shape;
        var edges = edgeCount[node.id] || 0;
        node.size = minSize + (edges / maxEdges) * (maxSize - minSize);
    });

    // Style reference edges differently (dashed, different color)
    data.edges.forEach(function(edge) {
        if (edge.dashes) {
            // Reference edge - use a distinct color
            edge.color = { color: '#e67e22', highlight: '#d35400', hover: '#d35400' };
            edge.width = 1.5;
        }
    });

    return data;
}

function updateGraphIncremental(newNodes, newEdges) {
    if (!graphData || !graphData.nodes || !graphData.edges) return false;

    // Filter new data by visible groups
    var visibleNewNodes = newNodes.filter(function(n) {
        return visibleGroups.has(n.group);
    });
    var visibleNewNodeIds = new Set(visibleNewNodes.map(function(n) { return n.id; }));
    var visibleNewEdges = newEdges.filter(function(e) {
        return visibleNewNodeIds.has(e.from) && visibleNewNodeIds.has(e.to);
    });

    // Build maps of current data
    var currentNodeIds = new Set(graphData.nodes.getIds());

    // Build maps of new visible data
    var newNodeIds = new Set(visibleNewNodes.map(function(n) { return n.id; }));
    var newEdgeMap = {};
    visibleNewEdges.forEach(function(e) {
        var edgeId = e.id || (e.from + '->' + e.to);
        newEdgeMap[edgeId] = e;
    });

    // Find nodes to add and remove
    var nodesToAdd = visibleNewNodes.filter(function(n) { return !currentNodeIds.has(n.id); });
    var nodesToRemove = Array.from(currentNodeIds).filter(function(id) { return !newNodeIds.has(id); });

    // Find edges to add and remove
    var currentEdges = graphData.edges.get();
    var currentEdgeMap = {};
    currentEdges.forEach(function(e) {
        var edgeId = e.id || (e.from + '->' + e.to);
        currentEdgeMap[edgeId] = e;
    });

    var edgesToAdd = [];
    for (var edgeId in newEdgeMap) {
        if (!currentEdgeMap[edgeId]) {
            edgesToAdd.push(newEdgeMap[edgeId]);
        }
    }

    var edgesToRemove = [];
    for (var edgeId in currentEdgeMap) {
        if (!newEdgeMap[edgeId]) {
            edgesToRemove.push(currentEdgeMap[edgeId].id || edgeId);
        }
    }

    // Check if any changes needed
    var hasChanges = nodesToAdd.length > 0 || nodesToRemove.length > 0 ||
                     edgesToAdd.length > 0 || edgesToRemove.length > 0;

    if (!hasChanges) {
        return false;
    }

    // Apply changes
    if (nodesToRemove.length > 0) {
        graphData.nodes.remove(nodesToRemove);
    }
    if (edgesToRemove.length > 0) {
        graphData.edges.remove(edgesToRemove);
    }
    if (nodesToAdd.length > 0) {
        graphData.nodes.add(nodesToAdd);
    }
    if (edgesToAdd.length > 0) {
        graphData.edges.add(edgesToAdd);
    }

    // Update sizes for all nodes if edges changed
    if (edgesToAdd.length > 0 || edgesToRemove.length > 0) {
        var allEdges = graphData.edges.get();
        var edgeCount = {};
        allEdges.forEach(function(e) {
            edgeCount[e.from] = (edgeCount[e.from] || 0) + 1;
            edgeCount[e.to] = (edgeCount[e.to] || 0) + 1;
        });
        var minSize = 12, maxSize = 30;
        var maxEdges = Math.max.apply(null, Object.values(edgeCount).concat([1]));
        var updates = [];
        graphData.nodes.forEach(function(node) {
            var edges = edgeCount[node.id] || 0;
            var newSize = minSize + (edges / maxEdges) * (maxSize - minSize);
            if (node.size !== newSize) {
                updates.push({ id: node.id, size: newSize });
            }
        });
        if (updates.length > 0) {
            graphData.nodes.update(updates);
        }
    }

    return true;
}

// Where the graph data comes from, decided when the graph is drawn rather
// than when this file loads: an embedding application sets
// window.METASEED_GRAPH_URL (or passes a URL to loadGraph) after the script
// tag, and metaseed's own UI falls back to its single-dataset endpoint.
function graphUrl(url) {
    if (url) return url;
    if (window.METASEED_GRAPH_URL) return window.METASEED_GRAPH_URL;
    return (typeof BASE_URL === 'undefined' ? '' : BASE_URL) + '/api/graph';
}

// The public drawing entry point: everything the fetch path does once the
// response has arrived. A host with its own transport calls this and never
// touches the fetch below — the drawing is what is worth reusing.
function renderGraphData(data) {
    var graphView = document.getElementById('graph-view');
    try {
        // Show empty graph canvas even with no entities
        if (!data || !data.nodes || data.nodes.length === 0) {
            data = { nodes: [], edges: [] };
        }

        // Check if this is initial load
        var isFirstLoad = !graphNetwork || !graphData;

        // Store original data for filtering
        allGraphNodes = data.nodes.slice();
        allGraphEdges = data.edges.slice();

        // Only initialize visible groups on first load
        if (isFirstLoad) {
            visibleGroups.clear();
            knownGroups.clear();
            // Use entity types from spec if available, otherwise from nodes
            var types = data.entity_types || [];
            types.forEach(function(t) {
                visibleGroups.add(t);
                knownGroups.add(t);
            });
            // Also add any types from nodes (in case spec is incomplete)
            allGraphNodes.forEach(function(n) {
                visibleGroups.add(n.group);
                knownGroups.add(n.group);
            });
        }

        // Check for genuinely new entity types before preparing data. A type
        // is new only if never seen before; a type the user toggled off is
        // already known and must not be re-shown by a poll.
        var hadNewTypes = false;
        if (!isFirstLoad) {
            data.nodes.forEach(function(n) {
                if (!knownGroups.has(n.group)) {
                    knownGroups.add(n.group);
                    visibleGroups.add(n.group);
                    hadNewTypes = true;
                }
            });
        }

        // Prepare node styling
        data = prepareGraphData(data);

        // If graph exists, update incrementally
        if (!isFirstLoad) {
            updateGraphIncremental(data.nodes, data.edges);
            // Update legend if new entity types appeared
            if (hadNewTypes) {
                renderGraphLegend(data);
            }
        } else {
            // Initial render
            renderGraph(data);
            renderGraphLegend(data);
        }
    } catch (error) {
        console.error('Error drawing graph:', error);
        if (graphView) {
            graphView.innerHTML = '<div class="graph-error">Failed to draw graph</div>';
        }
    }
}

function loadGraph(url) {
    var graphView = document.getElementById('graph-view');

    // Only show loading message on initial load
    if (!graphNetwork && graphView) {
        graphView.innerHTML = '<div class="graph-loading">Loading graph...</div>';
    }

    return fetch(graphUrl(url))
        .then(function(response) { return response.json(); })
        .then(renderGraphData)
        .catch(function(error) {
            console.error('Error loading graph:', error);
            if (graphView) {
                graphView.innerHTML = '<div class="graph-error">Failed to load graph</div>';
            }
        });
}

function renderGraph(data) {
    var container = document.getElementById('graph-view');
    if (!container) return;

    container.innerHTML = '';
    container.style.background = GRAPH_THEME.background;

    graphData = {
        nodes: new vis.DataSet(data.nodes),
        edges: new vis.DataSet(data.edges)
    };

    graphNetwork = new vis.Network(container, graphData, getGraphOptions(currentGraphLayout));
}

function renderGraphLegend(data) {
    var legendContainer = document.getElementById('graph-legend');
    if (!legendContainer) return;

    // Count nodes per type
    var typeCounts = {};
    data.nodes.forEach(function(node) {
        if (node.group) {
            typeCounts[node.group] = (typeCounts[node.group] || 0) + 1;
        }
    });

    // Use entity_types from spec (maintains spec order), fallback to node groups
    var entityTypes = data.entity_types || Object.keys(typeCounts);

    // Assign colors/shapes to all spec types
    assignEntityDisplay(new Set(entityTypes));

    var html = '';
    entityTypes.forEach(function(type, index) {
        var count = typeCounts[type] || 0;
        var display = getEntityDisplay(type);
        var isVisible = visibleGroups.has(type);
        var isEmpty = count === 0;
        var itemClass = 'graph-legend-item';
        if (!isVisible) itemClass += ' legend-hidden';
        if (isEmpty) itemClass += ' legend-empty';

        html += '<label class="' + itemClass + '" data-type="' + type + '">';
        html += '<input type="checkbox" ' + (isVisible ? 'checked' : '') + ' onchange="toggleNodeType(\'' + type + '\')">';
        html += getLegendShapeSvg(display.shape, display.color);
        html += '<span class="graph-legend-label">' + type;
        if (count > 0) {
            html += ' (' + count + ')';
        }
        html += '</span>';
        html += '</label>';
    });

    legendContainer.innerHTML = html;
}

function toggleNodeType(group) {
    if (visibleGroups.has(group)) {
        visibleGroups.delete(group);
    } else {
        visibleGroups.add(group);
    }
    filterGraph();
    var item = document.querySelector('.graph-legend-item[data-type="' + group + '"]');
    if (item) {
        item.classList.toggle('legend-hidden', !visibleGroups.has(group));
    }
}

function filterGraph() {
    if (!graphData || !allGraphNodes.length) return;

    var visibleNodeIds = new Set();
    var filteredNodes = allGraphNodes.filter(function(n) {
        if (visibleGroups.has(n.group)) {
            visibleNodeIds.add(n.id);
            return true;
        }
        return false;
    });

    var filteredEdges = allGraphEdges.filter(function(e) {
        return visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to);
    });

    filteredNodes.forEach(function(n) {
        n.color = getEntityDisplay(n.group).color;
    });

    graphData.nodes.clear();
    graphData.nodes.add(filteredNodes);
    graphData.edges.clear();
    graphData.edges.add(filteredEdges);

    if (graphNetwork) {
        if (currentGraphLayout === 'physics' && graphPhysicsRunning) {
            graphNetwork.setOptions({ physics: { enabled: true } });
        }
        graphNetwork.fit({ animation: { duration: 300 } });
    }
}

function toggleGraphPhysics() {
    graphPhysicsRunning = !graphPhysicsRunning;
    if (graphNetwork) {
        graphNetwork.setOptions({ physics: { enabled: graphPhysicsRunning } });
        // setOptions alone leaves the current solver loop running until it
        // settles; stop/start it explicitly so the freeze is immediate.
        if (graphPhysicsRunning) {
            graphNetwork.startSimulation();
        } else {
            graphNetwork.stopSimulation();
        }
    }
    var btn = document.getElementById('graph-physics-btn');
    if (btn) {
        btn.textContent = graphPhysicsRunning ? 'Stop Physics' : 'Start Physics';
    }
}

function toggleGraphLayout() {
    currentGraphLayout = currentGraphLayout === 'physics' ? 'hierarchical' : 'physics';
    var btn = document.getElementById('graph-layout-btn');
    if (btn) btn.textContent = currentGraphLayout === 'physics' ? 'Hierarchical' : 'Physics';

    if (graphNetwork && graphData) {
        var container = document.getElementById('graph-view');
        graphNetwork = new vis.Network(container, graphData, getGraphOptions(currentGraphLayout));
    }
}

function updateGraphPhysics() {
    if (!graphNetwork || currentGraphLayout !== 'physics' || !graphPhysicsRunning) return;

    var spacing = parseInt(document.getElementById('graph-spacing')?.value || 100);
    var repulsion = parseInt(document.getElementById('graph-repulsion')?.value || -500);
    var gravity = parseFloat(document.getElementById('graph-gravity')?.value || 0.01);

    graphNetwork.setOptions({
        physics: {
            enabled: true,
            forceAtlas2Based: {
                springLength: spacing,
                gravitationalConstant: repulsion,
                centralGravity: gravity
            }
        }
    });

    // Perturb nodes to trigger re-layout
    var positions = graphNetwork.getPositions();
    var updates = [];
    for (var id in positions) {
        updates.push({
            id: id,
            x: positions[id].x + (Math.random() - 0.5) * 10,
            y: positions[id].y + (Math.random() - 0.5) * 10
        });
    }
    graphData.nodes.update(updates);

    graphNetwork.once('stabilized', function() {
        graphNetwork.setOptions({ physics: { enabled: false } });
    });
}

function updateGraphEdgeWidth() {
    if (!graphNetwork || !graphData) return;
    var width = parseFloat(document.getElementById('graph-edge-width')?.value || 1.5);
    var edges = graphData.edges.get();
    edges.forEach(function(edge) {
        graphData.edges.update({ id: edge.id, width: width });
    });
}

function fitGraph() {
    if (graphNetwork) {
        graphNetwork.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
    }
}

// Watch for theme changes
if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function() {
        if (graphNetwork && graphData) {
            document.getElementById('graph-view').style.background = GRAPH_THEME.background;
            loadGraph();
        }
    });
}

// An embedding page that simply includes this file gets a drawn graph rather
// than a blank canvas and no error. Metaseed's own UI reveals the graph
// through htmx instead, so this only fires where the container is already on
// the page; a host driving its own draw sets METASEED_GRAPH_AUTOLOAD = false.
document.addEventListener('DOMContentLoaded', function() {
    if (window.METASEED_GRAPH_AUTOLOAD === false) return;
    var container = document.getElementById('graph-container');
    if (container && container.classList.contains('hidden')) return;
    if (document.getElementById('graph-view')) {
        loadGraph();
    }
});

// The embedding contract, documented in docs/guides/embedding-the-graph.md.
// Assigning explicitly rather than relying on implicit globals keeps the entry
// points findable, and survives a future move into a module.
window.renderGraphData = renderGraphData;
window.loadGraph = loadGraph;

// Refresh the graph after an entity operation, if the graph is visible.
// Debounced so a burst of swaps redraws once.
function scheduleGraphRefresh() {
    var graphContainer = document.getElementById('graph-container');
    if (!graphContainer || graphContainer.classList.contains('hidden')) return;
    if (window.graphRefreshTimeout) {
        clearTimeout(window.graphRefreshTimeout);
    }
    window.graphRefreshTimeout = setTimeout(function() {
        loadGraph();
    }, 100);
}

// A content swap (add row, delete, open an entity) redraws the graph.
document.addEventListener('htmx:afterSwap', scheduleGraphRefresh);

// An inline cell edit posts with hx-swap="none" and so fires no afterSwap; it
// signals its change with the entityChanged trigger instead. Without this a
// change to the field a node is labelled by only reached the graph on the next
// swap or a full reload.
document.addEventListener('entityChanged', scheduleGraphRefresh);

// Metaseed Entity Graph Visualization

var graphNetwork = null;
var graphData = null;
var currentGraphLayout = 'physics';
var allGraphNodes = [];
var allGraphEdges = [];
var visibleGroups = new Set();

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
                enabled: true,
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

function toggleGraph() {
    var container = document.getElementById('graph-container');
    var main = document.getElementById('main');
    var btn = document.getElementById('graph-toggle');

    if (container.classList.contains('hidden')) {
        container.classList.remove('hidden');
        main.classList.add('hidden');
        btn.textContent = 'Show List';
        loadGraph();
        startGraphPolling();
    } else {
        container.classList.add('hidden');
        main.classList.remove('hidden');
        btn.textContent = 'Show Graph';
        stopGraphPolling();
    }
}

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

    return nodesToAdd.length > 0 || nodesToRemove.length > 0 ||
           edgesToAdd.length > 0 || edgesToRemove.length > 0;
}

function loadGraph() {
    var graphView = document.getElementById('graph-view');

    // Only show loading message on initial load
    if (!graphNetwork && graphView) {
        graphView.innerHTML = '<div class="graph-loading">Loading graph...</div>';
    }

    fetch('/api/graph')
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (!data.nodes || data.nodes.length === 0) {
                if (graphView) {
                    graphView.innerHTML = '<div class="graph-empty">No entities to display. Create an entity to see it in the graph.</div>';
                }
                graphNetwork = null;
                graphData = null;
                return;
            }

            // Check if this is initial load
            var isFirstLoad = !graphNetwork || !graphData;

            // Store original data for filtering
            allGraphNodes = data.nodes.slice();
            allGraphEdges = data.edges.slice();

            // Only initialize visible groups on first load
            if (isFirstLoad) {
                visibleGroups.clear();
                allGraphNodes.forEach(function(n) { visibleGroups.add(n.group); });
            }

            // Prepare node styling
            data = prepareGraphData(data);

            // If graph exists, update incrementally (don't touch legend)
            // updateGraphIncremental respects visibleGroups filter
            if (!isFirstLoad) {
                updateGraphIncremental(data.nodes, data.edges);
            } else {
                // Initial render
                renderGraph(data);
                renderGraphLegend(data);
            }
        })
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

    var types = {};
    data.nodes.forEach(function(node) {
        if (node.group) {
            if (!types[node.group]) {
                var display = getEntityDisplay(node.group);
                types[node.group] = {
                    color: display.color,
                    shape: display.shape,
                    order: display.order,
                    count: 0
                };
            }
            types[node.group].count++;
        }
    });

    // Sort by assigned order
    var sortedTypes = Object.keys(types).sort(function(a, b) {
        return types[a].order - types[b].order;
    });

    var html = '';
    sortedTypes.forEach(function(type) {
        var info = types[type];
        var isVisible = visibleGroups.has(type);
        var itemClass = 'graph-legend-item' + (isVisible ? '' : ' legend-hidden');
        html += '<label class="' + itemClass + '" data-type="' + type + '">';
        html += '<input type="checkbox" ' + (isVisible ? 'checked' : '') + ' onchange="toggleNodeType(\'' + type + '\')">';
        html += getLegendShapeSvg(info.shape, info.color);
        html += '<span class="graph-legend-label">' + type + ' (' + info.count + ')</span>';
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
        if (currentGraphLayout === 'physics') {
            graphNetwork.setOptions({ physics: { enabled: true } });
        }
        graphNetwork.fit({ animation: { duration: 300 } });
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
    if (!graphNetwork || currentGraphLayout !== 'physics') return;

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

// Refresh graph after entity operations (if graph is visible)
document.addEventListener('htmx:afterSwap', function(e) {
    var graphContainer = document.getElementById('graph-container');
    if (graphContainer && !graphContainer.classList.contains('hidden')) {
        if (window.graphRefreshTimeout) {
            clearTimeout(window.graphRefreshTimeout);
        }
        window.graphRefreshTimeout = setTimeout(function() {
            loadGraph();
        }, 100);
    }
});

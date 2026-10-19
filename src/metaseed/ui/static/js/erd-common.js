/**
 * Common ERD (Entity Relationship Diagram) module.
 * Shared between spec-builder and merge pages.
 */
const ERD = (function() {
    // Private state
    let _network = null;
    let _nodes = null;
    let _edges = null;
    let _hierarchical = false;

    // The page's Tree button, where it has one, shows which layout is on.
    function _markHierarchicalButton() {
        const button = document.getElementById('btn-hierarchical');
        if (button) button.classList.toggle('active', _hierarchical);
    }

    const TREE_GAP = 60;

    // vis-network places tree levels a fixed distance apart, which the tall
    // entity boxes of a specification overrun. Keep the levels and the order
    // vis chose within each, and restack them so every level is centred below the
    // tallest box of the one above and boxes in a level sit side by side.
    function _spaceTreeBySize() {
        const positions = _network.getPositions();
        const levels = new Map();
        for (const id of Object.keys(positions)) {
            const key = Math.round(positions[id].y);
            if (!levels.has(key)) levels.set(key, []);
            const node = _nodes.get(id) !== null ? id : Number(id);
            levels.get(key).push({ id: node, x: positions[id].x, box: _network.getBoundingBox(node) });
        }
        let top = 0;
        for (const key of [...levels.keys()].sort((a, b) => a - b)) {
            const row = levels.get(key).sort((a, b) => a.x - b.x);
            const width = row.reduce((sum, n) => sum + n.box.right - n.box.left, 0)
                + TREE_GAP * (row.length - 1);
            const centre = row.reduce((sum, n) => sum + n.x, 0) / row.length;
            const height = Math.max(...row.map(n => n.box.bottom - n.box.top));
            let left = centre - width / 2;
            for (const n of row) {
                const w = n.box.right - n.box.left;
                _network.moveNode(n.id, left + w / 2, top + height / 2);
                left += w + TREE_GAP;
            }
            top += height + TREE_GAP * 2;
        }
    }

    // Standard network options
    const OPTIONS = {
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
            keyboard: { enabled: false }
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

    return {
        /**
         * Get the network options.
         */
        getOptions() {
            return structuredClone(OPTIONS);
        },

        /**
         * Create a new network.
         */
        createNetwork(container, nodeData, edgeData, customOptions = {}) {
            _nodes = new vis.DataSet(nodeData);
            _edges = new vis.DataSet(edgeData);

            const options = { ...OPTIONS, ...customOptions };

            if (_network) {
                _network.destroy();
            }

            _network = new vis.Network(container, { nodes: _nodes, edges: _edges }, options);
            // A new graph starts in the free arrangement, whatever the last one showed.
            _hierarchical = false;
            _markHierarchicalButton();

            _network.once('stabilizationIterationsDone', () => {
                _network.setOptions({ physics: { enabled: false } });
            });

            return _network;
        },

        /**
         * Get the current network instance.
         */
        getNetwork() {
            return _network;
        },

        /**
         * Get the nodes DataSet.
         */
        getNodes() {
            return _nodes;
        },

        /**
         * Get the edges DataSet.
         */
        getEdges() {
            return _edges;
        },

        /**
         * Auto-layout using force-directed algorithm.
         */
        autoLayout() {
            if (!_network) return;

            // Force direction and the tree are alternatives: asking for one
            // leaves the other.
            _hierarchical = false;
            _markHierarchicalButton();

            _network.setOptions({
                layout: { hierarchical: { enabled: false } },
                physics: {
                    enabled: true,
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {
                        gravitationalConstant: -100,
                        centralGravity: 0.01,
                        springLength: 150,
                        springConstant: 0.08,
                        damping: 0.4
                    },
                    stabilization: {
                        enabled: true,
                        iterations: 200,
                        updateInterval: 25
                    }
                }
            });

            _network.once('stabilizationIterationsDone', () => {
                _network.setOptions({ physics: { enabled: false } });
                _network.fit({ animation: true });
            });

            _network.stabilize();
        },

        /**
         * Switch between the tree layout and the free arrangement.
         *
         * A specification is a containment tree with a root, so laying it out
         * top-down says more than a force-directed arrangement does. It is a
         * toggle and not a replacement, because reference edges make the graph
         * a graph again and force direction reads those better. The
         * configuration is the one the dataset graph uses (graph.js), so the
         * views agree about what a hierarchy looks like.
         */
        toggleHierarchicalLayout() {
            if (!_network) return;

            _hierarchical = !_hierarchical;
            _network.setOptions(_hierarchical
                ? {
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
                }
                : {
                    layout: { hierarchical: { enabled: false } },
                    physics: { enabled: false }
                });
            if (_hierarchical) _spaceTreeBySize();
            _markHierarchicalButton();
            _network.fit({ animation: true });
        },

        /**
         * Zoom in.
         */
        zoomIn() {
            if (_network) {
                const scale = _network.getScale();
                _network.moveTo({ scale: scale * 1.15, animation: { duration: 200 } });
            }
        },

        /**
         * Zoom out.
         */
        zoomOut() {
            if (_network) {
                const scale = _network.getScale();
                _network.moveTo({ scale: scale / 1.15, animation: { duration: 200 } });
            }
        },

        /**
         * Fit graph to viewport.
         */
        fitGraph() {
            if (_network) {
                _network.fit({ animation: { duration: 300 } });
            }
        }
    };
})();

// Convenience functions for HTML onclick handlers
function autoLayout() { ERD.autoLayout(); }
function toggleHierarchicalLayout() { ERD.toggleHierarchicalLayout(); }
function zoomIn() { ERD.zoomIn(); }
function zoomOut() { ERD.zoomOut(); }
function fitGraph() { ERD.fitGraph(); }

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
        },

        /**
         * The graph as a PNG data URL: every shown node, whatever is in view,
         * on white. The canvas is resized to the frame `pngExportFrame`
         * decides and copied once vis has drawn it there (`afterDrawing`; a
         * redraw is asynchronous, so copying straight away copies a blank
         * canvas), then the size and view are put back.
         *
         * @returns {Promise<string|null>} The data URL, or null with no graph.
         */
        toPngDataUrl() {
            if (!_network) return Promise.resolve(null);
            const ids = _nodes.getIds().filter(id => !_nodes.get(id).hidden);
            if (!ids.length) return Promise.resolve(null);
            const frame = pngExportFrame(ids.map(id => _network.getBoundingBox(id)), window.devicePixelRatio || 1);
            const container = _network.body.container;
            const saved = {
                width: container.style.width,
                height: container.style.height,
                position: _network.getViewPosition(),
                scale: _network.getScale()
            };
            const restore = () => {
                container.style.width = saved.width;
                container.style.height = saved.height;
                _network.setSize('100%', '100%');
                _network.moveTo({ position: saved.position, scale: saved.scale });
            };
            return new Promise((resolve, reject) => {
                _network.once('afterDrawing', drawn => {
                    try {
                        const source = drawn.canvas;
                        const out = document.createElement('canvas');
                        out.width = source.width;
                        out.height = source.height;
                        const context = out.getContext('2d');
                        context.fillStyle = '#ffffff';
                        context.fillRect(0, 0, out.width, out.height);
                        context.drawImage(source, 0, 0);
                        resolve(out.toDataURL('image/png'));
                    } catch (error) {
                        reject(error);
                    } finally {
                        restore();
                    }
                });
                container.style.width = `${frame.width}px`;
                container.style.height = `${frame.height}px`;
                _network.setSize(`${frame.width}px`, `${frame.height}px`);
                _network.moveTo({ position: frame.center, scale: frame.scale });
                _network.redraw();
            });
        },

        /**
         * Download the graph as `<name>.png`.
         */
        async exportPng(name) {
            const url = await this.toPngDataUrl();
            if (!url) return;
            const link = document.createElement('a');
            link.href = url;
            link.download = `${name || 'graph'}.png`;
            document.body.appendChild(link);
            link.click();
            link.remove();
        }
    };
})();

/**
 * The frame a PNG export draws: the nodes' extent plus a margin, centred, at
 * two image pixels per graph unit and at most 8192 on a side.
 *
 * The browser multiplies the canvas by its pixel ratio, so the view scale is
 * divided by it and the image is the same size on every screen. Width and
 * height are CSS pixels, the unit the container is sized in.
 */
function pngExportFrame(boxes, devicePixelRatio) {
    const MARGIN = 40;
    const PIXELS_PER_UNIT = 2;
    const MAX_PIXELS = 8192;
    const left = Math.min(...boxes.map(b => b.left));
    const top = Math.min(...boxes.map(b => b.top));
    const right = Math.max(...boxes.map(b => b.right));
    const bottom = Math.max(...boxes.map(b => b.bottom));
    const width = right - left + 2 * MARGIN;
    const height = bottom - top + 2 * MARGIN;
    let scale = PIXELS_PER_UNIT / devicePixelRatio;
    const largest = Math.max(width, height) * scale * devicePixelRatio;
    if (largest > MAX_PIXELS) scale *= MAX_PIXELS / largest;
    return {
        center: { x: (left + right) / 2, y: (top + bottom) / 2 },
        width: Math.floor(width * scale),
        height: Math.floor(height * scale),
        scale
    };
}

// Convenience functions for HTML onclick handlers
function autoLayout() { ERD.autoLayout(); }
function toggleHierarchicalLayout() { ERD.toggleHierarchicalLayout(); }
function zoomIn() { ERD.zoomIn(); }
function zoomOut() { ERD.zoomOut(); }
function fitGraph() { ERD.fitGraph(); }

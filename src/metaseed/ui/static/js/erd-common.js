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
         * canvas), then the size and view are put back. Legend entries, as
         * `visibleLegend` reads them, are drawn as a band below the graph.
         *
         * @param {Array<Object>} [legend] The entries to draw; none by default.
         * @returns {Promise<string|null>} The data URL, or null with no graph.
         */
        toPngDataUrl(legend = []) {
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
                        const rows = pngLegendRows(out.getContext('2d'), legend, source.width);
                        out.height = source.height + rows.height;
                        const context = out.getContext('2d');
                        context.fillStyle = '#ffffff';
                        context.fillRect(0, 0, out.width, out.height);
                        context.drawImage(source, 0, 0);
                        drawPngLegend(context, rows, source.height);
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
         * Download the graph as `<name>.png`, with the given legend entries.
         */
        async exportPng(name, legend = []) {
            const url = await this.toPngDataUrl(legend);
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

// Legend text and swatches in the PNG, in image pixels per CSS pixel: the
// graph is drawn at two pixels per unit, so the legend matches its text size.
const LEGEND_SCALE = 2;
const LEGEND_FONT = 13 * LEGEND_SCALE;
const LEGEND_PAD = 16 * LEGEND_SCALE;
const LEGEND_ROW = 24 * LEGEND_SCALE;
const LEGEND_SWATCH = 20 * LEGEND_SCALE;
const LEGEND_GAP = 6 * LEGEND_SCALE;
const LEGEND_SPACING = 24 * LEGEND_SCALE;

/**
 * The entries of the legend the page shows under the canvas, for the PNG.
 *
 * Each `.legend-item` of the visible `.canvas-legend` becomes one entry: a
 * coloured dot, an edge line (dashed where the page draws it dashed), or a
 * glyph from its `<code>`, followed by its label. Items marked
 * `data-legend-hint` explain the page, not the graph, and are left out.
 *
 * @returns {Array<Object>} The entries, empty when no legend is shown.
 */
function visibleLegend() {
    const legend = [...document.querySelectorAll('.canvas-legend')]
        .find(element => element.offsetParent !== null);
    if (!legend) return [];
    return [...legend.querySelectorAll('.legend-item:not([data-legend-hint])')].map(item => {
        const label = item.textContent.replace(item.querySelector('code')?.textContent || '', '').trim();
        const dot = item.querySelector('[class*="legend-dot"]');
        const line = item.querySelector('[class*="legend-line"]');
        const code = item.querySelector('code');
        if (dot) {
            const style = getComputedStyle(dot);
            return { kind: 'dot', label, color: style.backgroundColor, border: style.borderColor };
        }
        if (line) {
            const style = getComputedStyle(line, '::after');
            return {
                kind: 'line', label, color: style.borderLeftColor,
                dashed: getComputedStyle(line).backgroundImage.includes('gradient')
            };
        }
        return { kind: 'glyph', label, glyph: code ? code.textContent : '' };
    });
}

/**
 * Lay the legend entries out in rows that fit the image width.
 *
 * @returns {{rows: Array<Array<Object>>, height: number}} The rows of entries
 *     with their x positions, and the band height (0 without entries).
 */
function pngLegendRows(context, legend, width) {
    if (!legend.length) return { rows: [], height: 0 };
    context.font = `${LEGEND_FONT}px sans-serif`;
    const rows = [[]];
    let x = LEGEND_PAD;
    for (const entry of legend) {
        const span = LEGEND_SWATCH + LEGEND_GAP + context.measureText(entry.label).width;
        if (x + span > width - LEGEND_PAD && rows[rows.length - 1].length) {
            rows.push([]);
            x = LEGEND_PAD;
        }
        rows[rows.length - 1].push({ ...entry, x });
        x += span + LEGEND_SPACING;
    }
    return { rows, height: rows.length * LEGEND_ROW + 2 * LEGEND_PAD };
}

/** Draw the rows `pngLegendRows` laid out, starting at `top`. */
function drawPngLegend(context, layout, top) {
    if (!layout.rows.length) return;
    context.strokeStyle = '#dddddd';
    context.lineWidth = LEGEND_SCALE;
    context.beginPath();
    context.moveTo(0, top + LEGEND_SCALE / 2);
    context.lineTo(context.canvas.width, top + LEGEND_SCALE / 2);
    context.stroke();
    context.font = `${LEGEND_FONT}px sans-serif`;
    context.textBaseline = 'middle';
    layout.rows.forEach((row, index) => {
        const y = top + LEGEND_PAD + index * LEGEND_ROW + LEGEND_ROW / 2;
        for (const entry of row) {
            const mid = entry.x + LEGEND_SWATCH / 2;
            if (entry.kind === 'dot') {
                context.beginPath();
                context.arc(mid, y, 6 * LEGEND_SCALE, 0, 2 * Math.PI);
                context.fillStyle = entry.color;
                context.fill();
                context.strokeStyle = entry.border;
                context.stroke();
            } else if (entry.kind === 'line') {
                context.strokeStyle = entry.color;
                context.lineWidth = 2 * LEGEND_SCALE;
                context.setLineDash(entry.dashed ? [4 * LEGEND_SCALE, 3 * LEGEND_SCALE] : []);
                context.beginPath();
                context.moveTo(entry.x, y);
                context.lineTo(entry.x + LEGEND_SWATCH, y);
                context.stroke();
                context.setLineDash([]);
                context.lineWidth = LEGEND_SCALE;
            } else {
                context.fillStyle = '#333333';
                context.textAlign = 'center';
                context.font = `bold ${LEGEND_FONT}px monospace`;
                context.fillText(entry.glyph, mid, y);
                context.font = `${LEGEND_FONT}px sans-serif`;
                context.textAlign = 'left';
            }
            context.fillStyle = '#333333';
            context.fillText(entry.label, entry.x + LEGEND_SWATCH + LEGEND_GAP, y);
        }
    });
}

// Convenience functions for HTML onclick handlers
function autoLayout() { ERD.autoLayout(); }
function toggleHierarchicalLayout() { ERD.toggleHierarchicalLayout(); }
function zoomIn() { ERD.zoomIn(); }
function zoomOut() { ERD.zoomOut(); }
function fitGraph() { ERD.fitGraph(); }

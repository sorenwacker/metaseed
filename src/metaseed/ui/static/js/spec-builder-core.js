/**
 * Spec Builder ERD core.
 *
 * Reusable graph engine for the spec-builder page. Shipped by metaseed and
 * consumed by any app that mounts metaseed's static directory (metaseed
 * itself via spec-builder.js; metaseed-hub via its own wiring script). All
 * endpoint URLs, entity data access, and app-specific layout behavior are
 * supplied through the config object; this file contains no app-specific
 * URLs or globals.
 *
 * Scripts a consumer must load, in order, before its wiring script:
 *   1. vis-network                (window.vis)
 *   2. htmx                       (window.htmx)
 *   3. static/js/erd-common.js    (window.ERD, plus the autoLayout/zoomIn/
 *                                  zoomOut/fitGraph toolbar globals)
 *   4. static/js/spec-builder-core.js (this file, window.SpecBuilderGraph)
 * Optionally static/js/ontology-autocomplete.js for inline ontology term
 * suggestion inputs.
 *
 * Usage: const graph = SpecBuilderGraph.create(config);
 * create() wires DOMContentLoaded initialization and the Escape-key handler
 * (close modals, editor panel, context menu) itself. The returned object is
 * the graph API; the consumer decides which methods to publish as globals
 * for its inline HTML handlers.
 *
 * Config contract - required:
 *   getEntities(): object
 *       Returns the live entity map {name: {fields: [...], ...}}. Called on
 *       every graph (re)build; the app may mutate or replace the map between
 *       calls.
 *   rootEntity(): string|null
 *       Returns the current root entity name.
 *   url(path): string
 *       Maps an endpoint path such as '/entity/Foo' to a URL. Called with ''
 *       to produce the full-page refresh target (metaseed:
 *       '/spec-builder' + path; hub: '/hub/spec-builder/<draftId>' + path).
 *
 * Config contract - optional:
 *   refresh(): void
 *       Full refresh after structural changes (entity added, renamed,
 *       deleted). Default: window.location.href = url('').
 *   createNetwork(container, nodeData, edgeData): {network, nodes, edges}
 *       Override network construction. Default delegates to
 *       ERD.createNetwork from erd-common.js.
 *   onNetworkReady(network): void
 *       Called after the network is created and the standard event handlers
 *       are attached; use for extra handlers such as zoom hints.
 *   updateEntityBody(formData, oldName): string
 *       Builds the x-www-form-urlencoded body for PUT /entity/<oldName>.
 *       formData already contains the trimmed 'name'. Default serializes the
 *       whole form. Override when the server expects different parameters
 *       (hub: new_name/description/ontology_term).
 *   afterSidebarTabSwitch(tabName): void
 *       App-specific layout work after a sidebar tab switch (e.g. widening
 *       the sidebar for a notes tab and refitting the network).
 *
 * DOM contract (identical element ids in every consumer): #erd-canvas,
 * #editor-panel, #editor-title, #editor-content, #add-entity-modal,
 * #new-entity-name, #preview-overlay, #validation-rule-modal,
 * #rule-modal-title, #rule-modal-content, #validation-rules-panel,
 * #node-context-menu, #ctx-node-name, #ctx-hide-btn, #ctx-show-btn,
 * #hidden-count-badge, #notification-container. Sidebar tab buttons carry
 * '.sidebar-tab[data-tab]'; tab content panels are matched by either the id
 * 'tab-<name>' or a 'data-tab' attribute, so both template variants work.
 */

const SpecBuilderGraph = (function() {
    'use strict';

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
        nodeWidth: 200
    };

    function create(config) {
        let network = null;
        let nodes = null;
        let edges = null;
        let selectedNode = null;
        let pendingPosition = null;
        const hiddenEntities = new Set();
        const originalNodeColors = {};

        function getEntities() {
            return config.getEntities() || {};
        }

        function refresh() {
            if (config.refresh) {
                config.refresh();
                return;
            }
            window.location.href = config.url('');
        }

        // =====================================================================
        // Initialization
        // =====================================================================

        function initERD() {
            if (network) return;

            const container = document.getElementById('erd-canvas');
            if (!container) return;

            const rect = container.getBoundingClientRect();
            if (rect.height < 50) {
                setTimeout(initERD, 200);
                return;
            }

            const entityNames = Object.keys(getEntities());
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
            const entities = getEntities();
            const nodeData = [];
            const edgeData = [];

            entityNames.forEach(name => {
                const entity = entities[name];
                const isRoot = name === config.rootEntity();
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
            const entities = getEntities();
            const edgeData = [];

            fields.forEach(field => {
                // Nested entity relationships
                if ((field.type === 'entity' || field.type === 'list') && field.items && entities[field.items]) {
                    edgeData.push(createEdge(name, field.items, field.name, 'nested',
                        name + '.' + field.name + ' contains ' + field.items));
                }

                // Reference relationships: label both connected fields, not just
                // the source field, so the edge names the exact columns it joins.
                if (field.reference) {
                    const parts = field.reference.split('.');
                    const targetEntity = parts[0];
                    const targetField = parts[1];
                    if (entities[targetEntity]) {
                        const label = targetField ? field.name + ' → ' + targetField : field.name;
                        edgeData.push(createEdge(name, targetEntity, label, 'reference',
                            name + '.' + field.name + ' → ' + field.reference));
                    }
                }
            });

            return edgeData;
        }

        /**
         * Create an edge configuration object. The title renders as the hover
         * tooltip with the fully qualified Entity.field endpoints.
         */
        function createEdge(from, to, label, type, title) {
            const colors = type === 'reference' ? EDGE_COLORS.reference : EDGE_COLORS.nested;
            const fontColor = type === 'reference' ? '#6b5a62' : '#5a6b62';

            return {
                from: from,
                to: to,
                label: label,
                title: title,
                arrows: { to: { enabled: true, type: 'arrow' } },
                color: colors,
                font: { size: 11, color: fontColor, background: 'white', strokeWidth: 0 },
                smooth: { type: 'cubicBezier', roundness: 0.4 },
                width: 2,
                dashes: type === 'reference'
            };
        }

        /**
         * Create the vis-network instance, by default via the shared ERD module.
         */
        function createNetwork(container, nodeData, edgeData) {
            if (config.createNetwork) {
                const created = config.createNetwork(container, nodeData, edgeData);
                network = created.network;
                nodes = created.nodes;
                edges = created.edges;
                return;
            }
            network = ERD.createNetwork(container, nodeData, edgeData);
            nodes = ERD.getNodes();
            edges = ERD.getEdges();
        }

        /**
         * Attach standard event handlers to the network.
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

            // Disable physics once the layout settles. Redundant but harmless
            // when ERD.createNetwork already registered the same handler; it
            // keeps custom createNetwork overrides from leaving physics on.
            network.once('stabilizationIterationsDone', function() {
                network.setOptions({ physics: { enabled: false } });
            });

            network.on('oncontext', function(params) {
                params.event.preventDefault();
                const nodeId = network.getNodeAt(params.pointer.DOM);
                if (nodeId) {
                    showContextMenu(params.event, nodeId);
                }
            });

            if (config.onNetworkReady) {
                config.onNetworkReady(network);
            }
        }

        // =====================================================================
        // Entity Selection & Editor Panel
        // =====================================================================

        function selectEntity(entityName) {
            selectedNode = entityName;
            document.getElementById('editor-title').textContent = entityName;
            document.getElementById('editor-panel').classList.add('open');
            htmx.ajax('GET', config.url('/entity/' + entityName), {
                target: '#editor-content',
                swap: 'innerHTML'
            });
        }

        function closeEditorPanel() {
            document.getElementById('editor-panel').classList.remove('open');
            if (network) network.unselectAll();
            selectedNode = null;
        }

        function hideSelectedEntity() {
            if (selectedNode) {
                hideEntity(selectedNode);
            }
        }

        // =====================================================================
        // Graph Controls
        // =====================================================================

        function refreshGraph() {
            refresh();
        }

        function deleteEntity(entityName) {
            if (!confirm(`Delete entity '${entityName}'? This will remove all fields and relationships.`)) {
                return;
            }

            fetch(config.url('/entity/' + encodeURIComponent(entityName)), {
                method: 'DELETE'
            })
            .then(response => {
                if (response.ok) {
                    refreshGraph();
                } else {
                    alert('Failed to delete entity');
                }
            })
            .catch(err => {
                console.error('Error deleting entity:', err);
                alert('Failed to delete entity: ' + err.message);
            });
        }

        function swapEditorContent(html) {
            const container = document.getElementById('editor-content');
            container.innerHTML = html;
            if (typeof htmx !== 'undefined') htmx.process(container);
        }

        function updateEntity(event, oldName) {
            event.preventDefault();

            const form = event.target;
            const formData = new FormData(form);
            const newName = (formData.get('name') || '').trim();
            formData.set('name', newName);
            // Send the whole form (name, description, ontology_term, ...) so
            // fields added to the editor are posted without touching this
            // handler; apps whose server expects different parameters override
            // via config.updateEntityBody.
            const body = config.updateEntityBody
                ? config.updateEntityBody(formData, oldName)
                : new URLSearchParams(formData).toString();

            fetch(config.url('/entity/' + encodeURIComponent(oldName)), {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: body
            })
            .then(response => {
                if (response.ok && newName !== oldName) {
                    // Renamed: full refresh to update the graph
                    refreshGraph();
                } else {
                    return response.text().then(swapEditorContent);
                }
            })
            .catch(err => {
                console.error('Error updating entity:', err);
                alert('Failed to update entity: ' + err.message);
            });

            return false;
        }

        function updateField(event, entityName, fieldIdx) {
            event.preventDefault();

            const form = event.target;
            const formData = new FormData(form);

            fetch(config.url('/entity/' + encodeURIComponent(entityName) + '/field/' + fieldIdx), {
                method: 'PUT',
                body: formData
            })
            .then(response => response.text())
            .then(swapEditorContent)
            .catch(err => {
                console.error('Error updating field:', err);
                alert('Failed to update field: ' + err.message);
            });

            return false;
        }

        function rebuildGraph() {
            const container = document.getElementById('erd-canvas');
            if (!container) return;

            const entityNames = Object.keys(getEntities());

            if (entityNames.length === 0) {
                if (network) {
                    network.destroy();
                    network = null;
                }
                container.innerHTML = '<div class="empty-canvas-message">Double-click to add an entity</div>';
                return;
            }

            const emptyMsg = container.querySelector('.empty-canvas-message');
            if (emptyMsg) {
                emptyMsg.remove();
            }

            const { nodeData, edgeData } = buildGraphData(entityNames);

            if (network) {
                nodes.clear();
                edges.clear();
                nodes.add(nodeData);
                edges.add(edgeData);
                setTimeout(() => network.fit({ animation: true }), 100);
            } else {
                createNetwork(container, nodeData, edgeData);
                attachNetworkEventHandlers();
            }
        }

        // =====================================================================
        // Add Entity Modal
        // =====================================================================

        function showAddEntityModal() {
            document.getElementById('add-entity-modal').classList.remove('hidden');
            document.getElementById('new-entity-name').value = '';
            document.getElementById('new-entity-name').focus();
        }

        function hideAddEntityModal() {
            document.getElementById('add-entity-modal').classList.add('hidden');
            pendingPosition = null;
        }

        function onEntityAdded(event) {
            if (event && event.detail && !event.detail.successful) {
                console.error('Entity add request failed:', event.detail);
                return;
            }
            hideAddEntityModal();
            setTimeout(refreshGraph, 100);
        }

        function submitAddEntityForm(event) {
            event.preventDefault();

            const nameInput = document.getElementById('new-entity-name');
            const name = nameInput.value.trim();

            if (!name) {
                return false;
            }

            fetch(config.url('/entity'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: 'name=' + encodeURIComponent(name)
            })
            .then(response => response.text())
            .then(html => {
                swapEditorContent(html);
                hideAddEntityModal();
                setTimeout(refreshGraph, 100);
            })
            .catch(err => {
                console.error('Error adding entity:', err);
                alert('Failed to add entity: ' + err.message);
            });

            return false;
        }

        function saveSpec() {
            const formData = new FormData();
            const fields = ['name', 'version', 'display_name', 'description', 'root_entity', 'ontology'];

            fields.forEach(field => {
                const input = document.querySelector(`[name="${field}"]`);
                if (input) {
                    formData.append(field, input.value);
                }
            });

            fetch(config.url('/save'), {
                method: 'POST',
                body: formData
            })
            .then(response => response.text())
            .then(html => {
                const container = document.getElementById('notification-container');
                container.insertAdjacentHTML('beforeend', html);
                // Auto-hide success notifications after 5 seconds
                setTimeout(() => {
                    const notification = container.querySelector('.notification-success');
                    if (notification) notification.remove();
                }, 5000);
            })
            .catch(err => {
                alert('Save failed: ' + err.message);
            });
        }

        // =====================================================================
        // Drag & Drop
        // =====================================================================

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

        // =====================================================================
        // Preview Modal
        // =====================================================================

        function showPreview() {
            document.getElementById('preview-overlay').classList.remove('hidden');
        }

        function hidePreview(event) {
            if (!event || event.target.id === 'preview-overlay') {
                document.getElementById('preview-overlay').classList.add('hidden');
            }
        }

        // =====================================================================
        // Validation Rule Modal
        // =====================================================================

        function showRuleModal(ruleIdx, ruleName) {
            document.getElementById('rule-modal-title').textContent = ruleName ? `Edit: ${ruleName}` : 'Edit Rule';
            document.getElementById('validation-rule-modal').classList.remove('hidden');
            htmx.ajax('GET', config.url('/validation-rule/' + ruleIdx), {
                target: '#rule-modal-content',
                swap: 'innerHTML'
            });
        }

        function hideRuleModal() {
            document.getElementById('validation-rule-modal').classList.add('hidden');
            htmx.ajax('GET', config.url('/validation-rules'), {
                target: '#validation-rules-panel',
                swap: 'innerHTML'
            });
        }

        // =====================================================================
        // Context Menu (Hide/Show Entities)
        // =====================================================================

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
            const isRoot = nodeId === config.rootEntity();
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
            if (!badge) return;
            const count = hiddenEntities.size;
            if (count > 0) {
                badge.textContent = count + ' hidden';
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        }

        // =====================================================================
        // Sidebar Tabs
        // =====================================================================

        function switchSidebarTab(tabName) {
            document.querySelectorAll('.sidebar-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.tab === tabName);
            });

            // Tab content panels are matched by id ('tab-<name>') or data-tab
            // attribute so both template variants work.
            document.querySelectorAll('.sidebar-tab-content').forEach(content => {
                const matches = content.id === `tab-${tabName}` || content.dataset.tab === tabName;
                content.classList.toggle('active', matches);
            });

            if (config.afterSidebarTabSwitch) {
                config.afterSidebarTabSwitch(tabName);
            }
        }

        // =====================================================================
        // Shared Event Wiring
        // =====================================================================

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                hideAddEntityModal();
                hideRuleModal();
                hidePreview();
                closeEditorPanel();
                closeContextMenu();
            }
        });

        document.addEventListener('DOMContentLoaded', initERD);
        // Also try immediately in case DOMContentLoaded already fired
        if (document.readyState !== 'loading') {
            setTimeout(initERD, 50);
        }

        return {
            initERD,
            buildGraphData,
            buildNodeConfig,
            buildNodeLabel,
            storeOriginalColors,
            buildEntityEdges,
            createEdge,
            createNetwork,
            attachNetworkEventHandlers,
            getNetwork: () => network,
            selectEntity,
            closeEditorPanel,
            hideSelectedEntity,
            refreshGraph,
            deleteEntity,
            updateEntity,
            updateField,
            rebuildGraph,
            showAddEntityModal,
            hideAddEntityModal,
            onEntityAdded,
            submitAddEntityForm,
            saveSpec,
            dragNewEntity,
            dropNewEntity,
            addEntityAtPosition,
            showPreview,
            hidePreview,
            showRuleModal,
            hideRuleModal,
            showContextMenu,
            closeContextMenu,
            hideEntity,
            showEntity,
            showAllEntities,
            updateHiddenCount,
            switchSidebarTab
        };
    }

    return { create };
})();

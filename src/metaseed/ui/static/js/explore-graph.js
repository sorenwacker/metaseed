/**
 * Draws the explorer graph from what the server sends.
 *
 * Every node arrives with its complete vis.js colour and font colour, and every
 * edge with its colour and a diff_type. This script lays the graph out and
 * filters it; it decides no colour, so the canvas cannot drift from the legend
 * the server's stylesheet explains. Shared by every host that renders the page.
 */

const FONT_CONFIG = { face: 'monospace', size: 12, align: 'left', multi: 'html' };

const LAYOUT = { nodeBaseHeight: 40, fieldHeight: 16, nodeWidth: 200 };

function buildGraphData(graphData, exploreMode) {
    const nodeData = [];
    const edgeData = [];

    // Spread nodes in a grid at first so the physics has somewhere to start.
    const gridCols = Math.ceil(Math.sqrt(graphData.nodes.length));
    const spacing = 300;

    graphData.nodes.forEach((node, index) => {
        const nodeConfig = buildNodeConfig(node, exploreMode);
        nodeConfig.x = (index % gridCols) * spacing;
        nodeConfig.y = Math.floor(index / gridCols) * spacing;
        nodeData.push(nodeConfig);
    });

    graphData.edges.forEach(edge => {
        const edgeColor = edge.color.color;
        const font = { size: 10, background: 'white' };
        if (edge.font && edge.font.color) font.color = edge.font.color;
        edgeData.push({
            from: edge.from,
            to: edge.to,
            label: edge.label || '',
            arrows: { to: { enabled: true, type: 'arrow' } },
            color: { color: edgeColor, highlight: edgeColor },
            font: font,
            smooth: { type: 'cubicBezier', roundness: 0.4 },
            width: edge.width || 2,
            title: edge.title || '',
            dashes: edge.dashes || false,
            diff_type: edge.diff_type
        });
    });

    return { nodeData, edgeData };
}

function buildNodeConfig(node, exploreMode) {
    const fields = node.data.fields || [];
    const diffType = node.data.diff_type || 'unchanged';
    const label = buildNodeLabel(node.label, fields, exploreMode);
    const nodeHeight = LAYOUT.nodeBaseHeight + fields.length * LAYOUT.fieldHeight;

    return {
        id: node.id,
        label: label,
        shape: 'box',
        size: Math.max(nodeHeight, LAYOUT.nodeWidth) / 2,
        mass: 1 + fields.length * 0.3,
        font: { ...FONT_CONFIG, color: node.font.color },
        color: node.color,
        borderWidth: diffType === 'conflict' ? 3 : 2,
        margin: 15,
        shadow: true,
        data: node.data
    };
}

function buildNodeLabel(name, fields, exploreMode) {
    let label = `<b>${name}</b>\n────────────────`;

    if (fields.length === 0) {
        return label + '\n<i>(no fields)</i>';
    }

    fields.forEach(field => {
        const req = field.required ? '*' : ' ';
        const fk = (field.type === 'entity' || field.type === 'list') && field.items ? '→' : ' ';
        const cv = field.vocabulary && field.vocabulary.length ? ` [${field.vocabulary.length} terms]` : '';
        if (exploreMode) {
            label += `\n${req}${fk} ${field.name}: ${field.type}${cv}`;
            return;
        }
        let ind = ' ';
        if (field.diff_type === 'conflict') ind = '!';
        else if (field.diff_type === 'added') ind = '+';
        else if (field.diff_type === 'removed') ind = '-';
        else if (field.diff_type === 'modified') ind = '~';
        label += `\n${ind}${req}${fk} ${field.name}: ${field.type}`;
    });

    return label;
}

/** Whether an edge stays on a filtered canvas, by the state the server named. */
function edgeIsVisible(edge, filters) {
    if (edge.diff_type === 'unchanged') return filters.showCommon;
    if (edge.diff_type === 'added') return filters.showCompare;
    if (edge.diff_type === 'removed') return filters.showBase;
    return true;
}

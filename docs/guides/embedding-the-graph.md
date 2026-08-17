# Embedding the entity graph

`metaseed/ui/static/js/graph.js` draws the entity graph: the network canvas, the legend with per-entity-type counts, click-a-type-to-hide filtering, and the layout and physics controls. It is meant to be reused by other applications rather than reimplemented, so the drawing is separate from where the data comes from.

## The DOM contract

The script looks up these elements by id. Only `graph-view` is required; the rest enable the controls they name.

| Element id | Purpose |
| --- | --- |
| `graph-view` | The canvas the network is drawn into. Required. |
| `graph-legend` | Container for the entity-type legend and its counts. |
| `graph-container` | Wrapper used to decide whether the graph is currently visible. |
| `graph-layout-btn` | Toggles hierarchical and free layout. |
| `graph-physics-btn` | Toggles physics simulation. |
| `graph-spacing` | Range input for spring length between nodes. |
| `graph-repulsion` | Range input for how strongly nodes push apart. |
| `graph-gravity` | Range input for the pull toward the centre. |

## Supplying the data

The graph expects the shape `metaseed.facade.graph.to_graph` produces: `{"nodes": [...], "edges": [...], "entity_types": [...]}`. There are two ways to get it there; pick whichever suits the host.

### Hand it the data (no transport involved)

```js
renderGraphData(myGraphData);
```

`renderGraphData(data)` is the public drawing entry point. It does everything the built-in fetch path does once the response arrives — first-load versus incremental update, legend state, and the bookkeeping that keeps a type the user hid from reappearing. A host that already has the data, from its own endpoint or a websocket, never has to touch the transport.

### Let it fetch

```js
window.METASEED_GRAPH_URL = '/api/graph/DigitalSpecimen/DS-B05909DA52/data';
loadGraph();
```

`loadGraph()` reads `window.METASEED_GRAPH_URL` **at call time**, so a host can set or change it after the script has loaded. `loadGraph(url)` takes an explicit URL, which wins over the global. With neither, it falls back to metaseed's own `BASE_URL + '/api/graph'`, which is what metaseed's UI uses.

## Drawing on a plain page load

When the page contains `graph-view` at load time, the script draws once on `DOMContentLoaded` by itself — a host that sets `window.METASEED_GRAPH_URL` before loading the file needs no init call.

It stays out of the way of applications that manage this themselves: set `window.METASEED_GRAPH_AUTOLOAD = false` before loading the script to suppress the automatic draw, then call `loadGraph()` or `renderGraphData()` when ready. Metaseed's own UI reveals the graph through htmx rather than on load, and refreshes it after entity operations.

## What the host still owns

Styling beyond the canvas background, when the graph becomes visible, and how often it refreshes. The script redraws on `htmx:afterSwap` when `graph-container` is visible and on a colour-scheme change; a host without htmx simply never triggers the former.

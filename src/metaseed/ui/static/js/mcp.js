// Metaseed MCP Server Management

var mcpServerRunning = false;

function updateMCPStatus(status) {
    mcpServerRunning = status.running;
    var indicator = document.getElementById('mcp-status-indicator');
    var button = document.getElementById('mcp-toggle');

    if (indicator) {
        indicator.classList.remove('status-on', 'status-off');
        indicator.classList.add(status.running ? 'status-on' : 'status-off');
    }

    if (button) {
        if (status.running && status.url) {
            button.title = 'MCP Server running at ' + status.url + ' (click to stop)';
        } else {
            button.title = 'MCP Server stopped (click to start)';
        }
    }
}

function checkMCPStatus() {
    fetch(BASE_URL + '/api/mcp/status')
        .then(function(response) { return response.json(); })
        .then(function(status) {
            updateMCPStatus(status);
        })
        .catch(function(err) {
            console.error('Failed to check MCP status:', err);
        });
}

function toggleMCP() {
    var button = document.getElementById('mcp-toggle');
    if (button) button.disabled = true;

    var endpoint = mcpServerRunning ? '/api/mcp/stop' : '/api/mcp/start';

    fetch(BASE_URL + endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: 8001 })
    })
        .then(function(response) { return response.json(); })
        .then(function(status) {
            updateMCPStatus(status);
            if (button) button.disabled = false;

            var msg = status.running
                ? 'MCP Server started at ' + status.url
                : 'MCP Server stopped';
            if (status.error) {
                msg = 'MCP Error: ' + status.error;
            }
            showNotification(msg, status.error ? 'error' : 'success');
        })
        .catch(function(err) {
            console.error('Failed to toggle MCP:', err);
            if (button) button.disabled = false;
            showNotification('Failed to toggle MCP server', 'error');
        });
}

function showNotification(message, type) {
    var container = document.getElementById('notification-container');
    if (!container) return;

    var notification = document.createElement('div');
    notification.className = 'notification notification-' + (type || 'info');
    notification.textContent = message;
    container.appendChild(notification);

    setTimeout(function() {
        notification.style.opacity = '0';
        setTimeout(function() {
            notification.remove();
        }, 200);
    }, 5000);
}

// Check MCP status on page load and periodically
document.addEventListener('DOMContentLoaded', function() {
    checkMCPStatus();
    setInterval(checkMCPStatus, 10000);
});

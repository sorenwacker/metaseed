// Minimal JavaScript for HTMX UI

// Handle collapsible sections
document.addEventListener('click', function(e) {
    const header = e.target.closest('.collapsible-header');
    if (header) {
        const collapsible = header.closest('.collapsible');
        collapsible.classList.toggle('open');
    }
});

// Handle profile select change
document.addEventListener('change', function(e) {
    if (e.target.id === 'profile-select') {
        const profile = e.target.value;
        window.location.href = '/profile/' + profile;
    }
});

// Auto-dismiss notifications after 5 seconds
document.addEventListener('htmx:afterSwap', function(e) {
    if (e.target.id === 'notification-container') {
        const notifications = e.target.querySelectorAll('.notification');
        notifications.forEach(function(notification) {
            setTimeout(function() {
                notification.style.opacity = '0';
                setTimeout(function() {
                    notification.remove();
                }, 200);
            }, 5000);
        });
    }
});

// Handle delete confirmation
function confirmDelete(nodeId, nodeLabel) {
    return confirm('Delete "' + nodeLabel + '"?');
}

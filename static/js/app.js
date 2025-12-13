/**
 * Copy Trade Dashboard - Client-side JavaScript
 * Handles account selection, tab switching, and UI interactions
 */

/**
 * Handle account dropdown change event
 * Redirects to page with copier_id query parameter for server-side state management
 */
function handleAccountChange() {
    const selector = document.getElementById('accountSelector');
    if (!selector) return;

    const selectedAccountId = selector.value;

    if (selectedAccountId) {
        // Redirect with copier_id query parameter
        window.location.href = '/?copier_id=' + encodeURIComponent(selectedAccountId);
    } else {
        // Clear selection - redirect without query param
        window.location.href = '/';
    }
}

/**
 * Show a specific page tab (Overview or Trades)
 * @param {string} which - 'overview' or 'trades'
 */
function showPageTab(which) {
    const btnOverview = document.getElementById('pageTabOverview');
    const btnTrades = document.getElementById('pageTabTrades');
    const overview = document.getElementById('overviewSection');
    const trades = document.getElementById('tradesSection');

    if (which === 'trades') {
        btnTrades?.classList.add('active');
        btnOverview?.classList.remove('active');
        trades?.classList.add('active');
        overview?.classList.remove('active');
        localStorage.setItem('selectedPageTab', 'trades');
    } else {
        btnOverview?.classList.add('active');
        btnTrades?.classList.remove('active');
        overview?.classList.add('active');
        trades?.classList.remove('active');
        localStorage.setItem('selectedPageTab', 'overview');
    }
}

/**
 * Show a specific trades tab (Open or Closed)
 * @param {string} which - 'open' or 'closed'
 */
function showTradesTab(which) {
    const tabOpen = document.getElementById('tabOpen');
    const tabClosed = document.getElementById('tabClosed');
    const panelOpen = document.getElementById('panelOpen');
    const panelClosed = document.getElementById('panelClosed');
    const rangeSelector = document.getElementById('closedRangeSelector');
    const statsRow = document.getElementById('closedStatsRow');

    if (which === 'closed') {
        tabClosed?.classList.add('active');
        tabOpen?.classList.remove('active');
        panelClosed?.classList.add('active');
        panelOpen?.classList.remove('active');
        // Show range selector and stats for closed trades
        if (rangeSelector) rangeSelector.style.display = 'flex';
        if (statsRow) statsRow.style.display = 'flex';
    } else {
        tabOpen?.classList.add('active');
        tabClosed?.classList.remove('active');
        panelOpen?.classList.add('active');
        panelClosed?.classList.remove('active');
        // Hide range selector and stats for open trades
        if (rangeSelector) rangeSelector.style.display = 'none';
        if (statsRow) statsRow.style.display = 'none';
    }
}

/**
 * Open the copy settings modal
 */
function openCopyModal() {
    const modal = document.getElementById('copyModal');
    if (modal) {
        modal.style.display = 'flex'; // Use flex for centering
        document.body.style.overflow = 'hidden'; // Prevent background scrolling
    }
}

/**
 * Close the copy settings modal
 */
function closeCopyModal() {
    const modal = document.getElementById('copyModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = ''; // Restore scrolling
    }
}

/**
 * Open the stop copying modal
 */
function openStopModal() {
    const modal = document.getElementById('stopModal');
    if (modal) {
        modal.style.display = 'flex'; // Use flex for centering
        document.body.style.overflow = 'hidden'; // Prevent background scrolling
    }
}

/**
 * Close the stop copying modal
 */
function closeStopModal() {
    const modal = document.getElementById('stopModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = ''; // Restore scrolling
    }
}

/**
 * Update the trade size label based on selected trade size type
 */
function updateTradeSizeLabel() {
    const typeSelect = document.getElementById('trade_size_type');
    const label = document.getElementById('trade_size_label');

    if (typeSelect && label) {
        const selectedType = typeSelect.value;
        if (selectedType === 'Fixed') {
            label.textContent = 'Lot Size';
        } else {
            label.textContent = 'Multiplier';
        }
    }
}

/**
 * Clean URL by removing specified query parameters
 * Uses history.replaceState to avoid page reload
 * @param {string[]} paramsToRemove - Array of parameter names to remove
 */
function cleanUrlParams(paramsToRemove) {
    const url = new URL(window.location.href);
    let changed = false;

    paramsToRemove.forEach(param => {
        if (url.searchParams.has(param)) {
            url.searchParams.delete(param);
            changed = true;
        }
    });

    if (changed) {
        // Reconstruct URL, preserving hash
        const hash = window.location.hash;
        const newUrl = url.pathname + (url.searchParams.toString() ? '?' + url.searchParams.toString() : '') + hash;
        window.history.replaceState({}, document.title, newUrl);
    }
}

/**
 * Open the link account modal
 */
function openLinkModal() {
    const modal = document.getElementById('linkModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

/**
 * Close the link account modal
 */
function closeLinkModal() {
    const modal = document.getElementById('linkModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

/**
 * Open the unlink confirmation modal
 */
function openUnlinkModal() {
    const modal = document.getElementById('unlinkModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

/**
 * Close the unlink confirmation modal
 */
function closeUnlinkModal() {
    const modal = document.getElementById('unlinkModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

/**
 * Confirm unlink action - shows modal with account details
 * @param {string} copierId - The copier account ID
 * @param {string} accountName - The account name to display
 */
function confirmUnlink(copierId, accountName) {
    const form = document.getElementById('unlinkForm');
    const nameDisplay = document.getElementById('unlinkAccountName');

    if (form && nameDisplay) {
        // Set the form action to the unlink route for this copier
        form.action = '/accounts/' + encodeURIComponent(copierId) + '/unlink';

        // Display the account name in the confirmation message
        nameDisplay.textContent = accountName;

        // Open the modal
        openUnlinkModal();
    }
}

/**
 * Handle broker selection change - dynamically fetch servers
 */
function handleBrokerChange() {
    const brokerSelect = document.getElementById('broker_code');
    const serverSelect = document.getElementById('server_code');

    if (!brokerSelect || !serverSelect) return;

    const brokerCode = brokerSelect.value;

    if (!brokerCode) {
        // Clear server options
        serverSelect.innerHTML = '<option value="" disabled selected>Select broker first</option>';
        return;
    }

    // Show loading state
    serverSelect.innerHTML = '<option value="" disabled selected>Loading servers...</option>';
    serverSelect.disabled = true;

    // Fetch servers for selected broker
    fetch('/accounts/servers?brokerCode=' + encodeURIComponent(brokerCode))
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch servers');
            }
            return response.json();
        })
        .then(data => {
            const servers = data.servers || [];

            // Rebuild server dropdown
            serverSelect.innerHTML = '<option value="" disabled selected>Select server</option>';

            servers.forEach(server => {
                const option = document.createElement('option');
                option.value = server.Code;
                option.textContent = server.Name + ' (' + server.Vendor + ')';
                serverSelect.appendChild(option);
            });

            serverSelect.disabled = false;
        })
        .catch(error => {
            console.error('Error fetching servers:', error);
            serverSelect.innerHTML = '<option value="" disabled selected>Error loading servers</option>';
            serverSelect.disabled = false;
        });
}

/**
 * Initialize the dashboard on page load
 * Restores saved tab selection from localStorage or URL hash
 * Handles auto-open modal query parameters
 */
window.addEventListener('DOMContentLoaded', () => {
    // Check if URL has #trades hash (for direct links like /?range=7d#trades)
    const urlHash = window.location.hash;
    let initialPageTab = localStorage.getItem('selectedPageTab') || 'overview';

    if (urlHash === '#trades') {
        initialPageTab = 'trades';
    }

    showPageTab(initialPageTab);

    // Default to 'closed' tab if there's a range parameter in URL
    const urlParams = new URLSearchParams(window.location.search);
    const hasRangeParam = urlParams.has('range');
    showTradesTab(hasRangeParam ? 'closed' : 'open');

    // Auto-open copy modal if query param is present
    if (urlParams.get('open_copy_modal') === '1') {
        openCopyModal();
        cleanUrlParams(['open_copy_modal']);
    }

    // Auto-open stop modal if query param is present
    if (urlParams.get('open_stop_modal') === '1') {
        openStopModal();
        cleanUrlParams(['open_stop_modal', 'stop_strategy_id']);
    }

    // Clean up flash message query params after a short delay
    setTimeout(() => {
        cleanUrlParams(['link_success', 'link_error', 'unlink_success', 'unlink_error']);
    }, 100);
});

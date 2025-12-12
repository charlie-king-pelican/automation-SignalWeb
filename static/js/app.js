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
        modal.style.display = 'block';
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
 * Initialize the dashboard on page load
 * Restores saved tab selection from localStorage or URL hash
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
});

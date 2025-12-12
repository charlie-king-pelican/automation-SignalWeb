/**
 * Copy Trade Dashboard - Client-side JavaScript
 * Handles account selection, tab switching, and UI interactions
 */

/**
 * Handle account dropdown change event
 * Saves selected account to localStorage and shows/hides copy button
 */
function handleAccountChange() {
    const selector = document.getElementById('accountSelector');
    if (!selector) return;

    const selectedOption = selector.options[selector.selectedIndex];
    const selectedAccountId = selector.value;
    const accountType = selectedOption ? selectedOption.getAttribute('data-type') : null;
    const copyBtns = document.querySelectorAll('.copy-btn');

    if (selectedAccountId) {
        localStorage.setItem('selectedAccountId', selectedAccountId);
        if (accountType) localStorage.setItem('selectedAccountType', accountType);
        copyBtns.forEach(btn => btn.classList.remove('hidden'));
    } else {
        localStorage.removeItem('selectedAccountId');
        localStorage.removeItem('selectedAccountType');
        copyBtns.forEach(btn => btn.classList.add('hidden'));
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

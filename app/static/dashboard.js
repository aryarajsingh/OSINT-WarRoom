// === OSINT War Room — Dashboard JS ===

// --- SSE Filter-Aware Feed ---

var activeFeedFilter = { region: 'all', minPriority: '' };
var pendingNewEvents = 0;

var PRIORITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 };

function priorityAtOrAbove(cardPriority, minPriority) {
    var cardRank = PRIORITY_RANK[cardPriority] !== undefined ? PRIORITY_RANK[cardPriority] : 3;
    var minRank = PRIORITY_RANK[minPriority] !== undefined ? PRIORITY_RANK[minPriority] : 3;
    return cardRank <= minRank;
}

// Track feed tab clicks to update active filter
document.addEventListener('click', function(e) {
    var tab = e.target.closest('#feed-tabs .tab');
    if (tab) {
        activeFeedFilter.region = tab.getAttribute('data-filter-region') || 'all';
        activeFeedFilter.minPriority = tab.getAttribute('data-filter-priority') || '';
        pendingNewEvents = 0;
        updateNewEventsBar();
    }
});

// Listen for SSE messages — filter client-side for feed, handle alerts
document.addEventListener('htmx:sseMessage', function(e) {
    if (e.detail.type === 'new_event') {
        var html = e.detail.data;

        var regionMatch = html.match(/data-region="([^"]*)"/);
        var priorityMatch = html.match(/data-priority="([^"]*)"/);
        var cardRegion = regionMatch ? regionMatch[1] : '';
        var cardPriority = priorityMatch ? priorityMatch[1] : 'low';

        var matches = true;
        if (activeFeedFilter.region && activeFeedFilter.region !== 'all' && activeFeedFilter.region !== '') {
            if (cardRegion !== activeFeedFilter.region) matches = false;
        }
        if (activeFeedFilter.minPriority) {
            if (!priorityAtOrAbove(cardPriority, activeFeedFilter.minPriority)) matches = false;
        }

        if (matches) {
            var feedList = document.getElementById('feed-list');
            if (feedList) feedList.insertAdjacentHTML('afterbegin', html);
        } else {
            pendingNewEvents++;
            updateNewEventsBar();
        }
    }

    if (e.detail.type === 'alert') {
        playAlertSound();
        var banner = document.getElementById('alert-banner');
        if (banner) {
            banner.classList.remove('hidden');
            setTimeout(function() { banner.classList.add('hidden'); }, 30000);
        }
    }
});

function updateNewEventsBar() {
    var bar = document.getElementById('feed-new-bar');
    if (!bar) return;
    if (pendingNewEvents > 0) {
        bar.textContent = pendingNewEvents + ' new event' + (pendingNewEvents > 1 ? 's' : '') + ' \u2014 Show All';
        bar.classList.remove('hidden');
    } else {
        bar.classList.add('hidden');
    }
}

function resetFeedFilter() {
    var allTab = document.querySelector('#feed-tabs .tab[data-filter-region="all"]');
    if (allTab) allTab.click();
    pendingNewEvents = 0;
    updateNewEventsBar();
}

// --- Fullscreen ---

var fullscreenPanelId = null;

function toggleFullscreen(panelId) {
    var panel = document.getElementById(panelId);
    if (!panel) return;
    var btn = panel.querySelector('.btn-fullscreen');

    if (fullscreenPanelId === panelId) {
        panel.classList.remove('fullscreen');
        document.body.classList.remove('has-fullscreen');
        if (btn) btn.innerHTML = '&#x26F6;';
        fullscreenPanelId = null;
    } else {
        if (fullscreenPanelId) {
            var oldPanel = document.getElementById(fullscreenPanelId);
            if (oldPanel) {
                oldPanel.classList.remove('fullscreen');
                var oldBtn = oldPanel.querySelector('.btn-fullscreen');
                if (oldBtn) oldBtn.innerHTML = '&#x26F6;';
            }
        }
        panel.classList.add('fullscreen');
        document.body.classList.add('has-fullscreen');
        if (btn) btn.innerHTML = '&#x2716;';
        fullscreenPanelId = panelId;
    }
    // Invalidate map after fullscreen toggle
    if (conflictMap) setTimeout(function() { conflictMap.invalidateSize(); }, 50);
}

function exitFullscreen() {
    if (fullscreenPanelId) toggleFullscreen(fullscreenPanelId);
}

// --- Keyboard Shortcuts ---
document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        if (e.key === 'Escape') {
            var searchResults = document.getElementById('search-results');
            var searchInput = document.getElementById('search-input');
            if (searchResults) searchResults.innerHTML = '';
            if (searchInput) { searchInput.value = ''; searchInput.blur(); }
        }
        return;
    }

    switch (e.key) {
        case '/':
            e.preventDefault();
            document.getElementById('search-input').focus();
            break;
        case 'm':
            document.getElementById('panel-map')?.scrollIntoView({ behavior: 'smooth' });
            break;
        case '1': case '2': case '3': case '4':
            var panelIds = { '1': 'panel-1', '2': 'panel-2', '3': 'panel-3', '4': 'panel-4' };
            document.getElementById(panelIds[e.key])?.scrollIntoView({ behavior: 'smooth' });
            break;
        case 'r':
            e.preventDefault();
            location.reload();
            break;
        case 'Escape':
            exitFullscreen();
            break;
    }
});

// --- Search Dropdown Close ---
function initSearchClose() {
    var searchResults = document.getElementById('search-results');
    if (!searchResults) return;

    document.addEventListener('click', function(e) {
        if (!e.target.closest('.topbar-center')) {
            searchResults.innerHTML = '';
        }
    });

    searchResults.addEventListener('click', function(e) {
        if (e.target.closest('a')) {
            setTimeout(function() { searchResults.innerHTML = ''; }, 150);
        }
    });
}

// --- Sound Alert ---
var alertSound = null;
try { alertSound = new Audio('/static/alert.mp3'); alertSound.volume = 0.5; } catch(e) {}

function playAlertSound() {
    if (alertSound) alertSound.play().catch(function() {});
}

// --- Time Ago ---
function updateTimeAgo() {
    document.querySelectorAll('[data-time]').forEach(function(el) {
        var time = el.getAttribute('data-time');
        if (!time) return;
        var diff = (Date.now() - new Date(time + 'Z').getTime()) / 1000;
        if (diff < 60) el.textContent = Math.floor(diff) + 's ago';
        else if (diff < 3600) el.textContent = Math.floor(diff / 60) + 'm ago';
        else if (diff < 86400) el.textContent = Math.floor(diff / 3600) + 'h ago';
        else el.textContent = Math.floor(diff / 86400) + 'd ago';
    });
}

// --- Tab active state + sync polling URL ---
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('tab')) {
        var bar = e.target.closest('.tab-bar');
        if (bar) bar.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
        e.target.classList.add('active');

        var targetSel = e.target.getAttribute('hx-target');
        var url = e.target.getAttribute('hx-get');
        if (targetSel && url) {
            var target = document.querySelector(targetSel);
            if (target && target.hasAttribute('hx-trigger')) {
                target.setAttribute('hx-get', url);
            }
        }
    }
});

// --- Re-run after HTMX swaps ---
document.addEventListener('htmx:afterSwap', function(e) {
    updateTimeAgo();
    initExpandables();
    renderSparklines();

    // Re-highlight active situation card after HTMX refresh
    if (e.detail.target && e.detail.target.id === 'situation-content') {
        if (activeFlashpoint) {
            var card = document.querySelector('.fp-card[data-flashpoint="' + activeFlashpoint + '"]');
            if (card) card.classList.add('fp-active');
        }
    }
});

// --- Expandable Summaries ---
function toggleSummary(btn) {
    var summary = btn.previousElementSibling;
    if (!summary || !summary.classList.contains('event-summary')) return;

    if (summary.classList.contains('expanded')) {
        summary.classList.remove('expanded');
        btn.textContent = 'more';
    } else {
        summary.classList.add('expanded');
        btn.textContent = 'less';
    }
}

function initExpandables() {
    document.querySelectorAll('.event-summary').forEach(function(el) {
        var btn = el.nextElementSibling;
        if (!btn || !btn.classList.contains('read-more')) return;

        if (el.classList.contains('expanded')) {
            btn.style.display = 'inline';
            return;
        }

        if (el.scrollHeight > el.clientHeight + 1) {
            btn.style.display = 'inline';
            btn.textContent = 'more';
        } else {
            btn.style.display = 'none';
        }
    });
}

// Sparklines are rendered by sparkline.js (loaded separately)

// ============================================
// DRAG RESIZE — 2-Row Command Center Layout
// ============================================

function initDragResize() {
    var dashboard = document.querySelector('.dashboard');
    var row2 = document.getElementById('row2-container');
    if (!dashboard) return;

    var dragging = null;
    var MIN_SIZE = 120;

    document.querySelectorAll('.drag-handle').forEach(function(handle) {
        handle.addEventListener('mousedown', function(e) {
            if (fullscreenPanelId) return;
            e.preventDefault();

            var direction = handle.dataset.direction;
            var target = handle.dataset.target;

            dragging = {
                handle: handle,
                direction: direction,
                target: target,
                startX: e.clientX,
                startY: e.clientY,
            };

            if (direction === 'row' && target === 'main') {
                var mapPanel = document.getElementById('panel-map');
                var r2c = document.getElementById('row2-container');
                dragging.startSizes = [mapPanel.offsetHeight, r2c.offsetHeight];
            } else if (direction === 'col' && target === 'row1') {
                var mapP = document.getElementById('panel-map');
                var intelP = document.getElementById('panel-1');
                dragging.startSizes = [mapP.offsetWidth, intelP.offsetWidth];
            } else if (direction === 'col' && target === 'row2') {
                var idx = parseInt(handle.dataset.index, 10);
                dragging.index = idx;
                var panels = [
                    document.getElementById('panel-4'),
                    document.getElementById('panel-2'),
                    document.getElementById('panel-3')
                ];
                dragging.startSizes = panels.map(function(p) { return p.offsetWidth; });
            }

            handle.classList.add('dragging');
            document.body.classList.add('is-dragging');
            document.body.style.cursor = direction === 'row' ? 'row-resize' : 'col-resize';
        });
    });

    document.addEventListener('mousemove', function(e) {
        if (!dragging) return;
        e.preventDefault();

        if (dragging.direction === 'row' && dragging.target === 'main') {
            var delta = e.clientY - dragging.startY;
            var s = dragging.startSizes;
            var newTop = Math.max(MIN_SIZE, s[0] + delta);
            var newBot = Math.max(MIN_SIZE, s[1] - delta);
            dashboard.style.gridTemplateRows = newTop + 'px 6px ' + newBot + 'px';
        } else if (dragging.direction === 'col' && dragging.target === 'row1') {
            var delta = e.clientX - dragging.startX;
            var s = dragging.startSizes;
            var newLeft = Math.max(MIN_SIZE, s[0] + delta);
            var newRight = Math.max(MIN_SIZE, s[1] - delta);
            dashboard.style.gridTemplateColumns = newLeft + 'px 6px ' + newRight + 'px';
        } else if (dragging.direction === 'col' && dragging.target === 'row2') {
            var delta = e.clientX - dragging.startX;
            var s = dragging.startSizes.slice();
            var idx = dragging.index;
            var total = s[idx] + s[idx + 1];
            var newLeft = Math.max(MIN_SIZE, s[idx] + delta);
            var newRight = Math.max(MIN_SIZE, total - newLeft);
            s[idx] = newLeft;
            s[idx + 1] = newRight;
            if (row2) row2.style.gridTemplateColumns = s[0] + 'px 6px ' + s[1] + 'px 6px ' + s[2] + 'px';
        }
    });

    document.addEventListener('mouseup', function() {
        if (!dragging) return;
        dragging.handle.classList.remove('dragging');
        document.body.classList.remove('is-dragging');
        document.body.style.cursor = '';
        dragging = null;
        initExpandables();
        if (conflictMap) conflictMap.invalidateSize();
    });

    window.addEventListener('resize', function() {
        dashboard.style.gridTemplateRows = '';
        dashboard.style.gridTemplateColumns = '';
        if (row2) row2.style.gridTemplateColumns = '';
        if (conflictMap) setTimeout(function() { conflictMap.invalidateSize(); }, 100);
    });
}

// ============================================
// CONFLICT MAP — Multi-Layer + Flashpoint Focus
// ============================================

var conflictMap = null;

var mapLayers = {
    conflict: null,
    aviation: null,
    thermal: null,
    seismic: null,
    news: null,
};
var layerVisible = {
    conflict: true,
    aviation: true,
    thermal: true,
    seismic: true,
    news: true,
};

var LAYER_CONFIG = {
    conflict: { label: 'Conflict', color: '#ff8800' },
    aviation: { label: 'Aviation', color: '#4488ff' },
    thermal:  { label: 'Thermal',  color: '#ff4444' },
    seismic:  { label: 'Seismic',  color: '#ffcc00' },
    news:     { label: 'News',     color: '#ff6644' },
};

// Flashpoint focus state
var activeFlashpoint = null;
var flashpointCircle = null;
var fpOverlayEl = null;

function initMap() {
    var mapEl = document.getElementById('conflict-map');
    if (!mapEl || typeof L === 'undefined') return;

    conflictMap = L.map('conflict-map', {
        center: [25, 55],
        zoom: 3,
        zoomControl: true,
        attributionControl: false,
        preferCanvas: true,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 18,
    }).addTo(conflictMap);

    for (var key in mapLayers) {
        mapLayers[key] = L.featureGroup().addTo(conflictMap);
    }

    initLayerToggles();

    // Initial load
    refreshMap(null);

    // Auto-refresh every 2 minutes
    setInterval(function() { refreshMap(activeFlashpoint); }, 120000);
}

function initLayerToggles() {
    var legendItems = document.querySelectorAll('.map-legend-item[data-layer]');
    legendItems.forEach(function(item) {
        item.addEventListener('click', function() {
            var layer = item.getAttribute('data-layer');
            if (!layer || !mapLayers[layer]) return;

            layerVisible[layer] = !layerVisible[layer];

            if (layerVisible[layer]) {
                conflictMap.addLayer(mapLayers[layer]);
                item.classList.remove('layer-off');
            } else {
                conflictMap.removeLayer(mapLayers[layer]);
                item.classList.add('layer-off');
            }
            updateMapCount();
        });
    });
}

function updateMapCount() {
    var count = 0;
    for (var key in mapLayers) {
        if (layerVisible[key] && mapLayers[key]) {
            count += mapLayers[key].getLayers().length;
        }
    }
    var countEl = document.getElementById('map-count');
    if (countEl) countEl.textContent = count + ' events visible';
}

function refreshMap(flashpointFilter) {
    if (!conflictMap) return;

    var url = '/api/events/geojson?hours=48';
    if (flashpointFilter) {
        url += '&flashpoint=' + encodeURIComponent(flashpointFilter);
    }

    fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(geojson) {
            for (var key in mapLayers) {
                if (mapLayers[key]) mapLayers[key].clearLayers();
            }

            var counts = {};

            if (geojson.features) {
                geojson.features.forEach(function(f) {
                    var coords = f.geometry.coordinates;
                    var props = f.properties;
                    var layer = props.layer || 'other';
                    var color = props.color || '#888888';
                    var size = props.size || 4;

                    var marker;
                    if (layer === 'aviation') {
                        marker = createAviationMarker(coords, props);
                    } else if (props.priority === 'critical') {
                        // Critical: pulsing DivIcon
                        var ms = size * 2;
                        marker = L.marker([coords[1], coords[0]], {
                            icon: L.divIcon({
                                className: 'marker-critical',
                                iconSize: [ms, ms],
                                iconAnchor: [ms/2, ms/2],
                                html: '<div style="width:' + ms + 'px;height:' + ms + 'px;border-radius:50%;background:' + color + ';opacity:0.85;"></div>',
                            }),
                        });
                    } else if (props.priority === 'high') {
                        marker = L.circleMarker([coords[1], coords[0]], {
                            radius: size + 1,
                            fillColor: color,
                            fillOpacity: 0.8,
                            color: '#ffffff',
                            weight: 1,
                            opacity: 0.4,
                        });
                    } else {
                        marker = L.circleMarker([coords[1], coords[0]], {
                            radius: size,
                            fillColor: color,
                            fillOpacity: 0.65,
                            color: color,
                            weight: 1,
                            opacity: 0.85,
                        });
                    }

                    marker.bindPopup(buildPopup(props));

                    if (layer === 'aviation') {
                        var callsign = (props.title || '').replace('Military flight: ', '').split(' — ')[0];
                        marker.bindTooltip(callsign, {
                            permanent: false,
                            direction: 'top',
                            className: 'map-tooltip',
                            offset: [0, -8],
                        });
                    }

                    var group = mapLayers[layer];
                    if (!group) group = mapLayers.news;
                    if (group) group.addLayer(marker);

                    counts[layer] = (counts[layer] || 0) + 1;
                });
            }

            for (var key in LAYER_CONFIG) {
                var badge = document.getElementById('layer-count-' + key);
                if (badge) badge.textContent = counts[key] || 0;
            }

            updateMapCount();
        })
        .catch(function(err) {
            console.warn('Map refresh failed:', err);
        });
}

function createAviationMarker(coords, props) {
    return L.circleMarker([coords[1], coords[0]], {
        radius: 5,
        fillColor: '#4488ff',
        fillOpacity: 0.9,
        color: '#88bbff',
        weight: 2,
        opacity: 1,
    });
}

function buildPopup(props) {
    var title = (props.title || '').substring(0, 150);
    var source = props.source || '';
    var summary = (props.summary || '').substring(0, 150);
    var url = props.url || '';
    var priority = props.priority || '';
    var created = props.created_at || '';
    var flashpoint = props.flashpoint || '';
    var region = props.region || '';

    var prioColors = { critical: '#ff3344', high: '#ff8800', medium: '#ffcc00', low: '#44aa66' };
    var prioColor = prioColors[priority] || '#666';

    var html = '<div class="map-popup">';
    html += '<div class="map-popup-prio" style="border-left:3px solid ' + prioColor + ';padding-left:8px;">';
    html += '<strong>' + escapeHtml(title) + '</strong>';
    html += '</div>';

    if (summary) {
        html += '<p class="map-popup-summary">' + escapeHtml(summary) + '</p>';
    }

    html += '<div class="map-popup-meta">';
    html += '<span>' + escapeHtml(source) + '</span>';
    if (region) html += ' &middot; <span>' + region + '</span>';
    if (flashpoint) html += ' &middot; <span style="color:#ff8800;">' + escapeHtml(flashpoint) + '</span>';
    html += '</div>';
    html += '<div class="map-popup-time">' + created + '</div>';

    if (url) {
        html += '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener" class="map-popup-link">Open source &#8594;</a>';
    }

    html += '</div>';
    return html;
}

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// FLASHPOINT FOCUS SYSTEM
// ============================================

var FP_SHORT_NAMES = {
    'Iran-Israel-US': 'Iran-Israel',
    'India-China LAC': 'India-China',
    'South China Sea': 'SCS',
    'Taiwan Strait': 'Taiwan',
    'Russia-NATO': 'Russia-NATO',
    'Korea': 'Korea'
};

var STATUS_COLORS = {
    critical: '#ff3344',
    escalating: '#ff8800',
    elevated: '#ffcc00',
    stable: '#44aa66',
    baseline: '#667788'
};

function initMapFilterBar() {
    var bar = document.getElementById('map-filter-bar');
    if (!bar || typeof FLASHPOINT_GEO === 'undefined') return;

    var html = '<span class="fp-chip active" data-fp="all">All</span>';
    FLASHPOINT_GEO.forEach(function(fp) {
        var label = FP_SHORT_NAMES[fp.name] || fp.name;
        html += '<span class="fp-chip" data-fp="' + escapeHtml(fp.name) + '">'
              + '<span class="fp-chip-dot dot-' + fp.status + '"></span>'
              + label
              + '</span>';
    });
    bar.innerHTML = html;

    // Get overlay element
    fpOverlayEl = document.getElementById('map-fp-overlay');

    // Wire chip clicks
    bar.addEventListener('click', function(e) {
        var chip = e.target.closest('.fp-chip');
        if (!chip) return;

        bar.querySelectorAll('.fp-chip').forEach(function(c) { c.classList.remove('active'); });
        chip.classList.add('active');

        var fpName = chip.getAttribute('data-fp');
        if (fpName === 'all') {
            clearFlashpointFocus();
        } else {
            focusFlashpoint(fpName);
        }
    });

    // Auto-focus on highest flashpoint if at least ELEVATED
    if (FLASHPOINT_GEO.length > 0) {
        var top = FLASHPOINT_GEO[0]; // Already sorted by score desc
        if (top.score >= 41) {
            setTimeout(function() {
                var chip = document.querySelector('.fp-chip[data-fp="' + top.name + '"]');
                if (chip) chip.click();
            }, 800);
        }
    }
}

function focusFlashpoint(name) {
    if (!conflictMap) return;

    var fp = null;
    for (var i = 0; i < FLASHPOINT_GEO.length; i++) {
        if (FLASHPOINT_GEO[i].name === name) { fp = FLASHPOINT_GEO[i]; break; }
    }
    if (!fp) return;

    activeFlashpoint = name;

    // Compute zoom from radius
    var zoom = 4;
    if (fp.radius_km <= 500) zoom = 7;
    else if (fp.radius_km <= 800) zoom = 6;
    else if (fp.radius_km <= 1500) zoom = 5;

    conflictMap.flyTo([fp.lat, fp.lon], zoom, { duration: 0.8 });

    // Draw radius circle
    if (flashpointCircle) conflictMap.removeLayer(flashpointCircle);
    var color = STATUS_COLORS[fp.status] || '#667788';
    flashpointCircle = L.circle([fp.lat, fp.lon], {
        radius: fp.radius_km * 1000,
        color: color,
        weight: 1.5,
        dashArray: '8, 6',
        fillColor: color,
        fillOpacity: 0.04,
        interactive: false,
    }).addTo(conflictMap);

    // Show overlay
    if (fpOverlayEl) {
        fpOverlayEl.innerHTML = '<span class="status-badge status-' + fp.status + '">' + fp.status.toUpperCase() + '</span> '
            + '<span>' + escapeHtml(fp.name) + '</span>'
            + ' <span class="fp-overlay-score" style="color:' + color + '">' + Math.round(fp.score) + '</span>';
        fpOverlayEl.classList.add('visible');
    }

    // Highlight situation card
    document.querySelectorAll('.fp-card').forEach(function(c) { c.classList.remove('fp-active'); });
    var card = document.querySelector('.fp-card[data-flashpoint="' + name + '"]');
    if (card) card.classList.add('fp-active');

    // Re-fetch filtered
    refreshMap(name);
}

function clearFlashpointFocus() {
    activeFlashpoint = null;

    if (flashpointCircle && conflictMap) {
        conflictMap.removeLayer(flashpointCircle);
        flashpointCircle = null;
    }

    if (fpOverlayEl) fpOverlayEl.classList.remove('visible');

    document.querySelectorAll('.fp-card').forEach(function(c) { c.classList.remove('fp-active'); });

    if (conflictMap) conflictMap.flyTo([25, 55], 3, { duration: 0.8 });

    refreshMap(null);
}

// Situation Board → Map interaction
function focusFlashpointFromCard(name) {
    var chip = document.querySelector('.fp-chip[data-fp="' + name + '"]');
    if (chip) {
        chip.click();
    } else {
        focusFlashpoint(name);
    }
}

// ============================================
// LIVE FLASHPOINT STATUS POLLING
// ============================================

function refreshFlashpointStatuses() {
    fetch('/api/flashpoints')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!Array.isArray(data)) return;

            data.forEach(function(fp) {
                // Update FLASHPOINT_GEO
                if (typeof FLASHPOINT_GEO !== 'undefined') {
                    for (var i = 0; i < FLASHPOINT_GEO.length; i++) {
                        if (FLASHPOINT_GEO[i].name === fp.name) {
                            FLASHPOINT_GEO[i].status = fp.status;
                            FLASHPOINT_GEO[i].score = fp.score;
                            FLASHPOINT_GEO[i].event_count_24h = fp.event_count_24h;
                            break;
                        }
                    }
                }

                // Update chip dot color
                var chip = document.querySelector('.fp-chip[data-fp="' + fp.name + '"]');
                if (chip) {
                    var dot = chip.querySelector('.fp-chip-dot');
                    if (dot) {
                        dot.className = 'fp-chip-dot dot-' + fp.status;
                    }
                }
            });

            // Update overlay if focused
            if (activeFlashpoint && fpOverlayEl) {
                for (var i = 0; i < FLASHPOINT_GEO.length; i++) {
                    if (FLASHPOINT_GEO[i].name === activeFlashpoint) {
                        var scoreEl = fpOverlayEl.querySelector('.fp-overlay-score');
                        if (scoreEl) {
                            scoreEl.textContent = Math.round(FLASHPOINT_GEO[i].score);
                            scoreEl.style.color = STATUS_COLORS[FLASHPOINT_GEO[i].status] || '#667788';
                        }
                        break;
                    }
                }
            }
        })
        .catch(function() {});
}

// ============================================
// INIT
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    initSearchClose();
    initDragResize();
    initExpandables();
    renderSparklines();
    initMap();
    initMapFilterBar();
    updateTimeAgo();
    setInterval(updateTimeAgo, 30000);
    setInterval(refreshFlashpointStatuses, 120000);
});

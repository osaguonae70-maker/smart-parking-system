document.addEventListener('DOMContentLoaded', function() {
    // Initialize Map
    let map;
    let marker;
    const parkingLocation = [8.843162, 7.906626]; // Nasarawa State University Keffi, Nigeria
    const SLOT_CACHE_KEY = 'nsuk-smart-parking-slots-cache';
    
    function initMap() {
        map = L.map('map', {
            zoomControl: false,
            dragging: false,
            touchZoom: false,
            doubleClickZoom: false,
            scrollWheelZoom: false,
            boxZoom: false,
            keyboard: false
        }).setView(parkingLocation, 16);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);

        marker = L.marker(parkingLocation).addTo(map)
            .bindPopup('<b>NSUK Smart Parking Lot</b>')
            .openPopup();
    }

    function renderOfflineMapFallback() {
        const mapElement = document.getElementById('map');
        if (!mapElement) return;
        mapElement.innerHTML = `
            <div class="d-flex align-items-center justify-content-center h-100 text-center text-muted px-3">
                <div>
                    <div class="fw-bold mb-2">Map unavailable offline</div>
                    <div class="small">Parking operations still work with the cached local system data.</div>
                </div>
            </div>
        `;
        mapElement.classList.add('bg-light');
    }

    if (document.getElementById('map') && window.L) {
        initMap();
    } else if (document.getElementById('map')) {
        renderOfflineMapFallback();
    }

    // Live Updates (AJAX)
    function cacheSlots(slots) {
        try {
            localStorage.setItem(SLOT_CACHE_KEY, JSON.stringify({
                savedAt: new Date().toISOString(),
                slots: Array.isArray(slots) ? slots : []
            }));
        } catch (error) {
            console.warn('Unable to cache slots locally:', error);
        }
    }

    function loadCachedSlots() {
        try {
            const raw = localStorage.getItem(SLOT_CACHE_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed.slots) ? parsed : null;
        } catch (error) {
            console.warn('Unable to read cached slots:', error);
            return null;
        }
    }

    function ensureLiveStatusBadge() {
        const sectionHeader = document.querySelector('#slots-grid')?.closest('.card')?.querySelector('.card-header');
        if (!sectionHeader) return null;

        let badge = document.getElementById('slot-live-status');
        if (badge) return badge;

        badge = document.createElement('span');
        badge.id = 'slot-live-status';
        badge.className = 'badge bg-light text-muted border fw-normal ms-2';
        badge.textContent = 'Live';
        sectionHeader.appendChild(badge);
        return badge;
    }

    function updateLiveStatus(isOffline, savedAt = null) {
        const badge = ensureLiveStatusBadge();
        if (!badge) return;

        if (isOffline) {
            badge.className = 'badge bg-warning text-dark border fw-normal ms-2';
            badge.textContent = savedAt ? `Offline cache: ${savedAt}` : 'Offline cache';
            return;
        }

        badge.className = 'badge bg-light text-muted border fw-normal ms-2';
        badge.textContent = 'Live';
    }

    async function fetchSlots() {
        try {
            const response = await fetch('/api/slots');
            const slots = await response.json();
            updateGrid(slots);
            updateAvailableCount(slots);
            cacheSlots(slots);
            updateLiveStatus(false);
        } catch (error) {
            console.error('Error fetching slots:', error);
            const cached = loadCachedSlots();
            if (cached && Array.isArray(cached.slots)) {
                updateGrid(cached.slots);
                updateAvailableCount(cached.slots);
                const savedAt = cached.savedAt ? new Date(cached.savedAt).toLocaleTimeString() : null;
                updateLiveStatus(true, savedAt);
            }
        }
    }

    function updateGrid(slots) {
        const grid = document.getElementById('slots-grid');
        if (!grid) return;

        slots
            .filter(slot => slot.zone === 'real_user')
            .forEach(slot => {
            const publicLabel = slot.slot_label || `R${slot.id}`;
            const slotItem = grid.querySelector(`[data-id="${publicLabel}"]`);
            if (slotItem) {
                // Update classes
                if (slot.is_occupied) {
                    slotItem.classList.remove('available');
                    slotItem.classList.add('occupied');
                    slotItem.setAttribute('data-vehicle', slot.vehicle);
                    slotItem.title = `Slot ${publicLabel} - ${slot.vehicle}`;
                    slotItem.querySelector('.slot-vehicle').innerHTML = `
                        <i class="fas fa-car mb-1"></i>
                        <span>${slot.vehicle}</span>
                    `;
                } else {
                    slotItem.classList.remove('occupied');
                    slotItem.classList.add('available');
                    slotItem.setAttribute('data-vehicle', '');
                    slotItem.title = `Slot ${publicLabel} - Available`;
                    slotItem.querySelector('.slot-vehicle').innerHTML = `
                        <i class="fas fa-check-circle mb-1"></i>
                        <span>FREE</span>
                    `;
                }
            }
        });
        
        // Re-apply search/filter after update
        applyFilters();
    }

    function updateAvailableCount(slots) {
        const available = slots.filter(s => s.zone === 'real_user' && !s.is_occupied).length;
        const countElement = document.getElementById('available-count');
        const mapCountElement = document.getElementById('map-available-count');
        
        if (countElement) countElement.innerText = available;
        if (mapCountElement) mapCountElement.innerText = available;
    }

    // Search and Filter logic
    const searchInput = document.getElementById('search-input');
    const filterRadios = document.getElementsByName('filter');

    if (searchInput) {
        searchInput.addEventListener('input', applyFilters);
    }

    if (filterRadios) {
        filterRadios.forEach(radio => {
            radio.addEventListener('change', applyFilters);
        });
    }

    function applyFilters() {
        const query = searchInput ? searchInput.value.toLowerCase() : '';
        const selectedFilter = Array.from(filterRadios).find(r => r.checked)?.id || 'filter-all';
        const slots = document.querySelectorAll('.slot-item');

        slots.forEach(slot => {
            const vehicle = slot.getAttribute('data-vehicle').toLowerCase();
            const id = slot.getAttribute('data-id');
            const isOccupied = slot.classList.contains('occupied');

            let matchesSearch = vehicle.includes(query) || id.includes(query);
            let matchesFilter = true;

            if (selectedFilter === 'filter-available') {
                matchesFilter = !isOccupied;
            } else if (selectedFilter === 'filter-occupied') {
                matchesFilter = isOccupied;
            }

            if (matchesSearch && matchesFilter) {
                slot.style.display = 'flex';
            } else {
                slot.style.display = 'none';
            }
        });
    }

    const hasSlotWidgets = Boolean(
        document.getElementById('slots-grid') ||
        document.getElementById('available-count') ||
        document.getElementById('map-available-count')
    );

    if (hasSlotWidgets) {
        fetchSlots();
        setInterval(fetchSlots, 3000);
    }
});

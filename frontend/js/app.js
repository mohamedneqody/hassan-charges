/**
 * Hassan Charges - Real-Time Forex Dashboard
 * Client-side Socket.IO + Live Price Updates
 */

class HassanChargesApp {
    constructor() {
        this.socket = null;
        this.prices = {};
        this.activeTab = 'all';
        this.searchQuery = '';
        this.updateCount = 0;
        this.lastCountReset = Date.now();
        this.flashTimers = {};
        this.watchlist = new Set(JSON.parse(localStorage.getItem('watchlist') || '[]'));
        this.priceAlerts = JSON.parse(localStorage.getItem('priceAlerts') || '{}');
        this.audioEnabled = false;
        this.audioContext = null;
        this.notifications = [];
        this.unreadNotifs = 0;
        this.theme = localStorage.getItem('theme') || 'dark';
        this.init();
    }

    init() {
        document.body.dataset.theme = this.theme;
        this.updateThemeIcon();
        this.initParticles();
        this.connectSocket();
        this.setupEventListeners();
        this.startClock();
        this.setupIntersectionObserver();
        this.initConverter();
    }

    initParticles() {
        const canvas = document.getElementById('particles-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        let width, height;
        const particles = [];
        
        const resize = () => {
            width = canvas.width = window.innerWidth;
            height = canvas.height = window.innerHeight;
        };
        window.addEventListener('resize', resize);
        resize();

        for(let i=0; i<50; i++) {
            particles.push({
                x: Math.random() * width,
                y: Math.random() * height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.5,
                size: Math.random() * 2 + 1
            });
        }

        const animate = () => {
            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = 'rgba(99, 102, 241, 0.5)';
            particles.forEach(p => {
                p.x += p.vx; p.y += p.vy;
                if (p.x < 0) p.x = width; if (p.x > width) p.x = 0;
                if (p.y < 0) p.y = height; if (p.y > height) p.y = 0;
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                ctx.fill();
            });
            requestAnimationFrame(animate);
        };
        animate();
    }

    /* ═══════════ SOCKET.IO CONNECTION ═══════════ */
    connectSocket() {
        this.socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
        });

        this.socket.on('connect', () => {
            this.setConnectionStatus(true);
            console.log('✅ Connected to Hassan Charges server');
        });

        this.socket.on('disconnect', () => {
            this.setConnectionStatus(false);
            console.log('❌ Disconnected from server');
        });

        this.socket.on('initial_prices', (data) => {
            console.log(`📦 Received ${Object.keys(data).length} pairs`);
            this.prices = data;
            this.renderAllCards();
            this.updateCounts();
        });

        this.socket.on('price_updates', (data) => {
            this.handlePriceUpdates(data);
        });
    }

    setConnectionStatus(connected) {
        const el = document.getElementById('connection-status');
        const text = el.querySelector('.status-text');
        el.className = 'connection-status ' + (connected ? 'connected' : 'disconnected');
        text.textContent = connected ? 'Live' : 'Disconnected';
    }

    /* ═══════════ PRICE UPDATES ═══════════ */
    handlePriceUpdates(updates) {
        this.updateCount++;
        let playSound = false;
        
        for (const [symbol, data] of Object.entries(updates)) {
            const prevPrice = this.prices[symbol]?.price;
            this.prices[symbol] = data;
            this.updateCard(symbol, data, prevPrice);
            
            // Notifications & Alerts logic
            if (prevPrice) {
                // Check User Price Alerts
                if (this.priceAlerts[symbol]) {
                    const target = this.priceAlerts[symbol];
                    const crossedUp = prevPrice < target && data.price >= target;
                    const crossedDown = prevPrice > target && data.price <= target;
                    
                    if (crossedUp || crossedDown) {
                        this.triggerSystemNotification(symbol, data.price, target);
                        delete this.priceAlerts[symbol]; // Remove alert after triggering
                        localStorage.setItem('priceAlerts', JSON.stringify(this.priceAlerts));
                        this.pushNotification(symbol, data.change_pct, data.price, `TARGET HIT: ${target}`);
                        playSound = true;
                    }
                }

                const movePct = Math.abs(data.change_pct);
                if (this.watchlist.has(symbol) && movePct > 0.05) {
                    playSound = true;
                }
                // Push notification if massive movement
                if (movePct > 0.15) {
                    this.pushNotification(symbol, data.change_pct, data.price);
                }
            }
        }
        
        if (playSound && this.audioEnabled) this.playTickSound();
        this.updateTicker();
    }

    playTickSound() {
        if (!this.audioContext) this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        if (this.audioContext.state === 'suspended') this.audioContext.resume();
        const osc = this.audioContext.createOscillator();
        const gain = this.audioContext.createGain();
        osc.connect(gain);
        gain.connect(this.audioContext.destination);
        osc.frequency.setValueAtTime(800, this.audioContext.currentTime);
        osc.frequency.exponentialRampToValueAtTime(1200, this.audioContext.currentTime + 0.1);
        gain.gain.setValueAtTime(0.1, this.audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, this.audioContext.currentTime + 0.1);
        osc.start();
        osc.stop(this.audioContext.currentTime + 0.1);
    }

    triggerSystemNotification(symbol, price, target) {
        if (!("Notification" in window)) return;
        if (Notification.permission === "granted") {
            new Notification(`🎯 Price Alert: ${symbol}`, {
                body: `${symbol} has reached your target of ${target} (Current: ${price})`,
                icon: '/favicon.ico'
            });
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(permission => {
                if (permission === "granted") this.triggerSystemNotification(symbol, price, target);
            });
        }
    }

    pushNotification(symbol, changePct, price, customMsg = null) {
        const type = changePct >= 0 ? 'bull' : 'bear';
        const msg = customMsg || `${symbol} moved by ${changePct.toFixed(2)}% to ${price.toFixed(4)}`;
        this.notifications.unshift({ msg, type, time: new Date() });
        if (this.notifications.length > 20) this.notifications.pop();
        
        this.unreadNotifs++;
        this.updateNotificationUI();
    }

    updateNotificationUI() {
        const badge = document.getElementById('notif-badge');
        const list = document.getElementById('notif-list');
        if(!badge || !list) return;

        if (this.unreadNotifs > 0) {
            badge.textContent = this.unreadNotifs;
            badge.style.display = 'block';
        } else {
            badge.style.display = 'none';
        }

        if (this.notifications.length === 0) {
            list.innerHTML = `<div class="empty-notif">No new notifications</div>`;
            return;
        }

        list.innerHTML = this.notifications.map(n => `
            <div class="notif-item ${n.type}">
                <span>${n.msg}</span>
                <span class="notif-time">${n.time.toLocaleTimeString()}</span>
            </div>
        `).join('');
    }

    updateTicker() {
        const sorted = Object.values(this.prices).sort((a,b) => b.change_pct - a.change_pct);
        if(sorted.length === 0) return;
        
        const top = sorted.slice(0, 5);
        const bottom = sorted.slice(-5).reverse();
        
        const tickerEl = document.getElementById('ticker-content');
        if(tickerEl) {
            let html = '';
            top.forEach(d => html += `<div class="ticker-item"><span style="color:var(--bullish)">▲ ${d.symbol}</span> ${d.change_pct.toFixed(2)}%</div>`);
            bottom.forEach(d => html += `<div class="ticker-item"><span style="color:var(--bearish)">▼ ${d.symbol}</span> ${d.change_pct.toFixed(2)}%</div>`);
            // duplicate for seamless scroll
            tickerEl.innerHTML = html + html;
        }

        // Sentiment
        const upCount = sorted.filter(d => d.change_pct > 0).length;
        const total = sorted.length;
        const upPct = (upCount / total) * 100 || 50;
        
        const bullBar = document.getElementById('sentiment-bull');
        const bearBar = document.getElementById('sentiment-bear');
        const text = document.querySelector('.sentiment-text');
        
        if(bullBar && bearBar && text) {
            bullBar.style.width = `${upPct}%`;
            bearBar.style.width = `${100 - upPct}%`;
            if(upPct > 55) text.innerHTML = `<span style="color:var(--bullish)">Bullish ${Math.round(upPct)}%</span>`;
            else if(upPct < 45) text.innerHTML = `<span style="color:var(--bearish)">Bearish ${Math.round(100-upPct)}%</span>`;
            else text.innerHTML = `Neutral`;
        }

        this.updateConverter();
    }

    updateCard(symbol, data, prevPrice) {
        const card = document.getElementById(`card-${this.symbolToId(symbol)}`);
        if (!card) return;
        if (card.style.display === 'none') return;

        const direction = data.price > prevPrice ? 'up' : data.price < prevPrice ? 'down' : null;

        // Update price
        const priceEl = card.querySelector('.price-value');
        priceEl.textContent = this.formatPrice(data.price, data.decimals);
        priceEl.className = 'price-value' + (direction ? ` ${direction}` : '');

        // Update change
        const changePct = card.querySelector('.change-pct');
        const arrow = data.change_pct >= 0 ? '▲' : '▼';
        changePct.textContent = `${arrow} ${Math.abs(data.change_pct).toFixed(2)}%`;
        changePct.className = 'change-pct ' + (data.change_pct >= 0 ? 'up' : 'down');

        const changeAbs = card.querySelector('.change-abs');
        const sign = data.change >= 0 ? '+' : '';
        changeAbs.textContent = `${sign}${data.change.toFixed(data.decimals)}`;

        // Update bid/ask
        const bidEl = card.querySelector('.bid-val');
        const askEl = card.querySelector('.ask-val');
        if (bidEl) bidEl.textContent = this.formatPrice(data.bid, data.decimals);
        if (askEl) askEl.textContent = this.formatPrice(data.ask, data.decimals);

        // Update high/low
        const highEl = card.querySelector('.high-val');
        const lowEl = card.querySelector('.low-val');
        if (highEl) highEl.textContent = this.formatPrice(data.high, data.decimals);
        if (lowEl) lowEl.textContent = this.formatPrice(data.low, data.decimals);

        // Update sparkline
        if (data.sparkline && data.sparkline.length > 1) {
            this.drawSparkline(card.querySelector('.sparkline-svg'), data.sparkline, data.change_pct >= 0);
        }

        // Flash animation (only if visible)
        if (direction && card.classList.contains('is-visible')) {
            clearTimeout(this.flashTimers[symbol]);
            card.classList.remove('flash-up', 'flash-down');
            void card.offsetWidth; // force reflow
            card.classList.add(`flash-${direction}`);
            this.flashTimers[symbol] = setTimeout(() => {
                card.classList.remove('flash-up', 'flash-down');
            }, 600);
        }
    }

    /* ═══════════ RENDERING ═══════════ */
    renderAllCards() {
        const grid = document.getElementById('currency-grid');
        grid.innerHTML = '';

        const sortedSymbols = Object.keys(this.prices).sort((a, b) => {
            const isWatchA = this.watchlist.has(a) ? 1 : 0;
            const isWatchB = this.watchlist.has(b) ? 1 : 0;
            if (this.activeTab === 'watchlist' || isWatchA !== isWatchB) {
                return isWatchB - isWatchA;
            }
            
            const catOrder = { major: 0, minor: 1, exotic: 2, crypto: 3 };
            const catA = catOrder[this.prices[a].category] ?? 99;
            const catB = catOrder[this.prices[b].category] ?? 99;
            if (catA !== catB) return catA - catB;
            return a.localeCompare(b);
        });

        for (const symbol of sortedSymbols) {
            const data = this.prices[symbol];
            const card = this.createCard(symbol, data);
            grid.appendChild(card);
            this.observer.observe(card);
        }
        this.filterCards();
        this.updateTicker();
        this.populateConverterOptions();
    }

    createCard(symbol, data) {
        const id = this.symbolToId(symbol);
        const card = document.createElement('div');
        card.className = 'currency-card';
        card.id = `card-${id}`;
        card.dataset.category = data.category;
        card.dataset.symbol = symbol;

        const arrow = data.change_pct >= 0 ? '▲' : '▼';
        const dir = data.change_pct >= 0 ? 'up' : 'down';
        const sign = data.change >= 0 ? '+' : '';

        const isStarred = this.watchlist.has(symbol);
        const hasAlert = !!this.priceAlerts[symbol];
        
        card.innerHTML = `
            <div class="card-header">
                <div class="pair-info">
                    <button class="star-btn ${isStarred ? 'starred' : ''}" data-symbol="${symbol}" title="Add to Watchlist">
                        ${isStarred ? '★' : '☆'}
                    </button>
                    <button class="alert-btn ${hasAlert ? 'active' : ''}" data-symbol="${symbol}" title="Set Price Alert">
                        ⏰
                    </button>
                    <span class="pair-flags">
                        ${data.base_flag}<span class="separator">/</span>${data.quote_flag}
                    </span>
                    <span class="pair-symbol">${symbol}</span>
                </div>
                <span class="pair-category ${data.category}">${data.category}</span>
            </div>
            <div class="card-price">
                <span class="price-value">${this.formatPrice(data.price, data.decimals)}</span>
                <div class="price-change">
                    <span class="change-pct ${dir}">${arrow} ${Math.abs(data.change_pct).toFixed(2)}%</span>
                    <span class="change-abs">${sign}${data.change.toFixed(data.decimals)}</span>
                </div>
            </div>
            <div class="sparkline-container">
                <svg class="sparkline-svg" viewBox="0 0 200 32" preserveAspectRatio="none"></svg>
            </div>
            <div class="card-footer">
                <div class="bid-ask">
                    <span><span class="bid-label">B</span><span class="bid-val">${this.formatPrice(data.bid, data.decimals)}</span></span>
                    <span><span class="ask-label">A</span><span class="ask-val">${this.formatPrice(data.ask, data.decimals)}</span></span>
                </div>
                <div class="high-low">
                    <span><span class="bid-label">H</span><span class="high-val">${this.formatPrice(data.high, data.decimals)}</span></span>
                    <span><span class="ask-label">L</span><span class="low-val">${this.formatPrice(data.low, data.decimals)}</span></span>
                </div>
            </div>
        `;

        // Draw initial sparkline
        if (data.sparkline && data.sparkline.length > 1) {
            requestAnimationFrame(() => {
                const svg = card.querySelector('.sparkline-svg');
                this.drawSparkline(svg, data.sparkline, data.change_pct >= 0, true);
            });
        }

        // 3D Hover Effect
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            const rotateX = ((y - centerY) / centerY) * -10;
            const rotateY = ((x - centerX) / centerX) * 10;
            card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
        });
        card.addEventListener('mouseleave', () => {
            card.style.transform = '';
        });

        return card;
    }

    /* ═══════════ SPARKLINE ═══════════ */
    drawSparkline(svg, points, isBullish) {
        if (!svg || points.length < 2) return;

        const w = 200, h = 32;
        const min = Math.min(...points);
        const max = Math.max(...points);
        const range = max - min || 1;

        const coords = points.map((p, i) => ({
            x: (i / (points.length - 1)) * w,
            y: h - ((p - min) / range) * (h - 4) - 2,
        }));

        // Smooth curve
        let path = `M ${coords[0].x},${coords[0].y}`;
        for (let i = 1; i < coords.length; i++) {
            const prev = coords[i - 1];
            const curr = coords[i];
            const cpx = (prev.x + curr.x) / 2;
            path += ` C ${cpx},${prev.y} ${cpx},${curr.y} ${curr.x},${curr.y}`;
        }

        // Gradient fill
        const last = coords[coords.length - 1];
        const fillPath = path + ` L ${last.x},${h} L ${coords[0].x},${h} Z`;
        const color = isBullish ? '#00e676' : '#ff5252';
        const gradId = `grad-${Math.random().toString(36).substr(2, 6)}`;

        svg.innerHTML = `
            <defs>
                <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="${color}" stop-opacity="0.25"/>
                    <stop offset="100%" stop-color="${color}" stop-opacity="0.02"/>
                </linearGradient>
            </defs>
            <path d="${fillPath}" fill="url(#${gradId})" />
            <path d="${path}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>
            <circle cx="${last.x}" cy="${last.y}" r="2.5" fill="${color}" opacity="0.9">
                <animate attributeName="r" values="2.5;3.5;2.5" dur="2s" repeatCount="indefinite"/>
            </circle>
        `;
    }

    /* ═══════════ FILTERING ═══════════ */
    filterCards() {
        const cards = document.querySelectorAll('.currency-card');
        let visibleCount = 0;

        cards.forEach(card => {
            const symbol = card.dataset.symbol.toLowerCase();
            const category = card.dataset.category;
            const data = this.prices[card.dataset.symbol];

            const baseName = data?.base_name?.toLowerCase() || '';
            const quoteName = data?.quote_name?.toLowerCase() || '';

            const matchesTab = this.activeTab === 'all' || 
                               (this.activeTab === 'watchlist' && this.watchlist.has(symbol.toUpperCase())) || 
                               category === this.activeTab;
            
            const matchesSearch = !this.searchQuery ||
                symbol.includes(this.searchQuery) ||
                baseName.includes(this.searchQuery) ||
                quoteName.includes(this.searchQuery);

            const visible = matchesTab && matchesSearch;
            card.style.display = visible ? '' : 'none';
            if (visible) visibleCount++;
        });

        document.getElementById('empty-state').style.display = visibleCount === 0 ? 'flex' : 'none';
    }

    updateCounts() {
        const counts = { all: 0, major: 0, minor: 0, exotic: 0, crypto: 0, watchlist: this.watchlist.size };
        for (const data of Object.values(this.prices)) {
            counts.all++;
            counts[data.category] = (counts[data.category] || 0) + 1;
        }
        for (const [key, val] of Object.entries(counts)) {
            const el = document.getElementById(`count-${key}`);
            if (el) el.textContent = val;
        }
        const statPairs = document.querySelector('#stat-pairs .stat-value');
        if(statPairs) statPairs.textContent = counts.all;
    }

    setupIntersectionObserver() {
        this.observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    // Refresh data instantly when scrolled into view
                    const symbol = entry.target.dataset.symbol;
                    if(this.prices[symbol]) this.updateCard(symbol, this.prices[symbol], null);
                } else {
                    entry.target.classList.remove('is-visible');
                }
            });
        }, { rootMargin: '100px' });
    }

    /* ═══════════ CONVERTER ═══════════ */
    initConverter() {
        const amt = document.getElementById('conv-amount');
        const from = document.getElementById('conv-from');
        const to = document.getElementById('conv-to');
        if(!amt || !from || !to) return;
        
        [amt, from, to].forEach(el => el.addEventListener('input', () => this.updateConverter()));
    }

    populateConverterOptions() {
        const currencies = new Set(['USD']); // base
        Object.keys(this.prices).forEach(sym => {
            const [b, q] = sym.split('/');
            currencies.add(b); currencies.add(q);
        });
        
        const sorted = Array.from(currencies).sort();
        let optionsHTML = sorted.map(c => `<option value="${c}">${c}</option>`).join('');
        
        const from = document.getElementById('conv-from');
        const to = document.getElementById('conv-to');
        if(!from || !to) return;
        
        const oldFrom = from.value; const oldTo = to.value;
        from.innerHTML = optionsHTML; to.innerHTML = optionsHTML;
        if(sorted.includes(oldFrom)) from.value = oldFrom; else from.value = 'USD';
        if(sorted.includes(oldTo)) to.value = oldTo; else to.value = sorted.includes('EGP') ? 'EGP' : sorted[0];
        this.updateConverter();
    }

    getUsdRate(currency) {
        if(currency === 'USD') return 1;
        // Check direct pair like EUR/USD
        const pair1 = `${currency}/USD`;
        if(this.prices[pair1]) return this.prices[pair1].price;
        // Check reverse pair like USD/EGP
        const pair2 = `USD/${currency}`;
        if(this.prices[pair2]) return 1 / this.prices[pair2].price;
        return null; // Cross rates fallbacks would go here if needed
    }

    updateConverter() {
        const amtEl = document.getElementById('conv-amount');
        const fromEl = document.getElementById('conv-from');
        const toEl = document.getElementById('conv-to');
        const resultEl = document.getElementById('conv-result');
        if(!amtEl || !fromEl || !toEl || !resultEl) return;

        const amt = parseFloat(amtEl.value) || 0;
        const from = fromEl.value;
        const to = toEl.value;

        const rateFromToUsd = this.getUsdRate(from);
        const rateToToUsd = this.getUsdRate(to);

        if(rateFromToUsd === null || rateToToUsd === null) {
            resultEl.textContent = "N/A";
            return;
        }

        // Convert From -> USD -> To
        const valueInUsd = amt * rateFromToUsd;
        const finalValue = valueInUsd / rateToToUsd;
        
        resultEl.textContent = finalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    }

    updateThemeIcon() {
        const btn = document.getElementById('theme-toggle');
        if (!btn) return;
        const icon = btn.querySelector('.icon');
        if (this.theme === 'dark') icon.textContent = '🌙';
        else if (this.theme === 'light') icon.textContent = '☀️';
        else icon.textContent = '🌈';
    }

    /* ═══════════ EVENT LISTENERS ═══════════ */
    setupEventListeners() {
        // Theme
        const themeBtn = document.getElementById('theme-toggle');
        if (themeBtn) {
            themeBtn.addEventListener('click', () => {
                if (this.theme === 'dark') this.theme = 'light';
                else if (this.theme === 'light') this.theme = 'neon';
                else this.theme = 'dark';
                
                document.body.dataset.theme = this.theme;
                localStorage.setItem('theme', this.theme);
                this.updateThemeIcon();
            });
        }

        // Notifications
        const notifBtn = document.getElementById('notif-toggle');
        const notifPanel = document.getElementById('notif-panel');
        if (notifBtn && notifPanel) {
            notifBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                notifPanel.classList.toggle('open');
                this.unreadNotifs = 0;
                this.updateNotificationUI();
            });
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.notification-wrapper')) {
                    notifPanel.classList.remove('open');
                }
            });
        }

        // Audio
        const audioBtn = document.getElementById('audio-toggle');
        if (audioBtn) {
            audioBtn.addEventListener('click', () => {
                this.audioEnabled = !this.audioEnabled;
                audioBtn.classList.toggle('active', this.audioEnabled);
                audioBtn.innerHTML = this.audioEnabled ? '<span class="icon">🔊</span>' : '<span class="icon">🔇</span>';
                if (this.audioEnabled) this.playTickSound();
            });
        }

        // Watchlist Delegation
        document.getElementById('currency-grid').addEventListener('click', (e) => {
            const btn = e.target.closest('.star-btn');
            if (!btn) return;
            const symbol = btn.dataset.symbol;
            if (this.watchlist.has(symbol)) {
                this.watchlist.delete(symbol);
                btn.classList.remove('starred');
                btn.textContent = '☆';
            } else {
                this.watchlist.add(symbol);
                btn.classList.add('starred');
                btn.textContent = '★';
            }
            localStorage.setItem('watchlist', JSON.stringify([...this.watchlist]));
            this.updateCounts();
            if(this.activeTab === 'watchlist') this.filterCards();
        });

        // Price Alert Delegation
        document.getElementById('currency-grid').addEventListener('click', (e) => {
            const btn = e.target.closest('.alert-btn');
            if (!btn) return;
            const symbol = btn.dataset.symbol;
            
            if (this.priceAlerts[symbol]) {
                if(confirm(`Remove price alert for ${symbol}?`)) {
                    delete this.priceAlerts[symbol];
                    btn.classList.remove('active');
                    localStorage.setItem('priceAlerts', JSON.stringify(this.priceAlerts));
                }
            } else {
                const currentPrice = this.prices[symbol]?.price;
                const target = prompt(`Set target price for ${symbol} (Current: ${currentPrice}):`, currentPrice);
                if (target && !isNaN(target)) {
                    this.priceAlerts[symbol] = parseFloat(target);
                    btn.classList.add('active');
                    localStorage.setItem('priceAlerts', JSON.stringify(this.priceAlerts));
                    
                    // Request notification permission if not granted
                    if ("Notification" in window && Notification.permission !== "granted" && Notification.permission !== "denied") {
                        Notification.requestPermission();
                    }
                }
            }
        });

        // Tabs
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                this.activeTab = tab.dataset.tab;
                if(this.activeTab === 'watchlist') this.renderAllCards();
                this.filterCards();
            });
        });

        // Search
        const searchInput = document.getElementById('search-input');
        let debounce;
        searchInput.addEventListener('input', () => {
            clearTimeout(debounce);
            debounce = setTimeout(() => {
                this.searchQuery = searchInput.value.toLowerCase().trim();
                this.filterCards();
            }, 150);
        });

        // Updates/sec counter
        setInterval(() => {
            const now = Date.now();
            const elapsed = (now - this.lastCountReset) / 1000;
            const rate = elapsed > 0 ? Math.round(this.updateCount / elapsed) : 0;
            document.querySelector('#stat-updates .stat-value').textContent = rate;
            this.updateCount = 0;
            this.lastCountReset = now;
        }, 3000);
    }

    /* ═══════════ CLOCK ═══════════ */
    startClock() {
        const update = () => {
            const now = new Date();
            document.getElementById('clock').textContent =
                now.toLocaleTimeString('en-US', { hour12: false });
        };
        update();
        setInterval(update, 1000);
    }

    /* ═══════════ UTILITIES ═══════════ */
    symbolToId(symbol) {
        return symbol.replace(/[\/\s]/g, '-');
    }

    formatPrice(price, decimals) {
        if (typeof price !== 'number') return '--';
        return price.toFixed(decimals);
    }
}

// ═══════════ LAUNCH ═══════════
document.addEventListener('DOMContentLoaded', () => {
    window.app = new HassanChargesApp();
});

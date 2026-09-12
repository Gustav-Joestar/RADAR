// RADAR Application Controller

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[m]);
}

document.addEventListener('DOMContentLoaded', () => {
  const state = {
    category: 'movies',
    year: 'all',
    min_rating: 0.0,
    max_size: 999.0,
    qualities: ['1080p', '720p'],
    genre: 'all',
    origin: 'foreign',
    search: '',
    page: 1,
    limit: 15,
    totalPages: 1
  };

  // DOM Elements
  const progressBar = document.getElementById('global-progress-bar');
  const cardsGrid = document.getElementById('cards-grid');
  const tableViewContainer = document.getElementById('table-view-container');
  const ignoredTableBody = document.getElementById('ignored-table-body');
  const countWatchlist = document.getElementById('count-watchlist');
  const countIgnored = document.getElementById('count-ignored');
  const emptyState = document.getElementById('empty-state');
  const resultsCount = document.getElementById('results-count');
  const currentPageSpan = document.getElementById('current-page');
  const totalPagesSpan = document.getElementById('total-pages');
  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');
  const btnRefresh = document.getElementById('btn-refresh');
  const btnApplyFilters = document.getElementById('btn-apply-filters');
  const ratingToggle = document.getElementById('rating-toggle');
  const ratingWrap = document.getElementById('rating-filter-wrap');
  const russianToggle = document.getElementById('russian-toggle');
  const russianWrap = document.getElementById('russian-filter-wrap');
  const qualityWrap = document.getElementById('quality-filter-wrap');
  const yearWrap = document.getElementById('year-filter-wrap');
  const yearSelect = document.getElementById('year-select');
  const searchInput = document.getElementById('search-input');
  const genreSelect = document.getElementById('genre-select');
  const genreWrap = document.getElementById('genre-filter-wrap');
  const btnReset = document.getElementById('btn-reset-filters');
  const modalOverlay = document.getElementById('detail-modal');
  const modalContent = document.getElementById('modal-content');
  const modalClose = document.getElementById('modal-close');
  const consoleLogFeed = document.getElementById('console-log-feed');
  const consoleToggle = document.getElementById('console-toggle');
  const consoleStatusText = document.getElementById('console-status-text');
  const consoleMinimizeBtn = document.getElementById('console-minimize-btn');
  const debugConsole = document.getElementById('debug-console');
  const progressFill = document.getElementById('progress-fill');

  // Poster loading tracker
  let posterLoadQueue = [];   // [{torrentId, attempt}]
  let posterLoadTotal = 0;
  let posterLoadDone = 0;
  let posterRetryTimers = {}; // torrentId -> setTimeout id

  // Initialize
  initEventListeners();
  updateCounts();

  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has('genre')) {
    state.genre = urlParams.get('genre');
  }
  if (urlParams.has('year')) {
    let y = urlParams.get('year');
    if (y === '< 2000' || y === '<2000') y = '<2000';
    state.year = y;
  }
  if (urlParams.has('rating')) {
    state.min_rating = parseFloat(urlParams.get('rating'));
    if (ratingToggle) ratingToggle.checked = state.min_rating > 0;
  }
  if (urlParams.has('origin')) {
    state.origin = urlParams.get('origin');
    if (russianToggle) russianToggle.checked = state.origin === 'russian';
  }
  if (urlParams.has('search')) {
    state.search = urlParams.get('search');
    if (searchInput) searchInput.value = state.search;
  }
  if (urlParams.has('page')) {
    state.page = parseInt(urlParams.get('page')) || 1;
  }
  if (urlParams.has('modal')) {
    setTimeout(() => openModal(urlParams.get('modal')), 700);
  }

  Promise.all([loadYears(), loadGenres()]).finally(() => {
    if (yearSelect && state.year) {
      yearSelect.value = state.year;
    }
    if (genreSelect && state.genre) {
      genreSelect.value = state.genre;
    }
    const initialTab = urlParams.get('tab') || window.location.hash.replace('#', '');
    if (initialTab && ['watchlist', 'ignored', 'movies', 'series', 'games', 'software'].includes(initialTab)) {
      const targetBtn = document.querySelector(`.cat-btn[data-category="${initialTab}"]`);
      if (targetBtn) {
        targetBtn.click();
      } else {
        fetchReleases();
      }
    } else {
      fetchReleases();
    }
  });

  pollLogs();
  setInterval(pollLogs, 2000);
  setInterval(updateCounts, 5000);

  function initEventListeners() {
    // Category & List Tabs
    document.querySelectorAll('.cat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.category = btn.dataset.category;
        state.page = 1;

        if (state.category === 'watchlist' || state.category === 'ignored') {
          if (ratingWrap) ratingWrap.style.display = 'none';
          if (qualityWrap) qualityWrap.style.display = 'none';
          if (yearWrap) yearWrap.style.display = 'none';
          if (genreWrap) genreWrap.style.display = 'none';
          if (russianWrap) russianWrap.style.display = 'none';
        } else if (state.category === 'games' || state.category === 'software') {
          if (ratingWrap) ratingWrap.style.display = 'none';
          if (qualityWrap) qualityWrap.style.display = 'none';
          if (yearWrap) yearWrap.style.display = 'none';
          if (genreWrap) genreWrap.style.display = 'flex';
          if (russianWrap) russianWrap.style.display = 'none';
          state.min_rating = 0.0;
        } else {
          if (ratingWrap) ratingWrap.style.display = 'flex';
          if (qualityWrap) qualityWrap.style.display = 'flex';
          if (yearWrap) yearWrap.style.display = 'flex';
          if (genreWrap) genreWrap.style.display = 'flex';
          if (russianWrap) russianWrap.style.display = 'flex';
          state.min_rating = ratingToggle && ratingToggle.checked ? 7.0 : 0.0;
        }

        if (!['watchlist', 'ignored'].includes(state.category)) {
          loadYears();
          loadGenres();
        }
        fetchReleases();
      });
    });

    // Apply Filters Button
    if (btnApplyFilters) {
      btnApplyFilters.addEventListener('click', applyFilters);
    }

    // Search Input: Apply on Enter
    if (searchInput) {
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          applyFilters();
        }
      });
    }

    // Reset Filters
    btnReset.addEventListener('click', resetFilters);

    // Refresh Tracker Data
    btnRefresh.addEventListener('click', () => {
      btnRefresh.classList.add('loading');
      const yearInfo = (['movies', 'series', 'anime'].includes(state.category)) ? ` (${state.year})` : '';
      consoleStatusText.textContent = `Сканирование трекера [${state.category}]${yearInfo}...`;
      fetch('/api/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: state.category, year: state.year })
      })
      .then(res => res.json())
      .then(() => {
        let attempts = 0;
        const interval = setInterval(() => {
          attempts++;
          fetchReleases(true); // silent update
          if (attempts >= 6) {
            clearInterval(interval);
            btnRefresh.classList.remove('loading');
          }
        }, 2000);
      })
      .catch(() => btnRefresh.classList.remove('loading'));
    });

    // Pagination
    btnPrev.addEventListener('click', () => {
      if (state.page > 1) {
        state.page--;
        fetchReleases();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });

    btnNext.addEventListener('click', () => {
      const isDiscovery = !['watchlist', 'ignored'].includes(state.category) && !state.search;
      if (!isDiscovery && state.page >= state.totalPages) return;
      state.page++;
      fetchReleases();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // Modal Close
    modalClose.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) closeModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModal();
    });

    // Console Toggle
    consoleToggle.addEventListener('click', (e) => {
      if (e.target.tagName !== 'BUTTON') {
        debugConsole.classList.toggle('minimized');
      }
    });
    consoleMinimizeBtn.addEventListener('click', () => {
      debugConsole.classList.toggle('minimized');
      consoleMinimizeBtn.textContent = debugConsole.classList.contains('minimized') ? '▢' : '_';
    });
  }

  function applyFilters() {
    state.page = 1;
    fetchReleases();
  }

  function resetFilters() {
    state.year = 'all';
    state.min_rating = 0.0;
    state.max_size = 999.0;
    state.qualities = ['1080p', '720p'];
    state.genre = 'all';
    state.origin = 'foreign';
    state.search = '';
    state.page = 1;

    if (yearSelect) yearSelect.value = 'all';
    if (searchInput) searchInput.value = '';
    if (ratingToggle) ratingToggle.checked = false;
    if (russianToggle) russianToggle.checked = false;
    if (genreSelect) genreSelect.value = 'all';

    const q1080 = document.getElementById('q-1080p');
    const q720 = document.getElementById('q-720p');
    const q4k = document.getElementById('q-4k');
    if (q1080) q1080.checked = true;
    if (q720) q720.checked = true;
    if (q4k) q4k.checked = false;

    fetchReleases();
  }

  function updateCounts() {
    fetch('/api/counts')
      .then(res => res.json())
      .then(counts => {
        if (countWatchlist) countWatchlist.textContent = counts.watchlist || 0;
        if (countIgnored) countIgnored.textContent = counts.ignored || 0;
      })
      .catch(() => {});
  }

  function loadYears() {
    if (['games', 'software', 'watchlist', 'ignored'].includes(state.category)) {
      if (yearWrap) yearWrap.style.display = 'none';
      return Promise.resolve();
    }
    if (yearWrap) yearWrap.style.display = 'flex';
    return fetch(`/api/years?category=${state.category}`)
      .then(res => res.json())
      .then(data => {
        if (!data.years || !yearSelect) return;
        const currentYear = state.year || 'all';
        yearSelect.innerHTML = '';
        
        const optAll = document.createElement('option');
        optAll.value = 'all';
        optAll.textContent = 'Все годы';
        yearSelect.appendChild(optAll);

        data.years.forEach(y => {
          const opt = document.createElement('option');
          const yStr = String(y).trim();
          if (yStr === '< 2000' || yStr === '<2000') {
            opt.value = '<2000';
            opt.textContent = 'До 2000 года (< 2000)';
          } else {
            opt.value = yStr;
            opt.textContent = `${yStr} год`;
          }
          yearSelect.appendChild(opt);
        });

        if (currentYear === '< 2000' || currentYear === '<2000') {
          yearSelect.value = '<2000';
        } else {
          yearSelect.value = currentYear;
        }
      })
      .catch(() => {});
  }

  function loadGenres() {
    if (['games', 'software', 'watchlist', 'ignored'].includes(state.category)) {
      if (genreWrap) genreWrap.style.display = 'none';
      return Promise.resolve();
    }
    if (genreWrap) genreWrap.style.display = 'flex';
    return fetch(`/api/genres?category=${state.category}`)
      .then(res => res.json())
      .then(data => {
        if (!data.genres || !genreSelect) return;
        const currentGenre = state.genre || 'all';
        genreSelect.innerHTML = '';

        const optAll = document.createElement('option');
        optAll.value = 'all';
        optAll.textContent = 'Все жанры';
        genreSelect.appendChild(optAll);

        data.genres.forEach(g => {
          const opt = document.createElement('option');
          opt.value = g;
          opt.textContent = g;
          genreSelect.appendChild(opt);
        });

        genreSelect.value = currentGenre;
      })
      .catch(() => {});
  }

  function fetchReleases(isSilent = false) {
    updateCounts();
    if (progressBar) progressBar.classList.add('active');

    // 1. "Не буду смотреть" (Compact Table View)
    if (state.category === 'ignored') {
      cardsGrid.style.display = 'none';
      tableViewContainer.style.display = 'block';

      const p = new URLSearchParams({
        search: state.search,
        page: state.page,
        limit: state.limit
      });

      fetch(`/api/ignored?${p.toString()}`)
        .then(res => res.json())
        .then(data => {
          renderIgnoredTable(data.items);
          state.totalPages = data.pages;
          currentPageSpan.textContent = data.page;
          totalPagesSpan.textContent = data.pages;
          resultsCount.textContent = `Отклонённых фильмов: ${data.total} (показано ${data.items.length})`;
          btnPrev.disabled = data.page <= 1;
          btnNext.disabled = data.page >= data.pages;

          if (data.total === 0) {
            tableViewContainer.style.display = 'none';
            emptyState.style.display = 'block';
          } else {
            emptyState.style.display = 'none';
          }
          consoleStatusText.textContent = `Отклонённые фильмы: ${data.total} в чёрном списке`;
        })
        .catch(err => {
          tableViewContainer.innerHTML = `<div style="color: #ef4444; padding: 20px;">Ошибка: ${err.message}</div>`;
        })
        .finally(() => {
          if (progressBar) progressBar.classList.remove('active');
        });
      return;
    }

    // 2. "Буду смотреть" (Watchlist Grid View)
    if (state.category === 'watchlist') {
      tableViewContainer.style.display = 'none';
      cardsGrid.style.display = 'grid';

      const p = new URLSearchParams({
        search: state.search,
        page: state.page,
        limit: state.limit
      });

      fetch(`/api/watchlist?${p.toString()}`)
        .then(res => res.json())
        .then(data => {
          renderCards(data.items, true);
          state.totalPages = data.pages;
          currentPageSpan.textContent = data.page;
          totalPagesSpan.textContent = data.pages;
          resultsCount.textContent = `В списке «Буду смотреть»: ${data.total} (показано ${data.items.length})`;
          btnPrev.disabled = data.page <= 1;
          btnNext.disabled = data.page >= data.pages;

          if (data.total === 0) {
            cardsGrid.style.display = 'none';
            emptyState.style.display = 'block';
          } else {
            cardsGrid.style.display = 'grid';
            emptyState.style.display = 'none';
          }
          consoleStatusText.textContent = `Буду смотреть: ${data.total} отобранных фильмов`;
        })
        .catch(err => {
          cardsGrid.innerHTML = `<div style="grid-column: 1/-1; color: #ef4444; padding: 40px; text-align: center;">Ошибка: ${err.message}</div>`;
        })
        .finally(() => {
          if (progressBar) progressBar.classList.remove('active');
        });
      return;
    }

    // 3. Regular Discovery Grid View (movies, series, anime, games, software)
    tableViewContainer.style.display = 'none';
    cardsGrid.style.display = 'grid';

    if (!isSilent) {
      cardsGrid.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 60px 0; color: var(--text-muted);">
          <div style="font-size: 36px; margin-bottom: 12px; animation: spin 1.5s linear infinite;">📡</div>
          Поиск релизов на радаре...
        </div>
      `;
    }

    if (russianToggle) state.origin = russianToggle.checked ? 'russian' : 'foreign';
    if (yearSelect) state.year = yearSelect.value;
    if (genreSelect) state.genre = genreSelect.value;
    if (ratingToggle) state.min_rating = ratingToggle.checked ? 7.0 : 0.0;
    if (searchInput) state.search = searchInput.value.trim();

    const activeQualities = [];
    if (document.getElementById('q-1080p')?.checked) activeQualities.push('1080p');
    if (document.getElementById('q-720p')?.checked) activeQualities.push('720p');
    if (document.getElementById('q-4k')?.checked) activeQualities.push('4K');
    state.qualities = activeQualities;

    const params = new URLSearchParams({
      category: state.category,
      year: state.year,
      min_rating: state.min_rating,
      max_size: state.max_size,
      genre: state.genre,
      origin: state.origin,
      search: state.search,
      page: state.page,
      limit: state.limit
    });

    if (state.qualities.length > 0) {
      params.append('quality', state.qualities.join(','));
    }

    if (!isSilent) {
      renderSkeletonGrid(state.limit || 15);
      const yearInfo = (['movies', 'series'].includes(state.category)) ? ` (${state.year === 'all' ? 'все годы' : state.year})` : '';
      const origInfo = state.origin === 'russian' ? ' [Русское]' : '';
      consoleStatusText.textContent = `Запрос релизов (категория: ${state.category}${yearInfo}${origInfo}, стр. ${state.page})...`;
    }

    fetch(`/api/items?${params.toString()}`)
      .then(res => res.json())
      .then(data => {
        renderCards(data.items, false);
        const isDiscovery = !['watchlist', 'ignored'].includes(state.category) && !state.search;
        state.totalPages = isDiscovery ? Math.max(data.pages || 1, data.page + 1) : (data.pages || 1);
        currentPageSpan.textContent = data.page;
        totalPagesSpan.textContent = state.totalPages;
        resultsCount.textContent = `Найдено релизов: ${data.total} (показано ${data.items.length})`;

        btnPrev.disabled = data.page <= 1;
        btnNext.disabled = isDiscovery ? (data.items.length === 0) : (data.page >= state.totalPages);

        if (data.total === 0 && data.items.length === 0) {
          cardsGrid.style.display = 'none';
          emptyState.style.display = 'block';
        } else {
          cardsGrid.style.display = 'grid';
          emptyState.style.display = 'none';
        }
        consoleStatusText.textContent = `Найдено ${data.total} уникальных релизов (${state.year === 'all' ? 'все годы' : `${state.year} г.`}, стр. ${data.page})`;

      })
      .catch(err => {
        if (!isSilent) {
          cardsGrid.innerHTML = `<div style="grid-column: 1/-1; color: #ef4444; padding: 40px; text-align: center;">Ошибка загрузки данных: ${err.message}</div>`;
        }
      })
      .finally(() => {
        if (posterLoadTotal === 0 || posterLoadDone >= posterLoadTotal) {
          if (progressBar) progressBar.classList.remove('active');
        }
      });
  }

  function formatCountryBadge(countryStr) {
    if (!countryStr || typeof countryStr !== 'string') return '';
    const clean = countryStr.split(/[,/|;]/)[0].trim();
    if (!clean) return '';
    return `
      <div class="card-country-box">
        <span class="card-country-text" title="${countryStr}">${clean}</span>
      </div>
    `;
  }

  function renderSkeletonGrid(count = 15) {
    let html = '';
    for (let i = 0; i < count; i++) {
      html += `
        <div class="skeleton-card">
          <div class="skeleton-poster skeleton"></div>
          <div class="skeleton-content">
            <div class="skeleton-line w-80 skeleton"></div>
            <div class="skeleton-line w-40 skeleton"></div>
            <div class="skeleton-line w-60 skeleton"></div>
            <div class="skeleton-line w-30 skeleton"></div>
          </div>
        </div>
      `;
    }
    cardsGrid.innerHTML = html;
    cardsGrid.style.display = 'grid';
    emptyState.style.display = 'none';
  }

  let hydrationTimer = null;
  function startCardHydration(torrentIds) {
    if (hydrationTimer) clearInterval(hydrationTimer);
    if (!torrentIds || torrentIds.length === 0) return;

    let attempts = 0;
    const maxAttempts = 20;

    hydrationTimer = setInterval(() => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(hydrationTimer);
        hydrationTimer = null;
        return;
      }

      fetch(`/api/cards_status?ids=${torrentIds.join(',')}`)
        .then(res => res.json())
        .then(data => {
          if (!data || !data.items) return;
          let allDone = true;

          data.items.forEach(st => {
            const card = document.getElementById(`card-${st.torrent_id}`);
            if (!card) return;

            // 1. Hydrate Genre
            if (st.genre && st.genre !== 'Фильм' && st.genre !== 'Сериал') {
              const gEl = card.querySelector('.card-genres');
              if (gEl && (gEl.classList.contains('skeleton') || gEl.textContent === 'Фильм' || gEl.textContent === 'Сериал')) {
                gEl.className = 'card-genres';
                gEl.textContent = st.genre;
              }
            }

            // 2. Hydrate Country
            if (st.country) {
              const cEl = card.querySelector('.card-country-box');
              if (cEl && (cEl.classList.contains('skeleton') || !cEl.querySelector('.card-country-text'))) {
                cEl.outerHTML = formatCountryBadge(st.country);
              }
            }

            // 3. Hydrate Poster
            if (st.poster_url) {
              const loader = card.querySelector('.poster-loading');
              if (loader) {
                const wrap = card.querySelector('.poster-wrap');
                if (wrap) {
                  const img = document.createElement('img');
                  img.className = 'poster-img poster-loaded';
                  img.src = st.poster_url;
                  img.alt = card.dataset.titleRu || '';
                  loader.replaceWith(img);
                }
              }
            }

            // 4. Hydrate Ratings
            if (st.kp_rating > 0 || st.imdb_rating > 0) {
              const rWrap = card.querySelector('.card-ratings-wrap');
              if (rWrap && rWrap.querySelector('.skeleton')) {
                let rHtml = '';
                if (st.kp_rating > 0) rHtml += `<div class="badge-rating kp-badge" title="Кинопоиск">КП ${st.kp_rating}</div>`;
                if (st.imdb_rating > 0) rHtml += `<div class="badge-rating imdb-badge" title="IMDb">IMDb ${st.imdb_rating}</div>`;
                rWrap.innerHTML = rHtml;
              }
            }

            const stillNeeds = (st.kp_rating === 0 && st.imdb_rating === 0) || !st.poster_url;
            if (stillNeeds) allDone = false;
          });

          if (allDone) {
            clearInterval(hydrationTimer);
            hydrationTimer = null;
          }
        })
        .catch(() => {});
    }, 600);
  }

  function renderCards(items, isWatchlist = false) {
    cardsGrid.innerHTML = '';
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'media-card';
      card.id = `card-${item.torrent_id}`;
      card.dataset.titleRu = (item.title_ru || '').trim().toLowerCase();
      card.onclick = () => openModal(item.torrent_id);

      const escapedTitle = (item.title_ru || '').replace(/'/g, "\\'");
      const escapedEn = (item.title_en || '').replace(/'/g, "\\'");

      const posterHtml = item.poster_url 
        ? `<img class="poster-img poster-loaded" src="${item.poster_url}" alt="${item.title_ru}" loading="lazy" onerror="this.onerror=null; repairPoster(this, '${item.torrent_id}', '${escapedTitle}', ${item.year || 0}, '${escapedEn}');"/><div class="poster-placeholder" style="display:none;">🎬</div>`
        : `<div class="poster-loading skeleton" id="loader-${item.torrent_id}" data-torrent-id="${item.torrent_id}"></div>`;

      let ratingBadges = '';
      if (item.kp_rating > 0 || item.imdb_rating > 0) {
        if (item.kp_rating > 0) ratingBadges += `<div class="badge-rating kp-badge" title="Кинопоиск">КП ${item.kp_rating}</div>`;
        if (item.imdb_rating > 0) ratingBadges += `<div class="badge-rating imdb-badge" title="IMDb">IMDb ${item.imdb_rating}</div>`;
      } else {
        ratingBadges = `<div class="badge-rating skeleton skeleton-field" title="Определение рейтинга..."></div>`;
      }

      const hasRealGenre = item.genre && item.genre !== 'Фильм' && item.genre !== 'Сериал';
      const genreHtml = hasRealGenre
        ? `<div class="card-genres">${item.genre}</div>`
        : `<div class="card-genres skeleton skeleton-field"></div>`;

      const countryHtml = item.country
        ? formatCountryBadge(item.country)
        : `<div class="card-country-box skeleton skeleton-field" style="margin-top: 4px;"></div>`;

      // Status badges for items in watchlist or ignored
      let statusBadgeHtml = '';
      if (item.user_status === 'watchlist' || item.user_status === 'watchlist_alt') {
        statusBadgeHtml = `<div class="card-status-badge badge-status-watchlist">💚 В списке «Буду смотреть»</div>`;
      } else if (item.user_status === 'ignored' || item.user_status === 'ignored_alt') {
        statusBadgeHtml = `<div class="card-status-badge badge-status-ignored">🚫 В списке «Не буду смотреть»</div>`;
      }

      let hoverActionsHtml = '';
      if (isWatchlist || item.user_status === 'watchlist' || item.user_status === 'watchlist_alt') {
        hoverActionsHtml = `
          <div class="card-hover-actions">
            <button class="btn-card-action btn-card-ignore" onclick="event.stopPropagation(); removeFromWatchlist('${item.torrent_id}')">
              ✕ Убрать из списка
            </button>
          </div>
        `;
      } else if (item.user_status === 'ignored' || item.user_status === 'ignored_alt') {
        hoverActionsHtml = `
          <div class="card-hover-actions">
            <button class="btn-card-action btn-card-watch" onclick="event.stopPropagation(); restoreFromIgnored('${item.torrent_id}')">
              ↩️ Вернуть в радар
            </button>
          </div>
        `;
      } else {
        hoverActionsHtml = `
          <div class="card-hover-actions">
            <button class="btn-card-action btn-card-watch" onclick="event.stopPropagation(); addToWatchlist('${item.torrent_id}', '${escapedTitle}')">
              💚 Буду смотреть
            </button>
            <button class="btn-card-action btn-card-ignore" onclick="event.stopPropagation(); addToIgnored('${item.torrent_id}', '${escapedTitle}')">
              🚫 Не буду смотреть
            </button>
          </div>
        `;
      }

      card.innerHTML = `
        <div class="poster-wrap">
          ${posterHtml}
          ${statusBadgeHtml}
          ${hoverActionsHtml}
          <div class="badge-quality">${item.quality || 'HD'}</div>
          <div class="card-ratings-wrap">${ratingBadges}</div>
        </div>
        <div class="card-content">
          <h3 class="card-title" title="${item.title}">${item.title_ru}</h3>
          <div class="card-orig">${item.title_en ? `${item.title_en} · ` : ''}${item.year || ''}</div>
          ${genreHtml}
          ${countryHtml}
          <div class="card-meta-row">
            <span class="card-size">${item.size_str || `${item.size_gb} GB`}</span>
            <div class="card-peers">
              <span class="seeds" title="Раздают (сиды)">▲ ${item.seeds}</span>
              <span class="peers" title="Качают (пиры)">▼ ${item.peers}</span>
            </div>
          </div>
        </div>
      `;
      cardsGrid.appendChild(card);
    });

    // Start live hydration for cards on the current page
    const candidateIds = items.map(it => it.torrent_id);
    startCardHydration(candidateIds);
  }

  window.repairPoster = function(imgElem, torrentId, titleRu, year, titleEn) {
    const nextElem = imgElem ? imgElem.nextElementSibling : null;
    if (nextElem) nextElem.style.display = 'flex';
    if (imgElem) imgElem.style.display = 'none';
  };

  // --- Poster Loading System ---
  function tryLoadPoster(torrentId, attempt) {
    const maxAttempts = 10;
    const loader = document.getElementById(`loader-${torrentId}`);
    if (!loader) return; // Card no longer in DOM

    // Create a test image to probe if poster is ready
    const testImg = new Image();
    testImg.onload = function() {
      // Poster is ready! Replace spinner with the image
      const img = document.createElement('img');
      img.className = 'poster-img poster-loaded';
      img.src = `/posters/${torrentId}.jpg`;
      img.alt = '';
      img.loading = 'lazy';
      loader.replaceWith(img);

      posterLoadDone++;
      updatePosterProgress(posterLoadDone, posterLoadTotal);
      delete posterRetryTimers[torrentId];

      // Fetch fresh metadata to update card genre, country, and ratings dynamically
      fetch(`/api/item?id=${torrentId}`)
        .then(res => res.json())
        .then(item => {
          if (!item || item.error) return;
          const card = document.getElementById(`card-${torrentId}`);
          if (!card) return;
          const genreEl = card.querySelector('.card-genres');
          if (genreEl && item.genre) {
            genreEl.textContent = item.genre;
          }
          if (item.country) {
            const countryEl = card.querySelector('.card-country-box');
            if (countryEl) {
              countryEl.outerHTML = formatCountryBadge(item.country);
            } else {
              const genreNode = card.querySelector('.card-genres');
              if (genreNode) {
                genreNode.insertAdjacentHTML('afterend', formatCountryBadge(item.country));
              }
            }
          }
          if (item.kp_rating > 0 || item.imdb_rating > 0) {
            const ratingsWrap = card.querySelector('.card-ratings-wrap');
            if (ratingsWrap) {
              let rHtml = '';
              if (item.kp_rating > 0) rHtml += `<div class="badge-rating kp-badge" title="Кинопоиск">КП ${item.kp_rating}</div>`;
              if (item.imdb_rating > 0) rHtml += `<div class="badge-rating imdb-badge" title="IMDb">IMDb ${item.imdb_rating}</div>`;
              ratingsWrap.innerHTML = rHtml;
            }
          }
        })
        .catch(() => {});
    };
    testImg.onerror = function() {
      if (attempt >= maxAttempts) {
        // Give up — show placeholder
        loader.innerHTML = '<span style="font-size:24px;">🎬</span><span class="spinner-text">Нет обложки</span>';
        loader.classList.remove('poster-loading');
        loader.classList.add('poster-placeholder');
        posterLoadDone++;
        updatePosterProgress(posterLoadDone, posterLoadTotal);
        delete posterRetryTimers[torrentId];
        return;
      }
      // Retry with increasing delay (2s, 3s, 4s, ...)
      const delay = 1500 + attempt * 1000;
      posterRetryTimers[torrentId] = setTimeout(() => {
        tryLoadPoster(torrentId, attempt + 1);
      }, delay);
    };
    // Cache-bust to avoid stale 404s
    testImg.src = `/posters/${torrentId}.jpg?t=${Date.now()}`;
  }

  function updatePosterProgress(loaded, total) {
    if (total === 0) return;
    const pct = Math.round((loaded / total) * 100);
    if (progressFill) {
      progressFill.style.width = `${pct}%`;
    }
    if (pct >= 100) {
      // Finished — keep bar visible briefly then fade out
      setTimeout(() => {
        progressBar.classList.remove('active');
        if (progressFill) progressFill.style.width = '0%';
      }, 800);
      consoleStatusText.textContent = `Все обложки загружены ✅`;
    } else {
      consoleStatusText.textContent = `Загрузка обложек: ${loaded}/${total} (${pct}%)`;
    }
  }

  function renderIgnoredTable(items) {
    if (!ignoredTableBody) return;
    ignoredTableBody.innerHTML = items.map(item => {
      let rHtml = '';
      if (item.kp_rating > 0) rHtml += `<span class="badge-rating kp-badge" style="position:static; margin-right:4px;">КП ${item.kp_rating}</span>`;
      if (item.imdb_rating > 0) rHtml += `<span class="badge-rating imdb-badge" style="position:static;">IMDb ${item.imdb_rating}</span>`;
      if (!rHtml) rHtml = '<span style="color:var(--text-muted);">—</span>';

      return `
        <tr id="row-ign-${item.torrent_id}">
          <td>
            <div class="table-title-main">${item.title_ru}</div>
            ${item.title_en ? `<div class="table-title-sub">${item.title_en}</div>` : ''}
          </td>
          <td><strong>${item.year || '—'}</strong></td>
          <td>${item.genre || '—'}</td>
          <td>${rHtml}</td>
          <td style="text-align: right;">
            <button class="btn-restore" onclick="restoreFromIgnored('${item.torrent_id}')">
              ↩️ Вернуть в радар
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  // Global actions for card hover and buttons
  window.addToWatchlist = function(torrentId, titleRu) {
    const cleanTitle = (titleRu || '').trim().toLowerCase();
    const cards = document.querySelectorAll('.media-card');
    cards.forEach(c => {
      if (c.id === `card-${torrentId}` || (cleanTitle && c.dataset.titleRu === cleanTitle)) {
        c.classList.add('card-removing');
        setTimeout(() => c.remove(), 260);
      }
    });
    fetch('/api/watchlist/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ torrent_id: torrentId })
    })
    .then(r => r.json())
    .then(() => updateCounts())
    .catch(() => {});
  };

  window.addToIgnored = function(torrentId, titleRu) {
    const cleanTitle = (titleRu || '').trim().toLowerCase();
    const cards = document.querySelectorAll('.media-card');
    cards.forEach(c => {
      if (c.id === `card-${torrentId}` || (cleanTitle && c.dataset.titleRu === cleanTitle)) {
        c.classList.add('card-removing');
        setTimeout(() => c.remove(), 260);
      }
    });
    fetch('/api/ignored/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ torrent_id: torrentId })
    })
    .then(r => r.json())
    .then(() => updateCounts())
    .catch(() => {});
  };

  window.removeFromWatchlist = function(torrentId) {
    const card = document.getElementById(`card-${torrentId}`);
    if (card) {
      card.classList.add('card-removing');
      setTimeout(() => card.remove(), 260);
    }
    fetch('/api/watchlist/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ torrent_id: torrentId })
    })
    .then(r => r.json())
    .then(() => updateCounts())
    .catch(() => {});
  };

  window.restoreFromIgnored = function(torrentId) {
    const row = document.getElementById(`row-ign-${torrentId}`);
    if (row) {
      row.style.opacity = '0';
      setTimeout(() => row.remove(), 250);
    }
    fetch('/api/ignored/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ torrent_id: torrentId })
    })
    .then(r => r.json())
    .then(() => updateCounts())
    .catch(() => {});
  };

  function openModal(torrentId) {
    modalOverlay.style.display = 'flex';
    modalContent.innerHTML = `
      <div class="modal-skeleton-layout">
        <div class="modal-skeleton-poster skeleton"></div>
        <div class="modal-skeleton-body">
          <div class="skeleton-line w-80 skeleton" style="height: 28px;"></div>
          <div class="skeleton-line w-40 skeleton" style="height: 18px;"></div>
          <div style="display: flex; gap: 8px; margin-top: 8px;">
            <div class="skeleton-line skeleton" style="width: 70px; height: 24px; border-radius: 6px;"></div>
            <div class="skeleton-line skeleton" style="width: 80px; height: 24px; border-radius: 6px;"></div>
            <div class="skeleton-line skeleton" style="width: 60px; height: 24px; border-radius: 6px;"></div>
          </div>
          <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 16px;">
            <div class="skeleton-line w-100 skeleton"></div>
            <div class="skeleton-line w-100 skeleton"></div>
            <div class="skeleton-line w-80 skeleton"></div>
            <div class="skeleton-line w-60 skeleton"></div>
          </div>
          <div style="display: flex; flex-direction: column; gap: 10px; margin-top: 20px;">
            <div class="skeleton-line w-100 skeleton" style="height: 36px; border-radius: 6px;"></div>
            <div class="skeleton-line w-100 skeleton" style="height: 36px; border-radius: 6px;"></div>
          </div>
        </div>
      </div>
    `;

    fetch(`/api/item?id=${torrentId}`)
      .then(res => res.json())
      .then(item => renderModalDetails(item))
      .catch(err => {
        modalContent.innerHTML = `<div style="color: #ef4444; padding: 40px;">Ошибка загрузки деталей: ${err.message}</div>`;
      });
  }

  function renderModalDetails(item) {
    // Also synchronize the background card in the grid if present
    const gridCard = document.getElementById(`card-${item.torrent_id}`);
    if (gridCard) {
      const gEl = gridCard.querySelector('.card-genres');
      if (gEl && item.genre) gEl.textContent = item.genre;
      if (item.country) {
        const cEl = gridCard.querySelector('.card-country-box');
        if (cEl) {
          cEl.outerHTML = formatCountryBadge(item.country);
        } else {
          const gNode = gridCard.querySelector('.card-genres');
          if (gNode) gNode.insertAdjacentHTML('afterend', formatCountryBadge(item.country));
        }
      }
      if (item.kp_rating > 0 || item.imdb_rating > 0) {
        const ratingsWrap = gridCard.querySelector('.card-ratings-wrap');
        if (ratingsWrap) {
          let rHtml = '';
          if (item.kp_rating > 0) rHtml += `<div class="badge-rating kp-badge" title="Кинопоиск">КП ${item.kp_rating}</div>`;
          if (item.imdb_rating > 0) rHtml += `<div class="badge-rating imdb-badge" title="IMDb">IMDb ${item.imdb_rating}</div>`;
          ratingsWrap.innerHTML = rHtml;
        }
      }
    }

    let audioTracksList = [];
    try {
      audioTracksList = typeof item.audio_tracks === 'string' ? JSON.parse(item.audio_tracks || '[]') : item.audio_tracks;
    } catch(e) {}

    let subsList = [];
    try {
      subsList = typeof item.subtitles === 'string' && item.subtitles.startsWith('[') ? JSON.parse(item.subtitles) : [item.subtitles];
    } catch(e) {}

    let seasonsList = [];
    try {
      seasonsList = typeof item.seasons_info === 'string' ? JSON.parse(item.seasons_info || '[]') : item.seasons_info;
    } catch(e) {}

    const audioTagsHtml = (audioTracksList && audioTracksList.length > 0)
      ? audioTracksList.map(t => `<div class="stream-tag" style="display: block; width: 100%; margin-bottom: 6px; padding: 6px 10px; font-size: 12px; line-height: 1.4; border-radius: 6px; background: rgba(0, 255, 204, 0.07); border: 1px solid rgba(0, 255, 204, 0.2);">🔊 ${t}</div>`).join('')
      : (item.audio_info 
          ? `<span class="stream-tag">${item.audio_info}</span>`
          : (item.voiceover ? '' : `<span class="stream-tag">Информация о звуке отсутствует</span>`));

    const subsTagsHtml = (subsList && subsList.length > 0 && subsList[0])
      ? subsList.map(s => `<span class="stream-tag" style="margin-right: 4px; margin-bottom: 4px; display: inline-block;">📄 ${s}</span>`).join('')
      : `<span class="stream-tag">Субтитры отсутствуют или не указаны</span>`;

    const seasonsBlockHtml = (state.category === 'series' && seasonsList && seasonsList.length > 0)
      ? `
        <div class="seasons-block">
          <h4>📺 ДРУГИЕ СЕЗОНЫ ЭТОГО СЕРИАЛА:</h4>
          <div class="tag-list">
            ${seasonsList.map(s => `
              <button class="season-btn" onclick="searchSeason('${s.search_query.replace(/'/g, "\\'")}')">
                🔍 ${s.season}
              </button>
            `).join('')}
          </div>
        </div>
      `
      : '';

    const alternativesHtml = (item.alternatives && item.alternatives.length > 0)
      ? `
        <div class="alternatives-box" style="margin-top: 14px; padding: 12px; background: rgba(0,255,204,0.06); border: 1px solid rgba(0,255,204,0.25); border-radius: 8px;">
          <h4 style="font-size: 13px; color: var(--accent); margin-bottom: 8px; font-weight: 600;">💾 ДРУГИЕ КАЧЕСТВА И РАЗДАЧИ ЭТОГО ТАЙТЛА (${item.alternatives.length}):</h4>
          <div style="display: flex; flex-direction: column; gap: 6px;">
            ${item.alternatives.map(alt => `
              <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); padding: 8px 12px; border-radius: 6px; font-size: 13px; border: 1px solid var(--border-color);">
                <div>
                  <span class="badge-quality" style="position:static; margin-right: 6px; display: inline-block;">${alt.quality || 'HD'}</span>
                  <strong>${alt.size_str}</strong>
                  <span style="color: var(--accent); margin-left: 8px;">▲ ${alt.seeds}</span>
                </div>
                <div style="display: flex; gap: 6px;">
                  <a href="${alt.torrent_url}" class="btn-download-torrent" style="padding: 4px 10px; font-size: 12px; text-decoration: none; border-radius: 4px;" target="_blank">⬇ .torrent</a>
                  ${alt.magnet_url ? `<a href="${alt.magnet_url}" class="btn-magnet" style="padding: 4px 8px; font-size: 12px; text-decoration: none; border-radius: 4px;">🧲</a>` : ''}
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `
      : '';

    modalContent.innerHTML = `
      <div class="modal-left">
        ${item.poster_url 
          ? `<img class="modal-poster" src="${item.poster_url}" alt="Постер" onerror="this.onerror=null; repairPoster(this, '${item.torrent_id}', '${(item.title_ru || '').replace(/'/g, "\\'")}', ${item.year || 0}, '${(item.title_en || '').replace(/'/g, "\\'")}');"/>` 
          : '<div class="poster-placeholder" style="border-radius:12px; height: 380px;">🎬</div>'}
        
        <!-- Modal Quick Actions -->
        <div style="display: flex; gap: 8px; margin: 10px 0;">
          <button class="btn-card-action btn-card-watch" style="flex:1;" onclick="addToWatchlist('${item.torrent_id}', '${(item.title_ru || '').replace(/'/g, "\\'")}'); closeModal();">
            💚 Буду смотреть
          </button>
          <button class="btn-card-action btn-card-ignore" style="flex:1;" onclick="addToIgnored('${item.torrent_id}', '${(item.title_ru || '').replace(/'/g, "\\'")}'); closeModal();">
            🚫 Не буду
          </button>
        </div>

        <a href="${item.torrent_url}" class="btn-download-torrent" target="_blank">
          ⬇ Скачать .torrent (${item.size_str || `${item.size_gb} GB`})
        </a>

        ${item.magnet_url ? `
          <a href="${item.magnet_url}" class="btn-magnet">
            🧲 Открыть Magnet-ссылку
          </a>
        ` : ''}

        <a href="${item.source_url}" class="link-tracker" target="_blank">
          🔗 Открыть раздачу на трекере
        </a>

        <div class="card-meta-row" style="background: var(--bg-card); padding: 12px; border-radius: 8px;">
          <span>Раздача:</span>
          <div class="card-peers">
            <span class="seeds">▲ ${item.seeds} сидов</span>
            <span class="peers">▼ ${item.peers} пиров</span>
          </div>
        </div>

        ${alternativesHtml}
      </div>

      <div class="modal-right">
        <div>
          <h2 class="modal-title-h2">${item.title_ru}</h2>
          <div class="modal-orig-sub">
            ${item.title_en ? `${item.title_en} · ` : ''}${item.year || ''}
          </div>
        </div>

        <div class="modal-ratings-row">
          ${item.kp_rating > 0 ? `<div class="rating-badge-lg kp-badge">Кинопоиск: ${item.kp_rating}</div>` : ''}
          ${item.imdb_rating > 0 ? `<div class="rating-badge-lg imdb-badge">IMDb: ${item.imdb_rating}</div>` : ''}
          ${item.quality ? `<div class="rating-badge-lg" style="background: var(--bg-card); border: 1px solid var(--border-color); color: #fff;">${item.quality}</div>` : ''}
        </div>

        <div class="audio-subs-box">
          <div class="audio-subs-item">
            <h4>🎧 АУДИОДОРОЖКИ И ОЗВУЧКА</h4>
            ${item.voiceover ? `
              <div style="margin-bottom: 10px; font-size: 13px;">
                ${item.voiceover.split(/;\s*/).filter(Boolean).map(v => `<div style="margin-bottom: 4px; color: var(--text-main);"><strong style="color: var(--accent);">🎙️</strong> ${v}</div>`).join('')}
              </div>
            ` : ''}
            <div class="tag-list">${audioTagsHtml}</div>
          </div>

          <div class="audio-subs-item">
            <h4>📝 СУБТИТРЫ</h4>
            <div class="tag-list">${subsTagsHtml}</div>
          </div>
        </div>

        ${seasonsBlockHtml}

        <div class="detail-info-table">
          ${item.genre ? `<div class="detail-row"><span class="detail-label">Жанр:</span><span class="detail-value">${item.genre}</span></div>` : ''}
          ${item.director ? `<div class="detail-row"><span class="detail-label">Режиссёр:</span><span class="detail-value">${item.director}</span></div>` : ''}
          ${item.actors ? `<div class="detail-row"><span class="detail-label">В ролях:</span><span class="detail-value">${item.actors}</span></div>` : ''}
          ${item.country ? `<div class="detail-row"><span class="detail-label">Страна / Студия:</span><span class="detail-value">${item.country}</span></div>` : ''}
          ${item.duration ? `<div class="detail-row"><span class="detail-label">Хронометраж:</span><span class="detail-value">${item.duration}</span></div>` : ''}
          ${item.video_info ? `<div class="detail-row"><span class="detail-label">Видео:</span><span class="detail-value font-mono">${item.video_info}</span></div>` : ''}
          <div class="detail-row"><span class="detail-label">Дата добавления:</span><span class="detail-value">${item.date_added}</span></div>
        </div>

        ${item.description ? `
          <div style="margin-top: 8px;">
            <h4 style="font-size: 14px; margin-bottom: 6px; color: var(--accent);">ОПИСАНИЕ СЮЖЕТА:</h4>
            <p class="synopsis-text">${item.description}</p>
          </div>
        ` : ''}
      </div>
    `;
  }

  window.searchSeason = function(query) {
    closeModal();
    searchInput.value = query;
    state.search = query;
    state.page = 1;
    fetchReleases();
  };

  function closeModal() {
    modalOverlay.style.display = 'none';
  }

  function loadGenres() {
    fetch(`/api/genres?category=${state.category}`)
      .then(res => res.json())
      .then(data => {
        genreSelect.innerHTML = '<option value="all">Все жанры</option>';
        data.genres.forEach(g => {
          const opt = document.createElement('option');
          opt.value = g;
          opt.textContent = g;
          if (g === state.genre) opt.selected = true;
          genreSelect.appendChild(opt);
        });
      })
      .catch(() => {});
  }

  function pollLogs() {
    fetch('/api/logs')
      .then(res => res.json())
      .then(data => {
        if (!data.logs) return;
        consoleLogFeed.innerHTML = data.logs.map(l => `
          <div class="log-entry">
            <span class="log-time">[${l.time}]</span>
            <span class="log-level-${l.level}">[${l.level}]</span>
            <span class="log-msg">${escapeHtml(l.msg)}</span>
          </div>
        `).join('');
        consoleLogFeed.scrollTop = consoleLogFeed.scrollHeight;
      })
      .catch(() => {});
  }

  // Heartbeat to keep server running while browser window is open
  function sendHeartbeat() {
    fetch('/api/heartbeat', { method: 'POST' }).catch(() => {});
  }
  sendHeartbeat();
  setInterval(sendHeartbeat, 2500);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) sendHeartbeat();
  });

  // Notify server when window is closing so process can exit cleanly
  window.addEventListener('beforeunload', () => {
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/browser_closing');
    } else {
      fetch('/api/browser_closing', { method: 'POST', keepalive: true }).catch(() => {});
    }
  });
});

// RADAR Application Controller — Multi-Category Release Acquisition & Discovery Engine

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[m]);
}

document.addEventListener('DOMContentLoaded', () => {
  const state = {
    category: 'movies', // 'movies', 'series', 'anime', 'games', 'software'
    view: 'catalog',    // 'catalog', 'watchlist', 'ignored'
    curationSubcategory: 'all',
    year: 'all',
    min_rating: 0.0,
    max_size: 999.0,
    qualities: ['1080p', '720p'],
    genre: 'all',
    origin: 'foreign',
    search: '',
    page: 1,
    limit: 15,
    totalPages: 1,
    // Series-specific
    streaming: 'all',
    voiceover: 'all',
    ongoing: 'all',     // 'all', 'finished', 'ongoing'
    // Anime-specific
    anime_type: 'all',
    has_subtitles: false,
    // Games-specific
    repack_author: 'all',
    release_format: 'all',
    crack_status: 'all',
    // Software-specific
    software_category: 'all'
  };

  // Dictionaries for dynamic filter options
  const STREAMING_PLATFORMS = [
    'all', 'Netflix', 'HBO / Max', 'Apple TV+', 'Amazon Prime', 'Disney+',
    'Кинопоиск', 'Иви', 'START', 'Premier', 'Okko', 'Wink', 'AMC', 'Hulu',
    'Paramount+', 'Showtime', 'BBC'
  ];

  const SERIES_VOICEOVERS = [
    'all', 'LostFilm', 'HDRezka', 'NewStudio', 'Кубик в кубе', 'TVShows',
    'AlexFilm', 'Пифагор', 'Дубликат', 'Red Head Sound', 'Flarrow Films'
  ];

  const ANIME_TYPES = [
    'all', 'TV-сериал', 'Полнометражный фильм'
  ];

  const ANIME_STUDIOS = [
    'all', 'AniLibria', 'Studio Band', 'AniDUB', 'SHIZA Project',
    'Dream Cast', 'AnimeVost', 'Persona99', 'СВ-Дубль'
  ];

  const GAME_REPACKERS = [
    'all', 'FitGirl', 'DODI', 'Decepticon', 'Choo-Choo', 'ElAmigos', 'GOG', 'Scene / P2P', 'Portable'
  ];

  const GAME_FORMATS = [
    'all', 'RePack', 'Лицензия / Scene', 'Portable', 'Early Access', 'VR'
  ];

  const GAME_CRACKS = [
    'all', 'Вшито', 'Не требуется (DRM-Free)', 'Таблетка отдельно'
  ];

  const GAME_GENRES = [
    'all', 'RPG', 'Экшен', 'Приключения', 'Стратегия', 'Симулятор', 'Хоррор', 'Шутер', 'Гонки', 'Инди'
  ];

  const SOFT_CATEGORIES = [
    'all', 'Графика и дизайн', 'Видеомонтаж и 3D', 'Аудио и звук', 'Офис и текст',
    'Система и безопасность', 'Разработка и утилиты', 'Сети и интернет'
  ];

  const SOFT_FORMATS = [
    'all', 'Установщик (RePack)', 'Портативная (Portable)', 'Образ (ISO)'
  ];

  const SOFT_AUTHORS = [
    'all', 'KpoJIuK', 'elchupacabra', 'D!akov', 'TryRooM', 'm0nkrus', 'SanLex'
  ];

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
  const filtersContainer = document.getElementById('filters-container');
  const modalOverlay = document.getElementById('detail-modal');
  const modalContent = document.getElementById('modal-content');
  const modalClose = document.getElementById('modal-close');
  const consoleLogFeed = document.getElementById('console-log-feed');
  const consoleToggle = document.getElementById('console-toggle');
  const consoleStatusText = document.getElementById('console-status-text');
  const consoleMinimizeBtn = document.getElementById('console-minimize-btn');
  const debugConsole = document.getElementById('debug-console');
  const progressFill = document.getElementById('progress-fill');

  function getCategoryTitle(cat) {
    const map = {
      movies: 'Фильмы',
      series: 'Сериалы',
      anime: 'Аниме',
      games: 'Игры',
      software: 'Программы'
    };
    return map[cat] || cat;
  }

  // Initialize
  initEventListeners();
  renderCategoryToolbar();
  updateCounts();

  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has('category')) {
    const c = urlParams.get('category');
    if (['movies', 'series', 'anime', 'games', 'software'].includes(c)) {
      state.category = c;
    }
  }
  if (urlParams.has('view')) {
    const v = urlParams.get('view');
    if (['catalog', 'watchlist', 'ignored'].includes(v)) {
      state.view = v;
    }
  }
  if (urlParams.has('search')) {
    state.search = urlParams.get('search');
  }
  if (urlParams.has('page')) {
    state.page = parseInt(urlParams.get('page')) || 1;
  }
  if (urlParams.has('modal')) {
    setTimeout(() => openModal(urlParams.get('modal')), 700);
  }

  updateTabsUI();
  renderCategoryToolbar();
  loadYearsAndGenres().finally(() => {
    fetchReleases();
  });

  pollLogs();
  setInterval(pollLogs, 2500);
  setInterval(updateCounts, 6000);

  function initEventListeners() {
    // Category & List Tabs
    document.querySelectorAll('.cat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const catKey = btn.dataset.category;
        if (catKey === 'watchlist') {
          state.view = 'watchlist';
          state.curationSubcategory = 'all';
        } else if (catKey === 'ignored') {
          state.view = 'ignored';
          state.curationSubcategory = 'all';
        } else {
          state.category = catKey;
          state.view = 'catalog';
        }
        state.page = 1;
        state.search = '';

        updateTabsUI();
        renderCategoryToolbar();
        updateCounts();

        if (state.view === 'catalog') {
          loadYearsAndGenres();
        }
        fetchReleases();
      });
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
      const isDiscovery = (state.view === 'catalog') && !state.search;
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

  function updateTabsUI() {
    document.querySelectorAll('.cat-btn').forEach(btn => {
      btn.classList.remove('active');
      const catKey = btn.dataset.category;
      if (state.view === 'watchlist' && catKey === 'watchlist') {
        btn.classList.add('active');
      } else if (state.view === 'ignored' && catKey === 'ignored') {
        btn.classList.add('active');
      } else if (state.view === 'catalog' && catKey === state.category) {
        btn.classList.add('active');
      }
    });
  }

  // -------------------------------------------------------------
  // Dynamic Category Filters Toolbar — Two Stable Rows
  // -------------------------------------------------------------
  function renderCategoryToolbar() {
    if (!filtersContainer) return;

    if (state.view === 'watchlist' || state.view === 'ignored') {
      const isWatch = state.view === 'watchlist';
      const label = isWatch ? 'Заинтересовало' : 'Хрень';
      filtersContainer.innerHTML = `
        <div class="toolbar-row toolbar-row-primary">
          <div class="filter-group search-group" style="flex: 2; max-width: 460px;">
            <span class="filter-icon">🔍</span>
            <input type="text" id="search-input" placeholder="Поиск в «${label}»..." value="${escapeHtml(state.search)}" />
          </div>
          <button id="btn-apply-filters" class="btn-primary btn-apply" title="Искать">🔍 Найти</button>
          <button id="btn-reset-filters" class="btn-reset" title="Сбросить поиск">✕ Сброс</button>
        </div>
        <div class="toolbar-row toolbar-row-secondary">
          <div class="subtabs-nav" id="subtabs-nav">
            <button class="subtab-btn ${state.curationSubcategory === 'all' ? 'active' : ''}" data-subcat="all">Все <span class="subtab-count" id="subtab-count-all"></span></button>
            <button class="subtab-btn ${state.curationSubcategory === 'movies' ? 'active' : ''}" data-subcat="movies">Фильмы <span class="subtab-count" id="subtab-count-movies"></span></button>
            <button class="subtab-btn ${state.curationSubcategory === 'series' ? 'active' : ''}" data-subcat="series">Сериалы <span class="subtab-count" id="subtab-count-series"></span></button>
            <button class="subtab-btn ${state.curationSubcategory === 'anime' ? 'active' : ''}" data-subcat="anime">Аниме <span class="subtab-count" id="subtab-count-anime"></span></button>
            <button class="subtab-btn ${state.curationSubcategory === 'games' ? 'active' : ''}" data-subcat="games">Игры <span class="subtab-count" id="subtab-count-games"></span></button>
            <button class="subtab-btn ${state.curationSubcategory === 'software' ? 'active' : ''}" data-subcat="software">Программы <span class="subtab-count" id="subtab-count-software"></span></button>
          </div>
        </div>
      `;
      bindToolbarEvents();
      updateCounts();
      return;
    }

    const cat = state.category;

    // Build Row 1: Common primary controls
    let row1 = `
      <button id="btn-refresh" class="btn-refresh" title="Сканировать трекер и обновить базу данных">
        <span class="refresh-icon">🔄</span> Сканировать трекер
      </button>
      <div class="filter-group search-group">
        <span class="filter-icon">🔍</span>
        <input type="text" id="search-input" placeholder="${getSearchPlaceholder(cat)}" value="${escapeHtml(state.search)}" />
      </div>
      <button id="btn-apply-filters" class="btn-primary btn-apply" title="Применить выбранные фильтры и начать поиск">🔍 Найти</button>
    `;

    // Row 1 Qualities
    if (cat === 'movies') {
      row1 += `
        <div class="filter-group quality-group">
          <label>Качество:</label>
          <label class="checkbox-label"><input type="checkbox" id="q-less720p" ${state.qualities.includes('<720p') ? 'checked' : ''} value="<720p">&lt; 720p</label>
          <label class="checkbox-label"><input type="checkbox" id="q-720p" ${state.qualities.includes('720p') ? 'checked' : ''} value="720p">720p</label>
          <label class="checkbox-label"><input type="checkbox" id="q-1080p" ${state.qualities.includes('1080p') ? 'checked' : ''} value="1080p">1080p</label>
        </div>
      `;
    } else if (cat === 'series') {
      // Quality filter removed for series: qualities are selected per-release in the season tabs
      row1 += '';
    } else if (cat === 'anime') {
      row1 += `
        <div class="filter-group quality-group">
          <label>Качество:</label>
          <label class="checkbox-label"><input type="checkbox" id="q-less720p" ${state.qualities.includes('<720p') ? 'checked' : ''} value="<720p">&lt; 720p</label>
          <label class="checkbox-label"><input type="checkbox" id="q-720p" ${state.qualities.includes('720p') ? 'checked' : ''} value="720p">720p</label>
          <label class="checkbox-label"><input type="checkbox" id="q-1080p" ${state.qualities.includes('1080p') ? 'checked' : ''} value="1080p">1080p</label>
        </div>
      `;
    }

    // Row 1 Ratings
    if (cat === 'movies') {
      row1 += `
        <div class="filter-group rating-group">
          <label class="checkbox-label">
            <input type="checkbox" id="rating-toggle" ${state.min_rating > 0 ? 'checked' : ''}>
            <span>⭐ Рейтинг &gt; 7.0</span>
          </label>
        </div>
      `;
    } else if (cat === 'series') {
      row1 += `
        <div class="filter-group rating-group">
          <label class="checkbox-label">
            <input type="checkbox" id="rating-toggle" ${state.min_rating > 0 ? 'checked' : ''}>
            <span>⭐ Рейтинг &gt; 8.0</span>
          </label>
        </div>
      `;
    } else if (cat === 'anime') {
      row1 += `
        <div class="filter-group rating-group">
          <label class="checkbox-label">
            <input type="checkbox" id="rating-toggle" ${state.min_rating > 0 ? 'checked' : ''}>
            <span>⭐ Shiki/MAL &gt; 8.0</span>
          </label>
        </div>
      `;
    } else if (cat === 'games') {
      row1 += `
        <div class="filter-group rating-group">
          <label class="checkbox-label">
            <input type="checkbox" id="rating-toggle" ${state.min_rating > 0 ? 'checked' : ''}>
            <span>⭐ Рейтинг &gt; 75 (MC / OC / Steam)</span>
          </label>
        </div>
      `;
    }

    // Row 1 Year & Genre dropdowns
    if (['movies', 'series', 'anime'].includes(cat)) {
      row1 += `
        <div class="filter-group year-group">
          <label for="year-select">Год:</label>
          <select id="year-select"><option value="all">Все годы</option></select>
        </div>
        <div class="filter-group genre-group">
          <label for="genre-select">Жанр:</label>
          <select id="genre-select"><option value="all">Все жанры</option></select>
        </div>
      `;
    } else if (cat === 'games') {
      row1 += `
        <div class="filter-group">
          <label for="games-genre-select">Жанр:</label>
          <select id="games-genre-select">
            ${GAME_GENRES.map(g => `<option value="${g}" ${state.genre === g ? 'selected' : ''}>${g === 'all' ? 'Все жанры' : g}</option>`).join('')}
          </select>
        </div>
      `;
    }

    row1 += `
      <button id="btn-reset-filters" class="btn-reset" title="Сбросить все фильтры на стандартные">✕ Сброс</button>
    `;

    // Build Row 2: Category-specific controls
    let row2 = '';
    if (cat === 'movies') {
      row2 = `
        <div class="filter-group russian-group">
          <label class="checkbox-label">
            <input type="checkbox" id="russian-toggle" ${state.origin === 'russian' ? 'checked' : ''}>
            <span>Русское</span>
          </label>
        </div>
      `;
    } else if (cat === 'series') {
      row2 = `
        <div class="filter-group russian-group">
          <label class="checkbox-label">
            <input type="checkbox" id="russian-toggle" ${state.origin === 'russian' ? 'checked' : ''}>
            <span>Русское</span>
          </label>
        </div>
        <div class="filter-group">
          <label for="series-ongoing-select">Статус:</label>
          <select id="series-ongoing-select">
            <option value="all" ${state.ongoing === 'all' ? 'selected' : ''}>Все сериалы</option>
            <option value="finished" ${state.ongoing === 'finished' ? 'selected' : ''}>Только завершённые</option>
            <option value="ongoing" ${state.ongoing === 'ongoing' ? 'selected' : ''}>Онгоинги</option>
          </select>
        </div>
        <div class="filter-group">
          <label for="series-streaming-select">Стриминг:</label>
          <select id="series-streaming-select">
            ${STREAMING_PLATFORMS.map(p => `<option value="${p}" ${state.streaming === p ? 'selected' : ''}>${p === 'all' ? 'Все платформы' : p}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label for="series-voice-select">Озвучка:</label>
          <select id="series-voice-select">
            ${SERIES_VOICEOVERS.map(v => `<option value="${v}" ${state.voiceover === v ? 'selected' : ''}>${v === 'all' ? 'Все студии' : v}</option>`).join('')}
          </select>
        </div>
      `;
    } else if (cat === 'anime') {
      row2 = `
        <div class="filter-group">
          <label for="anime-type-select">Тип:</label>
          <select id="anime-type-select">
            ${ANIME_TYPES.map(t => `<option value="${t}" ${state.anime_type === t ? 'selected' : ''}>${t === 'all' ? 'Все типы' : t}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label for="anime-studio-select">Озвучка:</label>
          <select id="anime-studio-select">
            ${ANIME_STUDIOS.map(s => `<option value="${s}" ${state.voiceover === s ? 'selected' : ''}>${s === 'all' ? 'Все студии' : s}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label class="checkbox-label">
            <input type="checkbox" id="subtitles-toggle" ${state.has_subtitles ? 'checked' : ''}>
            <span>Субтитры</span>
          </label>
        </div>
      `;
    } else if (cat === 'games') {
      row2 = `
        <div class="filter-group">
          <label for="games-repacker-select">Репакер:</label>
          <select id="games-repacker-select">
            ${GAME_REPACKERS.map(r => `<option value="${r}" ${state.repack_author === r ? 'selected' : ''}>${r === 'all' ? 'Все авторы' : r}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label for="games-format-select">Формат:</label>
          <select id="games-format-select">
            ${GAME_FORMATS.map(f => `<option value="${f}" ${state.release_format === f ? 'selected' : ''}>${f === 'all' ? 'Все форматы' : f}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label for="games-crack-select">Таблетка:</label>
          <select id="games-crack-select">
            ${GAME_CRACKS.map(c => `<option value="${c}" ${state.crack_status === c ? 'selected' : ''}>${c === 'all' ? 'Все статусы' : c}</option>`).join('')}
          </select>
        </div>
      `;
    } else if (cat === 'software') {
      row2 = `
        <div class="filter-group">
          <label for="soft-cat-select">Категория:</label>
          <select id="soft-cat-select">
            ${SOFT_CATEGORIES.map(c => `<option value="${c}" ${state.software_category === c ? 'selected' : ''}>${c === 'all' ? 'Все категории' : c}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label for="soft-format-select">Формат:</label>
          <select id="soft-format-select">
            ${SOFT_FORMATS.map(f => `<option value="${f}" ${state.release_format === f ? 'selected' : ''}>${f === 'all' ? 'Все форматы' : f}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label for="soft-author-select">Автор сборки:</label>
          <select id="soft-author-select">
            ${SOFT_AUTHORS.map(a => `<option value="${a}" ${state.repack_author === a ? 'selected' : ''}>${a === 'all' ? 'Все авторы' : a}</option>`).join('')}
          </select>
        </div>
      `;
    }

    filtersContainer.innerHTML = `
      <div class="toolbar-row toolbar-row-primary">${row1}</div>
      ${row2 ? `<div class="toolbar-row toolbar-row-secondary">${row2}</div>` : ''}
    `;

    bindToolbarEvents();
  }

  function getSearchPlaceholder(category) {
    if (category === 'games') return 'Поиск игры по названию';
    if (category === 'software') return 'Поиск программы по названию или версии';
    if (category === 'anime') return 'Поиск аниме (рус / ромадзи)';
    if (category === 'series') return 'Поиск сериала по названию';
    return 'Поиск фильма по названию';
  }

  function bindToolbarEvents() {
    const searchInput = document.getElementById('search-input');
    const btnApply = document.getElementById('btn-apply-filters');
    const btnReset = document.getElementById('btn-reset-filters');
    const btnRefresh = document.getElementById('btn-refresh');

    if (searchInput) {
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          applyFilters();
        }
      });
    }

    if (btnApply) {
      btnApply.addEventListener('click', applyFilters);
    }

    if (btnReset) {
      btnReset.addEventListener('click', resetFilters);
    }

    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => {
        btnRefresh.classList.add('loading');
        const cat = state.category;
        const yearInfo = (['movies', 'series', 'anime'].includes(cat)) ? ` (${state.year})` : '';
        consoleStatusText.textContent = `Сканирование трекера [${getCategoryTitle(cat)}]${yearInfo}...`;
        fetch('/api/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category: cat, year: state.year })
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
    }

    // Subcategory switcher buttons for Watchlist and Ignored
    document.querySelectorAll('.subtab-btn').forEach(b => {
      b.addEventListener('click', () => {
        state.curationSubcategory = b.dataset.subcat || 'all';
        document.querySelectorAll('.subtab-btn').forEach(btn => btn.classList.remove('active'));
        b.classList.add('active');
        state.page = 1;
        fetchReleases();
      });
    });

    // NOTE: Checkboxes and dropdowns intentionally do NOT auto-submit on change.
    // The user MUST click "Найти" or press Enter in search to apply filters!
  }

  function applyFilters() {
    const searchInput = document.getElementById('search-input');
    if (searchInput) state.search = searchInput.value.trim();

    // Qualities
    const activeQualities = [];
    if (document.getElementById('q-less720p')?.checked) activeQualities.push('<720p');
    if (document.getElementById('q-720p')?.checked) activeQualities.push('720p');
    if (document.getElementById('q-1080p')?.checked) activeQualities.push('1080p');
    if (document.getElementById('q-4k')?.checked) activeQualities.push('4K');
    state.qualities = activeQualities;

    // Rating
    const ratingToggle = document.getElementById('rating-toggle');
    if (ratingToggle) {
      if (ratingToggle.checked) {
        state.min_rating = (state.category === 'games') ? 75.0 : ((state.category === 'movies') ? 7.0 : 8.0);
      } else {
        state.min_rating = 0.0;
      }
    }

    // Russian / Origin
    const russianToggle = document.getElementById('russian-toggle');
    if (russianToggle) {
      state.origin = russianToggle.checked ? 'russian' : 'foreign';
    }

    // Year & Genre
    const yearSelect = document.getElementById('year-select');
    if (yearSelect) state.year = yearSelect.value;

    const genreSelect = document.getElementById('genre-select') || document.getElementById('games-genre-select');
    if (genreSelect) state.genre = genreSelect.value;

    // Series
    const seriesOngoing = document.getElementById('series-ongoing-select');
    if (seriesOngoing) state.ongoing = seriesOngoing.value;

    const seriesStreaming = document.getElementById('series-streaming-select');
    if (seriesStreaming) state.streaming = seriesStreaming.value;

    const seriesVoice = document.getElementById('series-voice-select');
    if (seriesVoice) state.voiceover = seriesVoice.value;

    // Anime
    const animeType = document.getElementById('anime-type-select');
    if (animeType) state.anime_type = animeType.value;

    const animeStudio = document.getElementById('anime-studio-select');
    if (animeStudio) state.voiceover = animeStudio.value;

    const subToggle = document.getElementById('subtitles-toggle');
    if (subToggle) state.has_subtitles = subToggle.checked;

    // Games
    const gameRepacker = document.getElementById('games-repacker-select');
    if (gameRepacker) state.repack_author = gameRepacker.value;

    const gameFormat = document.getElementById('games-format-select');
    if (gameFormat) state.release_format = gameFormat.value;

    const gameCrack = document.getElementById('games-crack-select');
    if (gameCrack) state.crack_status = gameCrack.value;

    // Software
    const softCat = document.getElementById('soft-cat-select');
    if (softCat) state.software_category = softCat.value;

    const softFormat = document.getElementById('soft-format-select');
    if (softFormat) state.release_format = softFormat.value;

    const softAuthor = document.getElementById('soft-author-select');
    if (softAuthor) state.repack_author = softAuthor.value;

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

    state.streaming = 'all';
    state.voiceover = 'all';
    state.ongoing = 'all';
    state.anime_type = 'all';
    state.has_subtitles = false;
    state.repack_author = 'all';
    state.release_format = 'all';
    state.crack_status = 'all';
    state.software_category = 'all';
    state.curationSubcategory = 'all';

    renderCategoryToolbar();
    loadYearsAndGenres().finally(() => {
      fetchReleases();
    });
  }
  window.resetFilters = resetFilters;

  function updateCounts() {
    fetch(`/api/counts?category=${state.category}`)
      .then(res => res.json())
      .then(counts => {
        if (countWatchlist) countWatchlist.textContent = counts.watchlist || 0;
        if (countIgnored) countIgnored.textContent = counts.ignored || 0;

        if (counts.by_category) {
          const isWatch = state.view === 'watchlist';
          const type = isWatch ? 'watchlist' : 'ignored';
          let totalSum = 0;
          Object.keys(counts.by_category).forEach(cat => {
            const cnt = counts.by_category[cat][type] || 0;
            totalSum += cnt;
            const el = document.getElementById(`subtab-count-${cat}`);
            if (el) el.textContent = `(${cnt})`;
          });
          const allEl = document.getElementById('subtab-count-all');
          if (allEl) allEl.textContent = `(${totalSum})`;
        }
      })
      .catch(() => {});
  }
  function loadYearsAndGenres() {
    const cat = state.category;
    if (!['movies', 'series', 'anime'].includes(cat)) {
      return Promise.resolve();
    }

    const yearPromise = fetch(`/api/years?category=${cat}`)
      .then(res => res.json())
      .then(data => {
        const yearSelect = document.getElementById('year-select');
        if (!data.years || !yearSelect) return;
        const currentYear = state.year || 'all';
        yearSelect.innerHTML = '<option value="all">Все годы</option>';

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
          if (opt.value === currentYear) opt.selected = true;
          yearSelect.appendChild(opt);
        });
      })
      .catch(() => {});

    const genrePromise = fetch(`/api/genres?category=${cat}`)
      .then(res => res.json())
      .then(data => {
        const genreSelect = document.getElementById('genre-select');
        if (!data.genres || !genreSelect) return;
        const currentGenre = state.genre || 'all';
        genreSelect.innerHTML = '<option value="all">Все жанры</option>';

        data.genres.forEach(g => {
          const opt = document.createElement('option');
          opt.value = g;
          opt.textContent = g;
          if (g === currentGenre) opt.selected = true;
          genreSelect.appendChild(opt);
        });
      })
      .catch(() => {});

    return Promise.all([yearPromise, genrePromise]);
  }

  // -------------------------------------------------------------
  // Data Fetching & Views Router
  // -------------------------------------------------------------
  function fetchReleases(isSilent = false) {
    updateCounts();
    if (progressBar) progressBar.classList.add('active');

    const catTitle = getCategoryTitle(state.category);

    // 1. "Хрень" (Ignored Compact Table View)
    if (state.view === 'ignored') {
      cardsGrid.style.display = 'none';
      tableViewContainer.style.display = 'block';

      const curSubcat = state.curationSubcategory || 'all';
      const catTitle = curSubcat === 'all' ? 'Все категории' : getCategoryTitle(curSubcat);

      const p = new URLSearchParams({
        category: curSubcat,
        search: state.search,
        page: state.page,
        limit: state.limit
      });

      fetch(`/api/ignored?${p.toString()}`)
        .then(res => res.json())
        .then(data => {
          renderIgnoredTable(data.items);
          state.totalPages = data.pages || 1;
          currentPageSpan.textContent = data.page;
          totalPagesSpan.textContent = data.pages || 1;
          resultsCount.textContent = `В списке «Хрень» (${catTitle}): ${data.total} (показано ${data.items.length})`;
          btnPrev.disabled = data.page <= 1;
          btnNext.disabled = data.page >= data.pages;

          if (data.total === 0) {
            tableViewContainer.style.display = 'none';
            emptyState.style.display = 'block';
            emptyState.querySelector('.empty-text').textContent = `В списке «Хрень» (${catTitle}) пока пусто`;
          } else {
            emptyState.style.display = 'none';
          }
          consoleStatusText.textContent = `Список «Хрень» [${catTitle}]: ${data.total} позиций`;
        })
        .catch(err => {
          tableViewContainer.innerHTML = `<div style="color: #ef4444; padding: 20px;">Ошибка: ${err.message}</div>`;
        })
        .finally(() => {
          if (progressBar) progressBar.classList.remove('active');
        });
      return;
    }

    // 2. "Заинтересовало" (Watchlist Grid View)
    if (state.view === 'watchlist') {
      cardsGrid.style.display = 'grid';
      tableViewContainer.style.display = 'none';

      const curSubcat = state.curationSubcategory || 'all';
      const catTitle = curSubcat === 'all' ? 'Все категории' : getCategoryTitle(curSubcat);

      const p = new URLSearchParams({
        category: curSubcat,
        search: state.search,
        page: state.page,
        limit: state.limit
      });

      fetch(`/api/watchlist?${p.toString()}`)
        .then(res => res.json())
        .then(data => {
          renderCards(data.items, true);
          state.totalPages = data.pages || 1;
          currentPageSpan.textContent = data.page;
          totalPagesSpan.textContent = data.pages || 1;
          resultsCount.textContent = `В списке «Заинтересовало» (${catTitle}): ${data.total} (показано ${data.items.length})`;
          btnPrev.disabled = data.page <= 1;
          btnNext.disabled = data.page >= data.pages;

          if (data.total === 0) {
            cardsGrid.style.display = 'none';
            emptyState.style.display = 'block';
            emptyState.querySelector('.empty-text').textContent = `В списке «Заинтересовало» (${catTitle}) пока пусто`;
          } else {
            cardsGrid.style.display = 'grid';
            emptyState.style.display = 'none';
          }
          consoleStatusText.textContent = `Заинтересовало [${catTitle}]: ${data.total} отобранных релизов`;
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
      renderSkeletonGrid(state.limit || 15);
      const yearInfo = (['movies', 'series', 'anime'].includes(state.category)) ? ` (${state.year === 'all' ? 'все годы' : state.year})` : '';
      consoleStatusText.textContent = `Запрос релизов [${catTitle}${yearInfo}], стр. ${state.page}...`;
    }

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

    if (state.qualities && state.qualities.length > 0) {
      params.append('quality', state.qualities.join(','));
    }
    if (state.streaming && state.streaming !== 'all') {
      params.append('streaming', state.streaming);
    }
    if (state.voiceover && state.voiceover !== 'all') {
      params.append('voiceover', state.voiceover);
    }
    if (state.ongoing && state.ongoing !== 'all') {
      params.append('ongoing', state.ongoing);
    }
    if (state.has_subtitles) {
      params.append('has_subtitles', '1');
    }
    if (state.anime_type && state.anime_type !== 'all') {
      params.append('anime_type', state.anime_type);
    }
    if (state.repack_author && state.repack_author !== 'all') {
      params.append('repack_author', state.repack_author);
    }
    if (state.release_format && state.release_format !== 'all') {
      params.append('release_format', state.release_format);
    }
    if (state.crack_status && state.crack_status !== 'all') {
      params.append('crack_status', state.crack_status);
    }
    if (state.software_category && state.software_category !== 'all') {
      params.append('software_category', state.software_category);
    }

    fetch(`/api/items?${params.toString()}`)
      .then(res => res.json())
      .then(data => {
        renderCards(data.items, false);
        const isDiscovery = (state.view === 'catalog') && !state.search;
        state.totalPages = isDiscovery ? Math.max(data.pages || 1, data.page + 1) : (data.pages || 1);
        currentPageSpan.textContent = data.page;
        totalPagesSpan.textContent = state.totalPages;
        resultsCount.textContent = `Найдено на радаре (${catTitle}): ${data.total} (показано ${data.items.length})`;

        btnPrev.disabled = data.page <= 1;
        btnNext.disabled = isDiscovery ? (data.items.length === 0) : (data.page >= state.totalPages);

        if (data.total === 0 && data.items.length === 0) {
          cardsGrid.style.display = 'none';
          emptyState.style.display = 'block';
          emptyState.querySelector('.empty-text').textContent = 'По вашему запросу ничего не найдено';
        } else {
          cardsGrid.style.display = 'grid';
          emptyState.style.display = 'none';
        }
        consoleStatusText.textContent = `Каталог [${catTitle}]: ${data.total} релизов (${state.year === 'all' ? 'все годы' : `${state.year} г.`}, стр. ${data.page})`;
      })
      .catch(err => {
        if (!isSilent) {
          cardsGrid.innerHTML = `<div style="grid-column: 1/-1; color: #ef4444; padding: 40px; text-align: center;">Ошибка загрузки данных: ${err.message}</div>`;
        }
      })
      .finally(() => {
        if (progressBar) progressBar.classList.remove('active');
      });
  }

  function formatCountryBadge(countryStr) {
    if (!countryStr || typeof countryStr !== 'string') return '';
    const clean = countryStr.split(/[,/|;]/)[0].trim();
    if (!clean) return '';
    return `
      <div class="card-country-box">
        <span class="card-country-text" title="${escapeHtml(countryStr)}">${escapeHtml(clean)}</span>
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

  // -------------------------------------------------------------
  // Live Hydration of Cards
  // -------------------------------------------------------------
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

      fetch(`/api/cards_status?ids=${torrentIds.join(',')}&category=${state.category}`)
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
                const img = document.createElement('img');
                img.className = 'poster-img poster-loaded';
                img.src = st.poster_url;
                img.alt = card.dataset.titleRu || '';
                loader.replaceWith(img);
              }
            }

            // 4. Hydrate Category Ratings Badges
            const rWrap = card.querySelector('.card-ratings-wrap');
            if (rWrap && rWrap.querySelector('.skeleton')) {
              const updatedBadges = buildRatingsBadgesHtml(st);
              if (updatedBadges) {
                rWrap.innerHTML = updatedBadges;
              }
            }

            // 5. Hydrate Series Seasons Badge and Date
            if (st.seasons_count) {
              const sBadge = card.querySelector('.card-seasons-badge');
              if (sBadge) sBadge.innerHTML = `📺 ${escapeHtml(formatSeasonsCount(st.seasons_count))}`;
            }
            if (st.date_added) {
              const dBadge = card.querySelector('.card-series-date');
              if (dBadge) dBadge.innerHTML = `📅 ${escapeHtml(st.date_added)}`;
            }

            const stillNeeds = (!st.poster_url) || (
              st.category === 'anime' ? (st.shikimori_rating === 0 && st.mal_rating === 0) :
              (st.category === 'games' ? (st.metacritic_critic === 0 && st.metacritic_user === 0 && st.opencritic_rating === 0) :
              (st.category === 'movies' || st.category === 'series' ? (st.kp_rating === 0 && st.imdb_rating === 0) : false))
            );

            if (stillNeeds) allDone = false;
          });

          if (allDone) {
            clearInterval(hydrationTimer);
            hydrationTimer = null;
          }
        })
        .catch(() => {});
    }, 700);
  }

  function buildRatingsBadgesHtml(item) {
    let rHtml = '';
    const cat = item.category || state.category;

    if (cat === 'anime') {
      if (item.shikimori_rating > 0) rHtml += `<div class="badge-rating shiki-badge" title="Shikimori">Shiki ${item.shikimori_rating}</div>`;
      if (item.mal_rating > 0) rHtml += `<div class="badge-rating mal-badge" title="MyAnimeList">MAL ${item.mal_rating}</div>`;
    } else if (cat === 'games') {
      if (item.metacritic_critic > 0) rHtml += `<div class="badge-rating mc-critic-badge" title="Metacritic Critics">MC ${item.metacritic_critic}</div>`;
      if (item.metacritic_user > 0) rHtml += `<div class="badge-rating mc-user-badge" title="Metacritic Users">MCU ${item.metacritic_user}</div>`;
      if (item.opencritic_rating > 0) rHtml += `<div class="badge-rating oc-badge" title="OpenCritic">OC ${item.opencritic_rating}</div>`;
    } else if (cat === 'software') {
      if (item.app_version) rHtml += `<div class="badge-rating soft-ver-badge" title="Версия ПО">v${escapeHtml(item.app_version)}</div>`;
    } else {
      // movies & series
      if (item.kp_rating > 0) rHtml += `<div class="badge-rating kp-badge" title="Кинопоиск">КП ${item.kp_rating}</div>`;
      if (item.imdb_rating > 0) rHtml += `<div class="badge-rating imdb-badge" title="IMDb">IMDb ${item.imdb_rating}</div>`;
    }

    return rHtml;
  }

  function parseSeasonFromTitle(title) {
    if (!title) return 1;
    const mMulti = title.match(/(?:\[|\()(\d{1,2})-(\d{1,2})\s*сезон/i);
    if (mMulti) return parseInt(mMulti[2]) || 1;
    const mX = title.match(/(?:\[|\()\s*(\d{1,2})x/i);
    if (mX) return parseInt(mX[1]) || 1;
    const mS = title.match(/(?:\[|\()\s*S(\d{1,2})/i);
    if (mS) return parseInt(mS[1]) || 1;
    const mWord = title.match(/(?:\[|\()(?:сезон\s*(\d{1,2})|(\d{1,2})\s*сезон)/i);
    if (mWord) return parseInt(mWord[1] || mWord[2]) || 1;
    return 1;
  }

  function formatSeasonsCount(count) {
    const n = parseInt(count) || 1;
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 14) {
      return `${n} сезонов`;
    }
    if (mod10 === 1) {
      return `${n} сезон`;
    }
    if (mod10 >= 2 && mod10 <= 4) {
      return `${n} сезона`;
    }
    return `${n} сезонов`;
  }

  // -------------------------------------------------------------

  function cleanSeriesTitle(title, title_ru) {
    let t = title_ru || title || '';
    if (t.includes('/')) t = t.split('/')[0].trim();
    // 1. Remove bracketed patterns [ ... ]
    t = t.replace(/\[.*?\]/g, '');
    // 2. Remove parentheses with season/episodes/repack/years
    t = t.replace(/\([^)]*(?:сезон|сери|s\d+|г\.|20\d\d|19\d\d)[^)]*\)/gi, '');
    // 3. Remove standalone season/episode mentions
    t = t.replace(/\b(?:\d+\s*сезон|сезон\s*\d+|\d+x\d+|s\d+)\b/gi, '');
    // 4. Remove trailing punctuation, dashes, spaces
    t = t.replace(/[\s\-–—:]+$/g, '').trim();
    return t || title_ru || title || '';
  }

  function cleanOrigTitle(title_en) {
    let t = title_en || '';
    t = t.replace(/\[.*?\]/g, '');
    t = t.replace(/\([^)]*(?:season|s\d+|episodes?|20\d\d|19\d\d)[^)]*\)/gi, '');
    t = t.replace(/\b(?:season\s*\d+|\d+\s*season|s\d+e\d+|\d+x\d+)\b/gi, '');
    t = t.replace(/[\s\-–—:]+$/g, '').trim();
    return t;
  }

  // Cards Rendering
  // -------------------------------------------------------------
  function renderCards(items, isWatchlistView = false) {
    cardsGrid.innerHTML = '';
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'media-card';
      card.id = `card-${item.torrent_id}`;
      card.dataset.titleRu = (item.title_ru || '').trim().toLowerCase();
      card.onclick = () => openModal(item.torrent_id);

      const isSeriesOrAnimeSeries = item.category === 'series' || (item.category === 'anime' && item.anime_type !== 'Полнометражный фильм');

      let displayTitle = item.title_ru || item.title || '';
      let displayOrig = '';
      if (item.category === 'series' || state.category === 'series') {
        displayTitle = cleanSeriesTitle(item.title, item.title_ru);
        displayOrig = cleanOrigTitle(item.title_en);
      }

      const escapedTitle = (displayTitle || item.title_ru || '').replace(/'/g, "\\'");
      const escapedEn = (item.title_en || '').replace(/'/g, "\\'");

      const posterHtml = item.poster_url 
        ? `<img class="poster-img poster-loaded" src="${item.poster_url}" alt="${escapeHtml(item.title_ru)}" loading="lazy" onerror="this.onerror=null; repairPoster(this, '${item.torrent_id}', '${escapedTitle}', ${item.year || 0}, '${escapedEn}');"/><div class="poster-placeholder" style="display:none;">🎬</div>`
        : `<div class="poster-loading skeleton" id="loader-${item.torrent_id}" data-torrent-id="${item.torrent_id}"></div>`;

      let ratingBadges = buildRatingsBadgesHtml(item);
      if (!ratingBadges) {
        ratingBadges = `<div class="badge-rating skeleton skeleton-field" title="Определение рейтинга..."></div>`;
      }

      // Card Subtitle & Genre/Country
      let subTitleText = '';
      if (item.category === 'games') {
        subTitleText = `${item.repack_author ? `[${item.repack_author}] · ` : ''}${item.release_format || 'RePack'}`;
      } else if (item.category === 'software') {
        subTitleText = `${item.repack_author ? `[${item.repack_author}] · ` : ''}${item.software_category || 'ПО'}`;
      } else if (item.category === 'anime') {
        subTitleText = `${item.title_en ? `${item.title_en} · ` : ''}${item.anime_type ? `${item.anime_type} · ` : ''}${item.year || ''}`;
      } else {
        subTitleText = `${item.title_en ? `${item.title_en} · ` : ''}${item.year || ''}`;
      }

      const hasRealGenre = item.genre && item.genre !== 'Фильм' && item.genre !== 'Сериал';
      const genreHtml = hasRealGenre
        ? `<div class="card-genres">${escapeHtml(item.genre)}</div>`
        : `<div class="card-genres skeleton skeleton-field"></div>`;

      let countryHtml = '';
      if (item.category === 'movies' || item.category === 'series') {
        countryHtml = item.country
          ? formatCountryBadge(item.country)
          : `<div class="card-country-box skeleton skeleton-field" style="margin-top: 4px;"></div>`;
      } else if (item.category === 'anime') {
        const studioBadge = item.voice_studio ? item.voice_studio : (item.has_subtitles ? 'Субтитры' : '');
        countryHtml = studioBadge ? `<div class="card-country-box"><span class="card-country-text">${escapeHtml(studioBadge)}</span></div>` : '';
      } else if (item.category === 'games') {
        countryHtml = item.crack_status ? `<div class="card-country-box"><span class="card-country-text">${escapeHtml(item.crack_status)}</span></div>` : '';
      }

      // Status badges
      let statusBadgeHtml = '';
      if (item.user_status === 'watchlist' || item.user_status === 'watchlist_alt') {
        statusBadgeHtml = `<div class="card-status-badge badge-status-watchlist">💚 В списке «Заинтересовало»</div>`;
      } else if (item.user_status === 'ignored' || item.user_status === 'ignored_alt') {
        statusBadgeHtml = `<div class="card-status-badge badge-status-ignored">🚫 В списке «Хрень»</div>`;
      }

      // Quick hover actions
      let hoverActionsHtml = '';
      if (isWatchlistView || item.user_status === 'watchlist' || item.user_status === 'watchlist_alt') {
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
              💚 Заинтересовало
            </button>
            <button class="btn-card-action btn-card-ignore" onclick="event.stopPropagation(); addToIgnored('${item.torrent_id}', '${escapedTitle}')">
              🚫 Хрень
            </button>
          </div>
        `;
      }

      const qualityBadgeText = item.quality || item.release_format || 'HD';

      let metaRowHtml = '';
      if (isSeriesOrAnimeSeries) {
        const sCount = item.seasons_count || parseSeasonFromTitle(item.title || item.title_ru);
        const sStr = formatSeasonsCount(sCount);
        metaRowHtml = `
          <div class="card-meta-row card-meta-series" style="margin-bottom: 4px;">
            <span class="card-seasons-badge" title="Последний вышедший сезон">📺 ${escapeHtml(sStr)}</span>
            <span class="card-size">${escapeHtml(item.size_str || `${item.size_gb} GB`)}</span>
          </div>
          <div class="card-meta-row">
            <div class="card-peers">
              <span class="seeds" title="Раздают (сиды)">▲ ${item.seeds}</span>
              <span class="peers" title="Качают (пиры)">▼ ${item.peers}</span>
            </div>
            ${item.date_added ? `<span class="card-series-date" title="Дата выхода / обновления">📅 ${escapeHtml(item.date_added)}</span>` : ''}
          </div>
        `;
      } else {
        metaRowHtml = `
          <div class="card-meta-row">
            <span class="card-size">${escapeHtml(item.size_str || `${item.size_gb} GB`)}</span>
            <div class="card-peers">
              <span class="seeds" title="Раздают (сиды)">▲ ${item.seeds}</span>
              <span class="peers" title="Качают (пиры)">▼ ${item.peers}</span>
            </div>
          </div>
        `;
      }

      card.innerHTML = `
        <div class="poster-wrap">
          ${posterHtml}
          ${statusBadgeHtml}
          ${hoverActionsHtml}
          <div class="badge-quality">${escapeHtml(qualityBadgeText)}</div>
          <div class="card-ratings-wrap">${ratingBadges}</div>
        </div>
        <div class="card-content">
          <h3 class="card-title" title="${escapeHtml(item.title)}">${escapeHtml(displayTitle)}</h3>
          <div class="card-orig">${escapeHtml(displayOrig ? (displayOrig + (item.year ? ' · ' + item.year : '')) : subTitleText)}</div>
          ${genreHtml}
          ${countryHtml}
          ${metaRowHtml}
        </div>
      `;
      cardsGrid.appendChild(card);
    });

    // Hydrate cards on current page
    const candidateIds = items.map(it => it.torrent_id);
    startCardHydration(candidateIds);
  }

  window.repairPoster = function(imgElem, torrentId, titleRu, year, titleEn) {
    const nextElem = imgElem ? imgElem.nextElementSibling : null;
    if (nextElem) nextElem.style.display = 'flex';
    if (imgElem) imgElem.style.display = 'none';
  };

  // -------------------------------------------------------------
  // Compact Ignored Table View
  // -------------------------------------------------------------
  function renderIgnoredTable(items) {
    if (!ignoredTableBody) return;
    ignoredTableBody.innerHTML = items.map(item => {
      let rHtml = buildRatingsBadgesHtml(item);
      if (!rHtml) rHtml = '<span style="color:var(--text-muted);">—</span>';

      const yearOrVer = item.category === 'software' ? (item.app_version ? `v${item.app_version}` : '—') : (item.year || '—');
      const genreOrCat = item.category === 'software' ? (item.software_category || 'ПО') : (item.genre || '—');

      return `
        <tr id="row-ign-${item.torrent_id}">
          <td>
            <div class="table-title-main">${escapeHtml(item.title_ru)}</div>
            ${item.title_en ? `<div class="table-title-sub">${escapeHtml(item.title_en)}</div>` : ''}
          </td>
          <td><strong>${escapeHtml(yearOrVer)}</strong></td>
          <td>${escapeHtml(genreOrCat)}</td>
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

  // -------------------------------------------------------------
  // Watchlist & Ignored Actions (Strict Category Isolation)
  // -------------------------------------------------------------
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

  // -------------------------------------------------------------
  // Interactive Modal with Category Spoilers & Wide Torrent Table
  // -------------------------------------------------------------
  function buildWideTorrentTable(validAlts, category) {
    if (!validAlts || validAlts.length === 0) return '';
    const isGame = category === 'games';
    const isSoft = category === 'software';

    return `
      <div class="wide-torrent-table-wrap">
        <table class="wide-torrent-table">
          <thead>
            <tr>
              <th>Качество / Релиз</th>
              <th>${isGame || isSoft ? 'Автор / Репакер' : 'Озвучка / Студия'}</th>
              <th>${isGame ? 'Таблетка' : (isSoft ? 'Формат' : 'Субтитры')}</th>
              <th>Размер</th>
              <th>Сиды / Пиры</th>
              <th>Скачать</th>
              <th>Magnet</th>
            </tr>
          </thead>
          <tbody>
            ${validAlts.map(rel => {
              const qStr = rel.quality || rel.release_format || 'HD';
              const hasDetails = Boolean(rel.voice_studio || rel.repack_author || rel.voiceover || rel.subtitles || rel.crack_status || isSoft);
              const voiceOrAuthor = rel.voice_studio || rel.repack_author || rel.voiceover || (hasDetails ? '—' : 'Загрузка...');
              const subOrCrack = isGame 
                ? (rel.crack_status || '—') 
                : (isSoft ? (rel.release_format || '—') : (rel.has_subtitles ? 'Есть' : (rel.subtitles ? 'Да' : (hasDetails ? '—' : 'Загрузка...'))));
              const loadingClass = !hasDetails ? 'cell-loading' : '';
              return `
                <tr>
                  <td>
                    <span class="badge-quality" style="position:static; display:inline-block; margin-right:4px;">${escapeHtml(qStr)}</span>
                    ${escapeHtml(rel.title_ru || rel.title || '')}
                  </td>
                  <td><span class="alt-voice-cell ${loadingClass}" data-tid="${rel.torrent_id}">${escapeHtml(voiceOrAuthor)}</span></td>
                  <td><span class="alt-sub-cell ${loadingClass}" data-tid="${rel.torrent_id}">${escapeHtml(subOrCrack)}</span></td>
                  <td><strong>${escapeHtml(rel.size_str || `${rel.size_gb} GB`)}</strong></td>
                  <td><span style="color:var(--accent);">▲ ${rel.seeds}</span> <span style="color:var(--text-muted); margin-left:4px;">▼ ${rel.peers}</span></td>
                  <td><a href="${rel.torrent_url}" class="btn-download-torrent" target="_blank" style="padding:4px 8px; font-size:11px; text-decoration:none;">⬇ .torrent</a></td>
                  <td>${rel.magnet_url ? `<a href="${rel.magnet_url}" class="btn-magnet" style="padding:4px 8px; font-size:11px; text-decoration:none;">🧲</a>` : '—'}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function attachAlternativesLazyLoader(detailsElem) {
    if (!detailsElem) return;
    detailsElem.addEventListener('toggle', () => {
      if (!detailsElem.open) return;
      const loadingCells = detailsElem.querySelectorAll('.cell-loading');
      if (loadingCells.length === 0) return;
      const idsToFetch = Array.from(new Set(Array.from(loadingCells).map(c => c.dataset.tid).filter(Boolean)));
      if (idsToFetch.length === 0) return;
      fetch(`/api/alternatives_details?ids=${idsToFetch.join(',')}`)
        .then(r => r.json())
        .then(data => {
          if (!data || !data.items) return;
          data.items.forEach(it => {
            const vCell = detailsElem.querySelector(`.alt-voice-cell[data-tid="${it.torrent_id}"]`);
            if (vCell) {
              vCell.classList.remove('cell-loading');
              const vText = it.voice_studio || it.repack_author || it.voiceover || '—';
              vCell.textContent = vText;
            }
            const sCell = detailsElem.querySelector(`.alt-sub-cell[data-tid="${it.torrent_id}"]`);
            if (sCell) {
              sCell.classList.remove('cell-loading');
              const sText = it.has_subtitles ? 'Есть' : (it.subtitles ? 'Да' : '—');
              sCell.textContent = sText;
            }
          });
        })
        .catch(() => {});
    }, { once: true });
  }

  function openModal(torrentId) {
    modalOverlay.style.display = 'flex';
    modalContent.innerHTML = `
      <div class="modal-loading-overlay" id="modal-blur-overlay">
        <div class="shimmer-pulse-badge">
          <div class="spinner-neon"></div>
          <span>Загрузка данных раздачи...</span>
        </div>
      </div>
      <div class="modal-skeleton-layout">
        <div class="modal-skeleton-poster skeleton"></div>
        <div class="modal-skeleton-body">
          <div class="skeleton-line w-80 skeleton" style="height: 28px;"></div>
          <div class="skeleton-line w-40 skeleton" style="height: 18px;"></div>
          <div style="display: flex; gap: 8px; margin-top: 8px;">
            <div class="skeleton-line skeleton" style="width: 70px; height: 24px; border-radius: 6px;"></div>
            <div class="skeleton-line skeleton" style="width: 80px; height: 24px; border-radius: 6px;"></div>
          </div>
          <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 16px;">
            <div class="skeleton-line w-100 skeleton"></div>
            <div class="skeleton-line w-100 skeleton"></div>
            <div class="skeleton-line w-80 skeleton"></div>
          </div>
        </div>
      </div>
    `;

    fetch(`/api/item?id=${torrentId}`)
      .then(res => res.json())
      .then(item => renderModalDetails(item))
      .catch(err => {
        modalContent.innerHTML = `<div style="color: #ef4444; padding: 40px; text-align: center;">Ошибка загрузки деталей: ${escapeHtml(err.message)}</div>`;
      });
  }

  function renderModalDetails(item) {
    const category = item.category || state.category;

    // Parse JSON fields
    let screenshots = [];
    try {
      screenshots = typeof item.screenshots_json === 'string' ? JSON.parse(item.screenshots_json || '[]') : (item.screenshots_json || []);
    } catch(e) {}

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

    // Exclude main item from alternative releases
    const validAlts = (item.alternatives || []).filter(a => String(a.torrent_id) !== String(item.torrent_id) && String(a.id) !== String(item.id));

    // 1. Screenshots Spoiler (Strict On-Demand, default closed)
    const screenshotsSpoilerHtml = (screenshots && screenshots.length > 0)
      ? `
        <details class="modal-spoiler" id="screenshots-spoiler">
          <summary>🖼️ Кадры и скриншоты (${screenshots.length})</summary>
          <div class="modal-spoiler-content">
            <div class="screenshots-gallery">
              ${screenshots.map(url => `
                <div class="screen-thumb-wrap" onclick="window.open('${escapeHtml(url)}', '_blank')">
                  <img class="screen-thumb-img lazy-screen" data-src="${escapeHtml(url)}" alt="Скриншот" onerror="this.parentElement.style.display='none';" />
                </div>
              `).join('')}
            </div>
          </div>
        </details>
      `
      : '';

    // 2. Audio & Subs HTML
    const audioTagsHtml = (audioTracksList && audioTracksList.length > 0)
      ? audioTracksList.map(t => `<div class="stream-tag" style="display: block; width: 100%; margin-bottom: 6px; padding: 6px 10px; font-size: 12px; line-height: 1.4; border-radius: 6px; background: rgba(0, 255, 204, 0.07); border: 1px solid rgba(0, 255, 204, 0.2);">🔊 ${escapeHtml(t)}</div>`).join('')
      : (item.audio_info 
          ? `<span class="stream-tag">${escapeHtml(item.audio_info)}</span>`
          : (item.voiceover ? '' : `<span class="stream-tag">Информация о звуке отсутствует</span>`));

    const subsTagsHtml = (subsList && subsList.length > 0 && subsList[0])
      ? subsList.map(s => `<span class="stream-tag" style="margin-right: 4px; margin-bottom: 4px; display: inline-block;">📄 ${escapeHtml(s)}</span>`).join('')
      : `<span class="stream-tag">Субтитры отсутствуют или не указаны</span>`;

    const audioSubsBlockHtml = `
      <div class="audio-subs-box">
        <div class="audio-subs-item">
          <h4>🎧 АУДИОДОРОЖКИ И ОЗВУЧКА</h4>
          ${item.voiceover ? `
            <div style="margin-bottom: 10px; font-size: 13px;">
              ${item.voiceover.split(/;\s*/).filter(Boolean).map(v => `<div style="margin-bottom: 4px; color: var(--text-main);"><strong style="color: var(--accent);">🎙️</strong> ${escapeHtml(v)}</div>`).join('')}
            </div>
          ` : ''}
          <div class="tag-list">${audioTagsHtml}</div>
        </div>
        <div class="audio-subs-item">
          <h4>📝 СУБТИТРЫ</h4>
          <div class="tag-list">${subsTagsHtml}</div>
        </div>
      </div>
    `;

    // 3. Seasons Block (for Series)
    const seasonsBlockHtml = (category === 'series' && seasonsList && seasonsList.length > 0)
      ? `
        <div class="seasons-block" style="margin-bottom: 12px;">
          <h4>📺 ДРУГИЕ СЕЗОНЫ ЭТОГО СЕРИАЛА:</h4>
          <div class="tag-list">
            ${seasonsList.map(s => `
              <button class="season-btn" onclick="searchSeason('${escapeHtml(s.search_query).replace(/'/g, "\\'")}')">
                🔍 ${escapeHtml(s.season)}
              </button>
            `).join('')}
          </div>
        </div>
      `
      : '';

    // 4. Build Spoilers in Exact Required Order (All Default Closed):
    // Order: 1) Описание сюжета, 2) Кадры и скриншоты, 3) Видео и звук / Системные требования, 4) Другие раздачи
    const altSpoilerLabel = (category === 'series') 
      ? `📺 Другие сезоны, серии и раздачи (${validAlts.length})` 
      : (category === 'games' 
          ? `💾 Другие раздачи и репаки (${validAlts.length})` 
          : (category === 'software' ? `💾 Раздачи и версии (${validAlts.length})` : `💾 Другие качества и раздачи (${validAlts.length})`));

    const alternativesSpoilerHtml = (validAlts.length > 0)
      ? `
        <details class="modal-spoiler" id="alternatives-spoiler">
          <summary>${altSpoilerLabel}</summary>
          <div class="modal-spoiler-content">
            ${category === 'series' ? seasonsBlockHtml : ''}
            ${buildWideTorrentTable(validAlts, category)}
          </div>
        </details>
      `
      : '';

    let spoilersHtml = '';

    if (category === 'movies') {
      spoilersHtml = `
        ${item.description ? `
          <details class="modal-spoiler">
            <summary>📖 Описание сюжета</summary>
            <div class="modal-spoiler-content">
              <p class="synopsis-text">${escapeHtml(item.description)}</p>
            </div>
          </details>
        ` : ''}
        ${screenshotsSpoilerHtml}
        <details class="modal-spoiler">
          <summary>🔊 Видео и звук (технические параметры)</summary>
          <div class="modal-spoiler-content">
            ${item.video_info ? `<div style="margin-bottom: 10px; font-family: monospace; font-size: 12px;"><strong>Видео:</strong> ${escapeHtml(item.video_info)}</div>` : ''}
            ${audioSubsBlockHtml}
          </div>
        </details>
        ${alternativesSpoilerHtml}
      `;
    } else if (category === 'series') {
      const cleanSeriesName = cleanSeriesTitle(item.title, item.title_ru);
      const maxSeason = Math.max(item.seasons_count || 1, 1);
      
      const seasonsTabsBlockHtml = `
        <div class="season-tabs-section" style="margin-top: 20px;">
          <h4 style="margin: 0 0 10px 0; color: var(--accent); font-size: 14px; font-weight: 700; letter-spacing: 0.5px;">
            📺 СЕЗОНЫ И РАЗДАЧИ
          </h4>
          <div class="season-tabs-container" id="season-tabs-bar">
            ${Array.from({length: maxSeason}, (_, i) => i + 1).map(sNum => `
              <button class="season-tab-btn ${sNum === maxSeason ? 'active' : ''}" data-season="${sNum}">
                Сезон ${sNum}
              </button>
            `).join('')}
          </div>
          <div id="season-releases-list" class="season-releases-wrap">
            <div style="padding: 24px; text-align: center; color: var(--text-muted);">
              <div class="spinner-neon" style="display: inline-block; margin-bottom: 8px;"></div>
              <div>Поиск раздач Сезона ${maxSeason}...</div>
            </div>
          </div>
        </div>
      `;

      spoilersHtml = `
        ${item.description ? `
          <details class="modal-spoiler">
            <summary>📖 Описание сюжета</summary>
            <div class="modal-spoiler-content">
              <p class="synopsis-text">${escapeHtml(item.description)}</p>
            </div>
          </details>
        ` : ''}
        ${screenshotsSpoilerHtml}
        <details class="modal-spoiler">
          <summary>🔊 Видео и звук</summary>
          <div class="modal-spoiler-content">
            ${item.video_info ? `<div style="margin-bottom: 10px; font-family: monospace; font-size: 12px;"><strong>Видео:</strong> ${escapeHtml(item.video_info)}</div>` : ''}
            ${audioSubsBlockHtml}
          </div>
        </details>
        ${seasonsTabsBlockHtml}
      `;
    } else if (category === 'anime') {
      spoilersHtml = `
        ${item.description ? `
          <details class="modal-spoiler">
            <summary>📖 Описание сюжета</summary>
            <div class="modal-spoiler-content">
              <p class="synopsis-text">${escapeHtml(item.description)}</p>
            </div>
          </details>
        ` : ''}
        ${screenshotsSpoilerHtml}
        <details class="modal-spoiler">
          <summary>🎙️ Озвучка и субтитры</summary>
          <div class="modal-spoiler-content">
            ${audioSubsBlockHtml}
          </div>
        </details>
        ${alternativesSpoilerHtml}
      `;
    } else if (category === 'games') {
      spoilersHtml = `
        ${item.description ? `
          <details class="modal-spoiler">
            <summary>🎮 Об игре</summary>
            <div class="modal-spoiler-content">
              <p class="synopsis-text">${escapeHtml(item.description)}</p>
            </div>
          </details>
        ` : ''}
        ${screenshotsSpoilerHtml}
        ${(item.repack_features || item.repack_author) ? `
          <details class="modal-spoiler">
            <summary>📦 Особенности репака / релиза</summary>
            <div class="modal-spoiler-content">
              ${item.repack_author ? `<div class="meta-highlight-box"><h4>Релиз от: ${escapeHtml(item.repack_author)}</h4>Таблетка / Лекарство: <strong>${escapeHtml(item.crack_status || 'Вшито')}</strong></div>` : ''}
              ${item.repack_features ? `<p class="synopsis-text" style="white-space: pre-line;">${escapeHtml(item.repack_features)}</p>` : ''}
            </div>
          </details>
        ` : ''}
        ${item.system_reqs ? `
          <details class="modal-spoiler">
            <summary>⚙️ Системные требования</summary>
            <div class="modal-spoiler-content">
              <p class="synopsis-text" style="white-space: pre-line; font-family: monospace; font-size: 13px;">${escapeHtml(item.system_reqs)}</p>
            </div>
          </details>
        ` : ''}
        ${alternativesSpoilerHtml}
      `;
    } else if (category === 'software') {
      spoilersHtml = `
        ${item.description ? `
          <details class="modal-spoiler">
            <summary>💻 О программе</summary>
            <div class="modal-spoiler-content">
              <p class="synopsis-text">${escapeHtml(item.description)}</p>
            </div>
          </details>
        ` : ''}
        ${screenshotsSpoilerHtml}
        ${(item.repack_features || item.repack_author) ? `
          <details class="modal-spoiler">
            <summary>📦 Особенности сборки / репака</summary>
            <div class="modal-spoiler-content">
              ${item.repack_author ? `<div class="meta-highlight-box"><h4>Автор сборки: ${escapeHtml(item.repack_author)}</h4>Категория: <strong>${escapeHtml(item.software_category || 'ПО')}</strong></div>` : ''}
              ${item.repack_features ? `<p class="synopsis-text" style="white-space: pre-line;">${escapeHtml(item.repack_features)}</p>` : ''}
            </div>
          </details>
        ` : ''}
        ${item.system_reqs ? `
          <details class="modal-spoiler">
            <summary>⚙️ Системные требования</summary>
            <div class="modal-spoiler-content">
              <p class="synopsis-text" style="white-space: pre-line; font-family: monospace; font-size: 13px;">${escapeHtml(item.system_reqs)}</p>
            </div>
          </details>
        ` : ''}
        ${alternativesSpoilerHtml}
      `;
    }

    // Modal Ratings Row
    let modalRatingsRowHtml = '';
    if (category === 'anime') {
      if (item.shikimori_rating > 0) modalRatingsRowHtml += `<div class="rating-badge-lg shiki-badge">Shikimori: ${item.shikimori_rating}</div>`;
      if (item.mal_rating > 0) modalRatingsRowHtml += `<div class="rating-badge-lg mal-badge">MAL: ${item.mal_rating}</div>`;
      if (item.anime_type) modalRatingsRowHtml += `<div class="rating-badge-lg" style="background: var(--bg-card); color: var(--accent); border: 1px solid var(--accent);">${escapeHtml(item.anime_type)}</div>`;
    } else if (category === 'games') {
      if (item.metacritic_critic > 0) modalRatingsRowHtml += `<div class="rating-badge-lg mc-critic-badge">Metacritic: ${item.metacritic_critic}</div>`;
      if (item.metacritic_user > 0) modalRatingsRowHtml += `<div class="rating-badge-lg mc-user-badge">Users: ${item.metacritic_user}</div>`;
      if (item.opencritic_rating > 0) modalRatingsRowHtml += `<div class="rating-badge-lg oc-badge">OpenCritic: ${item.opencritic_rating}</div>`;
    } else if (category === 'software') {
      if (item.app_version) modalRatingsRowHtml += `<div class="rating-badge-lg soft-ver-badge">Версия: ${escapeHtml(item.app_version)}</div>`;
      if (item.software_category) modalRatingsRowHtml += `<div class="rating-badge-lg" style="background: var(--bg-card); color: #fff; border: 1px solid var(--border-color);">${escapeHtml(item.software_category)}</div>`;
    } else {
      if (item.kp_rating > 0) modalRatingsRowHtml += `<div class="rating-badge-lg kp-badge">Кинопоиск: ${item.kp_rating}</div>`;
      if (item.imdb_rating > 0) modalRatingsRowHtml += `<div class="rating-badge-lg imdb-badge">IMDb: ${item.imdb_rating}</div>`;
      if (item.quality) modalRatingsRowHtml += `<div class="rating-badge-lg" style="background: var(--bg-card); border: 1px solid var(--border-color); color: #fff;">${escapeHtml(item.quality)}</div>`;
    }

    // Games Metadata Box
    let gameMetaBoxHtml = '';
    if (category === 'games') {
      const gSteam = item.steam_rating ? `<span class="steam-rating-badge">🎮 Steam: ${escapeHtml(item.steam_rating)}</span>` : '';
      const gDev = item.developer ? `<div class="game-meta-item">Разработчик:<strong>${escapeHtml(item.developer)}</strong></div>` : '';
      const gPub = item.publisher ? `<div class="game-meta-item">Издатель:<strong>${escapeHtml(item.publisher)}</strong></div>` : '';
      const gPlat = item.platform ? `<div class="game-meta-item">Платформа:<strong>${escapeHtml(item.platform)}</strong></div>` : '';
      const gEng = item.engine ? `<div class="game-meta-item">Движок:<strong>${escapeHtml(item.engine)}</strong></div>` : '';
      const gDate = item.release_date ? `<div class="game-meta-item">Дата выхода:<strong>${escapeHtml(item.release_date)}</strong></div>` : '';

      if (gDev || gPub || gPlat || gEng || gDate || gSteam) {
        gameMetaBoxHtml = `
          <div class="game-metadata-grid">
            ${gDev}
            ${gPub}
            ${gDate}
            ${gPlat}
            ${gEng}
            ${gSteam ? `<div class="game-meta-item">${gSteam}</div>` : ''}
          </div>
        `;
      }
    }

    modalContent.innerHTML = `
      <div class="modal-left">
        ${item.poster_url 
          ? `<img class="modal-poster" src="${item.poster_url}" alt="Постер" onerror="this.onerror=null; repairPoster(this, '${item.torrent_id}', '${(item.title_ru || '').replace(/'/g, "\\'")}', ${item.year || 0}, '${(item.title_en || '').replace(/'/g, "\\")}');"/>` 
          : '<div class="poster-placeholder" style="border-radius:12px; height: 380px;">🎬</div>'}
        
        <!-- Modal Quick Actions -->
        <div style="display: flex; gap: 8px; margin: 10px 0;">
          <button class="btn-card-action btn-card-watch" style="flex:1;" onclick="addToWatchlist('${item.torrent_id}', '${(item.title_ru || '').replace(/'/g, "\\")}'); closeModal();">
            💚 Заинтересовало
          </button>
          <button class="btn-card-action btn-card-ignore" style="flex:1;" onclick="addToIgnored('${item.torrent_id}', '${(item.title_ru || '').replace(/'/g, "\\")}'); closeModal();">
            🚫 Хрень
          </button>
        </div>

        <a href="${item.torrent_url}" class="btn-download-torrent" target="_blank">
          ⬇ Скачать .torrent (${escapeHtml(item.size_str || `${item.size_gb} GB`)})
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
      </div>

      <div class="modal-right">
        <div>
          <h2 class="modal-title-h2">${escapeHtml(category === 'series' ? cleanSeriesTitle(item.title, item.title_ru) : item.title_ru)}</h2>
          <div class="modal-orig-sub">
            ${item.title_en ? `${escapeHtml(cleanOrigTitle(item.title_en))} · ` : ''}${item.year || ''}
          </div>
        </div>

        <div class="modal-ratings-row">
          ${modalRatingsRowHtml}
        </div>

        ${gameMetaBoxHtml}

        <div class="detail-info-table">
          ${item.genre ? `<div class="detail-row"><span class="detail-label">Жанр / Категория:</span><span class="detail-value">${escapeHtml(item.genre)}</span></div>` : ''}
          ${item.director ? `<div class="detail-row"><span class="detail-label">${category === 'games' ? 'Разработчик:' : 'Режиссёр:'}</span><span class="detail-value">${escapeHtml(item.director)}</span></div>` : ''}
          ${item.actors ? `<div class="detail-row"><span class="detail-label">${category === 'games' ? 'Издатель:' : 'В ролях:'}</span><span class="detail-value">${escapeHtml(item.actors)}</span></div>` : ''}
          ${item.country ? `<div class="detail-row"><span class="detail-label">Страна / Студия:</span><span class="detail-value">${escapeHtml(item.country)}</span></div>` : ''}
          ${item.duration ? `<div class="detail-row"><span class="detail-label">Хронометраж:</span><span class="detail-value">${escapeHtml(item.duration)}</span></div>` : ''}
          <div class="detail-row"><span class="detail-label">Дата добавления:</span><span class="detail-value">${escapeHtml(item.date_added)}</span></div>
        </div>

        ${spoilersHtml}
      </div>
    `;

    // Lazy-load screenshots strictly on spoiler open
    const screenSpoiler = modalContent.querySelector('#screenshots-spoiler');
    if (screenSpoiler) {
      screenSpoiler.addEventListener('toggle', () => {
        if (screenSpoiler.open) {
          screenSpoiler.querySelectorAll('img.lazy-screen[data-src]').forEach(img => {
            img.src = img.dataset.src;
            img.removeAttribute('data-src');
          });
        }
      }, { once: true });
    }

    // Series Season Tabs setup and on-demand search
    if (category === 'series') {
      const cleanSeriesName = cleanSeriesTitle(item.title, item.title_ru);
      const maxSeason = Math.max(item.seasons_count || 1, 1);
      const tabsBar = modalContent.querySelector('#season-tabs-bar');
      if (tabsBar) {
        const tabBtns = tabsBar.querySelectorAll('.season-tab-btn');
        tabBtns.forEach(btn => {
          btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const sNum = parseInt(btn.dataset.season) || 1;
            loadSeasonTorrents(cleanSeriesName, sNum, item.title_en);
          });
        });
        loadSeasonTorrents(cleanSeriesName, maxSeason, item.title_en);
      }
    }

    // Attach lazy loader to alternatives spoiler if present
    const altSpoiler = modalContent.querySelector('#alternatives-spoiler');
    if (altSpoiler) {
      attachAlternativesLazyLoader(altSpoiler);
    }
  }
  window.searchSeason = function(query) {
    closeModal();
    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.value = query;
    state.search = query;
    state.page = 1;
    fetchReleases();
  };

  function closeModal() {
    modalOverlay.style.display = 'none';
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

  // Notify server when window is closing so session cleanup is triggered
  window.addEventListener('beforeunload', () => {
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/browser_closing');
    } else {
      fetch('/api/browser_closing', { method: 'POST', keepalive: true }).catch(() => {});
    }
  });
});


  function loadSeasonTorrents(cleanTitle, seasonNum, titleEn) {
    const container = document.getElementById('season-releases-list');
    if (!container) return;
    container.innerHTML = `
      <div style="padding: 24px; text-align: center; color: var(--text-muted);">
        <div class="spinner-neon" style="display: inline-block; margin-bottom: 8px;"></div>
        <div>Поиск раздач Сезона ${seasonNum}...</div>
      </div>
    `;

    fetch(`/api/series_season_torrents?title=${encodeURIComponent(cleanTitle)}&season=${seasonNum}&title_en=${encodeURIComponent(titleEn || '')}`)
      .then(res => res.json())
      .then(data => {
        if (!data.items || data.items.length === 0) {
          container.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted);">Раздачи для Сезона ${seasonNum} не найдены на трекере.</div>`;
          return;
        }

        let rowsHtml = data.items.map(rel => {
          const q = (rel.quality || '1080p').toLowerCase();
          let qClass = 'q-low';
          if (q.includes('1080')) qClass = 'q-1080p';
          else if (q.includes('720')) qClass = 'q-720p';

          let epStr = '';
          if (rel.episodes_released && rel.episodes_total) {
            const relPadded = String(rel.episodes_released).padStart(2, '0');
            const totPadded = String(rel.episodes_total).padStart(2, '0');
            epStr = `${relPadded} из ${totPadded}`;
          } else {
            const mEp = (rel.title || '').match(/(?:\[|\()?(?:\d+-)?(\d+)\s+из\s+(\d+)/i);
            if (mEp) {
              epStr = `${mEp[1].padStart(2, '0')} из ${mEp[2].padStart(2, '0')}`;
            } else {
              const mX = (rel.title || '').match(/\[\s*\d+x(?:\d+-)?(\d+)/i);
              if (mX) {
                epStr = `${mX[1].padStart(2, '0')} сер.`;
              } else {
                epStr = 'Все серии';
              }
            }
          }

          const isOngoing = rel.is_ongoing || (rel.episodes_released && rel.episodes_total && rel.episodes_released < rel.episodes_total);
          const epBadgeClass = isOngoing ? 'season-episodes-badge ongoing' : 'season-episodes-badge';

          const studio = rel.voice_studio || rel.voiceover || 'Оригинал / Не указано';
          const hasSubs = rel.has_subtitles || (rel.subtitles && !rel.subtitles.includes('нет'));

          const torrentUrl = rel.torrent_url || (rel.torrent_id ? `http://d.rutor.info/download/${rel.torrent_id}` : '#');
          const magnetUrl = rel.magnet_url || (rel.torrent_id ? `magnet:?xt=urn:btih:...` : '#');

          return `
            <tr class="season-release-row">
              <td style="width: 75px;">
                <span class="season-badge-quality ${qClass}">${escapeHtml(rel.quality || '1080p')}</span>
              </td>
              <td style="width: 105px;">
                <span class="${epBadgeClass}">${escapeHtml(epStr)}</span>
              </td>
              <td>
                <div class="season-voiceover" title="${escapeHtml(studio)}">🎙️ ${escapeHtml(studio)}</div>
              </td>
              <td style="width: 110px;">
                <span class="season-subs-tag ${hasSubs ? 'has-subs' : ''}">${hasSubs ? '📄 Сабы: Да' : '—'}</span>
              </td>
              <td style="width: 95px;">
                <span class="season-size">💾 ${escapeHtml(rel.size_str || (rel.size_gb ? rel.size_gb + ' ГБ' : '—'))}</span>
              </td>
              <td style="width: 120px;">
                <span class="season-seeds-peers">
                  <span class="season-seeds">▲ ${rel.seeds || 0}</span>
                  <span class="season-peers">▼ ${rel.peers || 0}</span>
                </span>
              </td>
              <td style="width: 130px; text-align: right;">
                <div class="season-row-actions">
                  <a href="${torrentUrl}" class="btn-torrent-season" download title="Скачать торрент-файл">⬇ .torrent</a>
                  ${magnetUrl && magnetUrl !== '#' ? `<a href="${magnetUrl}" class="btn-magnet-season" title="Magnet-ссылка">🧲</a>` : ''}
                </div>
              </td>
            </tr>
          `;
        }).join('');

        container.innerHTML = `
          <table class="season-releases-table">
            <tbody>${rowsHtml}</tbody>
          </table>
        `;
      })
      .catch(err => {
        container.innerHTML = `<div style="padding: 20px; text-align: center; color: #ef4444;">Ошибка загрузки раздач: ${escapeHtml(err.message)}</div>`;
      });
  }

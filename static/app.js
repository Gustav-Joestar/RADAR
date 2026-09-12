// RADAR Application Controller
document.addEventListener('DOMContentLoaded', () => {
  const state = {
    category: 'movies',
    days: 7,
    min_rating: 0.0,
    max_size: 15.0,
    qualities: ['1080p', '720p'],
    genre: 'all',
    search: '',
    page: 1,
    limit: 15,
    totalPages: 1
  };

  // DOM Elements
  const cardsGrid = document.getElementById('cards-grid');
  const emptyState = document.getElementById('empty-state');
  const resultsCount = document.getElementById('results-count');
  const currentPageSpan = document.getElementById('current-page');
  const totalPagesSpan = document.getElementById('total-pages');
  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');
  const btnRefresh = document.getElementById('btn-refresh');
  const sizeSlider = document.getElementById('size-slider');
  const sizeVal = document.getElementById('size-val');
  const ratingToggle = document.getElementById('rating-toggle');
  const ratingWrap = document.getElementById('rating-filter-wrap');
  const qualityWrap = document.getElementById('quality-filter-wrap');
  const searchInput = document.getElementById('search-input');
  const genreSelect = document.getElementById('genre-select');
  const btnReset = document.getElementById('btn-reset-filters');
  const modalOverlay = document.getElementById('detail-modal');
  const modalContent = document.getElementById('modal-content');
  const modalClose = document.getElementById('modal-close');
  const consoleLogFeed = document.getElementById('console-log-feed');
  const consoleToggle = document.getElementById('console-toggle');
  const consoleStatusText = document.getElementById('console-status-text');
  const consoleMinimizeBtn = document.getElementById('console-minimize-btn');
  const debugConsole = document.getElementById('debug-console');

  // Initialize
  initEventListeners();
  loadGenres();
  fetchReleases();
  pollLogs();
  setInterval(pollLogs, 2000);

  function initEventListeners() {
    // Category Tabs
    document.querySelectorAll('.cat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.category = btn.dataset.category;
        state.page = 1;
        state.genre = 'all';

        if (state.category === 'games' || state.category === 'software') {
          ratingWrap.style.display = 'none';
          qualityWrap.style.display = 'none';
          state.min_rating = 0.0;
        } else {
          ratingWrap.style.display = 'flex';
          qualityWrap.style.display = 'flex';
          state.min_rating = ratingToggle.checked ? 7.0 : 0.0;
        }

        loadGenres();
        fetchReleases();
      });
    });

    // Date Period Buttons
    document.querySelectorAll('#date-buttons .toggle-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#date-buttons .toggle-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.days = parseInt(btn.dataset.days);
        state.page = 1;
        fetchReleases();
      });
    });

    // Quality Checkboxes
    ['q-1080p', 'q-720p', 'q-4k'].forEach(id => {
      const cb = document.getElementById(id);
      if (cb) {
        cb.addEventListener('change', () => {
          const active = [];
          if (document.getElementById('q-1080p').checked) active.push('1080p');
          if (document.getElementById('q-720p').checked) active.push('720p');
          if (document.getElementById('q-4k').checked) active.push('4K');
          state.qualities = active;
          state.page = 1;
          fetchReleases();
        });
      }
    });

    // Size Slider
    sizeSlider.addEventListener('input', (e) => {
      sizeVal.textContent = `${e.target.value} GB`;
      state.max_size = parseFloat(e.target.value);
    });
    sizeSlider.addEventListener('change', () => {
      state.page = 1;
      fetchReleases();
    });

    // Rating Toggle
    ratingToggle.addEventListener('change', (e) => {
      state.min_rating = e.target.checked ? 7.0 : 0.0;
      state.page = 1;
      fetchReleases();
    });

    // Genre Select
    genreSelect.addEventListener('change', (e) => {
      state.genre = e.target.value;
      state.page = 1;
      fetchReleases();
    });

    // Search Input Debounce
    let searchTimeout = null;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        state.search = e.target.value;
        state.page = 1;
        fetchReleases();
      }, 350);
    });

    // Reset Filters
    btnReset.addEventListener('click', resetFilters);

    // Refresh Tracker Data
    btnRefresh.addEventListener('click', () => {
      btnRefresh.classList.add('loading');
      consoleStatusText.textContent = `Сканирование трекера [${state.category}]...`;
      fetch('/api/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: state.category })
      })
      .then(res => res.json())
      .then(() => {
        setTimeout(() => {
          btnRefresh.classList.remove('loading');
          loadGenres();
          fetchReleases();
        }, 3500);
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
      if (state.page < state.totalPages) {
        state.page++;
        fetchReleases();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
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

  function resetFilters() {
    state.days = 7;
    state.min_rating = 0.0;
    state.max_size = 15.0;
    state.qualities = ['1080p', '720p'];
    state.genre = 'all';
    state.search = '';
    state.page = 1;

    searchInput.value = '';
    sizeSlider.value = 15;
    sizeVal.textContent = '15 GB';
    ratingToggle.checked = false;
    genreSelect.value = 'all';

    document.getElementById('q-1080p').checked = true;
    document.getElementById('q-720p').checked = true;
    document.getElementById('q-4k').checked = false;

    document.querySelectorAll('#date-buttons .toggle-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.days === '7');
    });

    fetchReleases();
  }

  function fetchReleases() {
    cardsGrid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 60px 0; color: var(--text-muted);">
        <div style="font-size: 36px; margin-bottom: 12px; animation: spin 1.5s linear infinite;">📡</div>
        Поиск релизов на радаре...
      </div>
    `;

    const params = new URLSearchParams({
      category: state.category,
      days: state.days,
      min_rating: state.min_rating,
      max_size: state.max_size,
      genre: state.genre,
      search: state.search,
      page: state.page,
      limit: state.limit
    });

    if (state.qualities.length > 0) {
      params.append('quality', state.qualities.join(','));
    }

    consoleStatusText.textContent = `Запрос релизов (категория: ${state.category}, стр. ${state.page})...`;

    fetch(`/api/items?${params.toString()}`)
      .then(res => res.json())
      .then(data => {
        renderCards(data.items);
        state.totalPages = data.pages;
        currentPageSpan.textContent = data.page;
        totalPagesSpan.textContent = data.pages;
        resultsCount.textContent = `Найдено релизов: ${data.total} (показано ${data.items.length})`;

        btnPrev.disabled = data.page <= 1;
        btnNext.disabled = data.page >= data.pages;

        if (data.total === 0) {
          cardsGrid.style.display = 'none';
          emptyState.style.display = 'block';
        } else {
          cardsGrid.style.display = 'grid';
          emptyState.style.display = 'none';
        }
        consoleStatusText.textContent = `Найдено ${data.total} релизов (страница ${data.page})`;
      })
      .catch(err => {
        cardsGrid.innerHTML = `<div style="grid-column: 1/-1; color: #ef4444; padding: 40px; text-align: center;">Ошибка загрузки данных: ${err.message}</div>`;
      });
  }

  function renderCards(items) {
    cardsGrid.innerHTML = '';
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'media-card';
      card.onclick = () => openModal(item.torrent_id);

      const posterHtml = item.poster_url 
        ? `<img class="poster-img" src="${item.poster_url}" alt="${item.title_ru}" loading="lazy" onerror="this.onerror=null; this.parentElement.innerHTML='<div class=\'poster-placeholder\'>🎬</div>'"/>`
        : `<div class="poster-placeholder">🎬</div>`;

      const ratingBadge = (item.imdb_rating > 0 || item.kp_rating > 0)
        ? `<div class="badge-rating">⭐ ${item.kp_rating || item.imdb_rating}</div>`
        : '';

      const qualityBadge = item.quality 
        ? `<div class="badge-quality">${item.quality}</div>`
        : '';

      card.innerHTML = `
        <div class="poster-wrap">
          ${posterHtml}
          ${qualityBadge}
          ${ratingBadge}
        </div>
        <div class="card-content">
          <h3 class="card-title" title="${item.title}">${item.title_ru}</h3>
          <div class="card-orig">${item.title_en ? `${item.title_en} · ` : ''}${item.year || ''}</div>
          <div class="card-genres">${item.genre || 'Релиз трекера'}</div>
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
  }

  function openModal(torrentId) {
    modalOverlay.style.display = 'flex';
    modalContent.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 80px; color: var(--text-muted);">
        <div style="font-size: 36px; margin-bottom: 12px; animation: spin 1s linear infinite;">🔄</div>
        Загрузка полной информации (все 16 полей, дорожки, субтитры)...
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
      ? audioTracksList.map(t => `<span class="stream-tag">🔊 ${t}</span>`).join('')
      : `<span class="stream-tag">${item.audio_info || 'Информация уточняется'}</span>`;

    const subsTagsHtml = (subsList && subsList.length > 0 && subsList[0])
      ? subsList.map(s => `<span class="stream-tag">📄 ${s}</span>`).join('')
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

    modalContent.innerHTML = `
      <div class="modal-left">
        ${item.poster_url 
          ? `<img class="modal-poster" src="${item.poster_url}" alt="Постер" onerror="this.style.display='none'"/>` 
          : '<div class="poster-placeholder" style="border-radius:12px; height: 380px;">🎬</div>'}
        
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
            ${item.voiceover ? `<div style="font-size: 13px; margin-bottom: 6px; color: var(--text-main);"><strong>Перевод:</strong> ${item.voiceover}</div>` : ''}
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

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
});

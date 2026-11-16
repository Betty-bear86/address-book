/* ==========================================================================
 * 通讯录 · Address Book 前端逻辑（原生 ES6，无框架、无构建步骤）
 * 模块划分：状态 → 工具函数 → API → 渲染 → 交互 → 路由 → 启动
 * ========================================================================== */
(() => {
  'use strict';

  /* ------------------------------------------------------------------ 常量 */
  const TYPE_META = {
    phone: { label: '电话', icon: 'phone' },
    email: { label: '邮箱', icon: 'mail' },
    wechat: { label: '微信', icon: 'wechat' },
    qq: { label: 'QQ', icon: 'qq' },
    address: { label: '地址', icon: 'pin' },
    other: { label: '其他', icon: 'link' },
  };

  const AVATAR_GRADIENTS = [
    ['#6366f1', '#8b5cf6'],
    ['#0ea5e9', '#22d3ee'],
    ['#f59e0b', '#f97316'],
    ['#10b981', '#34d399'],
    ['#ec4899', '#f472b6'],
    ['#3b82f6', '#6366f1'],
    ['#14b8a6', '#0ea5e9'],
    ['#ef4444', '#f97316'],
  ];

  const GROUP_COLORS = ['#4f6ef7', '#f59e0b', '#10b981', '#ec4899', '#8b5cf6', '#0ea5e9', '#f97316', '#14b8a6'];

  /* ------------------------------------------------------------------ 状态 */
  const state = {
    contacts: [],
    meta: { types: [], labels: [], groups: [], stats: {} },
    filter: { kind: 'all', group: null },
    filterHash: '#/all',
    query: '',
    view: 'rows',
    sort: 'default',
    openId: null,
    editingId: null,
    importFile: null,
  };

  /* ------------------------------------------------------------- DOM 引用 */
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const els = {
    sidebar: $('#sidebar'),
    sidebarMask: $('#sidebarMask'),
    pillAll: $('#pillAll'),
    pillStarred: $('#pillStarred'),
    groupNav: $('#groupNav'),
    groupTotal: $('#groupTotal'),
    stats: $('#stats'),
    quickSection: $('#quickSection'),
    quickTrack: $('#quickTrack'),
    quickSub: $('#quickSub'),
    listTitle: $('#listTitle'),
    listSub: $('#listSub'),
    contactView: $('#contactView'),
    sortSelect: $('#sortSelect'),
    searchInput: $('#searchInput'),
    viewToggle: $('#viewToggle'),
    btnNew: $('#btnNew'),
    btnImport: $('#btnImport'),
    btnExport: $('#btnExport'),
    btnTemplate: $('#btnTemplate'),
    btnMenu: $('#btnMenu'),
    drawer: $('#drawer'),
    drawerMask: $('#drawerMask'),
    modalRoot: $('#modalRoot'),
    confirmRoot: $('#confirmRoot'),
    toasts: $('#toasts'),
  };

  /* ------------------------------------------------------------- 工具函数 */
  const escapeHtml = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));

  const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  const icon = (name, cls = '') => `<svg class="ic ${cls}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;

  const initials = (name) => {
    const text = String(name || '').trim();
    if (!text) return '?';
    if (/[\u4e00-\u9fa5]/.test(text)) {
      return text.length <= 2 ? text : text.slice(-2);
    }
    const parts = text.split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] || '') + (parts[1]?.[0] || '')).toUpperCase() || '?';
  };

  const gradientStyle = (seed) => {
    let hash = 0;
    for (const char of String(seed || '?')) hash = (hash * 31 + char.codePointAt(0)) >>> 0;
    const [a, b] = AVATAR_GRADIENTS[hash % AVATAR_GRADIENTS.length];
    return `--a:${a};--b:${b}`;
  };

  const avatarHtml = (contact, size = '') =>
    `<div class="avatar ${size}" style="${gradientStyle(contact.name)}">${escapeHtml(initials(contact.name))}</div>`;

  const findContact = (id) => state.contacts.find((item) => item.id === Number(id));

  const primaryMethod = (contact) =>
    contact.methods.find((method) => method.primary) || contact.methods[0] || null;

  const typeLabel = (type) => (TYPE_META[type] || TYPE_META.other).label;
  const typeIcon = (type) => (TYPE_META[type] || TYPE_META.other).icon;

  const formatBytes = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  };

  const highlight = (text) => {
    const safe = escapeHtml(text);
    const keyword = state.query.trim();
    if (!keyword) return safe;
    return safe.replace(new RegExp(escapeRegExp(escapeHtml(keyword)), 'gi'), (match) => `<mark>${match}</mark>`);
  };

  const debounce = (fn, delay = 120) => {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  };

  if (TYPE_META && window.localStorage) {
    try {
      const saved = window.localStorage.getItem('address-book:view');
      if (saved === 'rows' || saved === 'cards') state.view = saved;
    } catch (error) { /* 忽略隐私模式下的存储异常 */ }
  }

  /* ------------------------------------------------------------------- API */
  async function api(path, { method = 'GET', body, form } = {}) {
    const options = { method, headers: {} };
    if (form) {
      options.body = form;
    } else if (body !== undefined) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    const response = await fetch(`/api${path}`, options);
    const isJson = (response.headers.get('content-type') || '').includes('application/json');
    const payload = isJson ? await response.json() : null;
    if (!response.ok) {
      throw new Error((payload && payload.error && payload.error.message) || `请求失败（HTTP ${response.status}）`);
    }
    return payload;
  }

  async function loadContacts() {
    const data = await api('/contacts');
    state.contacts = data.items || [];
  }

  async function loadMeta() {
    state.meta = await api('/meta');
  }

  /* ------------------------------------------------------------------ 提示 */
  function toast(message, type = 'info') {
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    const iconName = type === 'success' ? 'check' : type === 'error' ? 'alert' : 'info';
    node.innerHTML = `${icon(iconName)}<span>${escapeHtml(message)}</span>`;
    els.toasts.appendChild(node);
    setTimeout(() => {
      node.classList.add('leaving');
      setTimeout(() => node.remove(), 240);
    }, 3200);
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const area = document.createElement('textarea');
        area.value = text;
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
      }
      toast('已复制到剪贴板', 'success');
    } catch (error) {
      toast('复制失败，请手动选择文本', 'error');
    }
  }

  /* -------------------------------------------------------------- 数据视图 */
  function groupCounts() {
    const map = new Map();
    state.contacts.forEach((contact) => {
      if (!contact.group) return;
      map.set(contact.group, (map.get(contact.group) || 0) + 1);
    });
    return Array.from(map, ([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-Hans-CN'));
  }

  function visibleContacts() {
    const keyword = state.query.trim().toLowerCase();
    const list = state.contacts.filter((contact) => {
      if (state.filter.kind === 'starred' && !contact.starred) return false;
      if (state.filter.kind === 'group' && contact.group !== state.filter.group) return false;
      if (!keyword) return true;
      const haystack = [
        contact.name, contact.company, contact.department, contact.title,
        contact.group, contact.note, ...contact.methods.map((method) => method.value),
      ].join(' ').toLowerCase();
      return haystack.includes(keyword);
    });

    const byName = (a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN');
    if (state.sort === 'name') list.sort(byName);
    else if (state.sort === 'updated') list.sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
    else list.sort((a, b) => Number(b.starred) - Number(a.starred) || byName(a, b));
    return list;
  }

  function titleForFilter() {
    if (state.query.trim()) return '搜索结果';
    if (state.filter.kind === 'starred') return '星标联系人';
    if (state.filter.kind === 'group') return `分组 · ${state.filter.group}`;
    return '全部联系人';
  }

  /* ---------------------------------------------------------------- 渲染层 */
  function renderAll() {
    renderSidebar();
    renderStats();
    renderQuick();
    renderList();
    if (state.openId && findContact(state.openId)) renderDrawer();
  }

  function renderSidebar() {
    els.pillAll.textContent = state.contacts.length;
    els.pillStarred.textContent = state.contacts.filter((contact) => contact.starred).length;

    $$('.nav-item').forEach((item) => {
      const isAll = item.dataset.filter === 'all' && state.filter.kind === 'all';
      const isStarred = item.dataset.filter === 'starred' && state.filter.kind === 'starred';
      item.classList.toggle('active', isAll || isStarred);
    });

    const groups = groupCounts();
    els.groupTotal.textContent = groups.length ? `${groups.length} 个` : '';
    els.groupNav.innerHTML = groups.length
      ? groups.map((group, index) => `
        <a class="group-item${state.filter.kind === 'group' && state.filter.group === group.name ? ' active' : ''}"
           href="#/group/${encodeURIComponent(group.name)}">
          <span class="group-dot" style="--c:${GROUP_COLORS[index % GROUP_COLORS.length]}"></span>
          <span>${escapeHtml(group.name)}</span>
          <span class="group-count">${group.count}</span>
        </a>`).join('')
      : '<div class="side-empty" style="padding:4px 12px;font-size:12px;color:#b6c2d4">暂无分组</div>';
  }

  function renderStats() {
    const total = state.contacts.length;
    const starred = state.contacts.filter((contact) => contact.starred).length;
    const methods = state.contacts.reduce((sum, contact) => sum + contact.methods.length, 0);
    const groups = groupCounts().length;
    els.stats.innerHTML = `
      <div class="stat">
        <div class="stat-ic">${icon('users')}</div>
        <div><div class="stat-num">${total}</div><div class="stat-label">联系人总数</div></div>
      </div>
      <div class="stat">
        <div class="stat-ic gold">${icon('star')}</div>
        <div><div class="stat-num">${starred}</div><div class="stat-label">星标联系人</div></div>
      </div>
      <div class="stat">
        <div class="stat-ic green">${icon('phone')}</div>
        <div><div class="stat-num">${methods}</div><div class="stat-label">联系方式 · ${groups} 个分组</div></div>
      </div>`;
  }

  function renderQuick() {
    const starred = state.contacts.filter((contact) => contact.starred);
    const visible = state.filter.kind === 'all' && !state.query.trim() && starred.length > 0;
    els.quickSection.hidden = !visible;
    if (!visible) return;
    els.quickSub.textContent = `${starred.length} 位常用联系人，点击卡片快速查看`;
    els.quickTrack.innerHTML = starred.slice(0, 8).map((contact) => {
      const method = primaryMethod(contact);
      return `
        <div class="quick-card" data-id="${contact.id}" role="button" tabindex="0">
          <span class="q-star">${icon('star')}</span>
          ${avatarHtml(contact, 'sm')}
          <div class="quick-body">
            <div class="q-name">${escapeHtml(contact.name)}</div>
            <div class="q-sub">${method ? escapeHtml(method.value) : '暂无联系方式'}</div>
          </div>
        </div>`;
    }).join('');
  }

  function renderList() {
    const list = visibleContacts();
    els.listTitle.textContent = titleForFilter();
    const meta = [`${list.length} 位联系人`];
    if (state.query.trim()) meta.push(`关键词「${state.query.trim()}」`);
    if (state.filter.kind === 'starred') meta.push('按星标筛选');
    els.listSub.textContent = meta.join(' · ');

    els.contactView.className = `contact-view ${state.view}`;
    if (!list.length) {
      els.contactView.innerHTML = emptyHtml();
      return;
    }
    els.contactView.innerHTML = state.view === 'cards'
      ? list.map(cardHtml).join('')
      : list.map(rowHtml).join('');
  }

  function rowHtml(contact) {
    const role = [contact.title, contact.company].filter(Boolean).map((part) => highlight(part)).join(' · ');
    const phone = contact.methods.find((method) => method.type === 'phone');
    const secondary = contact.methods.find((method) => method.type !== 'phone');
    const fact = (method) => (method
      ? `<div class="row-method">${icon(typeIcon(method.type))}<span>${highlight(method.value)}</span></div>`
      : '<div class="row-method muted">—</div>');
    return `
      <div class="row" data-id="${contact.id}" tabindex="0" role="button" aria-label="查看 ${escapeHtml(contact.name)}">
        ${avatarHtml(contact)}
        <div class="row-main">
          <div class="row-name">${highlight(contact.name)}${contact.group ? `<span class="chip">${escapeHtml(contact.group)}</span>` : ''}</div>
          <div class="row-sub">${role || '<span class="muted">未填写公司 / 职位</span>'}</div>
        </div>
        <div class="row-fact">${fact(phone)}</div>
        <div class="row-fact">${fact(secondary)}</div>
        <div class="row-group">${contact.methods.length ? `<span class="chip">${contact.methods.length} 项</span>` : ''}</div>
        <div class="row-actions">
          <button class="star-btn${contact.starred ? ' on' : ''}" data-action="star" title="${contact.starred ? '取消星标' : '加入星标'}" aria-label="切换星标">${icon('star')}</button>
          <button class="icon-btn" data-action="edit" title="编辑">${icon('edit')}</button>
          <button class="icon-btn danger" data-action="delete" title="删除">${icon('trash')}</button>
        </div>
      </div>`;
  }

  function cardHtml(contact) {
    const methods = contact.methods.slice(0, 2);
    const role = [contact.title, contact.company].filter(Boolean).join(' · ');
    return `
      <article class="card" data-id="${contact.id}" tabindex="0" role="button" aria-label="查看 ${escapeHtml(contact.name)}">
        <button class="star-btn card-star${contact.starred ? ' on' : ''}" data-action="star" title="切换星标">${icon('star')}</button>
        <header class="card-head">
          ${avatarHtml(contact)}
          <div style="min-width:0">
            <div class="card-name">${escapeHtml(contact.name)}</div>
            <div class="card-sub">${role ? escapeHtml(role) : '未填写公司 / 职位'}</div>
          </div>
        </header>
        <div class="card-methods">
          ${methods.length ? methods.map((method) => `
            <div class="card-method">${icon(typeIcon(method.type))}<span>${escapeHtml(method.value)}</span></div>`).join('')
            : '<div class="card-method muted">暂无联系方式</div>'}
        </div>
        <div class="card-note">${contact.note ? escapeHtml(contact.note) : '&nbsp;'}</div>
        <footer class="card-foot">
          <span>${contact.group ? escapeHtml(contact.group) : '未分组'}</span>
          <span>${contact.methods.length} 项联系方式</span>
        </footer>
      </article>`;
  }

  function emptyHtml() {
    if (state.query.trim()) {
      return `
        <div class="empty">
          <div class="empty-ic">${icon('search')}</div>
          <h3>没有找到匹配的联系人</h3>
          <p>没有与「${escapeHtml(state.query.trim())}」相关的记录，换个关键词试试，或者新建一个联系人。</p>
          <button class="btn btn-soft" id="emptyNew">${icon('plus')}新建联系人</button>
        </div>`;
    }
    if (state.filter.kind === 'starred') {
      return `
        <div class="empty">
          <div class="empty-ic">${icon('star')}</div>
          <h3>还没有星标联系人</h3>
          <p>点击联系人右侧的星标图标，即可把常用联系人固定到「常用联系人」区域，随时快速访问。</p>
        </div>`;
    }
    if (state.filter.kind === 'group') {
      return `
        <div class="empty">
          <div class="empty-ic">${icon('users')}</div>
          <h3>该分组下暂无联系人</h3>
          <p>可以新建联系人时填写分组，或在编辑已有联系人时补充分组信息。</p>
          <button class="btn btn-soft" id="emptyNew">${icon('plus')}新建联系人</button>
        </div>`;
    }
    return `
      <div class="empty">
        <div class="empty-ic">${icon('users')}</div>
        <h3>通讯录还是空的</h3>
        <p>手动新建第一位联系人，或者从 Excel 批量导入已有的通讯录，几秒钟就能开始使用。</p>
        <button class="btn btn-primary" id="emptyNew">${icon('plus')}新建联系人</button>
      </div>`;
  }

  function renderDrawer() {
    const contact = findContact(state.openId);
    if (!contact) return;
    const role = [contact.title, contact.department, contact.company].filter(Boolean).join(' · ');
    const methods = contact.methods.slice().sort((a, b) => {
      const order = state.meta.types.map((type) => type.key);
      return order.indexOf(a.type) - order.indexOf(b.type);
    });

    els.drawer.innerHTML = `
      <div class="drawer-head">
        <button class="icon-btn drawer-close" data-action="close" aria-label="关闭">${icon('close')}</button>
        <div class="drawer-top">
          ${avatarHtml(contact, 'lg')}
          <div style="min-width:0">
            <div class="drawer-name">${escapeHtml(contact.name)}</div>
            <div class="drawer-role">${role ? escapeHtml(role) : '暂无职位信息'}</div>
            <div class="drawer-chips">
              ${contact.group ? `<span class="chip">${escapeHtml(contact.group)}</span>` : ''}
              ${contact.starred ? '<span class="chip" style="background:#fff7e6;color:#b45309">★ 星标</span>' : ''}
              <span class="chip">${contact.methods.length} 项联系方式</span>
            </div>
          </div>
        </div>
        <div class="drawer-actions">
          <button class="btn btn-soft${contact.starred ? ' is-starred' : ''}" data-action="star">${icon('star', contact.starred ? 'filled' : '')}${contact.starred ? '取消星标' : '设为星标'}</button>
          <button class="btn btn-primary" data-action="edit">${icon('edit')}编辑</button>
          <button class="btn btn-soft" data-action="delete" aria-label="删除">${icon('trash')}</button>
        </div>
      </div>
      <div class="drawer-body">
        <div class="d-section">
          <div class="d-title">联系方式</div>
          ${methods.length ? methods.map((method) => `
            <div class="method">
              <div class="method-ic">${icon(typeIcon(method.type))}</div>
              <div style="min-width:0">
                <div class="method-label">${escapeHtml([typeLabel(method.type), method.label].filter(Boolean).join(' · '))}</div>
                <div class="method-value">${escapeHtml(method.value)}${method.primary ? '<span class="badge-primary">主</span>' : ''}</div>
              </div>
              <button class="icon-btn" data-copy="${escapeHtml(method.value)}" title="复制">${icon('copy')}</button>
            </div>`).join('') : '<div class="note-box">暂无联系方式，点击「编辑」补充</div>'}
        </div>
        ${contact.note ? `
        <div class="d-section">
          <div class="d-title">备注</div>
          <div class="note-box">${escapeHtml(contact.note)}</div>
        </div>` : ''}
        <div class="d-section">
          <div class="d-title">记录信息</div>
          <div class="meta-list">
            <div>创建时间：<b>${escapeHtml(contact.created_at)}</b></div>
            <div>最近更新：<b>${escapeHtml(contact.updated_at)}</b></div>
            <div>记录编号：#${contact.id}</div>
          </div>
        </div>
      </div>`;
  }

  /* ------------------------------------------------------------ 抽屉交互 */
  function openDrawer(id, { syncHash = false } = {}) {
    const contact = findContact(id);
    if (!contact) return;
    state.openId = Number(id);
    renderDrawer();
    els.drawer.classList.add('open');
    els.drawerMask.classList.add('show');
    els.drawer.setAttribute('aria-hidden', 'false');
    if (syncHash) window.history.replaceState(null, '', `#/contact/${id}`);
  }

  function closeDrawer({ syncHash = true } = {}) {
    els.drawer.classList.remove('open');
    els.drawerMask.classList.remove('show');
    els.drawer.setAttribute('aria-hidden', 'true');
    state.openId = null;
    if (syncHash && location.hash.startsWith('#/contact/')) navigate(state.filterHash, true);
  }

  async function toggleStar(contact, sourceButton = null) {
    const next = !contact.starred;
    contact.starred = next; // 乐观更新，失败时回滚
    renderAll();
    try {
      const updated = await api(`/contacts/${contact.id}/star`, { method: 'PATCH', body: { starred: next } });
      Object.assign(contact, updated);
      renderAll();
      toast(next ? `已将「${contact.name}」加入星标` : `已取消「${contact.name}」的星标`, next ? 'success' : 'info');
    } catch (error) {
      contact.starred = !next;
      renderAll();
      toast(error.message, 'error');
    }
  }

  /* -------------------------------------------------------------- 弹窗管理 */
  function showModal(root) {
    root.hidden = false;
    window.requestAnimationFrame(() => root.classList.add('show'));
  }

  function hideModal(root) {
    root.classList.remove('show');
    window.setTimeout(() => {
      if (!root.classList.contains('show')) {
        root.hidden = true;
        root.innerHTML = '';
      }
    }, 220);
  }

  function closeModal() {
    hideModal(els.modalRoot);
    if (/^#\/(new|edit|import)/.test(location.hash)) navigate(state.filterHash, true);
  }

  /* ---------------------------------------------------------------- 编辑器 */
  function methodRowHtml(method, index = 0) {
    const typeOptions = state.meta.types.map((type) =>
      `<option value="${type.key}"${type.key === method.type ? ' selected' : ''}>${escapeHtml(type.label)}</option>`).join('');
    const labelOptions = [''].concat(state.meta.labels).map((label) =>
      `<option value="${escapeHtml(label)}"${label === (method.label || '') ? ' selected' : ''}>${label ? escapeHtml(label) : '未标注'}</option>`).join('');
    return `
      <div class="method-row" data-row>
        <select data-type aria-label="联系方式类型">${typeOptions}</select>
        <select data-label aria-label="联系场景">${labelOptions}</select>
        <input data-value value="${escapeHtml(method.value || '')}" placeholder="如 13800000000 / name@example.com" />
        <label class="primary-toggle" title="设为主联系方式">
          <input type="radio" name="primaryMethod" data-primary${method.primary ? ' checked' : ''} />主
        </label>
        <button type="button" class="icon-btn danger" data-remove title="删除该行">${icon('trash')}</button>
      </div>`;
  }

  function editorHtml(contact) {
    const groups = Array.from(new Set(state.meta.groups.map((group) => group.name).concat(contact.group ? [contact.group] : [])));
    return `
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="editorTitle">
        <div class="modal-head">
          <div>
            <h3 id="editorTitle">${contact.id ? '编辑联系人' : '新建联系人'}</h3>
            <p>一个联系人可以保存多条联系方式，并指定其中一条为主联系方式</p>
          </div>
          <button class="icon-btn" data-close aria-label="关闭">${icon('close')}</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">
            <div class="field">
              <label for="fName">姓名 <i>*</i></label>
              <input id="fName" name="name" type="text" maxlength="40" placeholder="请输入姓名" value="${escapeHtml(contact.name)}" />
              <span class="error-text">请填写姓名</span>
            </div>
            <div class="field">
              <label for="fGroup">分组</label>
              <input id="fGroup" name="group" type="text" maxlength="20" list="groupOptions" placeholder="如：工作 / 家人 / 同学" value="${escapeHtml(contact.group)}" />
              <datalist id="groupOptions">
                ${groups.map((group) => `<option value="${escapeHtml(group)}"></option>`).join('')}
              </datalist>
            </div>
            <div class="field">
              <label for="fCompany">公司 / 单位</label>
              <input id="fCompany" name="company" type="text" maxlength="60" placeholder="选填" value="${escapeHtml(contact.company)}" />
            </div>
            <div class="field">
              <label for="fDepartment">部门</label>
              <input id="fDepartment" name="department" type="text" maxlength="60" placeholder="选填" value="${escapeHtml(contact.department)}" />
            </div>
            <div class="field">
              <label for="fTitle">职位</label>
              <input id="fTitle" name="title" type="text" maxlength="60" placeholder="选填" value="${escapeHtml(contact.title)}" />
            </div>
            <div class="field">
              <label>星标</label>
              <label class="switch">
                <input type="checkbox" name="starred"${contact.starred ? ' checked' : ''} />
                <span class="track"></span>
                <span>加入常用联系人</span>
              </label>
            </div>
            <div class="field full">
              <label for="fNote">备注</label>
              <textarea id="fNote" name="note" maxlength="500" placeholder="选填，例如：周三下午在办公室">${escapeHtml(contact.note)}</textarea>
            </div>
          </div>

          <div class="methods-head">
            <h4>联系方式</h4>
            <span>支持电话、邮箱、微信、QQ、地址等类型</span>
          </div>
          <div class="method-rows" id="methodRows">
            ${contact.methods.map((method) => methodRowHtml(method)).join('')}
          </div>
          <button type="button" class="btn btn-soft add-method" id="addMethod">${icon('plus')}添加联系方式</button>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" data-close>取消</button>
          <button class="btn btn-primary" id="saveContact">保存</button>
        </div>
      </div>`;
  }

  function openEditor(contact = null) {
    state.editingId = contact ? contact.id : null;
    const model = contact
      ? JSON.parse(JSON.stringify(contact))
      : { name: '', group: '', company: '', department: '', title: '', note: '', starred: false, methods: [{ type: 'phone', label: '工作', value: '', primary: true }] };
    if (!model.methods.length) model.methods.push({ type: 'phone', label: '', value: '', primary: true });

    els.modalRoot.innerHTML = editorHtml(model);
    showModal(els.modalRoot);

    const nameInput = $('#fName', els.modalRoot);
    window.setTimeout(() => nameInput?.focus(), 80);

    $('#addMethod', els.modalRoot).addEventListener('click', () => {
      const rows = $('#methodRows', els.modalRoot);
      if (rows.children.length >= 20) { toast('最多添加 20 条联系方式', 'error'); return; }
      rows.insertAdjacentHTML('beforeend', methodRowHtml({ type: 'other', label: '', value: '', primary: false }));
      const last = rows.lastElementChild.querySelector('[data-value]');
      last?.focus();
    });

    $('#methodRows', els.modalRoot).addEventListener('click', (event) => {
      const remove = event.target.closest('[data-remove]');
      if (!remove) return;
      const rows = $('#methodRows', els.modalRoot);
      if (rows.children.length <= 1) { toast('至少保留一条联系方式', 'info'); return; }
      remove.closest('.method-row').remove();
    });

    $('#methodRows', els.modalRoot).addEventListener('change', (event) => {
      if (event.target.matches('[data-primary]')) {
        $$('[data-primary]', els.modalRoot).forEach((radio) => { if (radio !== event.target) radio.checked = false; });
      }
    });

    $('#saveContact', els.modalRoot).addEventListener('click', saveContact);
    $$('[data-close]', els.modalRoot).forEach((button) => button.addEventListener('click', closeModal));

    $$('.field input, .field textarea', els.modalRoot).forEach((input) => {
      input.addEventListener('input', () => input.closest('.field')?.classList.remove('invalid'));
    });
  }

  function collectForm() {
    const value = (name) => ($(`[name="${name}"]`, els.modalRoot)?.value || '').trim();
    const methods = $$('.method-row', els.modalRoot).map((row) => ({
      type: row.querySelector('[data-type]').value,
      label: row.querySelector('[data-label]').value,
      value: row.querySelector('[data-value]').value.trim(),
      primary: row.querySelector('[data-primary]').checked,
    })).filter((method) => method.value);
    return {
      name: value('name'),
      group: value('group'),
      company: value('company'),
      department: value('department'),
      title: value('title'),
      note: value('note'),
      starred: $('[name="starred"]', els.modalRoot).checked,
      methods,
    };
  }

  async function saveContact() {
    const payload = collectForm();
    const nameField = $('#fName', els.modalRoot).closest('.field');
    if (!payload.name) {
      nameField.classList.add('invalid');
      $('#fName', els.modalRoot).focus();
      return;
    }

    const button = $('#saveContact', els.modalRoot);
    button.disabled = true;
    button.textContent = '保存中…';

    try {
      const id = state.editingId;
      const saved = id
        ? await api(`/contacts/${id}`, { method: 'PUT', body: payload })
        : await api('/contacts', { method: 'POST', body: payload });
      const wasEditing = Boolean(id);
      closeModal();
      await loadContacts();
      renderAll();
      toast(wasEditing ? '联系人已更新' : `已添加联系人「${saved.name}」`, 'success');
      if (wasEditing) openDrawer(saved.id);
    } catch (error) {
      toast(error.message, 'error');
      button.disabled = false;
      button.textContent = '保存';
    }
  }

  /* ------------------------------------------------------------ 删除确认 */
  function confirmDelete(contact) {
    const root = els.confirmRoot;
    root.innerHTML = `
      <div class="modal small" role="dialog" aria-modal="true" aria-labelledby="confirmTitle">
        <div class="modal-head">
          <div><h3 id="confirmTitle">删除联系人</h3><p>该操作不可撤销</p></div>
          <button class="icon-btn" data-no aria-label="关闭">${icon('close')}</button>
        </div>
        <div class="modal-body">
          <p class="confirm-text">确定要删除 <b>${escapeHtml(contact.name)}</b> 吗？该联系人的全部联系方式也会一并删除。</p>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" data-no>取消</button>
          <button class="btn btn-danger" data-yes>${icon('trash')}删除</button>
        </div>
      </div>`;
    showModal(root);

    return new Promise((resolve) => {
      const finish = (ok) => { hideModal(root); resolve(ok); };
      $$('[data-no]', root).forEach((button) => button.addEventListener('click', () => finish(false)));
      $('[data-yes]', root).addEventListener('click', async () => {
        try {
          await api(`/contacts/${contact.id}`, { method: 'DELETE' });
          await loadContacts();
          closeDrawer();
          renderAll();
          toast(`已删除「${contact.name}」`, 'success');
          finish(true);
        } catch (error) {
          toast(error.message, 'error');
          finish(false);
        }
      });
    });
  }

  /* -------------------------------------------------------------- 导入面板 */
  function importHtml() {
    return `
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="importTitle">
        <div class="modal-head">
          <div>
            <h3 id="importTitle">导入 Excel</h3>
            <p>每行一个联系人，同一类型的多个联系方式分列填写</p>
          </div>
          <button class="icon-btn" data-close aria-label="关闭">${icon('close')}</button>
        </div>
        <div class="modal-body">
          <label class="dropzone" id="dropzone" for="importFile">
            <input type="file" id="importFile" accept=".xlsx,.xlsm" hidden />
            <div class="dz-ic">${icon('upload')}</div>
            <div class="dz-title">点击选择文件，或把文件拖到这里</div>
            <div class="dz-hint">仅支持 .xlsx 格式，10MB 以内 · <a href="/api/template" id="tplLink">下载导入模板</a></div>
          </label>
          <div id="fileInfo"></div>

          <div class="import-options">
            <div class="opt-title">导入方式</div>
            <div class="mode-pills">
              <label class="mode-pill">
                <input type="radio" name="importMode" value="merge" checked />
                合并 <small>姓名与联系方式相同则更新</small>
              </label>
              <label class="mode-pill">
                <input type="radio" name="importMode" value="insert" />
                全部新增 <small>不去重，直接追加</small>
              </label>
            </div>
          </div>

          <div class="import-tip">
            ${icon('info')}
            <span>表头需包含「姓名」列，其余列按名称识别：分组、公司、部门、职位、电话1/2、邮箱、微信、QQ、地址、备注、星标。错误行会被跳过并给出行号。</span>
          </div>

          <div id="importReport"></div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" data-close>取消</button>
          <button class="btn btn-primary" id="doImport" disabled>开始导入</button>
        </div>
      </div>`;
  }

  function openImport() {
    state.importFile = null;
    els.modalRoot.innerHTML = importHtml();
    showModal(els.modalRoot);

    const fileInput = $('#importFile', els.modalRoot);
    const dropzone = $('#dropzone', els.modalRoot);

    fileInput.addEventListener('change', () => {
      if (fileInput.files && fileInput.files[0]) selectImportFile(fileInput.files[0]);
    });
    ['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add('drag');
    }));
    ['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.remove('drag');
    }));
    dropzone.addEventListener('drop', (event) => {
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) selectImportFile(file);
    });

    $('#tplLink', els.modalRoot).addEventListener('click', (event) => {
      event.preventDefault();
      downloadFile('/api/template', '通讯录导入模板.xlsx');
    });

    $$('[data-close]', els.modalRoot).forEach((button) => button.addEventListener('click', closeModal));
    $('#doImport', els.modalRoot).addEventListener('click', doImport);
  }

  function selectImportFile(file) {
    if (!/\.(xlsx|xlsm)$/i.test(file.name)) {
      toast('请选择 .xlsx 格式的 Excel 文件', 'error');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast('文件超过 10MB，请拆分后再导入', 'error');
      return;
    }
    state.importFile = file;
    $('#fileInfo', els.modalRoot).innerHTML = `
      <div class="file-chip">
        ${icon('file')}
        <span>${escapeHtml(file.name)}</span>
        <span class="file-size">${formatBytes(file.size)}</span>
        <button class="icon-btn" id="clearFile" title="移除">${icon('close')}</button>
      </div>`;
    const button = $('#doImport', els.modalRoot);
    button.disabled = false;
    button.textContent = '开始导入';
    $('#clearFile', els.modalRoot).addEventListener('click', () => {
      state.importFile = null;
      $('#fileInfo', els.modalRoot).innerHTML = '';
      $('#importFile', els.modalRoot).value = '';
      button.disabled = true;
    });
  }

  async function doImport() {
    if (!state.importFile) return;
    const button = $('#doImport', els.modalRoot);
    const mode = ($('input[name="importMode"]:checked', els.modalRoot) || {}).value || 'merge';
    button.disabled = true;
    button.textContent = '导入中…';

    const form = new FormData();
    form.append('file', state.importFile);
    form.append('mode', mode);

    try {
      const report = await api('/import', { method: 'POST', form });
      await loadContacts();
      renderAll();
      renderImportReport(report);
      toast(
        `导入完成：新增 ${report.imported} 条，更新 ${report.updated} 条${report.failed ? `，${report.failed} 行失败` : ''}`,
        report.failed ? 'info' : 'success'
      );
      button.textContent = '继续导入';
      button.disabled = false;
    } catch (error) {
      toast(error.message, 'error');
      button.textContent = '开始导入';
      button.disabled = false;
    }
  }

  function renderImportReport(report) {
    const errors = report.errors || [];
    $('#importReport', els.modalRoot).innerHTML = `
      <div class="report">
        <div class="report-item"><div class="report-num green">${report.imported}</div><div class="report-label">新增联系人</div></div>
        <div class="report-item"><div class="report-num blue">${report.updated}</div><div class="report-label">合并更新</div></div>
        <div class="report-item"><div class="report-num red">${report.failed}</div><div class="report-label">跳过 / 失败</div></div>
      </div>
      ${errors.length ? `
        <div class="report-errors">
          <table>
            <thead><tr><th>行号</th><th>失败原因</th></tr></thead>
            <tbody>
              ${errors.map((error) => `<tr><td>第 ${error.row} 行</td><td>${escapeHtml(error.message)}</td></tr>`).join('')}
            </tbody>
          </table>
        </div>
        ${report.errors_truncated ? '<p class="import-tip">仅展示前 50 条错误，其余错误已忽略。</p>' : ''}`
        : `<p class="import-tip" style="margin-top:12px">${icon('check')}<span>全部 ${report.total} 行数据导入成功，没有错误行。</span></p>`}`;
  }

  /* ------------------------------------------------------------ 导出/下载 */
  async function downloadFile(url, fallbackName) {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error((payload && payload.error && payload.error.message) || `下载失败（HTTP ${response.status}）`);
      }
      const blob = await response.blob();
      const disposition = response.headers.get('Content-Disposition') || '';
      const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition) || /filename="?([^";]+)"?/i.exec(disposition);
      const filename = match ? decodeURIComponent(match[1]) : fallbackName;
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(link.href), 2000);
      return filename;
    } catch (error) {
      toast(error.message, 'error');
      return null;
    }
  }

  function exportQuery() {
    const params = new URLSearchParams();
    if (state.filter.kind === 'starred') params.set('starred', '1');
    if (state.filter.kind === 'group') params.set('group', state.filter.group);
    if (state.query.trim()) params.set('q', state.query.trim());
    const query = params.toString();
    return query ? `?${query}` : '';
  }

  async function exportExcel() {
    toast('正在生成 Excel…', 'info');
    const filename = await downloadFile(`/api/export${exportQuery()}`, '通讯录.xlsx');
    if (filename) toast(`已导出 ${filename}`, 'success');
  }

  /* ------------------------------------------------------------------ 路由 */
  function navigate(hash, replace = false) {
    if (replace) {
      if (location.hash === hash) return;
      window.history.replaceState(null, '', hash);
      applyRoute();
    } else if (location.hash !== hash) {
      location.hash = hash;
    }
  }

  function setFilter(filter) {
    state.filter = filter;
    state.filterHash = filter.kind === 'all'
      ? '#/all'
      : filter.kind === 'starred'
        ? '#/starred'
        : `#/group/${encodeURIComponent(filter.group)}`;
    closeDrawer({ syncHash: false });
    renderAll();
    if (!location.hash) window.history.replaceState(null, '', state.filterHash);
  }

  function applyRoute() {
    const parts = location.hash.replace(/^#/, '').split('/').filter(Boolean).map(decodeURIComponent);
    const head = parts[0] || 'all';

    if (head === 'contact') {
      const contact = findContact(Number(parts[1]));
      if (contact) openDrawer(contact.id);
      else setFilter({ kind: 'all' });
      return;
    }
    if (head === 'edit') { openEditor(findContact(Number(parts[1])) || null); return; }
    if (head === 'new') { openEditor(null); return; }
    if (head === 'import') { openImport(); return; }
    if (head === 'starred') { setFilter({ kind: 'starred' }); return; }
    if (head === 'group' && parts[1]) { setFilter({ kind: 'group', group: parts.slice(1).join('/') }); return; }
    setFilter({ kind: 'all' });
  }

  /* -------------------------------------------------------------- 事件绑定 */
  function bindEvents() {
    els.contactView.addEventListener('click', (event) => {
      const actionEl = event.target.closest('[data-action]');
      const container = event.target.closest('[data-id]');
      if (!container) {
        if (event.target.closest('#emptyNew')) openEditor(null);
        return;
      }
      const contact = findContact(container.dataset.id);
      if (!contact) return;
      if (actionEl) {
        event.stopPropagation();
        const action = actionEl.dataset.action;
        if (action === 'star') toggleStar(contact, actionEl);
        else if (action === 'edit') openEditor(contact);
        else if (action === 'delete') confirmDelete(contact);
        return;
      }
      openDrawer(contact.id);
    });

    els.contactView.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const container = event.target.closest('[data-id]');
      if (!container) return;
      event.preventDefault();
      openDrawer(Number(container.dataset.id));
    });

    els.quickTrack.addEventListener('click', (event) => {
      const card = event.target.closest('[data-id]');
      if (card) openDrawer(Number(card.dataset.id));
    });
    els.quickTrack.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const card = event.target.closest('[data-id]');
      if (!card) return;
      event.preventDefault();
      openDrawer(Number(card.dataset.id));
    });

    els.drawer.addEventListener('click', (event) => {
      const copyButton = event.target.closest('[data-copy]');
      if (copyButton) { copyText(copyButton.dataset.copy); return; }
      const actionEl = event.target.closest('[data-action]');
      const contact = findContact(state.openId);
      if (!actionEl || !contact) return;
      const action = actionEl.dataset.action;
      if (action === 'close') closeDrawer();
      else if (action === 'star') toggleStar(contact);
      else if (action === 'edit') openEditor(contact);
      else if (action === 'delete') confirmDelete(contact);
    });

    els.drawerMask.addEventListener('click', () => closeDrawer());

    els.searchInput.addEventListener('input', debounce(() => {
      state.query = els.searchInput.value;
      renderQuick();
      renderList();
    }, 90));

    els.searchInput.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        els.searchInput.value = '';
        state.query = '';
        renderQuick();
        renderList();
        els.searchInput.blur();
      }
    });

    els.sortSelect.addEventListener('change', () => {
      state.sort = els.sortSelect.value;
      renderList();
    });

    els.viewToggle.addEventListener('click', (event) => {
      const button = event.target.closest('[data-view]');
      if (!button) return;
      state.view = button.dataset.view;
      $$('button', els.viewToggle).forEach((item) => item.classList.toggle('active', item === button));
      try { window.localStorage.setItem('address-book:view', state.view); } catch (error) { /* 忽略 */ }
      renderList();
    });

    els.btnNew.addEventListener('click', () => openEditor(null));
    els.btnImport.addEventListener('click', openImport);
    els.btnExport.addEventListener('click', exportExcel);
    els.btnTemplate.addEventListener('click', async () => {
      const filename = await downloadFile('/api/template', '通讯录导入模板.xlsx');
      if (filename) toast('模板已下载，按表头填写后即可导入', 'success');
    });

    els.btnMenu.addEventListener('click', () => {
      els.sidebar.classList.add('open');
      els.sidebarMask.classList.add('show');
    });
    els.sidebarMask.addEventListener('click', closeSidebar);
    els.groupNav.addEventListener('click', (event) => {
      if (event.target.closest('.group-item')) closeSidebar();
    });

    els.modalRoot.addEventListener('click', (event) => {
      if (event.target === els.modalRoot) closeModal();
    });
    els.confirmRoot.addEventListener('click', (event) => {
      if (event.target === els.confirmRoot) $('[data-no]', els.confirmRoot)?.click();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        if (!els.confirmRoot.hidden) { $('[data-no]', els.confirmRoot)?.click(); return; }
        if (!els.modalRoot.hidden) { closeModal(); return; }
        if (state.openId) { closeDrawer(); return; }
        closeSidebar();
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        els.searchInput.focus();
        els.searchInput.select();
      }
    });

    window.addEventListener('hashchange', applyRoute);

    $$('button', els.viewToggle).forEach((button) => {
      button.classList.toggle('active', button.dataset.view === state.view);
    });
    els.sortSelect.value = state.sort;
  }

  function closeSidebar() {
    els.sidebar.classList.remove('open');
    els.sidebarMask.classList.remove('show');
  }

  /* ---------------------------------------------------------------- 启动 */
  async function boot() {
    bindEvents();
    try {
      await Promise.all([loadMeta(), loadContacts()]);
    } catch (error) {
      toast(`数据加载失败：${error.message}`, 'error');
    }
    renderAll();
    applyRoute();
  }

  boot();
})();

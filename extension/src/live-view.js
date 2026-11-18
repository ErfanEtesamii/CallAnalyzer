/* نمای زنده: چت هم‌زمان با رونویسی (کارشناس راست، مشتری چپ) + نوار مراحل + حالت «در حال تحلیل».
   همه‌ی متن پویا با textContent ساخته می‌شود (بدون innerHTML). وابسته به helperهای sidepanel.js (el, icon, api, call, fa, mmss, ...). */
'use strict';
const LiveView = (() => {
  const L = self.CALive;
  const POLL_MS = 1200;
  const HINTS = ['بررسی شروع تماس و معرفی', 'سنجش کشف نیاز و پرسش‌ها', 'بررسی مدیریت اعتراض‌ها', 'ارزیابی ارائه‌ی ارزش و مزیت‌ها', 'سنجش کلوزینگ و قدم بعدی', 'محاسبه‌ی امتیاز و جمع‌بندی'];
  let S = null; // وضعیت نمای جاری

  const stop = () => { if (S) { S.dead = true; clearTimeout(S.timer); clearInterval(S.clock); clearInterval(S.hintTimer); } S = null; };

  const nearBottom = () => innerHeight + scrollY >= document.documentElement.scrollHeight - 160;
  const toBottom = () => scrollTo({ top: document.documentElement.scrollHeight, behavior: reduceMotion ? 'auto' : 'smooth' });

  function build(info) {
    const root = el('section', 'live');
    const head = el('div', 'lv-head');
    const top = el('div', 'lv-top');
    const wave = el('span', 'lv-wave', null, { 'aria-hidden': 'true' });
    for (let i = 0; i < 5; i++) wave.append(el('i'));
    const who = el('div', 'lv-who');
    who.append(el('b', 'ltr', info.number || 'در حال پردازش'), el('span', null, info.sub || ''));
    const live = el('span', 'lv-pill'); live.append(el('i'), document.createTextNode('زنده'));
    top.append(wave, who, live);
    const steps = el('div', 'steps', null, { role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 5, 'aria-label': 'مرحله‌ی پردازش' });
    STEPS.forEach((s) => { const d = el('div'); d.append(el('i'), document.createTextNode(s)); steps.append(d); });
    head.append(top, steps);

    const chat = el('div', 'lv-chat', null, { role: 'log', 'aria-live': 'polite', 'aria-label': 'گفتگوی زنده' });
    const typing = el('div', 'msg s typing');
    const think = el('div', 'lv-think'); think.hidden = true;
    const jump = el('button', 'lv-jump'); jump.hidden = true; jump.append(icon('chevron'), document.createTextNode('پیام جدید'));
    jump.onclick = () => { toBottom(); jump.hidden = true; };
    const foot = el('div', 'lv-foot'); const status = el('span', 'lv-status'); const count = el('span', 'lv-count');
    foot.append(status, count);
    root.append(head, chat, think, foot, jump);
    return { root, steps, chat, typing, think, jump, status, count, wave };
  }

  function bubbleCol(speaker, t) {
    const row = el('div', 'msg ' + (speaker === L.CUSTOMER ? 'c' : 's'));
    const av = el('span', 'av'); av.append(icon(speaker === L.CUSTOMER ? 'user' : 'headset'));
    const col = el('div', 'col');
    col.append(el('small', null, (speaker === L.CUSTOMER ? 'مشتری' : 'کارشناس') + ' · ' + mmss(t)));
    const bub = el('div', 'bub'); col.append(bub); row.append(av, col);
    return { row, bub };
  }

  /** «(موسیقی)» / «(تلفن گویا)» به‌صورت برچسب وسط چت؛ برای تلفن گویا متن پیام هم زیرش می‌آید. */
  function sysNote(sg) {
    const row = el('div', 'sys ' + sg.speaker); const tag = el('span', 'tag');
    if (sg.speaker === 'music') { const eq = el('span', 'eq', null, { 'aria-hidden': 'true' }); for (let i = 0; i < 4; i++) eq.append(el('i')); tag.append(eq); }
    else tag.append(icon('phone'));
    tag.append(document.createTextNode('(' + L.SPECIAL[sg.speaker] + ')'));
    const body = el('div', 'sys-tx'); row.append(tag, body);
    return { row, body };
  }

  function typeInto(node, text) {
    if (reduceMotion) { node.textContent = text; return; }
    const words = text.split(' '); const dur = L.revealMs(text.length); const t0 = performance.now();
    node.textContent = '';
    const step = (now) => {
      if (!node.isConnected) { node.textContent = text; return; }
      const k = Math.min(words.length, Math.ceil(((now - t0) / dur) * words.length));
      node.textContent = words.slice(0, k).join(' ');
      if (k < words.length) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function addSegments(list) {
    if (!list.length) return;
    const stick = nearBottom() || !S.segs.length;
    S.typing.remove();
    for (const sg of list) {
      if (L.isSpecial(sg)) { // موسیقی/تلفن گویا: برچسب وسط چت، پشت‌سرهم‌ها یکی می‌شوند
        if (L.joinsRun(S.run, sg, 20)) { S.run.end = sg.end; if (sg.speaker === 'ivr') { const p = el('p', 'ln'); S.run.bub.append(p); typeInto(p, sg.text); } }
        else { const n = sysNote(sg); S.chat.append(n.row); if (sg.speaker === 'ivr') { const p = el('p', 'ln'); n.body.append(p); typeInto(p, sg.text); } S.run = { speaker: sg.speaker, end: sg.end, bub: n.body }; }
        S.segs.push(sg); continue;
      }
      if (L.joinsRun(S.run, sg)) {
        const p = el('p', 'ln'); S.run.bub.append(p); typeInto(p, sg.text); S.run.end = sg.end;
      } else {
        const b = bubbleCol(L.spOf(sg), sg.start); const p = el('p', 'ln'); b.bub.append(p); typeInto(p, sg.text);
        S.chat.append(b.row); S.run = { speaker: L.spOf(sg), end: sg.end, bub: b.bub };
      }
      S.segs.push(sg);
    }
    S.count.textContent = fa.format(S.segs.length) + ' جمله';
    placeTyping();
    if (stick) requestAnimationFrame(toBottom); else S.ui.jump.hidden = false;
  }

  function placeTyping() {
    if (S.status === 'analyzing' || S.finished) { S.typing.remove(); return; }
    const side = L.nextSide(S.segs);
    S.typing.className = 'msg ' + (side === L.CUSTOMER ? 'c' : 's') + ' typing';
    S.typing.replaceChildren();
    const av = el('span', 'av'); av.append(icon(side === L.CUSTOMER ? 'user' : 'headset'));
    const dots = el('div', 'bub dots', null, { 'aria-label': 'در حال شنیدن' }); for (let i = 0; i < 3; i++) dots.append(el('i'));
    S.typing.append(av, dots);
    S.chat.append(S.typing);
  }

  function setStage(serverStatus, jobState) {
    const idx = L.stageIndex(serverStatus, jobState);
    [...S.ui.steps.children].forEach((d, i) => { d.className = i < idx ? 'on' : i === idx ? 'cur' : ''; });
    S.ui.steps.setAttribute('aria-valuenow', Math.max(0, idx));
    S.status = serverStatus;
    const analyzing = serverStatus === 'analyzing';
    S.ui.think.hidden = !analyzing;
    S.ui.root.classList.toggle('is-analyzing', analyzing);
    S.ui.status.textContent = { preprocessing: 'آماده‌سازی صدا…', transcribing: 'در حال شنیدن و نوشتن…', analyzing: 'تحلیل کل مکالمه…' }[serverStatus]
      || { queued: 'در صف انتظار…', downloading: 'دانلود از پنل…', uploading: 'ارسال به سرور…' }[jobState] || 'در حال پردازش…';
    if (analyzing && !S.thinkBuilt) {
      S.thinkBuilt = true;
      const ic = el('span', 'orb'); ic.append(icon('logo', 'fill'));
      const tx = el('div', 'tx'); const h = el('b', null, 'در حال تحلیل کل مکالمه'); const hint = el('span', null, HINTS[0]);
      tx.append(h, hint); const bar = el('div', 'bar'); bar.append(el('i'));
      S.ui.think.append(ic, tx, bar);
      let k = 0; S.hintTimer = setInterval(() => { k = (k + 1) % HINTS.length; hint.textContent = HINTS[k]; }, 2200);
      requestAnimationFrame(toBottom);
    }
    placeTyping();
  }

  async function tick() {
    const my = S; if (!my || my.dead) return;
    let nextDelay = POLL_MS;
    try {
      if (!my.aid) { // هنوز روی سرور ساخته نشده: از کار افزونه و شناسه‌ی یکتا پیگیری می‌کنیم
        const r = await api('/api/v1/analyses/by-unique-id/' + encodeURIComponent(my.uid));
        if (S !== my) return;
        if (r.data && r.data.id) { my.aid = r.data.id; setStage(r.data.status, null); }
        else {
          const { jobs } = await call('GET_JOBS'); const j = (jobs || {})[my.uid];
          if (S !== my) return;
          if (j && j.state === 'error') { stop(); $('#view').replaceChildren(empty('alert', 'پردازش ناموفق بود', j.error || 'خطا', { label: 'تلاش دوباره', fn: () => call('RETRY', { uniqueId: my.uid }).then(() => setTab('queue')) })); return; }
          if (!j || j.state === 'done') { stop(); load(my.uid); return; }
          setStage(null, j.state); nextDelay = 1800;
        }
      } else {
        const r = await api('/api/v1/analyses/' + my.aid + '/live?after=' + my.next);
        if (S !== my) return;
        if (r.error) { if (r.code === 'auth' || r.code === 'no_config') { stop(); $('#view').replaceChildren(errState('اتصال برقرار نشد', r, () => load(my.uid))); return; } nextDelay = 3000; }
        else {
          const d = r.data; setStage(d.status, null);
          const known = new Set(my.segs.map((x) => x.i));
          addSegments(L.merge([], d.segments).list.filter((x) => !known.has(x.i))); // مرتب و بدون تکرار
          my.next = Math.max(my.next, d.next || 0);
          if (d.status === 'done' || d.status === 'failed') { my.finished = true; placeTyping(); setTimeout(() => { if (S === my) { stop(); load(my.uid); } }, d.status === 'done' ? 700 : 0); return; }
        }
      }
    } catch (e) { console.warn('live tick failed', e); nextDelay = 3000; }
    if (S === my && !my.dead) my.timer = setTimeout(tick, nextDelay);
  }

  /** نمایش نمای زنده. info: { uid, aid?, number?, sub? } */
  function show(info) {
    if (S && S.uid === info.uid && S.ui.root.isConnected) return; // همین نما در حال اجراست
    stop(); viewKind = 'live';
    const ui = build(info);
    S = { uid: info.uid, aid: info.aid || null, next: 0, segs: [], run: null, typing: ui.typing, chat: ui.chat, count: ui.count, ui, status: null, t0: Date.now() };
    $('#view').replaceChildren(ui.root);
    setStage(info.status || null, info.jobState || null);
    placeTyping();
    const t = el('span', 'lv-clock'); ui.count.after(t);
    S.clock = setInterval(() => { const s = Math.floor((Date.now() - S.t0) / 1000); t.textContent = mmss(s); }, 1000);
    S.timer = setTimeout(tick, 50);
  }

  addEventListener('scroll', () => { if (S && nearBottom()) S.ui.jump.hidden = true; }, { passive: true });
  const isShowing = (uid) => !!(S && S.uid === uid && S.ui.root.isConnected);
  return { show, stop, isShowing, sysNote };
})();

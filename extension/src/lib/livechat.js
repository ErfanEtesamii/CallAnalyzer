/* منطق خالص چت زنده (بدون DOM/chrome): ادغام حباب‌های تازه، گروه‌بندی نوبت‌ها، مرحله‌ی پردازش. قابل‌تست با Node. */
(function (root) {
  const SELLER = 'seller', CUSTOMER = 'customer';
  const SERVER_STEP = { preprocessing: 2, transcribing: 3, analyzing: 4 };
  const JOB_STEP = { queued: -1, downloading: 0, uploading: 1 };

  /** ادغام بدون تکرار با کلید i (ایدم‌پوتنت: polling تکراری چیزی را دوباره اضافه نمی‌کند). */
  function merge(existing, incoming) {
    const byI = new Map(existing.map((s) => [s.i, s]));
    let added = 0;
    for (const s of incoming || []) if (!byI.has(s.i)) { byI.set(s.i, s); added++; }
    return { list: [...byI.values()].sort((a, b) => a.i - b.i), added };
  }

  /** نوبت‌های پشت‌سرهم یک گوینده در یک «دسته» (مثل پیام‌های پشت‌سرهم در چت). */
  const SPECIAL = { music: 'موسیقی', ivr: 'تلفن گویا' };
  const isSpecial = (s) => !!s && s.speaker in SPECIAL;
  const spOf = (s) => (isSpecial(s) ? s.speaker : s.speaker === CUSTOMER ? CUSTOMER : SELLER); // برچسب ناشناخته = کارشناس
  /** آیا قطعه به دسته‌ی قبلی (همان گوینده و بدون وقفه‌ی طولانی) می‌چسبد؟ */
  const joinsRun = (run, s, gapSec = 6) => !!run && run.speaker === spOf(s) && s.start - run.end <= gapSec;

  function groupRuns(segs, gapSec = 6) {
    const runs = [];
    for (const s of segs) {
      const last = runs[runs.length - 1];
      if (joinsRun(last, s, gapSec)) { last.items.push(s); last.end = s.end; }
      else runs.push({ speaker: spOf(s), start: s.start, end: s.end, items: [s] });
    }
    return runs;
  }

  /** شاخص مرحله (۰..۴) از وضعیت کار افزونه یا وضعیت سرور؛ -1 = در صف. */
  function stageIndex(serverStatus, jobState) {
    if (serverStatus && serverStatus in SERVER_STEP) return SERVER_STEP[serverStatus];
    if (serverStatus === 'queued') return 2;
    if (jobState && jobState in JOB_STEP) return JOB_STEP[jobState];
    return 2;
  }

  /** حباب «در حال شنیدن…» سمت چه کسی بیاید: نوبت احتمالی بعدی (مخالف آخرین گوینده). */
  const nextSide = (segs) => {
    const human = segs.filter((x) => !isSpecial(x)); // موسیقی/تلفن گویا نوبت گفتگو را عوض نمی‌کند
    return human.length && human[human.length - 1].speaker === SELLER ? CUSTOMER : SELLER;
  };

  /** سرعت تایپ‌شدن حباب تازه (حرف بر ثانیه)؛ کل نمایش از maxMs بیشتر نمی‌شود. */
  const revealMs = (len, cps = 55, maxMs = 1400) => Math.min(maxMs, Math.max(250, (len / cps) * 1000));

  const api = { SELLER, CUSTOMER, SPECIAL, isSpecial, merge, groupRuns, joinsRun, spOf, stageIndex, nextSide, revealMs };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.CALive = api;
})(typeof self !== 'undefined' ? self : globalThis);

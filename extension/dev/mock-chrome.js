/* شبیه‌ساز chrome.* برای پیش‌نمایش پنل بدون نصب اکستنشن. فقط برای توسعه؛ در زیپ نهایی نیست. */
(() => {
  const q = new URLSearchParams(location.search);
  const T = (s) => s; const seg = (a, b, sp, text) => ({ start: a, end: b, speaker: sp, text });
  const segments = [
    seg(0, 6, 'S1', 'سلام وقت بخیر، من از مجموعه‌ی فراز هنر تماس می‌گیرم. با آقای رضایی صحبت می‌کنم؟'),
    seg(6, 8, 'S2', 'بله بفرمایید'),
    seg(8, 22, 'S1', 'ما هدیه‌های سازمانی از جنس صنایع‌دستی ایرانی تولید می‌کنیم. برای مناسبت‌های پایان سال هدیه‌ای برای همکاران در نظر دارید؟'),
    seg(22, 30, 'S2', 'آره، هر سال برای عید یه چیزی می‌دیم ولی هنوز تصمیم نگرفتیم'),
    seg(30, 44, 'S1', 'عالیه. معمولاً چه تعداد هدیه نیاز دارید و بودجه‌ی تقریبی برای هر نفر چقدره؟'),
    seg(44, 55, 'S2', 'حدود دویست نفر، شاید دو میلیون برای هر نفر. قیمت‌ها چطوره؟'),
    seg(55, 72, 'S1', 'قیمت بستگی به طرح داره. می‌تونم کاتالوگ رو بفرستم و طرح‌های ترمه و خاتم رو نشونتون بدم'),
    seg(72, 80, 'S2', 'کمی گرونه به نظر میاد، پارسال از یه جای دیگه گرفتیم'),
    seg(80, 100, 'S1', 'حتماً. مشکل کجا بود؟ از تأمین‌کننده‌ی قبلی راضی بودید؟ ما امکان چاپ نام روی بسته‌بندی هم داریم'),
    seg(100, 112, 'S2', 'کیفیت بسته‌بندیش خوب نبود. کاتالوگ رو بفرستید ببینم'),
    seg(112, 125, 'S1', 'چشم، همین امروز می‌فرستم. فردا ساعت ده زنگ بزنم نظرتون رو بپرسم؟'),
    seg(125, 135, 'S2', 'فردا بعدازظهر بهتره'),
    seg(135, 149, 'S1', 'باشه، فردا ساعت چهار. ممنون از وقتتون، روز خوبی داشته باشید'),
  ];
  const ev = (t, qt) => ({ timestamp: t, speaker: 'S1', quote: qt });
  const C = (id, name, score, extra = {}) => ({ id, name, score, applicable: score != null, confidence: .8, reasoning: extra.r || 'نمونه‌ی توضیح مدل درباره‌ی این معیار بر اساس شواهد مکالمه.', evidence: extra.e || [], improvement: extra.i || '', better_phrase_example: extra.b || '', max_score: 10 });
  const analysis = {
    id: 1, unique_id: 'demo.1', status: 'done', seller_ext: '14', seller_name: null, call_datetime: '2026-11-17T13:34:14', dst_masked: '0912***4302', real_duration: 149, percentile: 68,
    transcript: { provider: 'mock', segments },
    result: {
      call_validity: { is_analyzable: true, call_type: 'cold_new' }, summary: 'تماس سرد با مدیر منابع انسانی؛ علاقه‌ی اولیه و درخواست کاتالوگ.',
      participants: { seller_speaker: 'S1', customer_speaker: 'S2' },
      overall: { score: 72, grade: 'B', rank_label: 'خوب', confidence: .82, headline: 'شروع حرفه‌ای و کشف نیاز خوب؛ اعتراض قیمت بدون پرسش عمیق رد شد.' },
      warnings: ['تفکیک گوینده‌ها با اطمینان متوسط انجام شده است.'],
      customer_status: { stage: 'warm_followup', interest_level: 7,
        buying_signals: [{ timestamp: '00:44', quote: 'قیمت‌ها چطوره؟' }, { timestamp: '01:40', quote: 'کاتالوگ رو بفرستید ببینم' }],
        objections: [{ timestamp: '01:12', type: 'price', quote: 'کمی گرونه به نظر میاد', handled: false }] },
      next_best_action: { recommendation: 'ارسال کاتالوگ طرح‌های ترمه و خاتم تا پایان امروز', suggested_followup: 'پیگیری تلفنی فردا ساعت ۱۶', talking_points: ['مشکل بسته‌بندی تأمین‌کننده‌ی قبلی را بپرسید', 'نمونه‌ی چاپ نام روی بسته‌بندی را نشان دهید', 'ارزش را به‌جای قیمت هر عدد، روی مجموعه‌ی ۲۰۰ نفره بگویید'] },
      criteria: [
        C('opening_intro', 'شروع و معرفی', 8.5, { e: [ev('00:00', 'سلام وقت بخیر، من از مجموعه‌ی فراز هنر تماس می‌گیرم')], r: 'معرفی کوتاه و محترمانه با نام مجموعه انجام شد.' }),
        C('rapport_trust', 'ایجاد اعتماد و ارتباط', 7.5),
        C('needs_discovery', 'کشف نیاز', 8, { e: [ev('00:30', 'چه تعداد هدیه نیاز دارید و بودجه‌ی تقریبی برای هر نفر چقدره؟')] }),
        C('active_listening', 'گوش دادن فعال', 6.5, { i: 'پس از «حدود دویست نفر» یک جمله‌ی بازتابی بگویید تا مشتری حس شنیده‌شدن کند.' }),
        C('questioning_technique', 'تکنیک پرسشگری', 7),
        C('value_presentation', 'ارائه‌ی ارزش', 6, { e: [ev('00:55', 'قیمت بستگی به طرح داره')], i: 'قبل از اعلام قیمت، ارزش و تمایز را بگویید.', b: 'برای ۲۰۰ نفر معمولاً مجموعه‌ی ترمه را پیشنهاد می‌دهیم؛ هم اصیل است و هم نام شرکت روی بسته چاپ می‌شود.' }),
        C('objection_handling', 'مدیریت اعتراض', 4.5, { r: 'اعتراض قیمت با «حتماً» پذیرفته شد و پرسشی برای کشف ریشه‌ی آن مطرح نشد.', e: [ev('01:12', 'کمی گرونه به نظر میاد'), { timestamp: '01:30', speaker: 'S1', quote: 'جمله‌ای که در ترنسکریپت نیست', verified: false }], i: 'قبل از پاسخ، بپرسید «گران‌تر نسبت به چه؟».', b: 'گرون‌تر نسبت به چی؟ اگه بدونم مقایسه با کدوم طرحه، بهتر می‌تونم کمک کنم.' }),
        C('closing_next_step', 'گرفتن قدم بعدی', 9, { e: [ev('02:05', 'فردا ساعت ده زنگ بزنم نظرتون رو بپرسم؟')] }),
        C('followup_quality', 'کیفیت پیگیری', null),
        C('professionalism_ethics', 'حرفه‌ای‌گری و اخلاق', 9),
        C('call_control_structure', 'کنترل و ساختار تماس', 7.5),
        C('product_market_knowledge', 'دانش محصول و بازار', 5.5),
      ],
      seller_performance: { strengths: ['قدم بعدی دقیق و زمان‌دار گرفته شد', 'پرسش درباره‌ی تعداد و بودجه در زمان مناسب مطرح شد'], weaknesses: ['اعتراض قیمت بدون کاوش پذیرفته شد', 'ارزش محصول پیش از قیمت توضیح داده نشد'], compliance_flags: [{ type: 'تعهد بدون بررسی', severity: 'low', quote: 'همین امروز می‌فرستم' }] },
      coaching: { top_3_improvements: ['اعتراض قیمت را با پرسش «گران‌تر نسبت به چه؟» بشکافید.', 'پیش از قیمت، ۲ تمایز اصلی را بگویید (اصالت و چاپ نام).', 'پس از دریافت عدد تعداد، آن را بازگو کنید.'] },
      lead_info: { contact_name: 'آقای رضایی', contact_title: null, 'occasion(s)': ['عید', 'پایان سال'], budget_range: 'حدود ۲ میلیون برای هر نفر', volume: 'حدود ۲۰۰ نفر', previous_supplier: 'یک مجموعه‌ی دیگر (نامشخص)', timeline: null, main_challenges: 'کیفیت بسته‌بندی', decision_criteria: null, agreed_next_step: 'ارسال کاتالوگ و تماس فردا ساعت ۱۶', followup_datetime: null },
    },
  };
  const mk = (i, grade, score, ext, stage) => ({ id: i + 10, unique_id: 'h.' + i, status: 'done', seller_ext: ext, call_datetime: `2026-11-${10 + i}T1${i % 9}:20:00`, dst_masked: `0912***${4300 + i * 7}`, grade, overall_score: score, customer_stage: stage });
  const history = [mk(7, 'A', 91, '33', 'hot_ready'), mk(6, 'B', 72, '14', 'warm_followup'), mk(5, 'C', 61, '14', 'nurturing'), mk(4, 'D', 44, '14', 'not_now'), mk(3, 'F', 28, '33', 'lost_competitor'), mk(2, null, null, '14', 'no_conversation')];
  const store = { theme: q.get('theme') || 'auto', sellersText: '14=سارا محمدی\n33=علی کریمی', focusUid: 'demo.1', backendUrl: 'https://x.local', token: 't',
    jobs: { a: { state: 'processing', serverStatus: 'transcribing', updatedAt: 3, meta: { dst: '09120264302' } }, b: { state: 'downloading', updatedAt: 2, meta: { dst: '09355370600' } }, c: { state: 'done', updatedAt: 1, meta: { dst: '09122592580' } }, d: { state: 'error', error: 'نشست پنل منقضی شده؛ یک‌بار وارد پنل شوید.', updatedAt: 0, meta: { dst: '09127025479' } } } };
  if (q.get('setup')) { delete store.backendUrl; delete store.token; delete store.focusUid; }
  window.chrome = {
    storage: { local: { get: async (k) => { const o = {}; (Array.isArray(k) ? k : [k]).forEach((x) => { if (x in store) o[x] = store[x]; }); return o; }, set: async (o) => Object.assign(store, o), remove: async () => {} }, onChanged: { addListener() {} } },
    runtime: { openOptionsPage() {}, getManifest: () => ({ version: 'dev' }), sendMessage: async (m) => {
      if (m.type === 'GET_JOBS') return { jobs: store.jobs };
      if (m.type !== 'API') return { ok: true };
      const p = m.path;
      if (q.get('setup')) return { error: 'آدرس سرور و توکن را در تنظیمات وارد کنید.', code: 'no_config' };
      if (p === '/health') return { data: { ok: true } };
      if (q.get('empty') && p.startsWith('/api/v1/sellers')) return { data: [] };
      if (p.startsWith('/api/v1/analyses/by-unique-id') || p === '/api/v1/analyses/1') return { data: analysis };
      if (p.startsWith('/api/v1/analyses?')) return { data: { items: q.get('empty') ? [] : history } };
      if (p === '/api/v1/sellers/stats') return { data: [{ seller_ext: '33', calls: 12, avg_score: 81 }, { seller_ext: '14', calls: 20, avg_score: 66 }, { seller_ext: '15', calls: 5, avg_score: 49 }] };
      return { data: {} };
    } },
  };
  window.__tab = q.get('tab');
})();

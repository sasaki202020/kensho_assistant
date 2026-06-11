/* 売る前チェック iOSアプリ本体 (オフライン完結・外部送信なし)
 * 判定ロジックは sell_before_check_ai/logic.py と同じ rules.json(rules.js) を使用。
 */
(function () {
  'use strict';

  var APP_VERSION = (window.SBC_RULES && window.SBC_RULES.version) || '0.0.0';
  var RULES = window.SBC_RULES;
  var KEY_OPT = 'sbc_save_history';
  var KEY_HIST = 'sbc_history';

  var CHECK_TYPES = {
    flyer: 'チラシチェック',
    item: '商品チェック',
    quote: '見積もりチェック'
  };

  var CHECK_PAGES = {
    flyer: {
      title: 'チラシチェック',
      lead: 'ポストに入っていた買取チラシの文言を貼り付けてください。気になる表現がないか確認します。',
      placeholder: '例: どんなものでも高価買取! 本日限り査定額アップ! 無料査定だけでもOK!'
    },
    item: {
      title: '商品チェック',
      lead: '売ろうとしている品物の説明を入力してください。注意が必要な品目かどうか確認します。',
      placeholder: '例: 母の形見の18金のネックレスと着物を売ろうと思っています。'
    },
    quote: {
      title: '見積もりチェック',
      lead: '受け取った見積もりや業者の説明を入力してください。あいまいな表現や注意点を確認します。',
      placeholder: '例: 買取一式 30,000円。本日中なら特別価格。キャンセル不可と言われました。'
    }
  };

  var DISCLAIMER = 'この判定はキーワードに基づく参考情報です。正確な査定額・真贋・法律判断を保証するものではなく、特定の事業者についての評価でもありません。';
  var HOTLINE_NOTE = '迷ったら消費者ホットライン「188（いやや）」へ。最寄りの消費生活センターにつながります。';

  // logic.py の evaluate() と同一仕様
  function evaluate(text, checkType, flags) {
    if (!CHECK_TYPES[checkType]) checkType = 'flyer';
    text = (text || '').trim();
    flags = flags || [];
    var score = 0;
    var hits = [];

    RULES.keywords.forEach(function (kw) {
      if (kw.targets.indexOf(checkType) !== -1 && text.indexOf(kw.pattern) !== -1) {
        score += kw.score;
        hits.push({ pattern: kw.pattern, score: kw.score, note: kw.note });
      }
    });

    var flagDefs = {};
    RULES.flags.forEach(function (f) { flagDefs[f.id] = f; });
    flags.forEach(function (id) {
      var f = flagDefs[id];
      if (f) {
        score += f.score;
        hits.push({ pattern: f.label, score: f.score, note: f.note });
      }
    });

    var level = RULES.levels[0];
    RULES.levels.forEach(function (lv) { if (score >= lv.min_score) level = lv; });

    return {
      check_type: checkType,
      check_type_label: CHECK_TYPES[checkType],
      level_id: level.id,
      level_label: level.label,
      tone: level.tone,
      summary: level.summary,
      score: score,
      hits: hits,
      disclaimer: DISCLAIMER,
      hotline: HOTLINE_NOTE,
      stored: false
    };
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function copyButtons(root) {
    root.querySelectorAll('.btn-copy').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var el = document.getElementById(btn.dataset.target);
        navigator.clipboard.writeText(el.textContent.trim()).then(function () {
          btn.textContent = 'コピーしました';
          setTimeout(function () { btn.textContent = 'コピー'; }, 1500);
        });
      });
    });
  }

  /* ---------- 各画面 ---------- */

  function renderHome() {
    return '<section class="hero"><h1>売る前に、ひと呼吸。</h1>' +
      '<p>買取チラシ・売りたい品物・見積もりの気になるポイントを、その場でかんたんチェック。</p></section>' +
      '<section class="menu-cards">' +
      card('#/flyer', '📰', 'チラシチェック', 'ポストの買取チラシの文言を確認') +
      card('#/item', '📦', '商品チェック', '売ろうとしている品物の注意点を確認') +
      card('#/quote', '🧾', '見積もりチェック', '見積もり・業者の説明のあいまいな点を確認') +
      '</section><section class="menu-cards sub">' +
      card('#/refusal', '🙅', '断り文例', 'そのまま使える断りフレーズ集') +
      card('#/market', '📈', '相場リンク', '公開されている相場を自分で確認') +
      card('#/hotline', '📞', '188相談案内', '消費者ホットラインの使い方') +
      '</section>' +
      '<section class="note-box"><p>判定は「問題なさそう / 確認推奨 / 即決注意 / 相談推奨」の4段階です。入力した内容は端末の外に送信されません。</p></section>';
  }

  function card(href, ico, title, desc) {
    return '<a class="card" href="' + href + '"><span class="card-ico">' + ico + '</span>' +
      '<span class="card-body"><strong>' + esc(title) + '</strong><small>' + esc(desc) + '</small></span></a>';
  }

  function renderCheckForm(type) {
    var p = CHECK_PAGES[type];
    var flagsHtml = RULES.flags.map(function (f) {
      return '<label class="flag-item"><input type="checkbox" name="flags" value="' + f.id + '">' +
        '<span>' + esc(f.label) + '</span></label>';
    }).join('');
    return '<h1 class="page-title">' + p.title + '</h1><p class="lead">' + p.lead + '</p>' +
      '<form class="check-form" id="check-form" data-type="' + type + '">' +
      '<label class="field-label" for="text">内容を入力</label>' +
      '<textarea id="text" rows="6" placeholder="' + esc(p.placeholder) + '"></textarea>' +
      '<fieldset class="flags"><legend>あてはまるものがあればチェック</legend>' + flagsHtml + '</fieldset>' +
      '<button type="submit" class="btn-primary">チェックする</button></form>' +
      '<section class="note-box"><p>入力内容はこの端末内で判定され、外部に送信されません。</p></section>';
  }

  function renderResult(verdict) {
    var hits = verdict.hits.length
      ? '<section><h2 class="sec-title">気になったポイント</h2><ul class="hit-list">' +
        verdict.hits.map(function (h) {
          return '<li><strong>「' + esc(h.pattern) + '」</strong><br>' + esc(h.note) + '</li>';
        }).join('') + '</ul></section>'
      : '<section class="note-box"><p>登録されている注意キーワードには該当しませんでした。それでも、契約前には金額と条件を書面で確認しましょう。</p></section>';

    var refusal = RULES.refusal_templates.slice(0, 3).map(function (r) {
      return '<li><p class="copy-title">' + esc(r.title) + '</p>' +
        '<p class="copy-text" id="copy-' + r.id + '">' + esc(r.text) + '</p>' +
        '<button class="btn-copy" data-target="copy-' + r.id + '">コピー</button></li>';
    }).join('');

    var market = RULES.market_links.slice(0, 2).map(function (m) {
      return '<li><a href="' + m.url + '" target="_blank" rel="noopener noreferrer">' + esc(m.title) + '</a>' +
        '<br><small>' + esc(m.desc) + '</small></li>';
    }).join('');

    return '<h1 class="page-title">診断結果</h1>' +
      '<section class="verdict tone-' + verdict.tone + '">' +
      '<p class="verdict-type">' + esc(verdict.check_type_label) + '</p>' +
      '<p class="verdict-level">' + esc(verdict.level_label) + '</p>' +
      '<p class="verdict-summary">' + esc(verdict.summary) + '</p></section>' +
      hits +
      '<section><h2 class="sec-title">そのまま使える断り文例</h2><ul class="copy-list">' + refusal + '</ul>' +
      '<p><a href="#/refusal">断り文例をもっと見る →</a></p></section>' +
      '<section><h2 class="sec-title">相場を自分で確認する</h2><ul class="link-list">' + market + '</ul>' +
      '<p><a href="#/market">相場リンクをもっと見る →</a></p></section>' +
      '<section class="hotline-box"><h2 class="sec-title">迷ったら 188（いやや）</h2>' +
      '<p>' + esc(verdict.hotline) + '</p>' +
      '<a class="btn-secondary" href="#/hotline">188相談案内を見る</a></section>' +
      '<section class="note-box"><p>' + esc(verdict.disclaimer) + '</p></section>' +
      '<p class="back-links"><a href="#/home">ホームに戻る</a></p>';
  }

  function renderRefusal() {
    var items = RULES.refusal_templates.map(function (r) {
      return '<li><p class="copy-title">' + esc(r.title) + '</p>' +
        '<p class="copy-text" id="copy-' + r.id + '">' + esc(r.text) + '</p>' +
        '<button class="btn-copy" data-target="copy-' + r.id + '">コピー</button></li>';
    }).join('');
    return '<h1 class="page-title">断り文例コピー</h1>' +
      '<p class="lead">そのまま読み上げたり、コピーして使える断りフレーズです。きっぱり・短く・理由を言いすぎないのがコツです。</p>' +
      '<ul class="copy-list">' + items + '</ul>' +
      '<section class="note-box"><p>断ったのに居座られる・帰ってくれない場合は、一人で対応せず周囲に助けを求め、消費者ホットライン188や警察相談専用電話 #9110 に相談しましょう。</p></section>';
  }

  function renderMarket() {
    var items = RULES.market_links.map(function (m) {
      return '<li><a href="' + m.url + '" target="_blank" rel="noopener noreferrer">' + esc(m.title) + '</a>' +
        '<br><small>' + esc(m.desc) + '</small></li>';
    }).join('');
    return '<h1 class="page-title">相場リンク</h1>' +
      '<p class="lead">売る前に、公開されている相場情報を自分の目で確認しましょう。このアプリが価格を取得・保証することはありません。</p>' +
      '<ul class="link-list">' + items + '</ul>' +
      '<section class="note-box"><p>相場はあくまで目安です。品物の状態・純度・付属品などで実際の買取額は変わります。複数の業者で見積もりを取り、比較してから決めましょう。</p></section>';
  }

  function renderHotline() {
    return '<h1 class="page-title">188相談案内</h1>' +
      '<section class="hotline-box big"><p class="hotline-number">📞 188</p>' +
      '<p>消費者ホットライン「188（いやや）」に電話すると、最寄りの消費生活センター・相談窓口を案内してもらえます。</p>' +
      '<a class="btn-primary" href="tel:188">188に電話する</a></section>' +
      '<section><h2 class="sec-title">こんなときに相談できます</h2><ul class="plain-list">' +
      '<li>訪問買取で、売るつもりのなかった貴金属まで求められた</li>' +
      '<li>「今日中に決めて」と契約を急がされている</li>' +
      '<li>契約してしまったが、やめたい（クーリング・オフできるか知りたい）</li>' +
      '<li>業者の説明や見積もりに不安がある</li></ul></section>' +
      '<section><h2 class="sec-title">知っておきたいこと</h2><ul class="plain-list">' +
      '<li>訪問購入では、一般に契約書面を受け取った日から8日間はクーリング・オフができるとされています。期間中は品物の引き渡しを拒むこともできます。</li>' +
      '<li>個別のケースで実際にどうなるかは、必ず188・消費生活センターで確認してください。</li>' +
      '<li>身の危険を感じる・帰ってくれない場合は、警察相談専用電話 #9110（緊急時は110）へ。</li></ul></section>' +
      '<section class="note-box"><p>このアプリは相談窓口を案内するものであり、法律判断を行うものではありません。特定の事業者についての評価も行いません。</p></section>';
  }

  function renderDisclaimer() {
    return '<h1 class="page-title">免責・注意事項</h1>' +
      '<section><h2 class="sec-title">このアプリができること</h2><ul class="plain-list">' +
      '<li>チラシ・品物・見積もりの文章から、注意した方がよい表現をお知らせします</li>' +
      '<li>判定は「問題なさそう / 確認推奨 / 即決注意 / 相談推奨」の4段階の参考情報です</li>' +
      '<li>断り文例・相場リンク・相談窓口（188）をご案内します</li></ul></section>' +
      '<section><h2 class="sec-title">このアプリができないこと（保証しないこと）</h2><ul class="plain-list">' +
      '<li>正確な査定額・買取額の算定や保証</li>' +
      '<li>品物の真贋（本物かどうか）の判定</li>' +
      '<li>法律上の判断（クーリング・オフの可否など個別ケースの判断）</li>' +
      '<li>特定の事業者が悪質・違法であるという判断や認定</li></ul></section>' +
      '<section><h2 class="sec-title">免責</h2><p>' + esc(DISCLAIMER) + '</p>' +
      '<p>本アプリの利用、または利用できなかったことにより生じたいかなる損害についても、開発者は責任を負いません。取引の最終判断はご自身で行い、不安がある場合は消費者ホットライン188などの公的窓口にご相談ください。</p></section>' +
      '<p class="back-links"><a href="#/home">ホームに戻る</a></p>';
  }

  function renderPrivacy() {
    return '<h1 class="page-title">プライバシーポリシー</h1>' +
      '<section><h2 class="sec-title">収集しない情報</h2><ul class="plain-list">' +
      '<li>入力されたチラシ・品物・見積もりの内容は、端末内で判定され、外部サービスに送信されません</li>' +
      '<li>氏名・住所・電話番号などの個人情報は収集しません</li>' +
      '<li>広告ID・位置情報・連絡先へのアクセスは行いません</li></ul></section>' +
      '<section><h2 class="sec-title">端末内に保存される情報</h2>' +
      '<p>チェック履歴を残す設定にした場合のみ、判定結果がお使いの端末内にのみ保存されます。この情報は「設定」画面からいつでも全件削除できます。</p></section>' +
      '<section><h2 class="sec-title">外部リンクについて</h2>' +
      '<p>相場リンクなどから外部サイトに移動した場合、移動先のサイトには各サイトのプライバシーポリシーが適用されます。</p></section>' +
      '<section><h2 class="sec-title">お問い合わせ</h2>' +
      '<p>本ポリシーに関するお問い合わせは、App Store の「Appサポート」リンクからお願いします。</p></section>' +
      '<p class="back-links"><a href="#/home">ホームに戻る</a></p>';
  }

  function renderSettings() {
    return '<h1 class="page-title">設定・データ削除</h1>' +
      '<section class="settings-group"><h2 class="sec-title">チェック履歴</h2>' +
      '<label class="flag-item"><input type="checkbox" id="save-history"><span>判定結果をこの端末に保存する</span></label>' +
      '<p id="history-count" class="muted"></p>' +
      '<p><a class="btn-secondary" href="#/history">履歴一覧を見る</a></p>' +
      '<button class="btn-danger" id="clear-history">保存データをすべて削除</button>' +
      '<p class="muted">履歴はこの端末の中だけに保存され、外部には送信されません。</p></section>' +
      '<section class="settings-group"><h2 class="sec-title">情報</h2><ul class="link-list">' +
      '<li><a href="#/disclaimer">免責・注意事項</a></li>' +
      '<li><a href="#/privacy">プライバシーポリシー</a></li>' +
      '<li><a href="#/hotline">188相談案内</a></li></ul>' +
      '<p class="muted">バージョン: v' + APP_VERSION + '</p></section>';
  }

  /* ---------- 履歴 (端末内のみ) ---------- */

  function loadHistory() {
    try { return JSON.parse(localStorage.getItem(KEY_HIST) || '[]'); } catch (e) { return []; }
  }

  function saveHistoryIfEnabled(verdict) {
    if (localStorage.getItem(KEY_OPT) !== '1') return;
    var items = loadHistory();
    items.unshift({
      at: new Date().toISOString(),
      check_type: verdict.check_type,
      level_label: verdict.level_label,
      tone: verdict.tone,
      score: verdict.score
    });
    localStorage.setItem(KEY_HIST, JSON.stringify(items.slice(0, 50)));
  }

  function formatWhen(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getFullYear() + '/' + pad(d.getMonth() + 1) + '/' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function renderHistory() {
    var items = loadHistory();
    if (!items.length) {
      return '<h1 class="page-title">チェック履歴</h1>' +
        '<section class="note-box"><p>保存された履歴はありません。履歴を残すには「設定」で「判定結果をこの端末に保存する」をオンにしてください。</p></section>' +
        '<p class="back-links"><a href="#/settings">設定へ</a> ・ <a href="#/home">ホームに戻る</a></p>';
    }
    var list = items.map(function (it) {
      var typeLabel = CHECK_TYPES[it.check_type] || 'チェック';
      var tone = it.tone || 'notice';
      return '<li><p class="copy-title">' + esc(formatWhen(it.at)) + ' ・ ' + esc(typeLabel) + '</p>' +
        '<p class="hist-level tone-text-' + esc(tone) + '">' + esc(it.level_label || '') + '</p></li>';
    }).join('');
    return '<h1 class="page-title">チェック履歴</h1>' +
      '<p class="lead">この端末に保存された判定結果です(最大50件)。外部には送信されません。</p>' +
      '<ul class="hist-list">' + list + '</ul>' +
      '<p class="back-links"><a href="#/settings">設定(履歴の削除)へ</a> ・ <a href="#/home">ホームに戻る</a></p>';
  }

  /* ---------- ルーター ---------- */

  var lastVerdict = null;

  function route() {
    var hash = (location.hash || '#/home').replace('#/', '');
    var view = document.getElementById('view');
    var html;

    if (hash === 'flyer' || hash === 'item' || hash === 'quote') {
      html = renderCheckForm(hash);
    } else if (hash === 'result') {
      html = lastVerdict ? renderResult(lastVerdict) : renderHome();
    } else if (hash === 'refusal') {
      html = renderRefusal();
    } else if (hash === 'market') {
      html = renderMarket();
    } else if (hash === 'hotline') {
      html = renderHotline();
    } else if (hash === 'disclaimer') {
      html = renderDisclaimer();
    } else if (hash === 'privacy') {
      html = renderPrivacy();
    } else if (hash === 'settings') {
      html = renderSettings();
    } else if (hash === 'history') {
      html = renderHistory();
    } else {
      hash = 'home';
      html = renderHome();
    }

    view.innerHTML = html;
    window.scrollTo(0, 0);

    var activeTab = hash === 'history' ? 'settings' : hash;
    document.querySelectorAll('.tabbar a').forEach(function (a) {
      a.classList.toggle('on', a.dataset.tab === activeTab);
    });

    copyButtons(view);

    var form = document.getElementById('check-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var text = document.getElementById('text').value;
        var flags = Array.prototype.map.call(
          form.querySelectorAll('input[name="flags"]:checked'),
          function (el) { return el.value; });
        lastVerdict = evaluate(text, form.dataset.type, flags);
        saveHistoryIfEnabled(lastVerdict);
        location.hash = '#/result';
      });
    }

    if (hash === 'settings') {
      var opt = document.getElementById('save-history');
      var count = document.getElementById('history-count');
      var refresh = function () {
        var items = [];
        try { items = JSON.parse(localStorage.getItem(KEY_HIST) || '[]'); } catch (e) {}
        count.textContent = '保存された履歴: ' + items.length + '件';
        opt.checked = localStorage.getItem(KEY_OPT) === '1';
      };
      opt.addEventListener('change', function () {
        localStorage.setItem(KEY_OPT, opt.checked ? '1' : '0');
      });
      document.getElementById('clear-history').addEventListener('click', function () {
        localStorage.removeItem(KEY_HIST);
        refresh();
        alert('保存データを削除しました。');
      });
      refresh();
    }
  }

  document.getElementById('app-version').textContent = 'v' + APP_VERSION;
  window.addEventListener('hashchange', route);
  route();
})();

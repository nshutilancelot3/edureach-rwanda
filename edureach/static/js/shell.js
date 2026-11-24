/* EduReach — offline application shell.
 *
 * Served by the service worker whenever a page request cannot reach the hub.
 * It reads the mirrored data out of IndexedDB and rebuilds the screen the user
 * asked for, using the same markup and classes as the server templates, so the
 * design is identical online and offline.
 *
 * Because it routes on location.pathname rather than replaying a cached
 * response, a lesson or quiz the device has never opened still works.
 */
(function (global) {
  'use strict';

  var D = global.EduDB;
  var STR = {};
  var LANG = 'en';
  var SUBJECTS = [];
  var GRADES = [];
  var user = null;

  var cache = { lessons: [], quizzes: [], questions: [], results: [] };

  /* ------------------------------------------------------------- helpers */

  function t(key) {
    var entry = STR[key];
    if (!entry) return key;
    return entry[LANG] || entry.en || key;
  }

  function esc(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function el(id) { return document.getElementById(id); }

  function icon(name, size) {
    var paths = {
      book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/><path d="M8 7h7"/>',
      books: '<path d="M4 19V5a2 2 0 0 1 2-2h4v18H6a2 2 0 0 0-2 2z"/><path d="M14 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4z"/>',
      star: '<path d="m12 3 2.7 5.5 6 .9-4.3 4.2 1 6-5.4-2.8L6.6 19.6l1-6L3.3 9.4l6-.9z"/>',
      pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
      search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
      open: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M21 14v7H3V3h7"/>',
      send: '<path d="m22 2-7 20-4-9-9-4z"/>',
      clip: '<path d="M21 12.5 12.5 21a5 5 0 0 1-7-7l9-9a3.5 3.5 0 1 1 5 5l-9 9a2 2 0 1 1-3-3l8-8"/>',
      'arrow-left': '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
      'arrow-right': '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
      globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20a15 15 0 0 1 0-20"/>',
      chart: '<path d="M3 3v18h18"/><path d="M7 15v3"/><path d="M12 10v8"/><path d="M17 6v12"/>',
      'wifi-off': '<path d="m2 2 20 20"/><path d="M12 19h.01"/><path d="M5 12.5a10 10 0 0 1 4-2.4"/><path d="M15 10.1a10 10 0 0 1 4 2.4"/>'
    };
    var s = size || 20;
    return '<svg class="icon" width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true">' + (paths[name] || '') + '</svg>';
  }

  function go(path) {
    history.pushState({}, '', path);
    route();
  }

  /* --------------------------------------------------------------- chrome */

  function renderChrome() {
    var nav = '';
    if (user) {
      if (user.role === 'student') {
        nav = '<a href="/student" data-nav>' + icon('books') + ' ' + esc(t('lessons')) + '</a>' +
              '<a href="/student/progress" data-nav>' + icon('star') + ' ' + esc(t('my_progress')) + '</a>';
      } else if (user.role === 'teacher') {
        nav = '<a href="/teacher" data-nav>' + icon('books') + ' My lessons</a>' +
              '<a href="/teacher/progress" data-nav>' + icon('chart') + ' Class progress</a>';
      } else {
        nav = '<a href="/admin/users" data-nav>' + icon('books') + ' Accounts</a>';
      }
    }
    var tabs = el('shell-tabs');
    tabs.innerHTML = nav;
    tabs.hidden = !nav;

    var current = location.pathname;
    Array.prototype.forEach.call(tabs.querySelectorAll('a'), function (a) {
      if (a.getAttribute('href') === current) a.className = 'on';
    });
  }

  function banner() {
    return '<div class="flash offline-note">' + icon('wifi-off', 16) +
      ' Offline — showing the copy saved on this device. Your work is kept here and ' +
      'sent to the hub automatically when it is reachable.</div>';
  }

  function paint(html) {
    el('shell-main').innerHTML = banner() + html;
    renderChrome();
    global.scrollTo(0, 0);
  }

  /* ----------------------------------------------------------- data reads */

  function loadAll() {
    return Promise.all([
      D.all('lessons'), D.all('quizzes'), D.all('questions'), D.all('results'), D.getMeta('user')
    ]).then(function (parts) {
      cache.lessons = parts[0] || [];
      cache.quizzes = parts[1] || [];
      cache.questions = parts[2] || [];
      cache.results = parts[3] || [];
      user = parts[4] || null;
    });
  }

  function quizFor(lessonId) {
    return cache.quizzes.filter(function (q) { return q.lesson_id === lessonId; });
  }

  function questionsFor(quizId) {
    return cache.questions
      .filter(function (q) { return q.quiz_id === quizId; })
      .sort(function (a, b) { return a.position - b.position; });
  }

  function resultFor(quizId) {
    for (var i = 0; i < cache.results.length; i++) {
      if (cache.results[i].quiz_id === quizId) return cache.results[i];
    }
    return null;
  }

  /* -------------------------------------------------------------- screens */

  function screenStudentHome() {
    var params = new URLSearchParams(location.search);
    var subject = params.get('subject') || '';
    var grade = params.get('grade');
    if (grade === null) grade = user && user.grade ? user.grade : '';
    var q = (params.get('q') || '').trim().toLowerCase();

    var rows = cache.lessons.filter(function (l) {
      if (subject && l.subject !== subject) return false;
      if (grade && grade !== 'all' && l.grade !== grade) return false;
      if (q) {
        var hay = ((l.title || '') + ' ' + (l.body || '')).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    }).sort(function (a, b) {
      return (a.subject + a.title).localeCompare(b.subject + b.title);
    });

    var opts = function (list, selected) {
      return list.map(function (v) {
        return '<option' + (selected === v ? ' selected' : '') + '>' + esc(v) + '</option>';
      }).join('');
    };

    var html =
      '<h1>' + esc(t('hello')) + ', ' + esc((user && user.full_name || '').split(' ')[0]) + '</h1>' +
      '<form class="filters card" id="shell-filters">' +
        '<label>' + esc(t('subject')) + '<select name="subject">' +
          '<option value=""' + (subject ? '' : ' selected') + '>' + esc(t('all')) + '</option>' +
          opts(SUBJECTS, subject) + '</select></label>' +
        '<label>' + esc(t('grade')) + '<select name="grade">' +
          '<option value="all"' + (grade === 'all' ? ' selected' : '') + '>' + esc(t('all')) + '</option>' +
          opts(GRADES, grade) + '</select></label>' +
        '<label class="grow">' + icon('search', 16) + ' ' + esc(t('search')) +
          '<input name="q" value="' + esc(params.get('q') || '') + '"></label>' +
        '<button>' + esc(t('search')) + '</button>' +
      '</form>' +
      '<div class="tiles">';

    if (!rows.length) {
      html += '</div><p class="muted">' + esc(t('no_lessons')) + '</p>';
    } else {
      rows.forEach(function (l) {
        var hasQuiz = quizFor(l.id).length > 0;
        html += '<a class="tile" href="/lessons/' + l.id + '" data-nav>' +
          '<span class="tile-subj">' + esc(l.subject) + ' · ' + esc(l.grade) + '</span>' +
          '<strong>' + esc(l.title) + '</strong>' +
          '<span class="tile-foot">' + icon('open', 16) + ' ' + esc(t('open')) +
          (hasQuiz ? ' · ' + icon('pencil', 16) + ' ' + esc(t('take_quiz')) : '') +
          '</span></a>';
      });
      html += '</div>';
    }

    paint(html);

    var form = el('shell-filters');
    form.addEventListener('submit', function (e) { e.preventDefault(); applyFilters(form); });
    Array.prototype.forEach.call(form.querySelectorAll('select'), function (sel) {
      sel.addEventListener('change', function () { applyFilters(form); });
    });
  }

  function applyFilters(form) {
    var data = new FormData(form);
    var params = new URLSearchParams();
    ['subject', 'grade', 'q'].forEach(function (k) {
      var v = (data.get(k) || '').toString().trim();
      if (v) params.set(k, v);
    });
    var qs = params.toString();
    go('/student' + (qs ? '?' + qs : ''));
  }

  function screenLesson(id) {
    var lesson = cache.lessons.filter(function (l) { return l.id === id; })[0];
    if (!lesson) return screenMissing('That lesson is not saved on this device yet.');

    recordActivity('view_lesson', { lesson_id: id });

    var html =
      '<a class="btn ghost small" href="/student" data-nav>' + icon('arrow-left', 16) + ' ' + esc(t('back')) + '</a>' +
      '<article class="card lesson">' +
        '<span class="tile-subj">' + esc(lesson.subject) + ' · ' + esc(lesson.grade) +
          (lesson.teacher ? ' · ' + esc(lesson.teacher) : '') + '</span>' +
        '<h1>' + esc(lesson.title) + '</h1>' +
        '<div class="notes">' + esc(lesson.body) + '</div>';

    if (lesson.file_name) {
      var ext = String(lesson.file_name).split('.').pop().toLowerCase();
      var src = '/files/' + encodeURIComponent(lesson.file_name);
      if (['png', 'jpg', 'jpeg'].indexOf(ext) !== -1) {
        html += '<img class="media" src="' + src + '" alt="">';
      } else if (ext === 'mp4') {
        html += '<video class="media" controls preload="metadata" src="' + src + '"></video>';
      } else {
        html += '<p><a class="btn" href="' + src + '">' + icon('clip') + ' ' + esc(t('attachment')) + '</a></p>';
      }
    }
    html += '</article>';

    quizFor(id).forEach(function (qz) {
      var done = resultFor(qz.id);
      html += done
        ? '<a class="btn big ghost" href="/quizzes/' + qz.id + '" data-nav>' + esc(qz.title) + ' · ' + esc(t('quiz_done')) + '</a>'
        : '<a class="btn big" href="/quizzes/' + qz.id + '" data-nav>' + icon('pencil') + ' ' + esc(t('take_quiz')) + ': ' + esc(qz.title) + '</a>';
    });

    paint(html);
  }

  function screenQuiz(id) {
    var quiz = cache.quizzes.filter(function (q) { return q.id === id; })[0];
    if (!quiz) return screenMissing('That quiz is not saved on this device yet.');

    var questions = questionsFor(id);
    var existing = resultFor(id);
    if (existing) return renderResult(quiz, questions, existing, true);

    var html = '<h1>' + icon('pencil', 24) + ' ' + esc(quiz.title) + '</h1><form id="shell-quiz">';
    questions.forEach(function (qn, i) {
      html += '<fieldset class="card"><legend>' + (i + 1) + '. ' + esc(qn.prompt) + '</legend>';
      ['a', 'b', 'c', 'd'].forEach(function (k) {
        var text = qn['option_' + k];
        if (!text) return;
        html += '<label class="choice"><input type="radio" name="q' + qn.id + '" value="' + k + '">' +
          '<span><b>' + k.toUpperCase() + '</b> ' + esc(text) + '</span></label>';
      });
      html += '</fieldset>';
    });
    html += '<button class="big">' + esc(t('submit')) + ' ' + icon('send') + '</button></form>';

    paint(html);

    el('shell-quiz').addEventListener('submit', function (e) {
      e.preventDefault();
      submitQuiz(quiz, questions, e.target);
    });
  }

  function submitQuiz(quiz, questions, form) {
    var data = new FormData(form);
    var answers = {};
    var missing = false;
    questions.forEach(function (qn) {
      var picked = data.get('q' + qn.id);
      if (!picked) missing = true;
      answers[String(qn.id)] = picked;
    });
    if (missing) {
      var warn = document.createElement('div');
      warn.className = 'flash error';
      warn.textContent = t('answer_all');
      el('shell-main').insertBefore(warn, el('shell-main').firstChild.nextSibling);
      global.scrollTo(0, 0);
      return;
    }

    // Marked on the device from the answer key the hub already sent (FR 3.3).
    var score = questions.reduce(function (n, qn) {
      return n + (answers[String(qn.id)] === qn.correct ? 1 : 0);
    }, 0);

    var uuid = D.uuid();
    var record = {
      id: -Date.now(),                 // negative until the hub assigns a real id
      client_uuid: uuid,
      quiz_id: quiz.id,
      student_id: user ? user.id : null,
      score: score,
      total: questions.length,
      answers: JSON.stringify(answers),
      submitted_at: new Date().toISOString(),
      sync_status: 'PENDING'
    };

    D.put('results', record)
      .then(function () {
        return D.put('outbox', {
          uuid: uuid,
          entity: 'quiz_result',
          op: 'create',
          payload: {
            client_uuid: uuid,
            quiz_id: quiz.id,
            score: score,
            total: questions.length,
            answers: answers,
            submitted_at: record.submitted_at
          },
          state: 'pending',
          attempts: 0,
          last_error: null,
          queued_at: new Date().toISOString()
        });
      })
      .then(function () {
        cache.results.push(record);
        if (global.EduSync) {
          global.EduSync.refreshPending();
          if (global.EduSync.isOnline()) global.EduSync.cycle();
        }
        renderResult(quiz, questions, record, false);
      })
      .catch(function (err) {
        paint('<div class="flash error">Could not save your answers on this device: ' + esc(err.message) + '</div>');
      });
  }

  function renderResult(quiz, questions, result, locked) {
    var pct = Math.round(100 * result.score / result.total);
    var answers = {};
    try { answers = JSON.parse(result.answers || '{}'); } catch (e) { answers = {}; }

    var html =
      '<section class="card score ' + (pct >= 50 ? 'good' : 'low') + '">' +
        '<p>' + esc(t('your_score')) + '</p>' +
        '<div class="big-score">' + result.score + ' / ' + result.total + '</div>' +
        '<p>' + pct + '%</p>' +
      '</section>';

    if (locked) html += '<div class="flash">' + esc(t('already_taken')) + '</div>';
    if (result.sync_status === 'PENDING') {
      html += '<div class="flash">Saved on this device. It will reach the hub automatically once you are back online.</div>';
    }

    questions.forEach(function (qn, i) {
      var mine = answers[String(qn.id)];
      var right = mine === qn.correct;
      html += '<div class="card review ' + (right ? 'ok' : 'bad') + '">' +
        '<strong>' + (i + 1) + '. ' + esc(qn.prompt) + '</strong>' +
        '<div>' + esc(right ? t('correct') : t('wrong')) + ' — ' + esc(t('right_answer')) + ': ' +
        '<b>' + esc(String(qn.correct).toUpperCase()) + '</b> ' + esc(qn['option_' + qn.correct]) + '</div></div>';
    });

    html += '<a class="btn big" href="/student" data-nav>' + icon('books') + ' ' + esc(t('lessons')) + '</a>';
    paint(html);
  }

  function screenStudentProgress() {
    var results = cache.results.slice().sort(function (a, b) {
      return String(b.submitted_at).localeCompare(String(a.submitted_at));
    });
    var avg = results.length
      ? Math.round(results.reduce(function (n, r) { return n + 100 * r.score / r.total; }, 0) / results.length)
      : null;

    return D.getMeta('counts').then(function (counts) {
      var opened = (counts && counts.lessons_opened) || 0;
      var html =
        '<h1>' + icon('star', 24) + ' ' + esc(t('my_progress')) + '</h1>' +
        '<div class="stats">' +
          '<div class="stat"><span>' + opened + '</span>' + esc(t('lessons_opened')) + '</div>' +
          '<div class="stat"><span>' + results.length + '</span>' + esc(t('quizzes_taken')) + '</div>' +
          '<div class="stat"><span>' + (avg === null ? '—' : avg + '%') + '</span>' + esc(t('average')) + '</div>' +
        '</div>' +
        '<section class="card"><h2>' + esc(t('quiz_history')) + '</h2>';

      if (!results.length) {
        html += '<p class="muted">' + esc(t('no_results')) + '</p>';
      } else {
        results.forEach(function (r) {
          var quiz = cache.quizzes.filter(function (q) { return q.id === r.quiz_id; })[0] || {};
          var lesson = cache.lessons.filter(function (l) { return l.id === quiz.lesson_id; })[0] || {};
          var pct = Math.round(100 * r.score / r.total);
          html += '<div class="row">' +
            '<div><strong>' + esc(quiz.title || 'Quiz') + '</strong>' +
              '<div class="muted">' + esc(lesson.subject || '') + ' · ' + esc(String(r.submitted_at).slice(0, 10)) +
              (r.sync_status === 'PENDING' ? ' · <span class="tag pending">PENDING</span>' : '') + '</div></div>' +
            '<div class="bar"><div style="width: ' + pct + '%"></div></div>' +
            '<b>' + r.score + '/' + r.total + '</b></div>';
        });
      }
      html += '</section>';
      paint(html);
    });
  }

  function screenTeacherHome() {
    var mine = cache.lessons.filter(function (l) { return l.teacher_id === (user && user.id); });
    var html = '<h1>' + esc(t('hello')) + ', ' + esc((user && user.full_name) || '') + '</h1>' +
      '<section class="card"><h2>My lessons (' + mine.length + ')</h2>';
    if (!mine.length) {
      html += '<p class="muted">No lessons saved on this device yet.</p>';
    }
    mine.forEach(function (l) {
      html += '<div class="row"><div><strong>' + esc(l.title) + '</strong>' +
        '<div class="muted">' + esc(l.subject) + ' · ' + esc(l.grade) + ' · ' +
        quizFor(l.id).length + ' quiz(zes) · <span class="tag ' +
        (l.sync_status === 'SYNCED' ? 'synced' : 'pending') + '">' + esc(l.sync_status || 'PENDING') +
        '</span></div></div></div>';
    });
    html += '</section>' +
      '<p class="muted">Creating and editing lessons needs the hub. Your saved lessons stay readable here.</p>';
    paint(html);
  }

  function screenTeacherProgress() {
    var myQuizzes = cache.quizzes.filter(function (q) { return q.teacher_id === (user && user.id); });
    var html = '<h1>Class progress</h1><section class="card"><h2>My quizzes</h2>';
    if (!myQuizzes.length) {
      html += '<p class="muted">Nothing saved on this device yet.</p>';
    } else {
      html += '<table><tr><th>Quiz</th><th>Questions</th></tr>';
      myQuizzes.forEach(function (q) {
        html += '<tr><td>' + esc(q.title) + '</td><td>' + questionsFor(q.id).length + '</td></tr>';
      });
      html += '</table>';
    }
    html += '</section><p class="muted">Class results are held on the hub and appear here once you reconnect.</p>';
    paint(html);
  }

  function screenMissing(message) {
    paint('<section class="card"><h1>Not saved yet</h1><p class="muted">' + esc(message) + '</p>' +
      '<a class="btn" href="/student" data-nav>' + icon('books') + ' ' + esc(t('lessons')) + '</a></section>');
  }

  function screenSignedOut() {
    el('shell-tabs').hidden = true;
    el('shell-main').innerHTML =
      '<section class="card narrow"><h1>' + esc(t('app_name')) + '</h1>' +
      '<p class="muted">This device has no saved copy yet. Connect to the hub once and sign in — ' +
      'after that EduReach keeps working without a connection.</p></section>';
  }

  /* --------------------------------------------------------------- record */

  function recordActivity(kind, payload) {
    var uuid = D.uuid();
    D.put('outbox', {
      uuid: uuid,
      entity: 'activity',
      op: 'create',
      payload: {
        client_uuid: uuid,
        kind: kind,
        lesson_id: payload.lesson_id || null,
        quiz_id: payload.quiz_id || null,
        at: new Date().toISOString()
      },
      state: 'pending',
      attempts: 0,
      last_error: null,
      queued_at: new Date().toISOString()
    }).then(function () {
      if (global.EduSync) global.EduSync.refreshPending();
    }).catch(function () { /* activity is best-effort */ });
  }

  /* ---------------------------------------------------------------- route */

  function route() {
    var path = location.pathname;

    if (!user) return screenSignedOut();

    if (path === '/' || path === '') {
      var home = user.role === 'student' ? '/student' : (user.role === 'teacher' ? '/teacher' : '/admin/users');
      history.replaceState({}, '', home);
      return route();
    }

    var lesson = path.match(/^\/lessons\/(\d+)$/);
    if (lesson) return screenLesson(parseInt(lesson[1], 10));

    var quiz = path.match(/^\/quizzes\/(\d+)$/);
    if (quiz) return screenQuiz(parseInt(quiz[1], 10));

    if (path === '/student') return screenStudentHome();
    if (path === '/student/progress') return screenStudentProgress();
    if (path === '/teacher') return screenTeacherHome();
    if (path === '/teacher/progress') return screenTeacherProgress();

    return screenMissing('That screen needs the hub. It will work again once you reconnect.');
  }

  /* ----------------------------------------------------------------- boot */

  function boot() {
    var cfg = el('shell-config');
    if (cfg) {
      try {
        var parsed = JSON.parse(cfg.textContent);
        STR = parsed.strings || {};
        SUBJECTS = parsed.subjects || [];
        GRADES = parsed.grades || [];
      } catch (e) { /* defaults stand */ }
    }

    D.getMeta('lang').then(function (saved) { if (saved) LANG = saved; })
      .then(loadAll)
      .then(function () {
        document.title = t('app_name');
        var brand = el('shell-brand');
        if (brand) brand.innerHTML = icon('book', 22) + ' ' + esc(t('app_name'));
        route();
      })
      .catch(function (err) {
        el('shell-main').innerHTML =
          '<div class="flash error">Could not open the device database: ' + esc(err.message) + '</div>';
      });

    // Client-side navigation keeps the shell alive instead of hitting the network.
    document.addEventListener('click', function (e) {
      var a = e.target.closest ? e.target.closest('a[data-nav]') : null;
      if (!a) return;
      var href = a.getAttribute('href');
      if (!href || href.charAt(0) !== '/') return;
      e.preventDefault();
      go(href);
    });

    global.addEventListener('popstate', route);

    // When the hub comes back, hand control back to the real server pages.
    global.addEventListener('edureach:netchange', function (e) {
      if (e.detail && e.detail.online) location.reload();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window);

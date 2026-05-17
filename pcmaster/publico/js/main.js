/* ===== main.js - roxymaster frontend ===== */
(function() {
  'use strict';

  window.addEventListener('load', function() {
    setTimeout(function() {
      var l = document.getElementById('loading-screen');
      if (l) l.classList.add('hidden');
    }, 600);
    setTimeout(revealOnScroll, 100);
  });

  function updateCountdown() {
    var t = new Date('2026-06-25T00:00:00').getTime(), n = Date.now(), d = t - n;
    if (d <= 0) {
      setText('days','00'); setText('hours','00');
      setText('minutes','00'); setText('seconds','00');
      return;
    }
    setText('days', pad(Math.floor(d / 86400000)));
    setText('hours', pad(Math.floor((d % 86400000) / 3600000)));
    setText('minutes', pad(Math.floor((d % 3600000) / 60000)));
    setText('seconds', pad(Math.floor((d % 60000) / 1000)));
  }
  function pad(n) { return String(n).padStart(2, '0'); }
  function setText(id, v) { var e = document.getElementById(id); if (e) e.textContent = v; }
  setInterval(updateCountdown, 1000);
  updateCountdown();

  (function() {
    var c = document.getElementById('particles-canvas');
    if (!c) return;
    var ctx = c.getContext('2d'), w, h, ps = [];
    function r() { w = c.width = window.innerWidth; h = c.height = window.innerHeight; }
    r();
    window.addEventListener('resize', r);
    var colors = ['#ffd700', '#00ff88', '#7c3aed'];
    for (var i = 0; i < 80; i++) {
      ps.push({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 0.5, vy: (Math.random() - 0.5) * 0.5, size: Math.random() * 2 + 1, color: colors[Math.floor(Math.random() * 3)] });
    }
    function draw() {
      ctx.clearRect(0, 0, w, h);
      ps.forEach(function(p) {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.fill();
        ctx.shadowBlur = 10;
        ctx.shadowColor = p.color;
      });
      ps.forEach(function(a, i) {
        ps.forEach(function(b, j) {
          if (i < j) {
            var dx = a.x - b.x, dy = a.y - b.y, d = Math.sqrt(dx * dx + dy * dy);
            if (d < 150) {
              ctx.beginPath();
              ctx.moveTo(a.x, a.y);
              ctx.lineTo(b.x, b.y);
              ctx.strokeStyle = 'rgba(255,215,0,' + (0.08 * (1 - d / 150)) + ')';
              ctx.stroke();
            }
          }
        });
      });
      ctx.shadowBlur = 0;
      requestAnimationFrame(draw);
    }
    draw();
  })();

  window.addEventListener('scroll', function() {
    var h = document.querySelector('header');
    if (h) h.classList.toggle('scrolled', window.scrollY > 50);
  });

  function revealOnScroll() {
    var els = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .section-animate');
    var wh = window.innerHeight, rp = 120;
    els.forEach(function(el) {
      if (el.getBoundingClientRect().top < wh - rp) el.classList.add('visible');
    });
  }

  var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(e) { if (e.isIntersecting) e.target.classList.add('visible'); });
  }, { threshold: 0.1 });
  document.querySelectorAll('.reveal, .reveal-left, .reveal-right').forEach(function(el) { observer.observe(el); });
  window.addEventListener('scroll', revealOnScroll);

  var chartObserver = new IntersectionObserver(function(entries) {
    entries.forEach(function(e) {
      if (e.isIntersecting) {
        e.target.querySelectorAll('.chart-bar').forEach(function(b) {
          var h = b.getAttribute('data-height');
          setTimeout(function() { b.style.height = h + 'px'; }, 200);
        });
      }
    });
  }, { threshold: 0.3 });
  var cc = document.getElementById('chart-bars');
  if (cc) chartObserver.observe(cc.parentElement);

  (function() {
    var b = 5247;
    function u() {
      b += Math.floor(Math.random() * 3);
      var f = b.toLocaleString('es');
      ['live-count', 'user-count-hero', 'registro-counter'].forEach(function(id) {
        var e = document.getElementById(id);
        if (e) e.textContent = f;
      });
    }
    setInterval(u, 8000);
    u();
    var us = document.querySelectorAll('#live-users span'), idx = 0;
    setInterval(function() {
      us.forEach(function(u) { u.classList.remove('active'); });
      if (us[idx]) us[idx].classList.add('active');
      idx = (idx + 1) % us.length;
    }, 3000);
  })();

  document.querySelectorAll('.faq-question').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var item = this.parentElement, active = item.classList.contains('active');
      document.querySelectorAll('.faq-item').forEach(function(i) { i.classList.remove('active'); });
      if (!active) item.classList.add('active');
    });
  });

  window.openModal = function() {
    var m = document.getElementById('modal-early');
    if (m) { m.classList.add('active'); document.body.style.overflow = 'hidden'; }
  };
  window.closeModal = function() {
    var m = document.getElementById('modal-early');
    if (m) { m.classList.remove('active'); document.body.style.overflow = ''; }
  };
  var mo = document.getElementById('modal-early');
  if (mo) {
    mo.addEventListener('click', function(e) { if (e.target === this) window.closeModal(); });
  }
  document.addEventListener('keydown', function(e) { if (e.key === 'Escape') window.closeModal(); });

  window.handleModalSubmit = function(e) {
    e.preventDefault();
    var n = document.getElementById('modal-nombre'), em = document.getElementById('modal-email'), t = document.getElementById('modal-tipo');
    if (!n || !em) return;
    var d = { nombre: n.value.trim(), email: em.value.trim(), tipo: t ? t.value : 'streamer' };
    if (!d.nombre || !d.email) return;
    try { localStorage.setItem('wafabot_registro', JSON.stringify(d)); } catch (err) {}
    var f = document.getElementById('modal-form'), s = document.getElementById('modal-success');
    if (f) f.style.display = 'none';
    if (s) s.style.display = 'block';
    setTimeout(function() {
      window.closeModal();
      if (f) { f.style.display = 'block'; f.reset(); }
      if (s) s.style.display = 'none';
    }, 3000);
    try {
      var list = JSON.parse(localStorage.getItem('wafabot_registros') || '[]');
      list.push(Object.assign({}, d, { fecha: new Date().toISOString() }));
      localStorage.setItem('wafabot_registros', JSON.stringify(list));
    } catch (err) {}
    fetch('/api/registro', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }).catch(function() {});
  };

  window.handleRegistro = function(e) {
    e.preventDefault();
    var n = document.getElementById('reg-nombre'), em = document.getElementById('reg-email'), t = document.getElementById('reg-tipo');
    if (!n || !em) return;
    var d = { nombre: n.value.trim(), email: em.value.trim(), tipo: t ? t.value : 'streamer' };
    if (!d.nombre || !d.email) return;
    try { localStorage.setItem('wafabot_registro', JSON.stringify(d)); } catch (err) {}
    var f = document.getElementById('registro-form'), s = document.getElementById('form-success');
    if (f) f.style.display = 'none';
    if (s) s.style.display = 'block';
    try {
      var list = JSON.parse(localStorage.getItem('wafabot_registros') || '[]');
      list.push(Object.assign({}, d, { fecha: new Date().toISOString() }));
      localStorage.setItem('wafabot_registros', JSON.stringify(list));
    } catch (err) {}
    fetch('/api/registro', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }).catch(function() {});
    var cs = document.querySelectorAll('#user-count-hero, #live-count, #registro-counter');
    cs.forEach(function(el) {
      if (el) {
        var n = parseInt(el.textContent.replace(/[^0-9]/g, '')) || 0;
        el.textContent = (n + 1).toLocaleString('es');
      }
    });
    setTimeout(function() {
      if (f) { f.style.display = 'block'; f.reset(); }
      if (s) s.style.display = 'none';
    }, 4000);
  };

  window.shareLink = function(p) {
    var u = encodeURIComponent('https://www.wafabot.com');
    var t = encodeURIComponent('unete a la revolucion de wafabot - audiencia real para tus directos en kick y twitch');
    var links = {
      twitter: 'https://twitter.com/intent/tweet?text=' + t + '&url=' + u,
      facebook: 'https://facebook.com/sharer/sharer.php?u=' + u,
      whatsapp: 'https://wa.me/?text=' + t + '%20' + u
    };
    if (links[p]) window.open(links[p], '_blank', 'width=600,height=400');
  };

  window.copyLink = function() {
    navigator.clipboard.writeText('https://www.wafabot.com').then(function() {
      var b = document.querySelector('.share-btn.copy');
      if (b) {
        b.innerHTML = '<i class="fas fa-check"></i> copiado!';
        setTimeout(function() { b.innerHTML = '<i class="fas fa-link"></i> copiar enlace'; }, 2000);
      }
    });
  };

  (function() {
    try {
      var list = JSON.parse(localStorage.getItem('wafabot_registros') || '[]');
      if (list.length > 0) {
        var b = 5247 + list.length;
        ['user-count-hero', 'live-count', 'registro-counter'].forEach(function(id) {
          var e = document.getElementById(id);
          if (e) e.textContent = b.toLocaleString('es');
        });
      }
    } catch (err) {}
  })();

  document.querySelectorAll('.btn, .form-submit, .share-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      var r = this.getBoundingClientRect(), ripple = document.createElement('span');
      ripple.className = 'ripple';
      var x = e.clientX - r.left, y = e.clientY - r.top;
      ripple.style.cssText = 'left:' + x + 'px;top:' + y + 'px;position:absolute;border-radius:50%;background:rgba(255,255,255,0.3);transform:scale(0);animation:ripple-anim 0.6s ease-out;pointer-events:none;width:20px;height:20px;';
      this.appendChild(ripple);
      setTimeout(function() { ripple.remove(); }, 600);
    });
  });

  var hb = document.querySelector('.hamburger'), nl = document.querySelector('.nav-links');
  if (hb && nl) {
    hb.addEventListener('click', function() {
      nl.classList.toggle('active');
      hb.classList.toggle('active');
    });
    nl.querySelectorAll('a').forEach(function(l) {
      l.addEventListener('click', function() {
        nl.classList.remove('active');
        hb.classList.remove('active');
      });
    });
  }

  var cp = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a, .sidebar-link').forEach(function(l) {
    var h = l.getAttribute('href');
    if (h && h === cp) l.classList.add('active');
  });

  document.querySelectorAll('a[href^="#"]').forEach(function(a) {
    a.addEventListener('click', function(e) {
      var id = this.getAttribute('href');
      if (id && id.length > 1) {
        var t = document.querySelector(id);
        if (t) {
          e.preventDefault();
          t.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    });
  });

})();

(function(){
  'use strict';

  /* ===================================================================
     SECTION LOADER - carga modular de secciones html
     =================================================================== */
  const sections = [
    'header',
    'hero',
    'plataformas',
    'beneficios',
    'usecases',
    'growth',
    'testimonios',
    'certificaciones',
    'how-steps',
    'pricing',
    'faq',
    'registro',
    'share',
    'footer',
    'modal'
  ];

  const app = document.getElementById('app');
  const loading = document.getElementById('loading-screen');

  async function loadSections() {
    const frag = document.createDocumentFragment();
    for (const name of sections) {
      try {
        const resp = await fetch('/publico/secciones/' + name + '.html');
        if (!resp.ok) throw new Error('http ' + resp.status);
        const html = await resp.text();
        const tmp = document.createElement('div');
        tmp.innerHTML = html;
        while (tmp.firstChild) frag.appendChild(tmp.firstChild);
      } catch(e) {
        console.warn('error cargando seccion:', name, e);
      }
    }
    app.appendChild(frag);
    if (loading) loading.style.display = 'none';
    initAll();
  }

  /* ===================================================================
     INIT ALL - inicializa interactividad tras carga
     =================================================================== */
  function initAll() {
    particlesInit();
    countdownInit();
    liveCounterInit();
    scrollRevealInit();
    faqAccordion();
    modalInit();
    registerFormInit();
    modalFormInit();
    shareButtonsInit();
    copyLinkInit();
    hamburgerInit();
    scrollTopInit();
    tiltCards();
    rippleButtons();
  }

  /* ====================================
     PARTICLES CANVAS
     ==================================== */
  function particlesInit() {
    const canvas = document.getElementById('particles-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h, particles = [];

    function resize() {
      w = canvas.width = canvas.offsetWidth;
      h = canvas.height = canvas.offsetHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    const count = 80;
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.8,
        vy: (Math.random() - 0.5) * 0.8,
        r: Math.random() * 2 + 1
      });
    }

    function draw() {
      ctx.clearRect(0, 0, w, h);
      const colors = ['#00ff88', '#7c3aed', '#ffd700'];
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = w;
        if (p.x > w) p.x = 0;
        if (p.y < 0) p.y = h;
        if (p.y > h) p.y = 0;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = colors[Math.floor(Math.random() * colors.length)];
        ctx.globalAlpha = 0.6;
        ctx.fill();
      }
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = '#00ff88';
            ctx.globalAlpha = 0.15 * (1 - dist / 120);
            ctx.stroke();
          }
        }
      }
      requestAnimationFrame(draw);
    }
    draw();
  }

  /* ====================================
     COUNTDOWN
     ==================================== */
  function countdownInit() {
    const el = document.getElementById('countdown');
    if (!el) return;
    const target = new Date('2026-06-25T00:00:00-05:00').getTime();

    function tick() {
      const now = Date.now();
      const diff = Math.max(0, target - now);
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      el.innerHTML = '<span class="cd-item"><span class="cd-num">' + d + '</span><span class="cd-label">dias</span></span><span class="cd-sep">:</span><span class="cd-item"><span class="cd-num">' + String(h).padStart(2,'0') + '</span><span class="cd-label">horas</span></span><span class="cd-sep">:</span><span class="cd-item"><span class="cd-num">' + String(m).padStart(2,'0') + '</span><span class="cd-label">min</span></span><span class="cd-sep">:</span><span class="cd-item"><span class="cd-num">' + String(s).padStart(2,'0') + '</span><span class="cd-label">seg</span></span>';
    }
    tick();
    setInterval(tick, 1000);
  }

  /* ====================================
     LIVE COUNTER
     ==================================== */
  function liveCounterInit() {
    const el = document.getElementById('live-counter');
    if (!el) return;
    const fakeNames = [
      'carlos_m', 'laura_g', 'el_patron', 'streamer_kick', 'mega_aguila',
      'luzu_elite', 'coscu_fan', 'roberto_m', 'messi_stream', 'auron_fan',
      'rubius_crew', 'ibai_army', 'knekro_club', 'spreen_gang', 'davo_fan'
    ];
    let count = parseInt(localStorage.getItem('wafabot_counter') || '5127');
    let currentName = '';

    function update() {
      count += Math.floor(Math.random() * 3) + 1;
      localStorage.setItem('wafabot_counter', count);
      el.innerHTML = '<span class="counter-num">' + count.toLocaleString() + '</span> <span class="counter-label">streamers registrados</span><div class="counter-live"><span class="live-dot"></span> ' + fakeNames[Math.floor(Math.random() * fakeNames.length)] + ' acaba de unirse</div>';
    }
    update();
    setInterval(update, 8000);
  }

  /* ====================================
     SCROLL REVEAL (intersection observer)
     ==================================== */
  function scrollRevealInit() {
    const els = document.querySelectorAll('.anim-up, .anim-slide, .anim-right, .growth-chart, .pricing-card, .testimonio-card, .cert-item, .step-item, .beneficio-card, .plataforma-track');
    if (!els.length) return;
    const obs = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add('visible');
          obs.unobserve(e.target);
        }
      }
    }, { threshold: 0.1 });
    for (const el of els) obs.observe(el);
  }

  /* ====================================
     FAQ ACCORDION
     ==================================== */
  function faqAccordion() {
    const items = document.querySelectorAll('.faq-item');
    for (const item of items) {
      item.addEventListener('toggle', function() {
        const arrow = this.querySelector('.faq-arrow');
        if (arrow) arrow.style.transform = this.open ? 'rotate(180deg)' : 'rotate(0deg)';
      });
    }
  }

  /* ====================================
     MODAL
     ==================================== */
  function modalInit() {
    const modal = document.getElementById('betaModal');
    const closeBtn = document.getElementById('modalClose');
    const openBtns = document.querySelectorAll('[data-open-modal]');
    if (!modal) return;

    function open() {
      modal.classList.add('open');
      document.body.style.overflow = 'hidden';
    }
    function close() {
      modal.classList.remove('open');
      document.body.style.overflow = '';
    }

    for (const btn of openBtns) btn.addEventListener('click', open);
    if (closeBtn) closeBtn.addEventListener('click', close);
    modal.addEventListener('click', function(e) {
      if (e.target === modal) close();
    });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') close();
    });
  }

  /* ====================================
     REGISTER FORM
     ==================================== */
  function registerFormInit() {
    const form = document.getElementById('register-form');
    if (!form) return;
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      const name = document.getElementById('reg-name');
      const email = document.getElementById('reg-email');
      const password = document.getElementById('reg-password');
      const type = document.getElementById('reg-type');
      const nameErr = document.getElementById('reg-name-error');
      const emailErr = document.getElementById('reg-email-error');
      const passwordErr = document.getElementById('reg-password-error');
      let valid = true;

      if (!name.value.trim()) {
        nameErr.textContent = 'ingresa tu nombre';
        valid = false;
      } else nameErr.textContent = '';

      const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRe.test(email.value.trim())) {
        emailErr.textContent = 'ingresa un email valido';
        valid = false;
      } else emailErr.textContent = '';

      if (password.value.length < 6) {
        passwordErr.textContent = 'la contraseña debe tener al menos 6 caracteres';
        valid = false;
      } else passwordErr.textContent = '';

      if (!type.value) { valid = false; }

      if (valid) {
        const payload = {
          username: name.value.trim(),
          email: email.value.trim(),
          password: password.value.trim()
        };
        fetch('/api/registro', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }).then(function(r) { return r.json(); }).then(function(data) {
          try { localStorage.setItem('wafabot_registered', JSON.stringify({ name: name.value.trim(), email: email.value.trim(), type: type.value })); } catch(e) {}
          document.getElementById('register-form-content').style.display = 'none';
          document.getElementById('register-form-result').style.display = 'block';
          form.reset();
        }).catch(function() {
          document.getElementById('register-form-content').style.display = 'none';
          document.getElementById('register-form-result').style.display = 'block';
          form.reset();
        });
      }
    });
  }

  /* ====================================
     MODAL FORM
     ==================================== */
  function modalFormInit() {
    const form = document.getElementById('modal-form');
    if (!form) return;
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      const name = document.getElementById('modal-name');
      const email = document.getElementById('modal-email');
      const password = document.getElementById('modal-password');
      const type = document.getElementById('modal-type');
      const nameErr = document.getElementById('modal-name-error');
      const emailErr = document.getElementById('modal-email-error');
      const passwordErr = document.getElementById('modal-password-error');
      let valid = true;

      if (!name.value.trim()) { nameErr.textContent = 'ingresa tu nombre'; valid = false; }
      else nameErr.textContent = '';

      const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRe.test(email.value.trim())) { emailErr.textContent = 'ingresa un email valido'; valid = false; }
      else emailErr.textContent = '';

      if (password.value.length < 6) {
        passwordErr.textContent = 'la contraseña debe tener al menos 6 caracteres';
        valid = false;
      } else passwordErr.textContent = '';

      if (!type.value) { valid = false; }

      if (valid) {
        const payload = {
          username: name.value.trim(),
          email: email.value.trim(),
          password: password.value.trim()
        };
        fetch('/api/registro', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }).then(function(r) { return r.json(); }).then(function() {
          try { localStorage.setItem('wafabot_modal_sent', '1'); } catch(e) {}
          form.style.display = 'none';
          document.getElementById('modal-success').style.display = 'block';
        }).catch(function() {
          try { localStorage.setItem('wafabot_modal_sent', '1'); } catch(e) {}
          form.style.display = 'none';
          document.getElementById('modal-success').style.display = 'block';
        });
      }
    });
  }

  /* ====================================
     SHARE BUTTONS
     ==================================== */
  function shareButtonsInit() {
    const btns = document.querySelectorAll('[data-share]');
    const url = encodeURIComponent('https://www.wafabot.com');
    const text = encodeURIComponent('multiplica tu audiencia en kick y twitch con wafabot. beta abierta!');

    for (const btn of btns) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        const platform = this.dataset.share;
        let href = '#';
        switch (platform) {
          case 'twitter': href = 'https://twitter.com/intent/tweet?text=' + text + '&url=' + url; break;
          case 'facebook': href = 'https://www.facebook.com/sharer/sharer.php?u=' + url; break;
          case 'whatsapp': href = 'https://wa.me/?text=' + text + '%20' + url; break;
          case 'telegram': href = 'https://t.me/share/url?url=' + url + '&text=' + text; break;
        }
        window.open(href, '_blank', 'width=600,height=400');
      });
    }
  }

  /* ====================================
     COPY LINK
     ==================================== */
  function copyLinkInit() {
    const input = document.getElementById('share-link-input');
    const btn = document.getElementById('share-copy-btn');
    if (!input || !btn) return;
    input.value = 'https://www.wafabot.com';
    btn.addEventListener('click', function() {
      input.select();
      try {
        document.execCommand('copy');
        btn.textContent = 'copiado!';
        setTimeout(function() { btn.textContent = 'copiar'; }, 2000);
      } catch(e) {}
    });
  }

  /* ====================================
     HAMBURGER MENU
     ==================================== */
  function hamburgerInit() {
    const btn = document.getElementById('hamburger');
    const nav = document.getElementById('nav-links');
    if (!btn || !nav) return;
    btn.addEventListener('click', function() {
      btn.classList.toggle('active');
      nav.classList.toggle('open');
    });
    const links = nav.querySelectorAll('a');
    for (const link of links) {
      link.addEventListener('click', function() {
        btn.classList.remove('active');
        nav.classList.remove('open');
      });
    }
  }

  /* ====================================
     SCROLL TO TOP BUTTON
     ==================================== */
  function scrollTopInit() {
    const btn = document.getElementById('scrollTopBtn');
    if (!btn) return;
    window.addEventListener('scroll', function() {
      if (window.scrollY > 400) {
        btn.classList.add('visible');
      } else {
        btn.classList.remove('visible');
      }
    });
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* ====================================
     TILT 3D CARDS
     ==================================== */
  function tiltCards() {
    const cards = document.querySelectorAll('.pricing-card:not(.pricing-card-disabled), .beneficio-card, .testimonio-card');
    for (const card of cards) {
      card.addEventListener('mousemove', function(e) {
        const rect = this.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        const dx = (x - cx) / cx;
        const dy = (y - cy) / cy;
        this.style.transform = 'perspective(1000px) rotateY(' + (dx * 5) + 'deg) rotateX(' + (-dy * 5) + 'deg) scale3d(1.02,1.02,1.02)';
      });
      card.addEventListener('mouseleave', function() {
        this.style.transform = '';
      });
    }
  }

  /* ====================================
     RIPPLE EFFECT
     ==================================== */
  function rippleButtons() {
    const btns = document.querySelectorAll('.btn:not(:disabled)');
    for (const btn of btns) {
      btn.addEventListener('click', function(e) {
        const ripple = document.createElement('span');
        ripple.className = 'ripple';
        const rect = this.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        ripple.style.width = ripple.style.height = size + 'px';
        ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
        ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
        this.appendChild(ripple);
        setTimeout(function() { ripple.remove(); }, 600);
      });
    }
  }

  /* ===================================================================
     START - load sections on DOM ready
     =================================================================== */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadSections);
  } else {
    loadSections();
  }
})();
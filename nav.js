'use strict';

(function () {
  const nav = document.getElementById('site-nav');
  const burger = document.querySelector('.nav-burger');
  const drops = Array.from(document.querySelectorAll('.nav-dd'));

  function shut(drop) {
    drop.classList.remove('open');
    drop.querySelector('button').setAttribute('aria-expanded', 'false');
  }

  function shutAll(except) {
    drops.forEach((drop) => { if (drop !== except) shut(drop); });
  }

  drops.forEach((drop) => {
    const button = drop.querySelector('button');
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      const open = !drop.classList.contains('open');
      shutAll(drop);
      drop.classList.toggle('open', open);
      button.setAttribute('aria-expanded', String(open));
    });
    drop.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') { shut(drop); button.focus(); }
    });
    drop.querySelectorAll('.nav-menu a').forEach((link) => link.addEventListener('click', () => {
      shut(drop);
      if (nav) nav.classList.remove('open');
      if (burger) { burger.classList.remove('open'); burger.setAttribute('aria-expanded', 'false'); }
    }));
  });

  document.addEventListener('click', () => shutAll());

  if (burger && nav) {
    burger.addEventListener('click', (event) => {
      event.stopPropagation();
      const open = !nav.classList.contains('open');
      nav.classList.toggle('open', open);
      burger.setAttribute('aria-expanded', String(open));
    });
  }
})();

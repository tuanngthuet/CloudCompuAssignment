'use strict';
// Keep each form and editor draft mounted while moving between screens.
(() => {
  const screens = [...document.querySelectorAll('[data-screen]')];
  const views = [...document.querySelectorAll('[data-admin-view]')];
  // Form controls named "id" shadow the form.id property.
  const adminIds = new Set(views.map(node => node.getAttribute('id')));
  const loginDialog = document.getElementById('login-panel');
  let authenticated = false, role = null, currentScreen = 'booking', returnHash = '#booking', loginOpener = null, bookingLoginRequested = false;
  const accountToggle=document.getElementById('account-toggle'),accountMenu=document.getElementById('account-menu');
  function closeAccount(){accountMenu.hidden=true;accountToggle.setAttribute('aria-expanded','false');}
  accountToggle.addEventListener('click',()=>{const open=accountMenu.hidden;accountMenu.hidden=!open;accountToggle.setAttribute('aria-expanded',String(open));});
  accountToggle.addEventListener('keydown',event=>{if(event.key==='ArrowDown'){event.preventDefault();accountMenu.hidden=false;accountToggle.setAttribute('aria-expanded','true');document.getElementById('profile-link').focus();}});
  document.addEventListener('click',event=>{if(!event.target.closest('.account'))closeAccount();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!accountMenu.hidden){closeAccount();accountToggle.focus();}});
  accountMenu.addEventListener('click',closeAccount);
  function authMode(mode,focus=true){
    const registering=mode==='register';
    document.getElementById('login').hidden=registering;
    document.getElementById('register').hidden=!registering;
    document.getElementById('show-login').setAttribute('aria-pressed',String(!registering));
    document.getElementById('show-register').setAttribute('aria-pressed',String(registering));
    document.getElementById('login-title').textContent=registering?'Tạo tài khoản':'Chào mừng bạn trở lại';
    document.getElementById('login-description').textContent=registering?'Tạo tài khoản để đăng kí ca.':'Đăng nhập để đăng kí ca.';
    document.getElementById('login-message').textContent='';
    if(focus)document.getElementById(registering?'register':'login').elements.username.focus();
  }
  document.getElementById('show-login').onclick=()=>authMode('login');
  document.getElementById('show-register').onclick=()=>authMode('register');
  function closeLogin() {
    history.replaceState(null, '', location.pathname + location.search + returnHash);
    navigate();
    (loginOpener?.isConnected ? loginOpener : document.getElementById('login-link')).focus({preventScroll:true});
  }
  document.addEventListener('click', event => {
    const home = event.target.closest('a[href="#booking"]');
    if (home && document.getElementById('session').value) {
      event.preventDefault();
      action(async () => { await exitQueue(); await availability(); location.hash = '#booking'; navigate(); window.dispatchEvent(new CustomEvent('labseat-home')); })();
    }
    const link = event.target.closest('a[href="#login-panel"]');
    if (link) loginOpener = link;
  });
  function navigate(focus = false) {
    const target = location.hash.slice(1) || 'booking';
    let screen = adminIds.has(target) ? 'admin-panel' : target;
    let promptLogin = target === 'login-panel' && !authenticated;
    if (target === 'login-panel') screen = currentScreen;
    if (!screens.some(node => node.id === screen)) screen = 'booking';
    if ((['tickets-panel','profile-panel','staff-panel'].includes(screen) && !authenticated) || (screen === 'admin-panel' && role !== 'admin') || (screen === 'staff-panel' && role !== 'staff')) {
      promptLogin = !authenticated;
      screen = 'booking';
    }
    const previousScreen = currentScreen;
    currentScreen = screen;
    for (const node of screens) node.hidden = node.id !== screen;
    const adminView = adminIds.has(target) ? target : 'event-form';
    for (const node of views) node.hidden = role==='staff'&&node.getAttribute('id')==='checkin-form' ? screen!=='staff-panel' : node.getAttribute('id') !== adminView;
    document.querySelector('.admin-session-context').hidden = adminView !== 'registrations-panel';
    for (const link of document.querySelectorAll('.primary-nav a, .admin-nav a')) {
      const active = link.hash === '#' + screen || link.hash === '#' + adminView && screen === 'admin-panel';
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
    document.title = ({booking:'Ca', 'tickets-panel':'Ca đã đăng kí', 'profile-panel':'Hồ sơ cá nhân', 'admin-panel':'Quản trị','staff-panel':'Ca được giao','auth-action':'Xác nhận liên kết'})[screen] + ' · LABSEAT';
    if (promptLogin) {
      loginDialog.hidden = false;
      if (!loginDialog.open) {
        returnHash = '#' + screen;
        document.getElementById('login-message').textContent = '';
        loginDialog.showModal();
      }
    } else {
      if (loginDialog.open) loginDialog.close();
      loginDialog.hidden = true;
      authMode('login',false);
    }
    document.documentElement.classList.toggle('modal-open', promptLogin);
    if (focus && !promptLogin) {
      const heading = document.getElementById(screen).querySelector('h1');
      heading?.setAttribute('tabindex', '-1');
      heading?.focus({preventScroll:true});
      window.scrollTo({top:0, behavior:'instant'});
    }
    if(previousScreen!==screen)window.dispatchEvent(new CustomEvent('labseat-screen',{detail:screen}));
    if (screen !== 'staff-panel' && (screen !== 'admin-panel' || adminView !== 'checkin-form')) stopCamera();
  }
  document.getElementById('close-login').addEventListener('click', closeLogin);
  document.getElementById('browse-without-login').addEventListener('click', closeLogin);
  loginDialog.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const controls = [...loginDialog.querySelectorAll('button, input, a[href], [tabindex]')].filter(node => !node.disabled && node.tabIndex >= 0 && node.getClientRects().length > 0);
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  loginDialog.addEventListener('cancel', event => { event.preventDefault(); closeLogin(); });
  loginDialog.addEventListener('click', event => {
    const bounds = loginDialog.getBoundingClientRect();
    if (event.target === loginDialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) closeLogin();
  });
  window.addEventListener('labseat-notice', event => {
    if (loginDialog.open) document.getElementById('login-message').textContent = event.detail;
  });
  window.addEventListener('labseat-login-request', event => {
    bookingLoginRequested=!!event.detail?.returnToBooking;
    loginOpener=event.detail?.opener||document.activeElement;
    location.hash='#login-panel';
  });
  window.addEventListener('hashchange', () => navigate(true));
  window.addEventListener('labseat-identity', event => {
    const previouslyAuthenticated = authenticated;
    authenticated = !!event.detail; role = event.detail?.role;
    document.getElementById('tickets-link').hidden = !authenticated;
    document.getElementById('profile-link').hidden = !authenticated;
    closeAccount();
    document.getElementById('login-link').hidden = authenticated;
    document.getElementById('booking-auth-hint').hidden = authenticated;
    if (authenticated && !previouslyAuthenticated && location.hash === '#login-panel') {
      location.hash = role === 'admin' && !bookingLoginRequested ? 'admin-panel' : 'booking';
      bookingLoginRequested=false;
    }
    navigate();
  });
  navigate();
})();

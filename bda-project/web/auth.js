function showAuth(message='') {
  $('#auth-screen').hidden=false;
  $('#auth-message').textContent=message;
}

let liveSocket=null;
function connectLive(){
  if(!currentUser)return;
  const scheme=location.protocol==='https:'?'wss:':'ws:';
  liveSocket=new WebSocket(`${scheme}//${location.host}/ws/live`);
  liveSocket.onmessage=event=>{try{const payload=JSON.parse(event.data);if(payload.tweets?.length)load()}catch{}};
  liveSocket.onclose=()=>{if(currentUser)setTimeout(connectLive,4000)};
}
try{if(!localStorage.getItem('sentinel-cookie-notice'))$('#cookie-notice').hidden=false}catch{}
$('#cookie-dismiss').onclick=()=>{try{localStorage.setItem('sentinel-cookie-notice','dismissed')}catch{}$('#cookie-notice').hidden=true};

function enterWorkspace(user) {
  currentUser=user;
  document.body.classList.toggle('viewer',user.role==='viewer');
  $('#auth-screen').hidden=true;
  $('#user-label').textContent=user.name;
  $('.avatar.mini').textContent=user.name.split(/\s+/).map(p=>p[0]).join('').slice(0,2).toUpperCase();
  $('#page-title').textContent=`Good morning, ${user.name.split(' ')[0]}`;
  $('#connection-label').textContent=`${user.role[0].toUpperCase()+user.role.slice(1)} access`;
  $('#feed-toggle').hidden=user.role==='viewer';
  $$('[data-page="admin"]').forEach(a=>a.hidden=user.role!=='admin');
  load();connectLive();
}

async function bootstrapAuth() {
  try {
    const csrf=await fetch('/auth/csrf',{credentials:'same-origin'});
    csrfToken=(await csrf.json()).csrf_token;
    if(resetToken){$('#auth-title').textContent='Reset your password';$('#auth-copy')?.classList.add('hidden');$('#login-form').elements.email.closest('label').hidden=true;$('#forgot-password').hidden=true;$('#auth-demo').hidden=true;$('.auth-register').hidden=true;$('#login-form').elements.password.value='';$('#login-form').elements.password.placeholder='New password (12+ characters)';showAuth('Choose a new password for your account.');return}
    const response=await fetch('/auth/me',{credentials:'same-origin'});
    if(response.ok) enterWorkspace((await response.json()).user);
    else showAuth();
  } catch { showAuth('The local service is unavailable. Start the server and try again.'); }
}

let registration=false;
let resetToken=new URLSearchParams(location.search).get('reset');
$('#fill-demo').onclick=()=>{
  $('#login-form').elements.email.value='admin@sentinelpulse.local';
  $('#login-form').elements.password.value='SentinelDemo!2026';
};
$('#register-toggle').onclick=()=>{
  registration=!registration;
  $('#auth-title').textContent=registration?'Create your account':'Welcome back';
  let label=$('#auth-form-name');
  if(registration&&!label){label=document.createElement('label');label.id='auth-form-name';label.append('Your name');const input=document.createElement('input');input.name='name';input.required=true;input.minLength=2;input.maxLength=80;label.append(input);$('#login-form').prepend(label)}
  if(!registration)label?.remove();
  $('#auth-form-name input')?.toggleAttribute('required',registration);
  $('#auth-demo').hidden=registration;
  $('#register-toggle').textContent=registration?'Back to sign in':'Create an account';
  $('#login-form').elements.password.minLength=registration?12:1;
  $('#login-form').elements.password.value='';
};
$('#login-form').onsubmit=async event=>{
  event.preventDefault();const form=event.currentTarget;
  const data={email:form.elements.email.value,password:form.elements.password.value};
  if(registration)data.name=form.elements.name.value;
  if(form.elements.totp_code?.value)data.totp_code=form.elements.totp_code.value;
  if(resetToken)data.token=resetToken;
  $('#auth-message').textContent='';
  try {
    const response=await api(resetToken?'/auth/password-reset/complete':registration?'/auth/register':'/auth/login',{method:'POST',body:JSON.stringify(resetToken?{token:resetToken,new_password:data.password}:data)});
    if(resetToken){resetToken=null;history.replaceState(null,'',location.pathname);$('#auth-title').textContent='Password reset';$('#auth-message').textContent='Password reset. Sign in with your new password.';$('#login-form').elements.password.value='';$('#login-form').elements.email.closest('label').hidden=false;$('#forgot-password').hidden=false;$('#auth-demo').hidden=false;$('.auth-register').hidden=false;$('#login-form').elements.password.placeholder='';return}
    csrfToken=response.csrf_token;enterWorkspace(response.user);toast(registration?'Account created':'Signed in successfully');
  } catch(error) { if(error.message.includes('authenticator code'))$('#totp-label').hidden=false;$('#auth-message').textContent=error.message; }
};
$('#forgot-password').onclick=async()=>{const email=$('#login-form').elements.email.value;if(!email){$('#auth-message').textContent='Enter your email first.';return}try{const response=await api('/auth/password-reset/request',{method:'POST',body:JSON.stringify({email})});$('#auth-message').textContent=response.message}catch(error){$('#auth-message').textContent=error.message}};
$('#logout-btn').onclick=async()=>{try{await api('/auth/logout',{method:'POST'})}catch{}currentUser=null;liveSocket?.close();showAuth('You are signed out.')};

const renderPageBeforeAdmin=renderPage;
renderPage=async function(page) {
  if(page!=='admin') return renderPageBeforeAdmin(page);
  if(currentUser?.role!=='admin') {$('#view-generic').innerHTML='<article class="panel empty-state">Administrator access required.</article>';return}
  const [users,audit]=await Promise.all([api('/api/admin/users'),api('/api/admin/audit?limit=30')]);
  $('#view-generic').innerHTML=`<article class="panel"><div class="panel-head"><div><h2>Workspace members</h2><p>Manage roles with server side access checks.</p></div></div><table class="data-table"><thead><tr><th>MEMBER</th><th>EMAIL</th><th>ROLE</th><th>JOINED</th></tr></thead><tbody>${users.map(u=>`<tr><td><b>${esc(u.display_name)}</b></td><td>${esc(u.email)}</td><td><select class="role-select" data-user="${esc(u.id)}"><option ${u.role==='admin'?'selected':''}>admin</option><option ${u.role==='analyst'?'selected':''}>analyst</option><option ${u.role==='viewer'?'selected':''}>viewer</option></select></td><td>${esc((u.created_at||'').slice(0,10))}</td></tr>`).join('')}</tbody></table></article><article class="panel"><h2>Audit log</h2><table class="data-table"><thead><tr><th>EVENT</th><th>ACTOR</th><th>DETAIL</th><th>TIME</th></tr></thead><tbody>${audit.map(a=>`<tr><td>${esc(a.event)}</td><td>${esc(a.user_id||'system')}</td><td>${esc(a.detail)}</td><td>${esc((a.created_at||'').replace('T',' ').slice(0,19))}</td></tr>`).join('')}</tbody></table></article>`;
  $$('.role-select').forEach(select=>select.onchange=async()=>{try{await api(`/api/admin/users/${encodeURIComponent(select.dataset.user)}/role`,{method:'PUT',body:JSON.stringify({role:select.value})});toast('Role updated');renderPage('admin')}catch(error){toast(error.message);renderPage('admin')}});
};

const renderPageBeforeReports=renderPage;
renderPage=async function(page){
  if(page==='settings'){
    $('#view-generic').innerHTML=`<div class="chart-grid"><article class="panel"><h2>Profile</h2><p class="subtitle">Update your display name.</p><form id="profile-form" class="setting-form"><label>Name<input name="name" value="${esc(currentUser.name)}" minlength="2" maxlength="80" required></label><button class="btn btn-purple" type="submit">Save profile</button></form></article><article class="panel"><h2>Account security</h2><p class="subtitle">Change your password or add an authenticator app.</p><form id="password-form" class="setting-form"><label>Current password<input name="current" type="password" required></label><label>New password<input name="next" type="password" minlength="12" required></label><button class="btn btn-outline" type="submit">Change password</button></form><hr><button class="btn btn-outline" id="totp-setup">Set up two factor authentication</button><div id="totp-area"></div></article></div><article class="panel"><h2>Appearance and demo controls</h2><p class="subtitle">Change the local display or preview stream behavior.</p><div class="generic-actions" style="margin-top:14px"><button id="settings-theme">Toggle dark mode</button><button id="settings-shortcuts">Keyboard shortcuts</button>${currentUser.role==='viewer'?'':`<button class="primary" id="settings-inject">Inject anomaly</button>`}</div></article>`;
    $('#profile-form').onsubmit=async e=>{e.preventDefault();try{const result=await api('/api/profile',{method:'PUT',body:JSON.stringify({name:e.currentTarget.elements.name.value})});currentUser.name=result.name;$('#user-label').textContent=result.name;$('#page-title').textContent=`Good morning, ${result.name.split(' ')[0]}`;toast('Profile saved')}catch(err){toast(err.message)}};
    $('#password-form').onsubmit=async e=>{e.preventDefault();try{await api('/auth/password',{method:'POST',body:JSON.stringify({current_password:e.currentTarget.elements.current.value,new_password:e.currentTarget.elements.next.value})});currentUser=null;showAuth('Password updated. Sign in again.')}catch(err){toast(err.message)}};
    $('#totp-setup').onclick=async()=>{try{const result=await api('/auth/totp/setup',{method:'POST'});$('#totp-area').innerHTML=`<p class="subtitle">Add this secret to an authenticator app, then verify the code.</p><code class="totp-secret">${esc(result.secret)}</code><form id="totp-form" class="setting-form"><label>6 digit code<input name="code" inputmode="numeric" pattern="[0-9]{6}" required></label><button class="btn btn-purple">Enable two factor</button></form>`;$('#totp-form').onsubmit=async e=>{e.preventDefault();try{await api('/auth/totp/enable',{method:'POST',body:JSON.stringify({code:e.currentTarget.elements.code.value})});toast('Two factor authentication enabled')}catch(err){toast(err.message)}}}catch(err){toast(err.message)}};
    $('#settings-theme').onclick=()=>document.body.classList.toggle('dark');$('#settings-shortcuts').onclick=()=>toast('Shortcut: press / to focus search');$('#settings-inject')?.addEventListener('click',inject);return;
  }
  if(page==='reports'){
    $('#view-generic').innerHTML=`<article class="panel"><h2>Sentiment report</h2><p class="subtitle">Download a filtered snapshot for Power BI, Excel, or sharing.</p><div class="generic-actions" style="margin-top:16px"><button class="primary" id="report-csv">↧ &nbsp; Export CSV</button><button id="report-pdf">▤ &nbsp; Export PDF</button></div></article><article class="panel"><h2>Current scope</h2><p class="subtitle">Available dataset · ${esc(state.brand==='all'?'all brands':state.brand)} · ${state.search?`Search: “${esc(state.search)}”`:'all matching tweets'}</p></article>`;
    $('#report-csv').onclick=()=>download('csv');$('#report-pdf').onclick=()=>download('pdf');return;
  }
  return renderPageBeforeReports(page);
};

const renderBeforeExplorer=renderPage;
let explorerSort='timestamp', explorerDesc=true, explorerSentiment='all';
renderPage=async function(page){
  if(page!=='explorer')return renderBeforeExplorer(page);
  const el=$('#view-generic');
  const result=await api('/api/tweets?'+query({limit:20,page:state.page,sentiment:explorerSentiment}));
  const items=[...result.items].sort((a,b)=>{const av=a[explorerSort],bv=b[explorerSort];const cmp=typeof av==='number'?av-bv:String(av??'').localeCompare(String(bv??''));return explorerDesc?-cmp:cmp});
  el.innerHTML=`<article class="panel"><div class="table-tools"><div><h2>Conversation explorer</h2><p class="subtitle">${fmt(result.total)} matching mentions</p></div><select id="sentiment-filter" class="role-select"><option value="all">All sentiment</option><option ${explorerSentiment==='Positive'?'selected':''}>Positive</option><option ${explorerSentiment==='Negative'?'selected':''}>Negative</option><option ${explorerSentiment==='Neutral'?'selected':''}>Neutral</option></select></div><table class="data-table"><thead><tr><th data-sort="tweet">TWEET ↕</th><th data-sort="brand">BRAND ↕</th><th data-sort="sentiment">SENTIMENT ↕</th><th data-sort="polarity">POLARITY ↕</th><th data-sort="timestamp">TIME ↕</th></tr></thead><tbody>${items.map(r=>`<tr><td>${esc(r.tweet)}</td><td>${esc(r.brand)}</td><td><span class="sentiment-chip ${esc(r.sentiment)}">${esc(r.sentiment)}</span></td><td>${Number(r.polarity).toFixed(2)}</td><td>${esc(r.timestamp)}</td></tr>`).join('')||'<tr><td colspan="5" class="empty-state">No mentions match these filters.</td></tr>'}</tbody></table><div class="table-pagination"><span>Page ${result.page} of ${result.pages}</span><div><button id="page-prev" ${result.page<=1?'disabled':''}>← Previous</button><button id="page-next" ${result.page>=result.pages?'disabled':''}>Next →</button></div></div></article>`;
  $('#sentiment-filter').onchange=e=>{explorerSentiment=e.target.value;state.page=1;renderPage('explorer')};$$('[data-sort]',el).forEach(th=>th.onclick=()=>{if(explorerSort===th.dataset.sort)explorerDesc=!explorerDesc;else{explorerSort=th.dataset.sort;explorerDesc=false}renderPage('explorer')});$('#page-prev').onclick=()=>{state.page=Math.max(1,state.page-1);renderPage('explorer')};$('#page-next').onclick=()=>{state.page=Math.min(result.pages,state.page+1);renderPage('explorer')};
};

$('#search').oninput=e=>{state.search=e.target.value;state.page=1;clearTimeout(window.searchTimer);window.searchTimer=setTimeout(()=>{load();if(location.hash==='#explorer')renderPage('explorer')},230)};
$('#brand-filter').onchange=e=>{state.brand=e.target.value;state.page=1;load();if(location.hash==='#explorer')renderPage('explorer')};

bootstrapAuth();
setInterval(()=>{if(currentUser&&!state.paused)load()},8000);
$('#export-btn').onclick=()=>download('csv');
$('#date-range').onclick=event=>{const options=['all','30','7','90'],labels={all:'All available',30:'Last 30 days',7:'Last 7 days',90:'Last 90 days'};state.days=options[(options.indexOf(state.days)+1)%options.length];event.currentTarget.innerHTML=`▦ &nbsp; ${labels[state.days]} <span class="down">⌄</span>`;load()};

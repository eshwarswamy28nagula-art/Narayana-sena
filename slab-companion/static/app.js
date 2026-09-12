const $ = (selector) => document.querySelector(selector);
const commandInput = $('#commandInput');
const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[character]));

function showError(message) {
  $('#browserState').textContent = 'Action could not be completed';
  $('#activityLog').innerHTML = `<div class="empty-log">${escapeHtml(message)}</div>`;
}

function renderMemory(memory) {
  const preferences = memory.preferences || [];
  const latest = preferences[0] || 'No preference learned yet.';
  $('#memoryContent').innerHTML = `<div class="memory-item"><span class="memory-badge">LEARNED</span><strong>${escapeHtml(latest)}</strong><span>Applied automatically to the next answer.</span></div><div class="strategy"><span>↳</span><div><small>LAST STRATEGY</small><strong>${escapeHtml(memory.strategies?.[0] || 'Start with the relevant campus section.')}</strong></div></div>`;
}

function renderMetrics(memory) {
  const history = memory.history || [];
  const adapted = history.filter((task) => task.adapted).length;
  $('#metricCompleted').textContent = history.length;
  $('#metricAdapted').textContent = history.length ? `${Math.round((adapted / history.length) * 100)}%` : '0%';
  $('#metricActions').textContent = history.reduce((total, task) => total + (task.actions || []).length, 0);
  $('#metricRecovery').textContent = history.reduce((total, task) => total + (task.recovery_attempts || 0), 0);
  $('#metricAverage').textContent = history.length ? `${Math.round(history.reduce((total, task) => total + (task.duration_ms || 0), 0) / history.length)}ms` : '0ms';
}

function renderHistory(memory) {
  const history = memory.history || [];
  $('#historyList').innerHTML = history.length ? history.slice(0, 5).map((task) => `<div class="history-item"><div><strong>${escapeHtml(task.command)}</strong><span>${task.adapted ? 'Adapted successfully' : 'Completed'} · ${Number(task.duration_ms) || 0}ms</span></div><b>${task.adapted ? 'ADAPTED' : 'DONE'}</b></div>`).join('') : '<span class="empty-log">Completed tasks will appear here.</span>';
}

function renderLog(logs) {
  $('#activityLog').innerHTML = logs.map((item) => `<div class="log-item"><i></i><div><strong>${escapeHtml(item.label)}</strong>${item.detail ? `<span>${escapeHtml(item.detail)}</span>` : ''}</div></div>`).join('');
}

function renderResult(task) {
  const adaptation = task.adapted ? 'Semantic recovery completed' : 'None';
  const sources = (task.sources || []).map((source) => source.title).join(' · ') || 'Controlled website / no external source';
  $('#resultPanel').innerHTML = `<div class="result-top"><div><span class="panel-kicker">04 / RESULT</span><h2>Here’s what I found</h2></div><span class="result-state">TASK COMPLETE</span></div><div class="result-content"><div><small class="result-request">USER REQUEST</small><div class="result-request-text">${escapeHtml(task.command)}</div><small class="result-request">ANSWER</small><div class="answer">${escapeHtml(task.answer)}</div><div class="result-details"><strong>SOURCES</strong>${escapeHtml(sources)}</div></div><div class="result-details"><strong>PAGES VISITED</strong>${Number((task.pages || []).length) || 0} page(s)<br><strong>ACTIONS PERFORMED</strong>${Number((task.actions || []).length) || 0}<br><strong>ADAPTATIONS</strong>${adaptation}<br><strong>MEMORY USED</strong>${Number((task.memory_used || []).length) || 0} item(s)<br><strong>TIME TAKEN</strong>${Number(task.duration_ms) || 0}ms</div></div>`;
}

async function runTask() {
  const button = $('#runButton');
  const command = commandInput.value.trim();
  if (!command) return;
  button.disabled = true;
  button.innerHTML = 'Working <span>◌</span>';
  $('#browserState').textContent = 'Agent is operating';
  $('#browserBody').innerHTML = '<div class="browser-placeholder"><span class="compass">◌</span><strong>Waypoint is opening the site...</strong><span>Inspecting the page structure and finding the right target.</span></div>';
  try {
    const response = await fetch('/api/agent', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({command, changed: $('#changedToggle').checked}) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    renderLog(data.logs);
    renderMemory(data.memory);
    renderMetrics(data.memory);
    renderHistory(data.memory);
    renderResult(data.task);
    $('#browserState').textContent = data.task.adapted ? 'Recovered after a site change' : 'Task complete';
    $('#browserBody').innerHTML = `<iframe class="demo-browser" title="Controlled campus website" src="${data.task.pages[data.task.pages.length - 1]}"></iframe>`;
    if (data.task.adapted) {
      const section = data.task.goal?.section || 'campus';
      const labels = { scholarships: ['Scholarships', 'Student Funding'], fees: ['Fees', 'Program Costs'], hostel: ['Hostel', 'Residential Life'], exams: ['Exam Timetable', 'Academic Schedule'], contact: ['Contact', 'Get in Touch'] };
      const [expected, found] = labels[section] || ['Expected target', 'Semantic alternative'];
      $('#adaptationContent').innerHTML = `<div class="adapted-box"><strong>✓ Website change handled</strong><span>Old element: ${escapeHtml(expected)}</span><span>New element: ${escapeHtml(found)}</span><span>Agent recovered successfully</span></div>`;
    } else {
      $('#adaptationContent').innerHTML = '<span class="adaptation-ring">↻</span><strong>No change detected</strong><span>Enable demo mode to test recovery.</span>';
    }
  } catch (error) {
    showError(error.message || 'The companion could not complete that task.');
  } finally {
    button.disabled = false;
    button.innerHTML = 'Run companion <span>▶</span>';
  }
}

async function loadState() {
  try {
    const response = await fetch('/api/state');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not load saved state.');
    renderMemory(data.memory);
    renderMetrics(data.memory);
    renderHistory(data.memory);
  } catch (error) {
    showError(error.message || 'Could not load saved state.');
  }
}

$('#runButton').addEventListener('click', runTask);
$('#startButton').addEventListener('click', () => { commandInput.focus(); commandInput.scrollIntoView({behavior: 'smooth', block: 'center'}); });
$('#exampleButton').addEventListener('click', () => { commandInput.value = 'Find the admission process.'; commandInput.focus(); });
document.querySelectorAll('[data-command]').forEach((button) => button.addEventListener('click', () => { commandInput.value = button.dataset.command; }));
$('#feedbackButton').addEventListener('click', async () => {
  const input = $('#feedbackInput');
  if (!input.value.trim()) return;
  const button = $('#feedbackButton');
  button.disabled = true;
  try {
    const response = await fetch('/api/feedback', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({feedback: input.value})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not save feedback.');
    renderMemory(data.memory);
    renderMetrics(data.memory);
    input.value = '';
  } catch (error) {
    showError(error.message || 'Could not save feedback.');
  } finally {
    button.disabled = false;
  }
});
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
$('#voiceButton').addEventListener('click', () => {
  if (!SpeechRecognition) {
    $('#browserState').textContent = 'Voice input is unavailable in this browser';
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.onstart = () => { $('#browserState').textContent = 'Listening for a command'; };
  recognition.onresult = (event) => { commandInput.value = event.results[0][0].transcript; $('#browserState').textContent = 'Voice command ready'; };
  recognition.onerror = () => { $('#browserState').textContent = 'Voice input could not be captured'; };
  recognition.start();
});
loadState();

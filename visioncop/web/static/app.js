const form = document.querySelector('#scan-form');
const referenceUpload = document.querySelector('#reference-upload');
const inputUpload = document.querySelector('#input-upload');
const referencePreview = document.querySelector('#reference-preview');
const inputPreview = document.querySelector('#input-preview');
const statusCard = document.querySelector('#status');
const statusPill = document.querySelector('#status-pill');
const progress = document.querySelector('#progress');
const message = document.querySelector('#message');
const results = document.querySelector('#results');
const download = document.querySelector('#download');
const cancel = document.querySelector('#cancel');

let pollTimer;
let currentJobId;


function renderUploadPreview(input, container) {
  container.innerHTML = '';
  Array.from(input.files || []).forEach((file) => {
    const url = URL.createObjectURL(file);
    const card = document.createElement('article');
    card.className = 'preview-card';
    const label = document.createElement('span');
    label.textContent = file.name;

    if (file.type.startsWith('image/')) {
      const image = document.createElement('img');
      image.src = url;
      image.alt = `Preview of ${file.name}`;
      image.onload = () => URL.revokeObjectURL(url);
      card.appendChild(image);
    } else if (file.type.startsWith('video/')) {
      const video = document.createElement('video');
      video.src = url;
      video.muted = true;
      video.controls = true;
      video.preload = 'metadata';
      video.onloadeddata = () => { video.currentTime = 0; };
      card.appendChild(video);
    } else {
      const placeholder = document.createElement('div');
      placeholder.className = 'file-placeholder';
      placeholder.textContent = 'File';
      card.appendChild(placeholder);
    }

    card.appendChild(label);
    container.appendChild(card);
  });
}

referenceUpload.addEventListener('change', () => renderUploadPreview(referenceUpload, referencePreview));
inputUpload.addEventListener('change', () => renderUploadPreview(inputUpload, inputPreview));


async function pollJob(jobId) {
  const response = await fetch(`/jobs/${jobId}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Unable to load job status');

  statusPill.textContent = payload.status;
  progress.value = payload.progress || 0;
  message.textContent = payload.message || '';

  if (['running', 'queued', 'cancelling'].includes(payload.status)) {
    cancel.classList.remove('hidden');
  } else {
    cancel.classList.add('hidden');
  }

  if (payload.status === 'complete') {
    clearInterval(pollTimer);
    download.href = `/jobs/${jobId}/download`;
    download.classList.remove('hidden');
    renderResults(payload.result);
  }

  if (payload.status === 'cancelled') {
    clearInterval(pollTimer);
    message.textContent = 'Scan cancelled';
  }

  if (payload.status === 'failed') {
    clearInterval(pollTimer);
    message.textContent = payload.error || 'Scan failed';
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearInterval(pollTimer);
  download.classList.add('hidden');
  cancel.classList.add('hidden');
  results.innerHTML = '';
  statusCard.classList.remove('hidden');
  statusPill.textContent = 'queued';
  progress.value = 0;
  message.textContent = 'Submitting job...';

  const response = await fetch('/jobs', { method: 'POST', body: new FormData(form) });
  const payload = await response.json();
  if (!response.ok) {
    message.textContent = payload.error || 'Unable to start job';
    statusPill.textContent = 'failed';
    return;
  }

  currentJobId = payload.job_id;
  await pollJob(payload.job_id);
  pollTimer = setInterval(() => pollJob(payload.job_id).catch((error) => {
    clearInterval(pollTimer);
    message.textContent = error.message;
    statusPill.textContent = 'failed';
  }), 1500);
});

cancel.addEventListener('click', async () => {
  if (!currentJobId) return;
  cancel.disabled = true;
  message.textContent = 'Cancelling scan...';
  await fetch(`/jobs/${currentJobId}/cancel`, { method: 'POST' });
  cancel.disabled = false;
});

function renderResults(result) {
  const runs = result?.runs?.length ? result.runs : [result || {}];
  const matches = runs.flatMap((run) => run.matches || []);
  const occurrences = runs.flatMap((run) => (run.occurrences || []).map((item) => ({ ...item, run })));
  const snapshots = matches.filter((match) => match.snapshot_url);
  const runSections = runs.map((run, index) => {
    const runOccurrences = run.occurrences || [];
    const runSnapshots = (run.matches || []).filter((match) => match.snapshot_url);
    const occurrenceItems = runOccurrences.length
      ? runOccurrences.map((item) => `<li><strong>${item.start}</strong>${item.end !== item.start ? ` – ${item.end}` : ''}</li>`).join('')
      : '<li>No matching timestamps found.</li>';
    const snapshotItems = runSnapshots.length
      ? runSnapshots.map((match) => `
        <article class="snapshot-card">
          <img src="${match.snapshot_url}" alt="Matched specimen at ${match.timestamp || 'image'}">
          <div><strong>Timestamp: ${match.timestamp || 'Image match'}</strong><span>Confidence ${(match.confidence * 100).toFixed(1)}%</span></div>
        </article>`).join('')
      : '<p>No snapshots were generated for this scan.</p>';
    return `
      <section class="run-card">
        <h3>Scan ${index + 1}: ${run.reference_name || 'Specimen'} → ${run.input_name || 'Input'}</h3>
        <h4>Timestamps before matches</h4>
        <ul class="timeline">${occurrenceItems}</ul>
        <h4>Matched snapshots</h4>
        <div class="snapshot-grid">${snapshotItems}</div>
      </section>
    `;
  }).join('');

  results.innerHTML = `
    <div class="summary-grid">
      <section><span class="metric">${matches.length}</span><p>matching sampled frame(s)</p></section>
      <section><span class="metric">${occurrences.length}</span><p>timestamp occurrence(s)</p></section>
      <section><span class="metric">${snapshots.length}</span><p>snapshot image(s)</p></section>
    </div>
    <h3>Results by specimen and test video</h3>
    ${runSections}
  `;
}

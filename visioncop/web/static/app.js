const form = document.querySelector('#scan-form');
const statusCard = document.querySelector('#status');
const statusPill = document.querySelector('#status-pill');
const progress = document.querySelector('#progress');
const message = document.querySelector('#message');
const results = document.querySelector('#results');
const download = document.querySelector('#download');

let pollTimer;

async function pollJob(jobId) {
  const response = await fetch(`/jobs/${jobId}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Unable to load job status');

  statusPill.textContent = payload.status;
  progress.value = payload.progress || 0;
  message.textContent = payload.message || '';

  if (payload.status === 'complete') {
    clearInterval(pollTimer);
    download.href = `/jobs/${jobId}/download`;
    download.classList.remove('hidden');
    const summary = {
      matches: payload.result?.matches?.length || 0,
      occurrences: payload.result?.occurrences || [],
    };
    results.textContent = JSON.stringify(summary, null, 2);
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
  results.textContent = '';
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

  await pollJob(payload.job_id);
  pollTimer = setInterval(() => pollJob(payload.job_id).catch((error) => {
    clearInterval(pollTimer);
    message.textContent = error.message;
    statusPill.textContent = 'failed';
  }), 1500);
});

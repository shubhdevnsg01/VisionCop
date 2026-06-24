const { useEffect, useMemo, useRef, useState } = React;

function filePreview(file) {
  return { name: file.name, type: file.type, url: URL.createObjectURL(file) };
}

function PreviewGrid({ files }) {
  if (!files.length) return <p className="muted">No local files selected yet.</p>;
  return (
    <div className="preview-grid">
      {files.map((file) => (
        <article className="preview-card" key={`${file.name}-${file.url}`}>
          {file.type.startsWith('image/') ? (
            <img src={file.url} alt={`Preview of ${file.name}`} />
          ) : file.type.startsWith('video/') ? (
            <video src={file.url} muted controls preload="metadata" />
          ) : (
            <div className="file-placeholder">File</div>
          )}
          <span>{file.name}</span>
        </article>
      ))}
    </div>
  );
}

function ModeAdvisor({ mode }) {
  const isFace = mode === 'face';
  return (
    <div className={`mode-advisor ${isFace ? 'info' : 'warn'}`}>
      <strong>{isFace ? 'Face/person mode' : 'Object/photo mode'}</strong>
      <span>
        {isFace
          ? 'Use a clear cropped human face. The backend validates the reference as a face before scanning.'
          : 'Use this for cars, plates, logos, documents, objects, or exact photo patterns. It does not identify a person by face.'}
      </span>
    </div>
  );
}

function ResultPanel({ job, result }) {
  if (!result) return null;
  const runs = result?.runs?.length ? result.runs : [result || {}];
  const matches = runs.flatMap((run) => run.matches || []);
  const occurrences = runs.flatMap((run) => run.occurrences || []);
  const snapshots = matches.filter((match) => match.snapshot_url);

  return (
    <section className="results-panel">
      <div className="summary-grid">
        <div><span>{matches.length}</span><p>matching sampled frames</p></div>
        <div><span>{occurrences.length}</span><p>timestamp occurrences</p></div>
        <div><span>{snapshots.length}</span><p>snapshot images</p></div>
      </div>
      <div className="result-heading">
        <div>
          <p className="eyebrow">Scan complete</p>
          <h2>Results by specimen and test video</h2>
        </div>
        {job?.id && <a className="button secondary" href={`/jobs/${job.id}/download`}>Download JSON</a>}
      </div>
      {runs.map((run, index) => {
        const runSnapshots = (run.matches || []).filter((match) => match.snapshot_url);
        return (
          <article className="run-card" key={`${run.reference_name || index}-${run.input_name || index}`}>
            <header>
              <span>Scan {index + 1}</span>
              <h3>{run.reference_name || 'Specimen'} → {run.input_name || 'Input'}</h3>
            </header>
            <div className="run-columns">
              <section>
                <h4>Timestamps before matches</h4>
                {(run.occurrences || []).length ? (
                  <ul className="timeline">
                    {(run.occurrences || []).map((item, itemIndex) => (
                      <li key={`${item.start}-${itemIndex}`}><strong>{item.start}</strong>{item.end !== item.start ? ` – ${item.end}` : ''}</li>
                    ))}
                  </ul>
                ) : <p className="muted">No matching timestamps found.</p>}
              </section>
              <section>
                <h4>Matched snapshots</h4>
                {runSnapshots.length ? (
                  <div className="snapshot-grid">
                    {runSnapshots.map((match, matchIndex) => (
                      <article className="snapshot-card" key={`${match.snapshot_url}-${matchIndex}`}>
                        <img src={match.snapshot_url} alt={`Matched specimen at ${match.timestamp || 'image'}`} />
                        <div><strong>{match.timestamp || 'Image match'}</strong><span>{(match.confidence * 100).toFixed(1)}% confidence</span></div>
                      </article>
                    ))}
                  </div>
                ) : <p className="muted">No snapshots were generated for this scan.</p>}
              </section>
            </div>
          </article>
        );
      })}
    </section>
  );
}

function App() {
  const formRef = useRef(null);
  const [referenceFiles, setReferenceFiles] = useState([]);
  const [inputFiles, setInputFiles] = useState([]);
  const [mode, setMode] = useState('face');
  const [job, setJob] = useState(null);
  const [status, setStatus] = useState('idle');
  const [message, setMessage] = useState('Upload specimens and videos to begin.');
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);

  useEffect(() => () => [...referenceFiles, ...inputFiles].forEach((file) => URL.revokeObjectURL(file.url)), [referenceFiles, inputFiles]);

  async function pollJob(jobId) {
    const response = await fetch(`/jobs/${jobId}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Unable to load job status');
    setStatus(payload.status);
    setProgress(payload.progress || 0);
    setMessage(payload.error || payload.message || 'Working...');
    if (payload.status === 'complete') {
      setResult(payload.result);
      setJob({ id: jobId });
      return true;
    }
    if (['failed', 'cancelled'].includes(payload.status)) return true;
    return false;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (mode === 'image') {
      const proceed = confirm('Object/photo mode will not recognize a person by face. Use Face/person mode for human faces. Continue?');
      if (!proceed) return;
    }
    setResult(null);
    setStatus('queued');
    setProgress(0);
    setMessage('Submitting scan job...');
    const response = await fetch('/jobs', { method: 'POST', body: new FormData(formRef.current) });
    const payload = await response.json();
    if (!response.ok) {
      setStatus('failed');
      setMessage(payload.error || 'Unable to start job');
      return;
    }
    setJob({ id: payload.job_id });
    const timer = setInterval(async () => {
      try {
        const done = await pollJob(payload.job_id);
        if (done) clearInterval(timer);
      } catch (error) {
        clearInterval(timer);
        setStatus('failed');
        setMessage(error.message);
      }
    }, 1500);
    await pollJob(payload.job_id);
  }

  async function cancelJob() {
    if (!job?.id) return;
    setMessage('Cancelling scan...');
    await fetch(`/jobs/${job.id}/cancel`, { method: 'POST' });
  }

  const busy = ['queued', 'running', 'cancelling'].includes(status);
  const progressLabel = status === 'idle' ? 'Ready' : status;

  return (
    <main className="app-shell">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">VisionCop AI Scanner</p>
          <h1>Find people, vehicles, plates, and objects in video.</h1>
          <p>Upload one or more specimens and scan one or more videos. Get readable timestamps, matched snapshots, and downloadable JSON evidence.</p>
        </div>
        <div className="hero-card">
          <span>Modes</span>
          <strong>Face + Object</strong>
          <small>Built for investigation workflows</small>
        </div>
      </section>

      <form ref={formRef} onSubmit={handleSubmit} className="glass-card form-card">
        <div className="section-title"><p className="eyebrow">Step 1</p><h2>Select specimens and videos</h2></div>
        <div className="form-grid">
          <label>Specimen/reference path(s)<input name="reference_path" type="text" placeholder="/data/person.jpg; /data/car.jpg" /></label>
          <label>Upload specimen image(s)<input name="reference_upload" type="file" accept="image/*" multiple onChange={(e) => setReferenceFiles(Array.from(e.target.files || []).map(filePreview))} /></label>
          <label>Video/image path(s)<input name="input_path" type="text" placeholder="/data/camera/video1.mp4; /data/camera/video2.mp4" /></label>
          <label>Upload video/image(s)<input name="input_upload" type="file" accept="video/*,image/*" multiple onChange={(e) => setInputFiles(Array.from(e.target.files || []).map(filePreview))} /></label>
        </div>
        <div className="preview-layout">
          <section><h3>Specimen preview</h3><PreviewGrid files={referenceFiles} /></section>
          <section><h3>Video/image preview</h3><PreviewGrid files={inputFiles} /></section>
        </div>

        <div className="section-title"><p className="eyebrow">Step 2</p><h2>Choose detection settings</h2></div>
        <div className="form-grid settings-grid">
          <label>Detection mode<select name="mode" value={mode} onChange={(e) => setMode(e.target.value)}><option value="face">Face/person</option><option value="image">Object/photo/number plate/car</option></select></label>
          <ModeAdvisor mode={mode} />
          <label>Sample rate per second<input name="sample_rate" type="number" defaultValue="1" min="0.1" step="0.1" /></label>
          <label>Match tolerance<input name="tolerance" type="number" defaultValue="0.6" min="0.1" max="1" step="0.01" /></label>
          <label>Merge gap seconds<input name="merge_gap_seconds" type="number" defaultValue="1.5" min="0" step="0.1" /></label>
          <label className="checkbox"><input name="annotated_output" type="checkbox" /> Write annotated video</label>
        </div>
        <div className="actions"><button className="button" type="submit">Start scan</button>{busy && <button className="button danger" type="button" onClick={cancelJob}>Stop scan</button>}</div>
      </form>

      <section className="glass-card status-card">
        <div className="status-head"><div><p className="eyebrow">Step 3</p><h2>Scan status</h2></div><span className={`pill ${status}`}>{progressLabel}</span></div>
        <progress value={progress} max="100"></progress>
        <p className="status-message">{message}</p>
        <p className="hint">Done means status <strong>complete</strong>, progress <strong>100%</strong>, and result cards below. Terminal <code>GET /jobs/...</code> lines are normal progress checks.</p>
        <ResultPanel job={job} result={result} />
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);

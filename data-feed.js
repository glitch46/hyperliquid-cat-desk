'use strict';

window.CatDeskData = (() => {
  let downloadUrl = null;
  function sectionTime(section) {
    if (!section) return 0;
    return Math.max(...['fetchedAt', 'marketObservedAt'].map((key) => Date.parse(section[key]) || 0));
  }

  async function json(path, optional = false) {
    const response = await fetch(path, { cache: 'no-cache' });
    if (optional && response.status === 404) return null;
    if (!response.ok) throw new Error(`Snapshot HTTP ${response.status}`);
    return response.json();
  }

  async function load() {
    const [baseResult, fastResult] = await Promise.allSettled([json('data/snapshot.json'), json('data/fast.json', true)]);
    const base = baseResult.status === 'fulfilled' ? baseResult.value : null;
    const fast = fastResult.status === 'fulfilled' ? fastResult.value : null;
    if (!base && !fast?.cohorts) throw new Error('No published source snapshot is available');
    const result = { ...(base || { schemaVersion: 1 }), errors: [...(base?.errors || [])] };
    let applied = false;
    if (fast?.schemaVersion === 1) {
      for (const section of ['cohorts', 'markets', 'xyz']) {
        if (sectionTime(fast[section]) > sectionTime(base?.[section])) {
          result[section] = fast[section];
          result.errors = result.errors.filter((error) => error.section !== section);
          applied = true;
        }
      }
      if (applied) {
        result.fullSnapshotGeneratedAt = base?.generatedAt;
        result.generatedAt = fast.generatedAt;
        result.errors.push(...(fast.errors || []));
      }
    }
    if (fastResult.status === 'rejected') result.errors.push({ section: 'fast-refresh', reason: 'Frequent snapshot unavailable' });
    return result;
  }

  function download(data) {
    const anchor = document.querySelector('a[download="hyperliquid-snapshot.json"]');
    if (!anchor) return;
    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    downloadUrl = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    anchor.href = downloadUrl;
    anchor.title = 'The merged published snapshot used by this page; section timestamps are preserved';
  }

  return { load, sectionTime, download };
})();

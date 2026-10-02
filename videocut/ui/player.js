window.vcSequence = function (mainId, overlayId, items) {
  const main = document.getElementById(mainId);
  const over = document.getElementById(overlayId);
  if (!main || !over || !items.length) return;
  let index = -1;
  let current = null;

  const seek = (video, src, at, then) => {
    if (video.dataset.src === src) { video.currentTime = at; then(); return; }
    video.dataset.src = src;
    video.src = src;
    video.onloadedmetadata = () => { video.currentTime = at; then(); };
  };
  const hideOverlay = () => { over.style.display = 'none'; over.pause(); over.dataset.key = ''; };
  const load = (next) => {
    index = next;
    hideOverlay();
    if (index >= items.length) { main.pause(); current = null; return; }
    current = items[index];
    seek(main, current.src, current.start, () => main.play());
  };

  main.ontimeupdate = () => {
    if (!current) return;
    if (main.currentTime >= current.end - 0.04) { load(index + 1); return; }
    const t = main.currentTime - current.start;
    const overlay = (current.overlays || []).find(o => t >= o.at && t < o.at + (o.end - o.start));
    if (!overlay) { if (over.dataset.key) hideOverlay(); return; }
    if (over.dataset.key !== overlay.key) {
      over.dataset.key = overlay.key;
      over.style.display = 'block';
      seek(over, overlay.src, overlay.start + (t - overlay.at), () => over.play());
    }
  };
  load(0);
};

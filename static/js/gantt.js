(function () {
  const DAY = 86400000;
  const dayNumber = value => Date.parse(`${value}T00:00:00Z`) / DAY;
  const isoDay = value => new Date(value * DAY).toISOString().slice(0, 10);

  function timelineRange(bars, today) {
    const current = dayNumber(today);
    const sixMonths = new Date(current * DAY);
    sixMonths.setUTCMonth(sixMonths.getUTCMonth() + 6, 1);
    const valid = bars.filter(bar => Number.isFinite(dayNumber(bar.start_date)) &&
      Number.isFinite(dayNumber(bar.end_date)) && bar.end_date >= bar.start_date);
    const first = new Date(Math.min(current, ...valid.map(bar => dayNumber(bar.start_date))) * DAY);
    first.setUTCDate(1);
    const last = new Date(Math.max(sixMonths / DAY, ...valid.map(bar => dayNumber(bar.end_date) + 1)) * DAY);
    if (last.getUTCDate() !== 1) last.setUTCMonth(last.getUTCMonth() + 1, 1);
    return { start: first / DAY, end: last / DAY, bars: valid };
  }

  if (typeof module !== 'undefined') module.exports = { dayNumber, isoDay, timelineRange };
  if (typeof document === 'undefined') return;
  const data = document.getElementById('gantt-data');
  if (!data) return;
  const bars = JSON.parse(data.textContent);
  const today = new Date();
  const todayISO = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const range = timelineRange(bars, todayISO);
  const span = range.end - range.start;
  const feedback = document.getElementById('gantt-feedback');
  const labels = document.getElementById('ganttChartLabels');
  const rows = document.getElementById('ganttChartBars');
  if (!labels || !rows) return;
  const percent = value => (value - range.start) / span * 100;

  function render() {
    labels.replaceChildren();
    rows.replaceChildren();
    let month = new Date(range.start * DAY);
    while (month / DAY < range.end) {
      const label = document.createElement('span');
      label.textContent = month.toLocaleDateString(undefined, { month: 'short', year: '2-digit', timeZone: 'UTC' });
      label.style.left = `${percent(month / DAY)}%`;
      labels.append(label);
      month.setUTCMonth(month.getUTCMonth() + 1);
    }
    range.bars.forEach(bar => {
      const row = document.createElement('div');
      row.className = 'gantt-row';
      const title = document.createElement('a');
      const url = new URL('/weekly', location.origin);
      url.searchParams.set('day', new URLSearchParams(location.search).get('day') || todayISO);
      url.searchParams.set('gantt_id', bar.id);
      title.href = url;
      title.className = 'gantt-title';
      title.textContent = bar.title;
      title.title = `${bar.title} · ${bar.status} · ${bar.start_date} → ${bar.end_date}`;
      const track = document.createElement('div');
      track.className = 'gantt-track';
      const marker = document.createElement('span');
      marker.className = 'gantt-today';
      marker.style.left = `${percent(dayNumber(todayISO))}%`;
      marker.title = `Today: ${todayISO}`;
      track.append(marker);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'timeline-bar';
      button.style.backgroundColor = /^#[0-9a-f]{6}$/i.test(bar.color) ? bar.color : '#347bb4';
      button.setAttribute('aria-label', title.title + '. Select to view tasks.');
      button.title = title.title;
      button.textContent = `${bar.status} · ${bar.start_date} → ${bar.end_date}`;
      let start = dayNumber(bar.start_date);
      let end = dayNumber(bar.end_date);
      let dragged = false;
      let busy = false;
      const position = () => {
        button.style.left = `${percent(start)}%`;
        button.style.width = `${(end - start + 1) / span * 100}%`;
      };
      position();
      button.addEventListener('click', event => {
        if (dragged || busy) { event.preventDefault(); return; }
        location.assign(url);
      });
      button.addEventListener('pointerdown', event => {
        if (busy || event.button !== 0) return;
        dragged = false;
        const initialX = event.clientX;
        const initialStart = start;
        const initialEnd = end;
        const bounds = button.getBoundingClientRect();
        const mode = bounds.width < 24 ? 'move' : event.clientX - bounds.left < 8 ? 'left' : bounds.right - event.clientX < 8 ? 'right' : 'move';
        button.setPointerCapture(event.pointerId);
        const move = next => {
          if (Math.abs(next.clientX - initialX) < 4 && !dragged) return;
          dragged = true;
          const delta = Math.round((next.clientX - initialX) / track.clientWidth * span);
          if (mode === 'move') {
            const shift = Math.max(range.start - initialStart, Math.min(range.end - 1 - initialEnd, delta));
            start = initialStart + shift;
            end = initialEnd + shift;
          } else if (mode === 'left') {
            start = Math.max(range.start, Math.min(initialEnd, initialStart + delta));
          } else {
            end = Math.max(initialStart, Math.min(range.end - 1, initialEnd + delta));
          }
          position();
          feedback.textContent = `${bar.title}: ${isoDay(start)} → ${isoDay(end)}`;
        };
        const cleanup = () => {
          button.removeEventListener('pointermove', move);
          button.removeEventListener('pointerup', save);
          button.removeEventListener('pointercancel', cancel);
        };
        const cancel = () => {
          cleanup();
          start = initialStart; end = initialEnd;
          position();
          feedback.textContent = 'Timeline change cancelled.';
        };
        const save = async () => {
          cleanup();
          if (!dragged || (start === initialStart && end === initialEnd)) return;
          busy = true;
          button.setAttribute('aria-busy', 'true');
          feedback.textContent = 'Saving timeline…';
          try {
            const updated = { bar_id: bar.id, title: bar.title, start_date: isoDay(start), end_date: isoDay(end), color: bar.color, status: bar.status, notes: bar.notes || '' };
            const response = await fetch('/weekly/gantt/update', { method: 'POST', body: new URLSearchParams(updated) });
            if (!response.ok) throw new Error('Could not save the timeline. Try again.');
            Object.assign(bar, { start_date: updated.start_date, end_date: updated.end_date });
            const savedRow = document.querySelector(`[data-gantt-row="${bar.id}"]`);
            if (savedRow) {
              savedRow.querySelector('[data-gantt-start]').textContent = updated.start_date;
              savedRow.querySelector('[data-gantt-end]').textContent = updated.end_date;
              savedRow.querySelector('[name="start_date"]').value = updated.start_date;
              savedRow.querySelector('[name="end_date"]').value = updated.end_date;
            }
            feedback.textContent = 'Timeline saved.';
            render();
          } catch (error) {
            start = initialStart; end = initialEnd;
            position();
            feedback.textContent = error.message;
          } finally {
            busy = false;
            button.removeAttribute('aria-busy');
          }
        };
        button.addEventListener('pointermove', move);
        button.addEventListener('pointerup', save);
        button.addEventListener('pointercancel', cancel);
      });
      track.append(button);
      row.append(title, track);
      rows.append(row);
    });
  }
  render();
})();

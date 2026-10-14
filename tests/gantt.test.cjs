const { test } = require('node:test');
const assert = require('node:assert/strict');
const { dayNumber, isoDay, timelineRange } = require('../static/js/gantt.js');

test('an empty weekly page renders without a chart container', () => {
  const fs = require('node:fs');
  const vm = require('node:vm');
  const source = fs.readFileSync(require.resolve('../static/js/gantt.js'), 'utf8');
  assert.doesNotThrow(() => vm.runInNewContext(source, {
    document: { getElementById: id => id === 'gantt-data' ? { textContent: '[]' } : null },
  }));
});

test('calendar days remain stable across DST and leap years', () => {
  for (const day of ['2026-03-08', '2026-11-01', '2028-02-29']) assert.equal(isoDay(dayNumber(day)), day);
  assert.equal(dayNumber('2026-03-09') - dayNumber('2026-03-08'), 1);
});

test('range includes old and future milestones and keeps same-day bars', () => {
  const bars = [
    { start_date: '2025-01-01', end_date: '2025-01-01' },
    { start_date: '2028-02-01', end_date: '2028-02-29' },
    { start_date: 'bad', end_date: 'bad' },
  ];
  const range = timelineRange(bars, '2026-10-14');
  assert.equal(range.bars.length, 2);
  assert.ok(range.start <= dayNumber('2025-01-01'));
  assert.ok(range.end > dayNumber('2028-02-29'));
});

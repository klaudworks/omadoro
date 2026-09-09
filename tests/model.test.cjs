const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function load(file) {
    const scope = vm.createContext({});
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'model', file), 'utf8'), scope);
    return scope;
}
const S = load('SettingsModel.js'), T = load('TimerModel.js');
const settings = patch => Object.assign({}, S.defaults, patch);
const make = (patch = {}, inputs = {}) => T.create(settings(patch), { mono: 0, boot: 0 }, Object.assign({ outputs: ['a'], available: true }, inputs));
function tick(m, seconds, patch = {}, boot = seconds) { m.reconcile({ mono: m.time.mono + seconds, boot: m.time.boot + boot }, patch); }
function ready(m, output = 'a', token = m.snapshot().attempt) { return m.ready(token, output); }
function breakNow(m) { assert.equal(m.command('break').status, 'accepted'); ready(m); }

test('settings: all numeric bounds, types, enums and atomic validation', () => {
    for (const [key, [low, high]] of Object.entries(S.bounds)) {
        for (const bad of [low - 1, high + 1, 1.5, NaN, Infinity, true, null, '', '12x', '1e2'])
            assert.equal(S.validate(settings({ [key]: bad }), S.defaults).ok, false, key + ':' + bad);
        assert.equal(S.validate(settings({ [key]: String(high) }), S.defaults).ok, true);
    }
    assert.equal(S.validate(settings({ skipPolicy: 'sometimes' })).ok, false);
    assert.equal(S.validate(settings({ autoStart: 'true' })).ok, false);
    const normalized = S.normalize({ workMinutes: true, skipPolicy: 'broken', unknown: 42 });
    assert.equal(normalized.value.workMinutes, 50);
    assert.match(normalized.issue, /workMinutes/);
    assert.equal(S.merge({ unknown: 42 }, S.defaults).unknown, 42);
});
test('every command / phase cell', () => {
    const expected = {
        Stopped: ['accepted', 'noop', 'rejected', 'noop', 'accepted', 'rejected', 'rejected', 'rejected'],
        Working: ['noop', 'accepted', 'noop', 'accepted', 'accepted', 'accepted', 'accepted', 'rejected'],
        Paused: ['rejected', 'noop', 'accepted', 'accepted', 'accepted', 'accepted', 'accepted', 'rejected'],
        Preparing: ['rejected', 'rejected', 'rejected', 'rejected', 'noop', 'rejected', 'rejected', 'rejected'],
        Breaking: ['rejected', 'rejected', 'rejected', 'rejected', 'noop', 'rejected', 'rejected', 'accepted']
    };
    const names = ['start', 'pause', 'resume', 'stop', 'break', 'add', 'reset', 'skip'];
    for (const [phase, results] of Object.entries(expected)) names.forEach((name, index) => {
        const m = make({ autoStart: phase !== 'Stopped' });
        if (phase === 'Paused') m.command('pause');
        if (phase === 'Preparing' || phase === 'Breaking') m.command('break');
        if (phase === 'Breaking') ready(m);
        assert.equal(m.command(name).status, results[index], phase + '/' + name);
    });
});
test('manual break replaces Stop/Pause and starts recurring work', () => {
    for (const paused of [false, true]) {
        const m = make({ autoStart: paused, breakSeconds: 5 });
        if (paused) m.command('pause');
        breakNow(m); tick(m, 5);
        assert.equal(m.phase, 'Working'); assert.equal(m.work, 3000);
    }
    const m = make({}, { locked: true });
    assert.equal(m.command('break').status, 'rejected');
});
test('delayed callbacks catch up; formatter ceilings', () => {
    const m = make(); tick(m, 101.6); assert.equal(m.work, 2898.4);
    for (const [seconds, label] of [[90, '2m'], [61, '2m'], [60, '1m'], [59, '59s'], [1, '1s'], [0, '0s'], [-5, '0s']])
        assert.equal(T.format(seconds), label);
    m.reconcile({ mono: -1, boot: 0 }, {}); assert.equal(m.phase, 'Stopped'); assert.match(m.error, /Clock/);
});
test('settings snapshots, work duration and autostart boundaries', () => {
    const m = make(); tick(m, 10); m.configure(settings({ workMinutes: 1, autoStart: false }));
    assert.equal(m.work, 2990); assert.equal(m.phase, 'Working');
    m.command('reset'); assert.equal(m.work, 60);
    breakNow(m); m.configure(settings({ breakSeconds: 1, skipPolicy: 'never' }));
    assert.equal(m.breakState.duration, 300); assert.equal(m.breakState.policy, 'allow');
    assert.equal(make({ autoStart: false }).phase, 'Stopped');
});
test('threshold period consumes work but counts toward continuous rest', () => {
    const m = make({ breakSeconds: 300 }); tick(m, 60, { idle: true, idleSince: 0 });
    assert.equal(m.work, 2940); tick(m, 100); assert.equal(m.work, 2940);
    tick(m, 0, { idle: false }); assert.equal(m.work, 2940);
    tick(m, 60, { idle: true, idleSince: 160 }); tick(m, 300);
    tick(m, 0, { idle: false }); assert.equal(m.work, 3000);
});
test('long idle preserves pause/stop intent and short-break credit', () => {
    for (const command of ['pause', 'stop']) {
        const m = make({ breakSeconds: 20 }); tick(m, 10); m.command(command);
        tick(m, 60, { idle: true, idleSince: 10 }); tick(m, 0, { idle: false });
        assert.equal(m.phase, command === 'pause' ? 'Paused' : 'Stopped');
        assert.equal(m.work, 3000);
    }
});
test('no outputs freezes without inventing rest', () => {
    const m = make(); tick(m, 10, { outputs: [] }); tick(m, 1000); tick(m, 0, { outputs: ['a'] });
    assert.equal(m.work, 2990);
});
test('lock/suspend overlaps count once; active break restores remaining and wait', () => {
    const m = make({ breakSeconds: 30, skipPolicy: 'wait', skipWaitSeconds: 15 }); breakNow(m);
    tick(m, 5, { locked: true }); assert.equal(m.snapshot().breakVisible, false);
    tick(m, 2, { sleeping: true }); tick(m, 0, { sleeping: false }, 10);
    tick(m, 0, { locked: false }); ready(m);
    assert.equal(m.breakState.remaining, 13); assert.equal(m.snapshot().canSkip, true);
    tick(m, 1, { locked: true }); tick(m, 0, {}, 20);
    assert.equal(m.phase, 'Breaking'); tick(m, 0, { locked: false });
    assert.equal(m.phase, 'Working'); assert.equal(m.work, 3000);
});
test('warning cancellation, no endless rearm, due resume gets full warning', () => {
    const m = make({ workMinutes: 1 }); tick(m, 45); const end = m.warning.end;
    tick(m, 5); assert.equal(m.warning.end, end);
    m.command('pause'); tick(m, 100); assert.equal(m.warning, null);
    m.command('resume'); tick(m, 0); assert.equal(m.warning.end, 165);
    tick(m, 14); assert.equal(m.phase, 'Working'); tick(m, 1); assert.equal(m.phase, 'Breaking');
    const n = make({ workMinutes: 1, warningEnabled: false }); tick(n, 60); assert.equal(n.phase, 'Breaking');
});
test('warning setting changes preserve visible attempt snapshot', () => {
    const m = make({ workMinutes: 1 }); tick(m, 45);
    m.configure(settings({ workMinutes: 1, warningEnabled: false }));
    tick(m, 5); assert.ok(m.warning); tick(m, 10); assert.equal(m.phase, 'Breaking');
});
test('conditions at warning expiry win over stale automatic readiness', () => {
    for (const patch of [{ idle: true, idleSince: 0 }, { locked: true }, { outputs: [] }]) {
        const m = make({ workMinutes: 1 }); tick(m, 45); tick(m, 15, patch);
        assert.equal(m.phase, 'Working'); assert.equal(m.warning, null);
    }
    const m = make({ workMinutes: 1, warningEnabled: false }); tick(m, 60); const token = m.snapshot().attempt;
    tick(m, 0, { locked: true }); assert.equal(ready(m, 'a', token), false);
});
test('readiness waits for all outputs and starts no clock early', () => {
    const m = make({}, { outputs: ['a', 'b'] }); m.command('break'); ready(m);
    tick(m, 4); assert.equal(m.breakState.remaining, 300); assert.equal(m.breakState.stage, 'preparing');
    ready(m, 'b'); tick(m, 1); assert.equal(m.breakState.remaining, 299);
    tick(m, 0, { outputs: ['a', 'b', 'c'] }); tick(m, 4, { outputs: ['a', 'b', 'c'] });
    assert.equal(m.phase, 'Breaking'); tick(m, 1, { outputs: ['a', 'b', 'c'] });
    assert.equal(m.phase, 'Stopped'); assert.match(m.error, /timed out/);
});
test('preparation timeout, coverage failure, stale callbacks, disable cleanup', () => {
    const m = make(); m.command('break'); const token = m.snapshot().attempt; tick(m, 5);
    assert.equal(m.phase, 'Stopped'); assert.equal(ready(m, 'a', token), false);
    breakNow(m); m.coverageLost(m.snapshot().attempt, 'a'); assert.equal(m.phase, 'Stopped');
    breakNow(m); const latest = m.snapshot().attempt; m.command('disable');
    assert.equal(ready(m, 'a', latest), false); assert.equal(m.snapshot().breakVisible, false);
    assert.equal(m.command('start').status, 'rejected');
});
test('skip policy boundary', () => {
    const m = make({ skipPolicy: 'wait', skipWaitSeconds: 15 }); breakNow(m);
    tick(m, 14.99); assert.equal(m.command('skip').status, 'rejected');
    tick(m, .01); assert.equal(m.command('skip').status, 'accepted'); assert.equal(m.phase, 'Working');
    const n = make({ skipPolicy: 'never' }); breakNow(n); tick(n, 20);
    assert.equal(n.command('skip').status, 'rejected');
});
test('manual preparation interrupted by lock credits only proven continuous rest', () => {
    const m = make({ breakSeconds: 10 }); m.command('break');
    tick(m, 1, { locked: true }); const stale = m.snapshot().attempt - 1;
    assert.equal(ready(m, 'a', stale), false);
    tick(m, 0, {}, 15); tick(m, 0, { locked: false });
    assert.equal(m.phase, 'Working'); assert.equal(m.work, 3000);
    const n = make({ breakSeconds: 10 }); n.command('break');
    tick(n, 1, { locked: true }); tick(n, 2, { locked: false, outputs: [] });
    tick(n, 100); tick(n, 0, { outputs: ['a'] });
    assert.equal(n.phase, 'Breaking'); assert.equal(n.breakState.stage, 'preparing');
});
test('automatic preparation cancels for new idle; manual overrides idle', () => {
    for (const patch of [{ idle: true, idleSince: 0 }]) {
        const m = make({ workMinutes: 1, warningEnabled: false }); tick(m, 60);
        const token = m.snapshot().attempt; tick(m, 0, patch);
        assert.equal(m.phase, 'Working'); assert.equal(m.work, 0); assert.equal(ready(m, 'a', token), false);
        const manual = make(); manual.command('break'); tick(manual, 0, patch); ready(manual);
        assert.equal(manual.breakState.stage, 'active');
    }
});
test('removed then reattached output must acknowledge again', () => {
    const m = make({}, { outputs: ['a', 'b'] }); m.command('break'); ready(m); ready(m, 'b');
    tick(m, 1, { outputs: ['a'] }); tick(m, 1, { outputs: ['a', 'b'] });
    assert.equal(m.breakState.ready.b, undefined);
    ready(m, 'b'); tick(m, 6); assert.equal(m.phase, 'Breaking');
});
test('full idle credit replaces an almost-due interval on return', () => {
    const m = make({ workMinutes: 2, breakSeconds: 300 }); tick(m, 60, { idle: true, idleSince: 0 });
    assert.equal(m.work, 60); tick(m, 600); tick(m, 0, { idle: false });
    assert.equal(m.work, 120); assert.equal(m.warning, null);
});
test('civil-clock changes are irrelevant to injected elapsed time', () => {
    const m = make();
    m.reconcile({ mono: 10, boot: 10, wall: -1000000 }, {});
    assert.equal(m.work, 2990);
    m.reconcile({ mono: 20, boot: 20, wall: 90000000000 }, {});
    assert.equal(m.work, 2980);
});

test('Removed microphone/grace settings are ignored and removed on save', () => {
    const old = settings({ meetingDetectionEnabled: true, meetingGraceSeconds: 3600, custom: 42 });
    const normalized = S.normalize(old).value;
    assert.equal(normalized.meetingDetectionEnabled, undefined);
    assert.equal(normalized.meetingGraceSeconds, undefined);
    const merged = S.merge(old, normalized);
    assert.equal(merged.meetingDetectionEnabled, undefined);
    assert.equal(merged.meetingGraceSeconds, undefined);
    assert.equal(merged.custom, 42);
    const m = make({ workMinutes: 1, warningEnabled: false }, { meeting: true, meetingHealthy: false });
    tick(m, 60);
    assert.equal(m.phase, 'Breaking');
    assert.equal(m.snapshot().grace, undefined);
});
test('Repeated postponement and reset preserve pause intent', () => {
    const m = make({ workMinutes: 1 }); m.command('pause');
    m.command('add'); m.command('add'); assert.equal(m.work, 660);
    m.command('reset'); assert.equal(m.work, 60); assert.equal(m.phase, 'Paused');
});
test('Warning postponement cancels warning, adds five minutes, and warns again later', () => {
    assert.equal(S.normalize({}).value.warningPostponeEnabled, true);
    assert.equal(S.validate(settings({ warningPostponeEnabled: false })).ok, true);
    assert.equal(S.validate(settings({ warningPostponeEnabled: 'false' })).ok, false);
    const m = make({ workMinutes: 1 });
    tick(m, 45);
    assert.equal(m.snapshot().warning, true);
    assert.equal(m.command('add').status, 'accepted');
    assert.equal(m.work, 315);
    assert.equal(m.snapshot().warning, false);
    tick(m, 300);
    assert.equal(m.snapshot().warning, true);
    tick(m, 15);
    assert.equal(m.phase, 'Breaking');
    assert.equal(m.command('add').status, 'rejected');
});
test('Break minutes convert to whole seconds without floating-point rejection', () => {
    for (const [input, seconds] of [['5', 300], ['0.5', 30], ['.5', 30], ['2.05', 123], ['60', 3600]])
        assert.equal(S.minutesToSeconds(input), seconds);
    for (const input of ['', '1e2', '0.001', 'oops', 'Infinity']) assert.ok(Number.isNaN(S.minutesToSeconds(input)));
    assert.equal(S.validate(settings({ breakSeconds: S.minutesToSeconds('61') })).ok, false);
});

test('session lock is opt-in and requested only after every break surface is ready', () => {
    const normal = make(); breakNow(normal);
    assert.equal(normal.takeLockRequest(), false);
    const m = make({ lockOnBreak: true }, { outputs: ['a', 'b'] });
    m.command('break');
    assert.equal(m.takeLockRequest(), false);
    ready(m, 'a'); assert.equal(m.takeLockRequest(), false);
    ready(m, 'b'); assert.equal(m.takeLockRequest(), true);
    assert.equal(m.takeLockRequest(), false);
});

test('unlocking early and output changes do not repeatedly lock the user', () => {
    const m = make({ lockOnBreak: true }); breakNow(m);
    assert.equal(m.takeLockRequest(), true);
    tick(m, 1, { locked: true }); tick(m, 1, { locked: false }); ready(m);
    assert.equal(m.takeLockRequest(), false);
    tick(m, 0, { outputs: ['a', 'b'] }); ready(m, 'b');
    assert.equal(m.takeLockRequest(), false);
});

test('lock preference is snapshotted per break and applies again on the next break', () => {
    const m = make({ lockOnBreak: true }); m.command('break');
    m.configure(settings({ lockOnBreak: false })); ready(m);
    assert.equal(m.takeLockRequest(), true);
    m.command('skip'); breakNow(m);
    assert.equal(m.takeLockRequest(), false);
    m.command('skip'); m.configure(settings({ lockOnBreak: true })); breakNow(m);
    assert.equal(m.takeLockRequest(), true);
});

test('finishing or disabling a break never clears the desktop lock', () => {
    const m = make({ lockOnBreak: true, breakSeconds: 5 }); breakNow(m);
    assert.equal(m.takeLockRequest(), true);
    tick(m, 0, { locked: true }); tick(m, 10);
    assert.equal(m.inputs.locked, true);
    assert.equal(m.command('skip').status, 'rejected');
    assert.equal(m.snapshot().breakVisible, false);
    assert.equal(m.takeLockRequest(), false);
    m.command('disable');
    assert.equal(m.inputs.locked, true);
});

test('existing preferences adopt inhibitor protection and keep session locking opt-in', () => {
    const old = Object.assign({}, S.defaults);
    delete old.respectIdleInhibitors; delete old.lockOnBreak;
    const result = S.normalize(old);
    assert.equal(result.value.respectIdleInhibitors, true);
    assert.equal(result.value.lockOnBreak, false);
    assert.equal(result.issue, '');
    assert.equal(S.validate(settings({ respectIdleInhibitors: 'false' })).ok, false);
});

test('changing idle inhibitor policy discards previous rest credit', () => {
    const m = make({ breakSeconds: 120 });
    tick(m, 60, { idle: true, idleSince: 0 });
    m.configure(settings({ breakSeconds: 120, respectIdleInhibitors: false }));
    assert.equal(m.rest, null);
    tick(m, 1, { idle: false });
    assert.ok(m.work < 3000);
    tick(m, 60, { idle: true, idleSince: 61 });
    tick(m, 61); tick(m, 0, { idle: false });
    assert.equal(m.work, 3000);
});

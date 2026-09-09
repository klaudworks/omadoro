// All times are injected seconds: monotonic running time and suspend-aware boot
// time. Reconciliation applies new desktop conditions before automatic expiry.
var MAX_WORK = Number.MAX_SAFE_INTEGER / 1000;
function format(seconds) {
    var whole = Math.max(0, Math.ceil(seconds));
    return whole >= 60 ? Math.ceil(whole / 60) + "m" : whole + "s";
}
function create(settings, time, inputs) { return new TimerModel(settings, time, inputs); }
function TimerModel(settings, time, inputs) {
    this.settings = Object.assign({}, settings);
    this.time = { mono: time.mono, boot: time.boot };
    this.inputs = Object.assign({ outputs: [], locked: false, sleeping: false,
        available: true, idle: false, idleSince: time.boot }, inputs || {});
    this.phase = settings.autoStart ? "Working" : "Stopped";
    this.work = settings.workMinutes * 60;
    this.breakState = null;
    this.warning = null;
    this.rest = null;
    this.restBaseline = time.boot;
    this.sequence = 0;
    this.error = "";
    this.disposed = false;
    this.reconcile(time, {});
}
TimerModel.prototype.available = function() {
    var i = this.inputs;
    return i.available && !i.locked && !i.sleeping && i.outputs.length > 0;
};
TimerModel.prototype.idle = function() { return this.inputs.idle; };
TimerModel.prototype.eligible = function() {
    return this.phase === "Working" && this.available() && !this.idle();
};
TimerModel.prototype.cancelWarning = function() { this.warning = null; };
TimerModel.prototype.releaseCoverage = function() {
    if (this.breakState) {
        this.breakState.surface = false;
        this.breakState.token = ++this.sequence;
        this.breakState.ready = {};
    }
};
TimerModel.prototype.fresh = function() {
    this.releaseCoverage();
    this.breakState = null;
    this.phase = "Working";
    this.work = this.settings.workMinutes * 60;
    this.warning = null;
    this.rest = null;
    this.restBaseline = this.time.boot;
};
TimerModel.prototype.fail = function(reason) {
    this.releaseCoverage();
    this.breakState = null;
    this.phase = "Stopped";
    this.warning = null;
    this.rest = null;
    this.error = reason;
};
TimerModel.prototype.prepare = function(manual) {
    this.warning = null;
    this.rest = null;
    this.phase = "Breaking";
    this.breakState = { manual: manual, stage: "preparing", surface: true,
        token: ++this.sequence, ready: {}, due: this.time.mono + 5,
        duration: this.settings.breakSeconds, remaining: this.settings.breakSeconds,
        policy: this.settings.skipPolicy, wait: Math.min(this.settings.skipWaitSeconds, this.settings.breakSeconds),
        elapsed: 0, lockOnBreak: this.settings.lockOnBreak === true, lockAttempted: false };
};
// The host owns the actual session lock and authentication. Request it once per
// break, after all reminder surfaces are ready; never request an unlock.
TimerModel.prototype.takeLockRequest = function() {
    var b = this.breakState;
    if (!b || b.stage !== "active" || !b.lockOnBreak || b.lockAttempted || !this.available()) return false;
    b.lockAttempted = true;
    return true;
};
TimerModel.prototype.reconcile = function(time, patch, deferEligibility) {
    if (this.disposed) return;
    var dm = time.mono - this.time.mono, db = time.boot - this.time.boot;
    if (!Number.isFinite(dm) || !Number.isFinite(db) || dm < -0.001 || db < -0.001 || db + 0.05 < dm) {
        this.fail("Clock continuity lost. Start again when desktop timing is available.");
        return;
    }
    dm = Math.max(0, dm); db = Math.max(0, db);
    var oldAvailable = this.available();
    var oldOutputs = this.inputs.outputs;
    var oldRest = this.inputs.locked || this.inputs.sleeping;
    if (this.phase === "Working" && oldAvailable && !this.idle())
        this.work = Math.max(0, this.work - dm);
    if (this.breakState && this.breakState.stage === "active") {
        var consumed = oldRest ? db : oldAvailable ? dm : 0;
        this.breakState.remaining = Math.max(0, this.breakState.remaining - consumed);
        this.breakState.elapsed += consumed;
    }
    this.time = { mono: time.mono, boot: time.boot };
    this.inputs = Object.assign({}, this.inputs, patch || {});
    var absent = this.inputs.locked || this.inputs.sleeping || this.idle();
    if (!this.breakState) {
        if (absent) {
            var since = this.inputs.locked || this.inputs.sleeping ? time.boot
                : Math.max(this.restBaseline, Math.min(time.boot, this.inputs.idleSince));
            if (!this.rest) this.rest = { since: since, target: this.settings.breakSeconds, satisfied: false };
            if (time.boot - this.rest.since >= this.rest.target) this.rest.satisfied = true;
        } else if (this.rest) {
            if ((this.rest.satisfied || time.boot - this.rest.since >= this.rest.target)
                && (this.phase === "Working" || this.phase === "Paused"))
                this.work = this.settings.workMinutes * 60;
            this.rest = null;
            this.restBaseline = time.boot;
        }
    }

    var b = this.breakState;
    if (b) {
        if (b.stage === "pending" && b.restSince !== undefined) {
            if (time.boot - b.restSince >= b.duration) b.restSatisfied = true;
            if (!this.inputs.locked && !this.inputs.sleeping) delete b.restSince;
        }
        if (b.stage === "active") {
            if (b.remaining === 0 && this.available()) this.fresh();
            else if (!this.available()) {
                if (b.surface) this.releaseCoverage();
            } else if (!b.surface) {
                b.surface = true; b.token = ++this.sequence; b.ready = {}; b.due = time.mono + 5;
            }
        } else if (!this.available() || (!b.manual && this.idle())) {
            if (b.manual && (this.inputs.locked || this.inputs.sleeping) && b.restSince === undefined)
                b.restSince = time.boot;
            this.releaseCoverage();
            if (b.manual) b.stage = "pending";
            else {
                this.breakState = null;
                this.phase = "Working";
                this.work = 0;
                // Establish reliable rest without waiting for the next tick.
                if (absent) this.rest = { since: this.idle() ? Math.max(this.restBaseline, this.inputs.idleSince) : time.boot,
                    target: b.duration, satisfied: false };
            }
        } else if (b.stage === "pending") {
            if (b.restSatisfied) this.fresh();
            else {
                b.stage = "preparing"; b.surface = true; b.token = ++this.sequence; b.ready = {}; b.due = time.mono + 5;
                delete b.restSince;
            }
        }
        b = this.breakState;
        if (b && b.surface) {
            Object.keys(b.ready).forEach(function(name) {
                if (this.inputs.outputs.indexOf(name) < 0) delete b.ready[name];
            }, this);
            var missing = this.inputs.outputs.some(function(name) { return !b.ready[name]; });
            if (missing && this.inputs.outputs.some(function(name) { return oldOutputs.indexOf(name) < 0; })
                && b.stage === "active") b.due = time.mono + 5;
            if (missing && time.mono >= b.due) this.fail("Break coverage timed out. All surfaces released.");
        }
    }
    if (!this.eligible()) this.cancelWarning();
    if (deferEligibility || this.breakState || !this.eligible()) return;
    var delay = Math.max(this.work, 0);
    if (!this.warning && this.settings.warningEnabled && delay <= 15)
        this.warning = { token: ++this.sequence, end: time.mono + 15 };
    var warned = this.warning ? time.mono >= this.warning.end : !this.settings.warningEnabled;
    if (this.work === 0 && warned) this.prepare(false);
};
TimerModel.prototype.ready = function(token, output) {
    var b = this.breakState;
    if (!b || !b.surface || token !== b.token || !this.available()
        || this.inputs.outputs.indexOf(output) < 0) return false;
    if (b.stage !== "active" && !b.manual && !this.eligibleForPending()) return false;
    b.ready[output] = true;
    if (b.stage === "preparing" && this.inputs.outputs.every(function(name) { return b.ready[name]; })) {
        b.stage = "active";
        b.elapsed = 0;
        b.remaining = b.duration;
    }
    return true;
};
TimerModel.prototype.eligibleForPending = function() { return this.available() && !this.idle(); };
TimerModel.prototype.coverageLost = function(token, output) {
    var b = this.breakState;
    if (b && b.surface && b.token === token && this.available() && this.inputs.outputs.indexOf(output) >= 0)
        this.fail("Break coverage lost on " + output + ". All surfaces released.");
};
TimerModel.prototype.configure = function(settings) {
    var old = this.settings;
    this.settings = Object.assign({}, settings);
    if (old.idleThresholdSeconds !== settings.idleThresholdSeconds
        || old.respectIdleInhibitors !== settings.respectIdleInhibitors) {
        this.rest = null; this.restBaseline = this.time.boot; this.inputs.idle = false;
    }

};
TimerModel.prototype.command = function(name) {
    if (this.disposed) return { status: "rejected", reason: "Plugin disabled" };
    var p = this.phase, b = this.breakState;
    var accepted = { status: "accepted" }, noop = { status: "noop" };
    function reject(reason) { return { status: "rejected", reason: reason }; }
    if (name === "disable") { this.fail(""); this.disposed = true; return accepted; }
    if (b) {
        if (name === "break") return noop;
        if (name === "skip" && b.stage === "active" && this.available()
            && (b.policy === "allow" || (b.policy === "wait" && b.elapsed >= b.wait))) {
            this.fresh(); return accepted;
        }
        return reject("Unavailable during a break");
    }
    if (name === "break") {
        if (!this.available()) return reject("Desktop unavailable");
        this.error = ""; this.prepare(true); return accepted;
    }
    if (name === "start") {
        if (p === "Working") return noop;
        if (p === "Paused") return reject("Use Resume");
        this.error = ""; this.fresh(); return accepted;
    }
    if (name === "pause") {
        if (p !== "Working") return noop;
        this.phase = "Paused";
    } else if (name === "resume") {
        if (p === "Working") return noop;
        if (p === "Stopped") return reject("Use Start");
        this.phase = "Working";
    } else if (name === "stop") {
        if (p === "Stopped") return noop;
        this.phase = "Stopped"; this.work = this.settings.workMinutes * 60;
    } else if (name === "add" || name === "reset") {
        if (p === "Stopped") return reject("Use Start");
        this.work = name === "add" ? Math.min(MAX_WORK, Math.max(0, this.work) + 300) : this.settings.workMinutes * 60;
    } else return reject(name === "skip" ? "No active break" : "Unknown command");
    this.cancelWarning();
    return accepted;
};
TimerModel.prototype.snapshot = function() {
    var b = this.breakState, available = this.available();
    var remaining = b ? b.remaining : this.work;
    var warningSeconds = this.warning ? Math.max(0, this.warning.end - this.time.mono) : 0;
    var status = this.phase;
    if (b) status = b.stage === "active" ? "Break" : "Preparing break";
    else if (!available) status += " · desktop unavailable";
    else if (this.idle()) status += " · idle";
    if (!b && this.phase === "Working" && this.work === 0) status += " · break due";
    return { phase: this.phase, status: status, remaining: remaining, label: format(remaining),
        warning: !!this.warning, warningSeconds: warningSeconds, warningLabel: format(warningSeconds),
        preparing: !!b && b.stage !== "active", breakVisible: !!b && b.surface,
        attempt: b ? b.token : this.sequence, skipPolicy: b ? b.policy : this.settings.skipPolicy,
        skipWait: b ? Math.max(0, b.wait - b.elapsed) : 0,
        skipLabel: b ? format(Math.max(0, b.wait - b.elapsed)) : "",
        canSkip: !!b && b.stage === "active" && available && (b.policy === "allow" || (b.policy === "wait" && b.elapsed >= b.wait)),
        available: available, idle: this.idle(),
        error: this.error };
};

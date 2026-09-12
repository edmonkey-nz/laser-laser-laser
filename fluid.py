"""
fluid.py — 2D vortex flow for the "fluid" shape.

A vortex-method fluid, which is the smallest thing that is *actually* fluid
dynamics rather than an impression of it: k regularised point vortices
advecting one another under Biot-Savart, and a closed elastic loop carried
along by the velocity field they induce. Four or more interacting vortices
is a chaotic system, so the motion never settles into a loop or a cycle —
that is what makes it worth simulating instead of summing sines.

Why this model and not a grid solver: the field a vortex sum induces is
divergence-free by construction, so it has no sinks. A sink is the one
thing this pipeline cannot draw — samples converge into a pile, a pile of
lit samples on one DAC coordinate is a stationary beam, and docs/SAFETY.md
§6 rules that out. A stable-fluids grid needs a pressure projection every
frame to earn the same property.

What this module does NOT do is worry about the point budget: `step()`
always simulates LOOP_N points and `loop()` hands them over as a closed
polyline. Spacing them for the galvos is the caller's job, and in this
project that means shapes.py's `_resample_closed` — the same arc-length
resample every other shape uses. Keeping the simulation resolution fixed
also means the physics does not change when the duplicator takes a slice
of the point budget, or when the user drags the points setting.

The vessel is a circle, and it is enforced by the field rather than by
clamping anything: each vortex is mirrored in the wall (Milne-Thomson,
see `_sources`), which makes the flow there purely tangential, so nothing
can be advected across it. `_step_vortices` says what that bought.

Four forces bound the loop, and each is here for a reason that ends at the
beam rather than at the look:

  * **Tension** — discrete Laplacian smoothing, run as a projection: pass
    after pass until the perimeter is back inside an allowance, which is
    what `morph` sets. An advected contour in a swirling field stretches
    without limit, and the perimeter is what sets node spacing, so holding
    it is what keeps the curve resolvable at LOOP_N nodes. There is a small
    always-on floor underneath the projection, bounding fold sharpness even
    when the loop is short.
  * **Thickness** — a short-range repulsion between parts of the loop that
    are close in space but far apart along the curve. This one is load
    bearing, and it took measuring to find. Strain folds the loop, the
    folds get thinner, and the redistribution cannot resolve a fold thinner
    than one node gap, so it interpolates across and zips the fold shut.
    Two coincident strands are then an *absorbing* state: identical points
    have identical velocities, so advection keeps them together, smoothing
    keeps them together, and scaling keeps them together — nothing in the
    model can separate them again. Measured without it, enclosed area fell
    to exactly 0.000 across the whole strongly-stirred half of the fader
    range and never came back, leaving a line traced out and back where a
    fluid body should be. Holding the perimeter down did not prevent it.

    Physically it stands in for diffusion, the thing a real dye interface
    has and a material contour does not: a real interface stops folding at
    the scale where diffusion smears it out. Here that scale is the node
    spacing, because that is the scale this model cannot resolve.
  * **Size restore** — curve-shortening flow, which is what tension is,
    shrinks a closed loop toward a point, and a figure collapsing toward a
    point is a parked beam. A uniform scale about the centroid corrects the
    size without flattening the shape the flow just made.

    It restores the mean radius and not the enclosed area, even though area
    is the physical invariant — a contour advected in a divergence-free
    field encloses a constant area, and tension is the only thing that
    loses any. Area was tried and is unrecoverable: a folded-shut loop has
    a signed area of exactly zero, and scaling a zero-area curve leaves it
    at zero, so the restore meant to rescue the figure has no gradient to
    work with. Mean radius is always recoverable, which is worth more here
    than being the right invariant.
  * **Centroid pull** — a vortex pair of opposite sign is a dipole, and a
    dipole translates: it would park the loop against one side of the
    vessel. Slow, so drifting around the field is still part of the look.

Cost is around 2.6 ms per frame at the defaults and 4.1 ms at the busiest
fader settings, against a 27 ms budget at 800 points and 30 kpps. That
makes this the most expensive shape in the synth by roughly an order of
magnitude, which is affordable but worth knowing before adding to it.
"""

import numpy as np

TWO_PI = 2.0 * np.pi

# Simulation resolution of the loop. Deliberately fixed and independent of
# the point budget (see the module docstring). 256 segments around the
# perimeter is finer than the beam resolves, so the resample downstream is
# interpolating along short chords rather than inventing geometry.
LOOP_N = 256

MAX_VORTICES = 12

# Vortex blob radius (Krasny desingularisation): v = G/2pi * r/(r^2 + d^2).
# The bare point-vortex 1/r is singular, and a loop point that wanders close
# to a singularity gets flung across the field in one step. Regularised, the
# induced speed peaks at |G|/(4*pi*d) at exactly r = d and falls away on
# both sides, so the field is bounded everywhere by construction.
CORE = 0.16

# Circulation, as a base plus a step per unit of the swirl fader. The base
# is there because the fader is shared with every other shape and its
# default sits at 2 of 12: mapped straight through, the shape a user meets
# when they first select it barely moved. At the default it now curls
# visibly, and at full swirl the field peaks around 2.5 field-widths per
# second, which is a fast churn without being a whip.
#
# Circulation is deliberately NOT normalised by the vortex count. It was,
# by 1/sqrt(k), on the assumption that k stirrers would otherwise be k
# times faster; measuring the loop said otherwise — alternating signs
# cancel in superposition, and the un-normalised peak speed came out flat
# at 1.4-2.1 across k = 1..12, while the normalisation made twelve
# vortices three times slower than one for no reason anybody would want.
GAMMA_BASE = 0.35
GAMMA_PER_STEP = 0.45

# Hard ceiling on field speed, applied to the sampled velocity. The vortex
# sum is bounded per vortex, not in total — twelve of them lining up briefly
# is rare but not impossible, and the loop must not be able to cross the
# field inside one frame whatever they do. A backstop, not a working limit:
# the swirl fader tops out well under it, so ordinary use never reaches it.
MAX_SPEED = 4.0

REST_RADIUS = 0.62      # loop mean radius the size restore aims for
RESTORE_RATE = 1.5      # how fast it eases there (1/s)
CENTRE_RATE = 0.8       # centroid pull toward the origin (1/s)

# Tension. `morph` sets the *slack* — how much longer than a relaxed circle
# the loop is allowed to get — rather than a tension rate directly, because
# a fixed rate does not control the thing that actually goes wrong.
#
# What goes wrong is filamentation: contour advection stretches a curve
# exponentially, and a stretched loop folds back on itself as a hairpin of
# two long parallel strands. Laplacian smoothing does not remove that — a
# hairpin is *locally* smooth, so smoothing sees nothing to fix — and the
# size restore cannot either, since it only scales. Measured at the default
# swirl, the loop grew a filament within about four seconds and kept it.
#
# So what is controlled is the perimeter, the way surface tension in a real
# fluid resists interface length. Curve-shortening flow removes length
# fastest where curvature is highest, which is the tip of a hairpin, so the
# excess comes off the filaments rather than out of the shape everywhere.
#
# It is enforced as a projection and not as a force: smoothing pass after
# pass until the perimeter is back inside the allowance, up to a cap. A
# force with a gain balances somewhere instead of holding, and where it
# balanced was too long — 2.2x the allowance, with the gain raised to the
# point where more gain changed nothing.
#
# Perimeter is the right quantity because it sets node spacing, which is
# allowance / LOOP_N, and the spacing decides whether the loop keeps a body
# at all: the redistribution cannot resolve a fold thinner than one node
# gap, so it zips that fold shut, and a loop that has zipped shut everywhere
# is a line traced out and back. Holding the perimeter holds the spacing
# fine enough not to.
#
# BASE is the floor that never switches off — the bound on fold sharpness,
# which is what keeps the curve drawable at LOOP_N points.
SLACK_MIN = 1.15        # morph 0: taut, a loop with a body
SLACK_MAX = 3.15        # morph 1: loose, stretched into strands
TENSION_BASE = 2.0      # 1/s of smoothing that is always on
TENSION_W = 0.5         # smoothing weight per projection pass (0.5 = stable max)
TENSION_ITERS = 24      # ceiling on projection passes per step
TENSION_BATCH = 4       # passes run between perimeter checks

# Thickness, as a multiple of the node spacing: no two parts of the loop
# more than THICK_SEP nodes apart along the curve may come closer than this
# many node gaps. Three keeps every fold resolvable by the redistribution
# with a gap to spare. THICK_SEP has to exceed it, or the force would fight
# the node spacing itself — points a few nodes apart are *supposed* to be
# one gap from each other.
THICK_GAPS = 3.0
THICK_SEP = 6
THICK_RATE = 8.0        # 1/s, how fast a too-thin fold is pushed apart

# Numerical backstop on the vortices, as a fraction of the vessel radius.
# The circle theorem (see `_sources`) already makes the wall impassable
# analytically — the flow there is purely tangential — so this only ever
# catches a finite-timestep overshoot. It clamps position on overshoot and
# damps nothing, which is the point: the soft inward wall it replaced was
# dissipative, and a dissipative wall has an equilibrium. Measured with it:
# a plus/minus vortex pair propelled itself outward until the inward push
# cancelled its own translation, all four vortices piled onto one point at
# the wall, and the velocity field went to zero and stayed there — the
# figure froze into a static wedge after about 25 seconds.
LEASH = 0.985

# Radius of the vessel, and the width of the soft knee the loop saturates
# through as it approaches. One radius for the whole model: this is also the
# circle the vortex images are reflected in, so the flow field itself is
# tangential here and the saturation is a backstop to that rather than the
# mechanism.
#
# The loop needs the backstop because the flow is not the only thing moving
# it. A single strong vortex winds it into a spiral and stretches it into
# filaments — the mean radius stays put, which is all the size restore
# holds, while individual points measured up to 4.8 field-widths out, so
# most of the figure was off the field and blanked: a few lit fragments
# where a whirlpool should be. Saturating with a tanh rather than clamping
# means the loop *asymptotes* to WALL_R and can never leave the field at
# all, which is a stronger property than relying on the off-field blanking
# downstream. It costs nothing either: a squashed filament reads as fluid
# meeting the side of the tank, which is what it is.
WALL_R = 0.95
WALL_SOFT = 0.15

# Longest step the simulator will take, whatever dt it is handed. A stall in
# the render loop (a device timeout, a window drag, the first frame after
# startup) arrives here as a large dt, and integrating the flow over 300 ms
# in one Euler step is how a stable simulation explodes. Slowing down is the
# right failure: the fluid lags for a frame and nobody can see it.
MAX_DT = 0.05


class FluidField:
    """Vortices plus one advected loop. One instance per engine; `step()`
    advances it by dt and `loop()` returns the current closed curve."""

    def __init__(self, seed=12345):
        self._seed = seed
        self.reset()

    # -------------------------------------------------------------- setup

    def reset(self):
        """Back to the seed state. Deterministic, so a recalled pattern and
        a fresh start render the same opening — the same reason
        ShapeEngine.reset_phases rewinds the spin angle."""
        self.rng = np.random.default_rng(self._seed)
        self.count = 0
        self.vx = np.zeros(0)
        self.vy = np.zeros(0)
        self.unit = np.zeros(0)     # circulation per unit swirl, signed
        self._seed_vortices(3)
        t = np.linspace(0, TWO_PI, LOOP_N, endpoint=False)
        self.lx = REST_RADIUS * np.cos(t)
        self.ly = REST_RADIUS * np.sin(t)
        # which node pairs the thickness force applies to: far enough apart
        # along the ring to be a genuine fold rather than neighbours.
        # Constant, since LOOP_N is, so it is built once.
        i = np.arange(LOOP_N)
        sep = np.abs(i[:, None] - i[None, :])
        self._fold = np.minimum(sep, LOOP_N - sep) > THICK_SEP

    def _seed_vortices(self, k):
        """Grow or shrink to k vortices, keeping the ones already running.

        Reseeding the whole set on every turn of the count fader would snap
        the flow to a new configuration each notch; appending instead lets
        the fader read as adding a stirrer to the tank.
        """
        k = int(np.clip(k, 1, MAX_VORTICES))
        if k == self.count:
            return
        if k < self.count:
            self.vx = self.vx[:k].copy()
            self.vy = self.vy[:k].copy()
            self.unit = self.unit[:k].copy()
        else:
            add = k - self.count
            # uniform in a disc, not in radius — sqrt keeps them from
            # clustering in the middle, where they would mostly cancel
            r = 0.7 * np.sqrt(self.rng.random(add))
            a = TWO_PI * self.rng.random(add)
            self.vx = np.concatenate([self.vx, r * np.cos(a)])
            self.vy = np.concatenate([self.vy, r * np.sin(a)])
            # alternating signs: near-zero net circulation, so the field
            # stirs instead of spinning the whole tank one way. The jitter
            # stops equal-and-opposite pairs from locking into a clean orbit.
            sign = np.where((np.arange(self.count, k) % 2) == 0, 1.0, -1.0)
            mag = 0.7 + 0.6 * self.rng.random(add)
            self.unit = np.concatenate([self.unit, sign * mag])
        self.count = k

    # ------------------------------------------------------------- physics

    def _redistribute(self):
        """Respace the loop's nodes at equal arc length.

        This is node management for the *simulation*, not spacing for the
        beam — shapes.py resamples again on the way out, for the galvos.
        Both are arc-length resamples and the duplication is deliberate:
        this one has to happen every step, before the tension term runs,
        and fluid.py does not import from this project (nor the other way
        round, which would be a cycle).

        It is what makes the tension term mean anything. Nodes advect at
        the local flow speed, so their spacing drifts apart in a stretching
        region and bunches in a stagnant one, and the discrete Laplacian is
        indexed by node rather than by distance — so with drifted spacing it
        stops being a curvature operator exactly where curvature matters,
        the two or three nodes left holding the tip of a filament. Measured
        without this: tension pinned at its 0.5-per-iteration ceiling and
        the perimeter still ran to 3.9x rest, i.e. the term was saturated
        and doing nothing.
        """
        px = np.append(self.lx, self.lx[0])
        py = np.append(self.ly, self.ly[0])
        cum = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(px),
                                                        np.diff(py)))])
        if cum[-1] < 1e-6:
            # collapsed to a point. Same call as _resample_closed makes in
            # shapes.py: never hand back a point, start the loop over.
            t = np.linspace(0, TWO_PI, LOOP_N, endpoint=False)
            self.lx = REST_RADIUS * np.cos(t)
            self.ly = REST_RADIUS * np.sin(t)
            return
        s = np.linspace(0.0, cum[-1], LOOP_N, endpoint=False)
        self.lx = np.interp(s, cum, px)
        self.ly = np.interp(s, cum, py)

    @staticmethod
    def _sources(vx, vy, gam):
        """Every vortex, plus its image in the vessel wall.

        Milne-Thomson's circle theorem: a vortex G at radius r inside a
        circle of radius R, mirrored by an image -G at the inverse point
        R^2/r on the same ray, gives a combined field with no flow through
        the circle. That one line of geometry buys three things at once.

        The wall becomes impassable rather than enforced — the velocity at
        the boundary is purely tangential, so neither a vortex nor a loop
        point can be advected across it, and the clamps elsewhere in this
        file are backstops against finite timesteps rather than the
        mechanism. It adds no damping, so unlike the inward push it
        replaced it cannot have an equilibrium to settle into. And it is
        what keeps the system alive: a vortex is driven by its own image,
        so a lone vortex orbits the vessel instead of sitting still, and a
        pair that would have propelled itself into the wall glides along it.

        The images sit at R^2/r >= R, outside the vessel, so they are never
        near the loop except when their vortex is itself at the wall — and
        there the two nearly coincide with opposite signs and cancel, which
        is exactly the no-through-flow the theorem is asserting.
        """
        r2 = vx * vx + vy * vy
        scale = WALL_R * WALL_R / np.maximum(r2, 1e-6)
        return (np.concatenate([vx, vx * scale]),
                np.concatenate([vy, vy * scale]),
                np.concatenate([gam, -gam]))

    @staticmethod
    def _induced(px, py, sx, sy, sg, drop_self=False):
        """Velocity the sources (sx, sy, sg) induce at the points (px, py).

        The blob denominator (r^2 + CORE^2) is what makes this safe to
        evaluate anywhere, including exactly on a vortex centre.
        drop_self zeroes the term of source j at point j, for the case
        where the points *are* the vortices: a vortex does not induce
        velocity on itself, and including the term would be both wrong and
        (even regularised) violent. Its image is not self, and is kept —
        that term is what makes it orbit. It relies on `_sources` putting
        the real vortices first, in order, which is why that ordering is
        not an implementation detail to be tidied.
        """
        dx = px[:, None] - sx[None, :]
        dy = py[:, None] - sy[None, :]
        w = sg[None, :] / (TWO_PI * (dx * dx + dy * dy + CORE * CORE))
        if drop_self:
            np.fill_diagonal(w[:, :len(px)], 0.0)
        u = -(dy * w).sum(axis=1)
        v = (dx * w).sum(axis=1)
        sp = np.hypot(u, v)
        over = sp > MAX_SPEED
        if over.any():
            scale = np.where(over, MAX_SPEED / np.maximum(sp, 1e-9), 1.0)
            u, v = u * scale, v * scale
        return u, v

    def _step_vortices(self, dt, gam):
        """Biot-Savart: every vortex is carried by the field of the others
        and of every image, its own included.

        Midpoint (RK2), for the same reason the loop gets it: a vortex
        driven by its own image is on a circular orbit, and explicit Euler
        walks a circular orbit outward a little every step. Measured with
        Euler, a lone vortex started at r = 0.33 crept out to the wall and
        stayed there, which the circle theorem says cannot happen — its
        radius is exactly conserved. With the midpoint step it holds 0.334
        indefinitely.

        Several vortices still work their way outward and spend much of
        their time near the rim (mean radius 0.76 to 0.91 across the fader
        range), and that part is real rather than numerical: a mixed-sign
        vortex system in a disc conserves total angular impulse, not each
        vortex's own radius, so the positives can move out as the negatives
        move in. They keep stirring from there, which is what matters.
        """
        u1, v1 = self._induced(self.vx, self.vy,
                               *self._sources(self.vx, self.vy, gam),
                               drop_self=True)
        hx = self.vx + u1 * dt * 0.5
        hy = self.vy + v1 * dt * 0.5
        u2, v2 = self._induced(hx, hy, *self._sources(hx, hy, gam),
                               drop_self=True)
        self.vx = self.vx + u2 * dt
        self.vy = self.vy + v2 * dt
        # Position-only backstop against a finite-timestep overshoot of a
        # wall the field says is impassable. No velocity is touched, so
        # nothing here can bring the flow to rest.
        r = np.hypot(self.vx, self.vy)
        far = r > LEASH * WALL_R
        if far.any():
            f = np.where(far, LEASH * WALL_R / np.maximum(r, 1e-9), 1.0)
            self.vx = self.vx * f
            self.vy = self.vy * f

    def _thicken(self, dt, spacing):
        """Push apart parts of the loop that have folded too thin.

        One LOOP_N x LOOP_N distance matrix per step — 65k pairs, which is
        nothing in numpy and is the whole reason this can be done exactly
        rather than with a spatial index. The displacement is clamped per
        node so a loop that arrives badly folded eases apart over several
        frames instead of exploding in one.
        """
        thick = THICK_GAPS * spacing
        dx = self.lx[:, None] - self.lx[None, :]
        dy = self.ly[:, None] - self.ly[None, :]
        d2 = dx * dx + dy * dy
        close = self._fold & (d2 < thick * thick)
        if not close.any():
            return
        d = np.sqrt(np.maximum(d2, 1e-12))
        push = np.where(close, (thick - d) / d, 0.0)
        fx = (push * dx).sum(axis=1)
        fy = (push * dy).sum(axis=1)
        mag = np.hypot(fx, fy)
        lim = 0.5 * thick
        move = np.minimum(THICK_RATE * dt * mag, lim)
        scale = np.where(mag > 1e-12, move / np.maximum(mag, 1e-12), 0.0)
        self.lx = self.lx + fx * scale
        self.ly = self.ly + fy * scale

    # Both of these run up to TENSION_ITERS times per step, which makes
    # them the hot path of the whole module — written with explicit slices
    # rather than np.roll/np.diff for that reason alone. The idiomatic
    # versions each allocate and go through several layers of Python per
    # call, and profiling put 5 of the worst case's 7.8 ms per step inside
    # np.roll. Same arithmetic, a quarter of the time.

    def _perimeter(self):
        lx, ly = self.lx, self.ly
        dx = np.empty_like(lx)
        dy = np.empty_like(ly)
        dx[:-1] = lx[1:] - lx[:-1]
        dy[:-1] = ly[1:] - ly[:-1]
        dx[-1] = lx[0] - lx[-1]          # the closing segment
        dy[-1] = ly[0] - ly[-1]
        return float(np.hypot(dx, dy).sum())

    def _smooth(self, w):
        """One pass of x += w * (neighbour mean - x) on the closed ring.
        Stable up to w = 0.5; above that a pass overshoots its neighbours
        and the ring can ring."""
        if w <= 1e-4:
            return
        lx, ly = self.lx, self.ly
        mx = np.empty_like(lx)
        my = np.empty_like(ly)
        mx[1:-1] = lx[:-2] + lx[2:]
        my[1:-1] = ly[:-2] + ly[2:]
        mx[0] = lx[-1] + lx[1]
        my[0] = ly[-1] + ly[1]
        mx[-1] = lx[-2] + lx[0]
        my[-1] = ly[-2] + ly[0]
        lx += w * (0.5 * mx - lx)
        ly += w * (0.5 * my - ly)

    def step(self, dt, p):
        """Advance the flow by dt, reading the shape faders out of p.

        ratio_a = vortex count, ratio_b = swirl strength, morph = how loose
        the loop is (0 taut and near-circular, 1 folding). dt = 0 (the
        engine's pause) is a legal no-op: the figure freezes where it is.
        """
        dt = float(np.clip(dt, 0.0, MAX_DT))
        self._seed_vortices(round(p.get("ratio_a", 3.0)))
        swirl = float(np.clip(p.get("ratio_b", 4.0), 1.0, 12.0))
        morph = float(np.clip(p.get("morph", 0.25), 0.0, 1.0))
        if dt <= 0.0:
            return

        gam = self.unit * (GAMMA_BASE + GAMMA_PER_STEP * (swirl - 1.0))

        self._step_vortices(dt, gam)
        # rebuilt after the vortices moved, so the loop is advected by the
        # field as it is now rather than as it was a step ago
        src = self._sources(self.vx, self.vy, gam)

        # Midpoint (RK2) advection of the loop. Explicit Euler in a rotating
        # field spirals outward — a circle drifting into a growing spiral
        # every frame — and no amount of size restore hides that. Two field
        # evaluations of 256 points against <=12 vortices is nothing.
        u1, v1 = self._induced(self.lx, self.ly, *src)
        u2, v2 = self._induced(self.lx + u1 * dt * 0.5,
                               self.ly + v1 * dt * 0.5, *src)
        self.lx = self.lx + u2 * dt
        self.ly = self.ly + v2 * dt

        self._redistribute()

        # Tension: x += w * (neighbour mean - x), on the closed ring. Rate
        # in 1/s so the curve behaves the same at 20 fps as at 60; capped at
        # 0.5 per iteration, which is where the smoothing stays stable.
        # The always-on floor first: rate in 1/s, so the curve behaves the
        # same at 20 fps as at 60.
        self._smooth(float(np.clip(TENSION_BASE * dt, 0.0, TENSION_W)))

        # Then project the perimeter back inside the slack allowance.
        slack = SLACK_MIN + (SLACK_MAX - SLACK_MIN) * morph
        allow = TWO_PI * REST_RADIUS * slack
        # Checked in batches: a pass is far cheaper than the check that
        # decides whether to run it, and overshooting the allowance by a
        # few percent costs nothing.
        for _ in range(TENSION_ITERS // TENSION_BATCH):
            if self._perimeter() <= allow:
                break
            for _ in range(TENSION_BATCH):
                self._smooth(TENSION_W)

        self._thicken(dt, self._perimeter() / LOOP_N)

        # Size and centroid restore — the two degrees of freedom that end in
        # a collapsed or an off-field figure. Both are eased, and the scale
        # is uniform about the centroid so the folds the flow just made
        # survive it.
        cx = self.lx.mean()
        cy = self.ly.mean()
        dx = self.lx - cx
        dy = self.ly - cy
        rbar = float(np.hypot(dx, dy).mean())
        if rbar > 1e-6:
            ease = float(np.clip(RESTORE_RATE * dt, 0.0, 1.0))
            scale = 1.0 + ease * (REST_RADIUS / rbar - 1.0)
            dx *= scale
            dy *= scale
        pull = float(np.clip(CENTRE_RATE * dt, 0.0, 1.0))
        cx *= (1.0 - pull)
        cy *= (1.0 - pull)
        self.lx = dx + cx
        self.ly = dy + cy

        # Vessel wall. tanh saturates at WALL_R without ever reaching it, so
        # the curve stays smooth and no run of points is pinned flat onto
        # the boundary — a pinned run is a stationary beam, the thing the
        # arc-length spacing downstream exists to avoid.
        r = np.hypot(self.lx, self.ly)
        knee = WALL_R - WALL_SOFT
        out = r > knee
        if out.any():
            sat = knee + WALL_SOFT * np.tanh((r - knee) / WALL_SOFT)
            f = np.where(out, sat / np.maximum(r, 1e-9), 1.0)
            self.lx = self.lx * f
            self.ly = self.ly * f

        # Non-finite coordinates would survive the clip at pack time and
        # land on the DAC as whatever int32 the cast happens to produce.
        # Nothing above should be able to produce one; if something does,
        # start over rather than stream it.
        if not (np.isfinite(self.lx).all() and np.isfinite(self.ly).all()
                and np.isfinite(self.vx).all() and np.isfinite(self.vy).all()):
            self.reset()

    # -------------------------------------------------------------- output

    def loop(self):
        """The current loop as a closed polyline (x, y), LOOP_N points, in
        normalised [-1,1] space. Closed implicitly: the last point joins the
        first, exactly as every generator in shapes.py returns them."""
        return self.lx, self.ly

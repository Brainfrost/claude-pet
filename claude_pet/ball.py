"""Ein Ball zum Spielen: hüpft über Textzeilen, Fensterkanten und erkannte Ebenen, rollt über Kanten."""
from .world import ROW_SCREEN, Platform


class Ball:
    def __init__(self, x, y, vx=0.0, vy=0.0, line_h=20.0):
        self.S = line_h / 24.0
        self.r = max(5, int(round(line_h * 0.32)))
        self.x, self.y = float(x), float(y)       # Mittelpunkt
        self.vx, self.vy = float(vx), float(vy)
        self.carried_by = None                    # "pet" | "user" | None
        self.resting = False
        self.support = None
        self.idle_t = 0.0                         # wie lange er schon still liegt
        self.angle = 0.0

    @property
    def bottom(self):
        return self.y + self.r

    @property
    def free(self):
        return self.carried_by is None

    def throw(self, vx, vy):
        cap = 2600 * self.S
        self.vx, self.vy = max(-cap, min(cap, vx)), max(-cap, min(cap, vy))
        self.carried_by, self.resting, self.support, self.idle_t = None, False, None, 0.0

    def step(self, dt, world, screen_floor, vbounds):
        if not self.free:
            self.idle_t = 0.0
            return
        G = 2000 * self.S
        if self.resting:
            self._roll(dt, world)
            return
        self.vy += G * dt
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        l, t, r, b = vbounds
        if nx - self.r < l or nx + self.r > r:
            nx = min(max(nx, l + self.r), r - self.r)
            self.vx = -self.vx * 0.7
        if ny - self.r < t:
            ny = t + self.r
            self.vy = abs(self.vy) * 0.5
        if self.vy > 0:
            p = world.landing(nx, self.bottom, ny + self.r, 0.0)
            floor = screen_floor(nx)
            if p is None and ny + self.r >= floor:
                p = Platform(nx - 10 ** 6, nx + 10 ** 6, floor, -1, ROW_SCREEN)
            if p is not None:
                self.x, self.y = nx, p.y - self.r
                if self.vy > 260 * self.S:            # aufprallen und zurückspringen
                    self.vy = -self.vy * 0.55
                    self.vx *= 0.85
                else:
                    self.vy = 0.0
                    self.resting, self.support = True, p
                self.angle += self.vx * dt / self.r
                return
        self.x, self.y = nx, ny
        self.angle += self.vx * dt / self.r

    def _roll(self, dt, world):
        p = self.support
        self.vx *= max(0.0, 1 - 2.2 * dt)
        if abs(self.vx) < 6 * self.S:
            self.vx = 0.0
            self.idle_t += dt
        self.x += self.vx * dt
        self.angle += self.vx * dt / self.r
        # liegt er noch auf etwas? (Text kann wegscrollen, Fenster sich bewegen)
        here = p if p is not None and p.row == ROW_SCREEN else next(
            (q for q in world.platforms if abs(q.y - self.bottom) < 3 and q.covers(self.x, self.r * 0.3)), None)
        if here is None or not here.covers(self.x, self.r * 0.3):
            self.resting, self.support = False, None
            self.vy = 0.0
        else:
            self.support = here
            self.y = here.y - self.r

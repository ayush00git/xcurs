"""Phase 1 demo: watch the cursor move by itself.

    python -m xcurs.demo              # draw a circle
    python -m xcurs.demo --shape square --loops 3
    python -m xcurs.demo --scroll     # also scroll down and back up
"""

from __future__ import annotations

import argparse
import math
import time

from .pointer import VirtualPointer

FPS = 120


def circle(radius: float, steps: int):
    """Yield relative steps that trace a circle: the difference between
    consecutive points, because a mouse only ever reports *movement*."""
    prev = (radius, 0.0)
    for i in range(1, steps + 1):
        a = 2 * math.pi * i / steps
        cur = (radius * math.cos(a), radius * math.sin(a))
        yield cur[0] - prev[0], cur[1] - prev[1]
        prev = cur


def square(side: float, steps: int):
    per_side = steps // 4
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        for _ in range(per_side):
            yield dx * side / per_side, dy * side / per_side


def main() -> None:
    p = argparse.ArgumentParser(description="Move the cursor with a virtual uinput mouse.")
    p.add_argument("--shape", choices=["circle", "square"], default="circle")
    p.add_argument("--size", type=float, default=200, help="radius / side in pixels")
    p.add_argument("--loops", type=int, default=2)
    p.add_argument("--seconds", type=float, default=2.0, help="time per loop")
    p.add_argument("--scroll", action="store_true", help="scroll a bit at the end")
    args = p.parse_args()

    steps = int(args.seconds * FPS)
    shape = circle if args.shape == "circle" else square

    with VirtualPointer() as mouse:
        # The compositor needs a moment to notice the new device before it
        # will act on its events.
        time.sleep(0.5)
        print(f"Drawing a {args.shape} ({args.loops} loops). Hands off the mouse!")
        for _ in range(args.loops):
            for dx, dy in shape(args.size, steps):
                mouse.move(dx, dy)
                time.sleep(1 / FPS)
        if args.scroll:
            print("Scrolling down, then up.")
            for direction in (-1, 1):
                for _ in range(FPS):
                    mouse.scroll(dy=direction * 0.05)  # smooth: 1/20 notch per frame
                    time.sleep(1 / FPS)
        print("Done.")


if __name__ == "__main__":
    main()

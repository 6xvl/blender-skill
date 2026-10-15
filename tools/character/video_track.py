"""Tracks the purple hat (head) through the first 4 s at 60 fps: bob, sway, and frame-to-frame jolt."""
import subprocess, sys
import numpy as np
W, H = 920, 720
raw = subprocess.run(["ffmpeg", "-v", "error", "-t", "4.1", "-i", sys.argv[1], "-vf", "crop=920:720:360:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
f = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3).astype(int)
xs, ys = [], []
for im in f:
    m = (im[..., 0] > 90) & (im[..., 2] > 110) & (im[..., 1] < 70) & (np.arange(H)[:, None] < 330) & (np.arange(W)[None, :] > 150) & (np.arange(W)[None, :] < 800)
    yy, xx = np.nonzero(m)
    hi = yy < np.percentile(yy, 35)            # the hat, not the bow tie below it
    xs.append(xx[hi].mean()); ys.append(yy[hi].mean())
x, y = np.array(xs), np.array(ys)
print("frames", len(x), "| hat x range", round(x.max() - x.min(), 1), "px | y range", round(y.max() - y.min(), 1), "px (character about 330 px tall)")
for name, v in (("x", x), ("y", y)):
    c = v - v.mean()
    ac = np.correlate(c, c, "full")[len(c) - 1:]
    lag = 30 + int(np.argmax(ac[30:200]))
    print(name, "repeats every", lag, "frames =", round(lag / 60, 2), "s")
dy = np.diff(y)
print("y per frame (down is +), every 2nd frame:", " ".join(f"{v:+.1f}" for v in dy[:130:2]))
print("y positions every 4th frame:", " ".join(f"{v:.0f}" for v in y[:130:4]))
print("x positions every 4th frame:", " ".join(f"{v:.0f}" for v in x[:130:4]))
jerk = np.abs(np.diff(y, 2))
print("biggest sudden changes in y speed at frames", sorted(np.argsort(jerk)[-8:].tolist()), "| sizes", [round(float(jerk[i]), 1) for i in sorted(np.argsort(jerk)[-8:].tolist())])

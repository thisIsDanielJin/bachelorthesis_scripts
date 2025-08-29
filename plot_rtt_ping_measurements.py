import os
import re
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np


# ================== CONFIG ==================
FOLDER = "RawMessungen/PingAWS"  # folder containing *.txt ping outputs
IMG_DIR = "img"
CLOCKTIME_LABEL = "Ping"
SCENARIO_NAME = "AWS"  # e.g., "AWS", "SingleLocal", "DoubleLocal"

# Annotation settings
ANNOTATION_FMT = "{:.3f} ms"  # label format for RTT values
MAX_LABEL_OFFSET = (0, 6)     # pixel offset for the max point label (above)
MIN_LABEL_OFFSET = (0, -10)   # pixel offset for the min point label (below)
ANNOTATION_FONTSIZE = 7

# Margins (relative fraction of data range)
X_MARGIN = 0.02  # ~2% extra space on the right (left stays pinned at 0)
Y_MARGIN = 0.10  # ~10% extra space on top

os.makedirs(IMG_DIR, exist_ok=True)

# Colors by namespace
namespace_colors = {
    "tundra-ns": "red",
    "jool-app-ns": "green",
    "tayga-ns": "blue",
}

# Only 30s data
TIME_LABEL = "30s"
ip_types = ["IPv4", "IPv6"]

# Data: (ip_type, TIME_LABEL) -> dict(label -> (seqs, rtts, namespace))
by_case = defaultdict(dict)

# Regex to parse ping lines
RE_SEQ = re.compile(r"icmp[_-]seq=(\d+)", re.IGNORECASE)
RE_TIME = re.compile(r"time[=<]?([\d.]+)\s*ms", re.IGNORECASE)

# Optional hard overrides for IP labels (filename token -> pretty label)
IP_LABEL_OVERRIDES = {
    "fd00_64_64_5f00_20d2__400": "fd00:64:64:5f00:20d2::400",
    "2a05_d014_144f_5f00_20d2__400": "2a05:d014:144f:5f00:20d2::400",
}


def normalize_ip_type(raw):
    s = (raw or "").strip().lower()
    if s in ("ipv4", "v4", "4"):
        return "IPv4"
    if s in ("ipv6", "v6", "6"):
        return "IPv6"
    return None


def reconstruct_ipv6_from_filename(ip_token_joined):
    # Your encoding: ':' -> '' and '::' -> ''
    s = ip_token_joined.replace("", "::")
    s = s.replace("", ":")
    return s


FILES = [
    f for f in os.listdir(FOLDER)
    if f.endswith(".txt") and f.endswith(f"_{TIME_LABEL}.txt")
]

for fname in FILES:
    path = os.path.join(FOLDER, fname)
    stem = os.path.splitext(fname)[0]
    parts = stem.split("_")

    # Expect: namespace + ip_tokens... + ipvx + 30s
    if len(parts) < 4:
        print(f"Skipping {fname}: not enough parts")
        continue

    namespace = parts[0]
    ipvx_token = parts[-2]
    time_label = parts[-1]

    if time_label != TIME_LABEL:
        continue

    ip_type = normalize_ip_type(ipvx_token)
    if not ip_type:
        print(f"Skipping {fname}: cannot determine IP type from '{ipvx_token}'")
        continue

    ip_tokens = parts[1:-2]
    raw_ip_token_joined = "_".join(ip_tokens)

    if ip_type == "IPv4":
        ip_label = raw_ip_token_joined  # e.g., 192.0.0.171
    else:
        # Apply override first, then fallback to reconstruction
        ip_label = IP_LABEL_OVERRIDES.get(
            raw_ip_token_joined,
            reconstruct_ipv6_from_filename(raw_ip_token_joined),
        )

    seqs, rtts = [], []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "icmp" not in line.lower():
                    continue
                m_seq = RE_SEQ.search(line)
                m_time = RE_TIME.search(line)
                if m_seq and m_time:
                    try:
                        seq = int(m_seq.group(1))
                        rtt_ms = float(m_time.group(1))
                        seqs.append(seq)
                        rtts.append(rtt_ms)
                    except ValueError:
                        pass
    except Exception as e:
        print(f"Failed to read {path}: {e}")
        continue

    if not seqs:
        print(f"No RTT datapoints in {fname}, skipping.")
        continue

    # Sort by sequence
    seqs, rtts = zip(*sorted(zip(seqs, rtts), key=lambda x: x[0]))

    label = f"{namespace} ({ip_label})"
    key = (ip_type, TIME_LABEL)
    by_case[key][label] = (list(seqs), list(rtts), namespace)


def annotate_extrema(ax, xs, ys, color):
    if not xs:
        return

    yarr = np.asarray(ys)
    i_min = int(np.argmin(yarr))
    i_max = int(np.argmax(yarr))

    ax.annotate(
        ANNOTATION_FMT.format(ys[i_max]),
        (xs[i_max], ys[i_max]),
        textcoords="offset points",
        xytext=MAX_LABEL_OFFSET,
        ha="center",
        fontsize=ANNOTATION_FONTSIZE,
        color=color,
        alpha=0.95,
    )

    if i_min != i_max:
        ax.annotate(
            ANNOTATION_FMT.format(ys[i_min]),
            (xs[i_min], ys[i_min]),
            textcoords="offset points",
            xytext=MIN_LABEL_OFFSET,
            ha="center",
            fontsize=ANNOTATION_FONTSIZE,
            color=color,
            alpha=0.95,
        )


# Make two panels: IPv4 (30s) and IPv6 (30s)
for ylog in [False, True]:
    fig, axs = plt.subplots(1, 2, figsize=(14, 5))
    if not isinstance(axs, np.ndarray):
        axs = np.array([axs])

    for idx, ip_type in enumerate(ip_types):
        ax = axs[idx]
        key = (ip_type, TIME_LABEL)
        this_case = by_case.get(key, {})

        if not this_case:
            ax.set_title(f"No data: {ip_type}, {TIME_LABEL}")
            ax.set_xlabel("ICMP sequence (≈ seconds)")
            ax.set_ylabel("RTT [ms]")
            ax.grid(True, alpha=0.3)
            if ylog:
                ax.set_yscale("log")
            ax.margins(x=X_MARGIN, y=Y_MARGIN)
            ax.set_xlim(left=0)
            if not ylog:
                ax.set_ylim(bottom=0)
            ax.autoscale_view()
            continue

        for label, (xs, ys, ns) in this_case.items():
            color = namespace_colors.get(ns, None)

            if ylog:
                points = [
                    (x, y) for x, y in zip(xs, ys)
                    if y > 0 and not np.isnan(y)
                ]
            else:
                points = [
                    (x, y) for x, y in zip(xs, ys)
                    if not np.isnan(y)
                ]

            if not points:
                continue

            xs2, ys2 = zip(*points)

            ax.plot(xs2, ys2, color=color, alpha=0.3, linewidth=1, zorder=1)
            ax.scatter(
                xs2, ys2, label=label, color=color,
                s=12, alpha=0.85, zorder=2
            )
            annotate_extrema(ax, list(xs2), list(ys2), color)

        ax.set_title(f"RTT: {ip_type}, {TIME_LABEL}")
        ax.set_xlabel("ICMP sequence (≈ seconds)")
        ax.set_ylabel("RTT [ms]")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9)

        if ylog:
            ax.set_yscale("log")
        ax.margins(x=X_MARGIN, y=Y_MARGIN)
        ax.set_xlim(left=0)
        if not ylog:
            ax.set_ylim(bottom=0)
        ax.autoscale_view()

    fig.suptitle(
        f"{SCENARIO_NAME} - ICMP RTT ({CLOCKTIME_LABEL}) - "
        f"{TIME_LABEL} (Y {'log' if ylog else 'linear'})",
        fontsize=16,
    )

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    yname = "log" if ylog else "linear"
    out_path = os.path.join(
        IMG_DIR,
        f"{SCENARIO_NAME}_ping_rtt_{CLOCKTIME_LABEL}_{TIME_LABEL}_{yname}.png"
    )
    plt.savefig(out_path, dpi=200)
    print(f"RTT plot saved to {out_path}")
    plt.close(fig)

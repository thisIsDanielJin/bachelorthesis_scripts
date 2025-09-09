import os
import re
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
from matplotlib.ticker import FuncFormatter
from matplotlib.lines import Line2D


# ================== CONFIG ==================
FOLDER = "RawMessungen/PingDoubleMachineRTT"  # folder containing *.txt ping outputs
IMG_DIR = "img"
CLOCKTIME_LABEL = "Ping"
SCENARIO_NAME = "Double"  # e.g., "AWS", "SingleLocal", "DoubleLocal"

# Annotation settings
ANNOTATION_FMT = "{:.3f} ms"  # label format for RTT values
MAX_LABEL_OFFSET = (0, 6)     # pixel offset for the max point label (above)
MIN_LABEL_OFFSET = (0, -10)   # pixel offset for the min point label (below)
ANNOTATION_FONTSIZE = 7

# Margins (relative fraction of data range)
X_MARGIN = 0.02  # ~2% extra space on the right (left stays pinned at 0)
Y_MARGIN = 0.10  # ~10% extra space on top

os.makedirs(IMG_DIR, exist_ok=True)

# Colors by namespace - strong colors for IPv4
namespace_colors_ipv4 = {
    "tundra-ns": "red",
    "jool-app-ns": "green",
    "tayga-ns": "blue",
}

# Distinct colors for IPv6 baseline
namespace_colors_ipv6 = {
    "tundra-ns": "orange",
    "jool-app-ns": "purple",
    "tayga-ns": "cyan",  # Won't be used since we skip it
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


# Display name mapping for namespaces
NAMESPACE_DISPLAY_NAME_IPV4 = {
    "jool-app-ns": "jool",
    "tayga-ns": "tayga",
    "tundra-ns": "tundra",
}

NAMESPACE_DISPLAY_NAME_IPV6 = {
    "tundra-ns": "1 Hop",
    "jool-app-ns": "2 Hops",
    # Removed "tayga-ns": "1 Hop" - redundant with tundra-ns
}

# Make single plot combining IPv4 and IPv6
for ylog in [False, True]:
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))

    plotted_any = False
    
    for ip_type in ip_types:
        key = (ip_type, TIME_LABEL)
        this_case = by_case.get(key, {})

        for label, (xs, ys, ns) in this_case.items():
            # Skip tayga-ns for IPv6 baseline since it's redundant with tundra-ns
            if ip_type == "IPv6" and ns == "tayga-ns":
                continue
                
            # Use appropriate color palette and marker based on IP type
            if ip_type == "IPv4":
                color = namespace_colors_ipv4.get(ns, None)
                marker_style = "o"
                display_name = NAMESPACE_DISPLAY_NAME_IPV4.get(ns, ns)
            else:
                color = namespace_colors_ipv6.get(ns, None)
                marker_style = "x"
                display_name = NAMESPACE_DISPLAY_NAME_IPV6.get(ns, ns)

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

            ax.plot(xs2, ys2, color=color, alpha=0.45, linewidth=1, zorder=1)
            ax.scatter(
                xs2, ys2, label=display_name, color=color,
                s=12, alpha=0.85, zorder=2, marker=marker_style
            )
            annotate_extrema(ax, list(xs2), list(ys2), color)
            plotted_any = True

    if plotted_any:
        ax.set_xlabel("ICMP sequence (≈ seconds)")
        ax.set_ylabel("RTT [ms]")
        ax.grid(True, alpha=0.3)
        
        # Main legend for the data
        legend1 = ax.legend(fontsize=9, loc='lower right')
        
        # Add shape legend for marker types
        shape_legend_elements = [
            Line2D([0], [0], marker='x', color='black', linestyle='None', 
                   markersize=8, label='IPv6 Baseline'),
            Line2D([0], [0], marker='o', color='black', linestyle='None', 
                   markersize=6, label='IPv4 Translation')
        ]
        legend2 = ax.legend(handles=shape_legend_elements, fontsize=9, 
                          loc='lower left', title='Marker Types')
        
        # Add the first legend back
        ax.add_artist(legend1)

        if ylog:
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:.0f}"))

        ax.margins(x=X_MARGIN, y=Y_MARGIN)
        ax.set_xlim(left=0)
        if not ylog:
            ax.set_ylim(bottom=0)
        ax.autoscale_view()
    else:
        ax.set_title(f"No data available for {TIME_LABEL}")
        ax.set_xlabel("ICMP sequence (≈ seconds)")
        ax.set_ylabel("RTT [ms]")
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    yname = "log" if ylog else "linear"
    out_path = os.path.join(
        IMG_DIR,
        f"{SCENARIO_NAME}_ping_rtt_{CLOCKTIME_LABEL}_{TIME_LABEL}_{yname}.svg"
    )
    plt.savefig(out_path, format='svg')
    print(f"RTT plot saved to {out_path}")
    plt.close(fig)

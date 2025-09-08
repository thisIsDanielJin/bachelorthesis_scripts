import os
import json
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np

# ================== CONFIG ==================
FOLDER = "RawMessungen/LocalSingle_tsc_clocktime"
IMG_DIR = "img"
CLOCKTIME_LABEL = "tsc"
SCENARIO_NAME = "Single Local" 

# Annotation settings
ANNOTATION_FMT = "{:.2f}"  # throughput label format in Gbit/s
MAX_LABEL_OFFSET = (0, 6)  # pixel offset for the max point label (above)
MIN_LABEL_OFFSET = (0, -10)  # pixel offset for the min point label (below)
ANNOTATION_FONTSIZE = 7

# Margins (relative fraction of data range)
X_MARGIN = 0.02  # ~2% extra space on the right (left stays pinned at 0)
Y_MARGIN = 0.10  # ~10% extra space on top

os.makedirs(IMG_DIR, exist_ok=True)

FILES = [f for f in os.listdir(FOLDER) if f.endswith(".json")]
by_scenario = defaultdict(dict)

namespace_colors = {
    "tundra-ns": "red",
    "jool-app-ns": "green",
    "tayga-ns": "blue",
}

NAMESPACE_DISPLAY_NAME = {
    "tundra-ns": "tundra",
    "jool-app-ns": "jool",
    "tayga-ns": "tayga",
}

# Display name mapping for plot titles
IP_DISPLAY_NAME = {
    "IPv4": "IPv4 Translation",
    "IPv6": "IPv6 Baseline",
}

# Load data
for jsonfile in FILES:
    filename = os.path.join(FOLDER, jsonfile)
    try:
        namepart = os.path.splitext(jsonfile)[0]
        parts = namepart.split("_")
        namespace = parts[0]
        time_label = parts[-1]
        ip_type = "IPv4" if "." in parts[1] else "IPv6"
    except Exception as e:
        print(f"Filename {jsonfile} could not be parsed: {e}, skipping.")
        continue

    try:
        with open(filename, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to load {filename}: {e}")
        continue

    times, throughput = [], []
    for interval in data.get("intervals", []):
        t = interval["sum"].get("start", float("nan"))
        times.append(t)
        throughput.append(interval["sum"].get("bits_per_second", 0) / 1e9)

    key = (ip_type, time_label)
    by_scenario[key][namespace] = (times, throughput)

ip_types = ["IPv4", "IPv6"]
time_labels = ["30s", "2min"]


# --- Helper for annotations ---
def annotate_extrema(ax, xs, ys, color):
    if not xs:
        return
    ys_arr = np.asarray(ys)
    i_min = int(np.argmin(ys_arr))
    i_max = int(np.argmax(ys_arr))

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


# --- Compute shared y-limits per time_label across both IP types ---
def compute_shared_ylim_per_time_label(by_scenario, ip_types, time_labels, ylog, y_margin):
    limits = {}
    for tl in time_labels:
        vals = []
        for ip in ip_types:
            case = by_scenario.get((ip, tl), {})
            for _, (_, ths) in case.items():
                if ylog:
                    vals.extend([th for th in ths if th is not None and not np.isnan(th) and th > 0])
                else:
                    vals.extend([th for th in ths if th is not None and not np.isnan(th)])
        if not vals:
            continue

        vmax = float(np.max(vals)) if vals else None
        if vmax is None or not np.isfinite(vmax):
            continue

        if ylog:
            pos_vals = [v for v in vals if v > 0]
            if not pos_vals:
                continue
            vmin = float(np.min(pos_vals))
            # Expand range a bit using multiplicative padding for log
            ymin = vmin / (1.0 + y_margin)
            ymax = vmax * (1.0 + y_margin)
            # Ensure strictly positive lower bound
            if ymin <= 0:
                ymin = vmin / 1.1
                if ymin <= 0:
                    ymin = max(vmin, 1e-6)
        else:
            ymin = 0.0
            ymax = vmax * (1.0 + y_margin)
            if not np.isfinite(ymax) or ymax <= 0:
                ymin, ymax = 0.0, 1.0

        limits[tl] = (ymin, ymax)
    return limits


# === Throughput plots (linear and log) ===
for ylog in [False, True]:
    # Pre-compute shared y-limits per time_label across IPv4 and IPv6 for this y-scale
    shared_ylim = compute_shared_ylim_per_time_label(by_scenario, ip_types, time_labels, ylog, Y_MARGIN)

    fig_thr, axs_thr = plt.subplots(2, 2, figsize=(14, 10))
    axs_thr = axs_thr.flatten()

    for i, ip_type in enumerate(ip_types):
        for j, time_label in enumerate(time_labels):
            idx = i * 2 + j
            ax = axs_thr[idx]
            key = (ip_type, time_label)
            this_case = by_scenario.get(key, {})
            display_ip = IP_DISPLAY_NAME.get(ip_type, ip_type)

            if not this_case:
                ax.set_title(f"No data: {display_ip}, {time_label}")
                ax.set_xlabel("Time [s]")
                ax.set_ylabel("Throughput [Gbit/s]")
                ax.grid(True, alpha=0.3)
                if ylog:
                    ax.set_yscale("log")
                ax.margins(x=X_MARGIN, y=Y_MARGIN)
                ax.set_xlim(left=0)
                # Apply shared y-limits if available; otherwise a sensible default
                if time_label in shared_ylim:
                    ax.set_ylim(*shared_ylim[time_label])
                else:
                    if ylog:
                        ax.set_ylim(1e-3, 1.0)
                    else:
                        ax.set_ylim(bottom=0)
                continue

            if ip_type == "IPv6":
                legend_map = {
                    "tundra-ns": "1 Hop",
                    "tayga-ns": "1 Hop",
                    "jool-app-ns": "2 Hops",
                }
            else:
                legend_map = NAMESPACE_DISPLAY_NAME

            for ns, (times, throughputs) in this_case.items():
                color = namespace_colors.get(ns, None)

                if ylog:
                    zipped = [
                        (t, th)
                        for t, th in zip(times, throughputs)
                        if th > 0 and not np.isnan(th) and not np.isnan(t)
                    ]
                else:
                    zipped = [
                        (t, th)
                        for t, th in zip(times, throughputs)
                        if not np.isnan(th) and not np.isnan(t)
                    ]
                if not zipped:
                    continue

                times2, throughputs2 = zip(*zipped)

                # Connect points with a low-opacity line
                ax.plot(
                    times2, throughputs2,
                    color=color, alpha=0.3, linewidth=1, zorder=1
                )

                # Scatter points
                marker_style = "o" if ip_type == "IPv4" else "x"
                ax.scatter(
                    times2, throughputs2,
                    label=legend_map.get(ns, ns),
                    color=color, s=20, alpha=0.85, zorder=2,
                    marker=marker_style
                )


                annotate_extrema(ax, list(times2), list(throughputs2), color)

            ax.set_title(f"{display_ip}, {time_label}")
            ax.set_xlabel("Time [s]")
            ax.set_ylabel("Throughput [Gbit/s]")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=9)

            if ylog:
                ax.set_yscale("log")
            ax.margins(x=X_MARGIN, y=Y_MARGIN)
            ax.set_xlim(left=0)

            # Apply shared y-limits across IPv4/IPv6 for this time_label
            if time_label in shared_ylim:
                ax.set_ylim(*shared_ylim[time_label])
            else:
                # Fallback if no data for both IP types for this time_label
                if not ylog:
                    ax.set_ylim(bottom=0)

    # Global title with SCENARIO_NAME
    yscale_name = "Log" if ylog else "Linear"
    fig_thr.suptitle(
        f"Environment: {SCENARIO_NAME}\n"
        f"TCP Throughput Over Time\n"
        f"Clocksource: {CLOCKTIME_LABEL}, Scale: {yscale_name}",
        fontsize=16,
    )

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    yscale_name_file = yscale_name.lower()
    throughput_plot_path = os.path.join(
        IMG_DIR,
        f"{SCENARIO_NAME}_tcp_sameScale_{CLOCKTIME_LABEL}_{yscale_name_file}.png"
    )
    plt.savefig(throughput_plot_path, dpi=200)
    print(f"Throughput plot saved to {throughput_plot_path}")
    plt.close(fig_thr)

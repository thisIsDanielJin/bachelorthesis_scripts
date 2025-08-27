import os
import json
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np

# ================== CONFIG ==================
FOLDER = "RawMessungen/AWS_hpet_clocktime"
IMG_DIR = "img"
CLOCKTIME_LABEL = "hpet"
SCENARIO_NAME = "AWS"  # <-- change to "AWS" or "SingleLocal" or "DoubleLocal"

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


# === Throughput plots (linear and log) ===
for ylog in [False, True]:
    fig_thr, axs_thr = plt.subplots(2, 2, figsize=(14, 10))
    axs_thr = axs_thr.flatten()

    for i, ip_type in enumerate(ip_types):
        for j, time_label in enumerate(time_labels):
            idx = i * 2 + j
            ax = axs_thr[idx]
            key = (ip_type, time_label)
            this_case = by_scenario.get(key, {})

            if not this_case:
                ax.set_title(f"No data: {ip_type}, {time_label}")
                ax.set_xlabel("Time [s]")
                ax.set_ylabel("Throughput [Gbit/s]")
                ax.grid(True, alpha=0.3)
                if ylog:
                    ax.set_yscale("log")
                ax.margins(x=X_MARGIN, y=Y_MARGIN)
                ax.set_xlim(left=0)
                if not ylog:
                    ax.set_ylim(bottom=0)
                ax.autoscale_view()
                continue

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
                ax.scatter(
                    times2, throughputs2,
                    label=ns, color=color, s=12, alpha=0.85, zorder=2
                )

                annotate_extrema(ax, list(times2), list(throughputs2), color)

            ax.set_title(f"Throughput: {ip_type}, {time_label}")
            ax.set_xlabel("Time [s]")
            ax.set_ylabel("Throughput [Gbit/s]")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=9)

            if ylog:
                ax.set_yscale("log")
            ax.margins(x=X_MARGIN, y=Y_MARGIN)
            ax.set_xlim(left=0)
            if not ylog:
                ax.set_ylim(bottom=0)
            ax.autoscale_view()

    # Global title with SCENARIO_NAME
    fig_thr.suptitle(
        f"{SCENARIO_NAME} - TCP Throughput Over Time ({CLOCKTIME_LABEL}) "
        f"(Y {'log' if ylog else 'linear'})",
        fontsize=16,
    )

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    yscale_name = "log" if ylog else "linear"
    throughput_plot_path = os.path.join(
        IMG_DIR,
        f"{SCENARIO_NAME}_tcp_throughput_over_time_{CLOCKTIME_LABEL}_{yscale_name}.png"
    )
    plt.savefig(throughput_plot_path, dpi=200)
    print(f"Throughput plot saved to {throughput_plot_path}")
    plt.close(fig_thr)

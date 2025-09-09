import os
import json
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
from matplotlib.lines import Line2D

# ================== CONFIG ==================
FOLDER = "RawMessungen/LocalSingle_tsc_clocktime"
IMG_DIR = "img"
CLOCKTIME_LABEL = "tsc"
SCENARIO_NAME = "Single"

# Annotation settings
ANNOTATION_FMT = "{:.2f}"  # throughput label format in Gbit/s
MAX_LABEL_OFFSET = (0, 6)  # pixel offset for the max point label (above)
MIN_LABEL_OFFSET = (0, -10)  # pixel offset for the min point label (below)
ANNOTATION_FONTSIZE = 7

# Legend positioning settings
LEGEND_POSITIONS = {
    "30s": {
        "main": "center right",
        "marker": "center left"
    },
    "2min": {
        "main": "center right",
        "marker": "center left"
    }
}

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

# ================== LOAD DATA ==================
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


# ================== HELPERS ==================
def annotate_extrema(ax, xs, ys, color):
    """Annotate min and max throughput points."""
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


def compute_shared_ylim_per_time_label(by_scenario, ip_types, time_labels, ylog, y_margin):
    """Compute shared y-axis limits across IPv4 and IPv6 for consistency."""
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
            ymin = vmin / (1.0 + y_margin)
            ymax = vmax * (1.0 + y_margin)
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


# ================== PLOTS ==================
for ylog in [False, True]:
    # Pre-compute shared y-limits
    shared_ylim = compute_shared_ylim_per_time_label(by_scenario, ip_types, time_labels, ylog, Y_MARGIN)

    ncols = max(1, len(time_labels))
    nrows = 1
    fig_width = 7 * ncols
    fig_height = 5
    fig_thr, axs_thr = plt.subplots(nrows, ncols, figsize=(fig_width, fig_height))
    if ncols == 1:
        axs_thr = [axs_thr]
    else:
        axs_thr = axs_thr.flatten()

    for j, time_label in enumerate(time_labels):
        ax = axs_thr[j]
        plotted_any = False

        # Plot both IP types on the same axis for this time interval
        for ip_type in ip_types:
            this_case = by_scenario.get((ip_type, time_label), {})

            # Legend labels
            if ip_type == "IPv6":
                legend_map = {
                    "tundra-ns": "1 Hop",
                    "jool-app-ns": "2 Hops",
                    # Removed "tayga-ns": "1 Hop" - we don't need this redundant blue baseline
                }
                marker_style = "x"
            else:
                legend_map = {
                    "tundra-ns": "tundra",
                    "jool-app-ns": "jool",
                    "tayga-ns": "tayga",
                }
                marker_style = "o"

            for ns, (times, throughputs) in this_case.items():
                # Skip tayga-ns for IPv6 baseline since it's redundant with tundra-ns
                if ip_type == "IPv6" and ns == "tayga-ns":
                    continue
                    
                color = namespace_colors.get(ns, None)
                
                # Make IPv6 baseline colors more distinct and noticeable
                if ip_type == "IPv6":
                    if color == "red":
                        color = "orange"
                    elif color == "green":
                        color = "purple"
                    elif color == "blue":
                        color = "cyan"

                if ylog:
                    zipped = [
                        (t, th)
                        for t, th in zip(times, throughputs)
                        if th is not None and t is not None and not np.isnan(th) and not np.isnan(t) and th > 0
                    ]
                else:
                    zipped = [
                        (t, th)
                        for t, th in zip(times, throughputs)
                        if th is not None and t is not None and not np.isnan(th) and not np.isnan(t)
                    ]
                if not zipped:
                    continue

                times2, throughputs2 = zip(*zipped)

                # Connect points
                ax.plot(
                    times2, throughputs2,
                    color=color, alpha=0.3, linewidth=1, zorder=1
                )

                # Scatter points
                scatter_alpha = 0.85  # Same alpha for both baseline and transition
                ax.scatter(
                    times2, throughputs2,
                    label=legend_map.get(ns, f"{ns} ({ip_type})"),
                    color=color, s=8, alpha=scatter_alpha, zorder=2,
                    marker=marker_style
                )

                annotate_extrema(ax, list(times2), list(throughputs2), color)
                plotted_any = True

        # Titles and axes
        ax.set_title(f"{time_label}")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Throughput [Gbit/s]")
        ax.grid(True, alpha=0.3)
        if ylog:
            ax.set_yscale("log")
        ax.margins(x=X_MARGIN, y=Y_MARGIN)
        ax.set_xlim(left=0)

        # Apply shared y-limits
        if time_label in shared_ylim:
            ax.set_ylim(*shared_ylim[time_label])
        else:
            if not ylog:
                ax.set_ylim(bottom=0)

        if plotted_any:
            # Get legend positions for this time interval
            legend_pos = LEGEND_POSITIONS.get(time_label, {"main": "center right", "marker": "center left"})
            
            # Main legend for the data
            legend1 = ax.legend(fontsize=9, loc=legend_pos["main"])
            
            # Add shape legend
            shape_legend_elements = [
                Line2D([0], [0], marker='x', color='black', linestyle='None', 
                       markersize=8, label='IPv6 Baseline'),
                Line2D([0], [0], marker='o', color='black', linestyle='None', 
                       markersize=6, label='IPv4 Transition')
            ]
            legend2 = ax.legend(handles=shape_legend_elements, fontsize=9, 
                              loc=legend_pos["marker"], title='Marker Types')
            
            # Add the first legend back
            ax.add_artist(legend1)

        else:
            ax.text(0.5, 0.5, f"No data for {time_label}", ha="center", va="center", transform=ax.transAxes)

    # Global title
    yscale_name = "Log" if ylog else "Linear"
    

    plt.tight_layout(rect=[0, 0, 1, 0.88])
    yscale_name_file = yscale_name.lower()
    throughput_plot_path = os.path.join(
        IMG_DIR,
        f"{SCENARIO_NAME}_tcp_sameScale_{CLOCKTIME_LABEL}_{yscale_name_file}.svg"
    )
    plt.savefig(throughput_plot_path, format='svg')
    print(f"Throughput plot saved to {throughput_plot_path}")
    plt.close(fig_thr)

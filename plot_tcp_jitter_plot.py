import os
import json
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
from matplotlib.lines import Line2D

# ================== CONFIG ==================
FOLDER = "RawMessungen/LocalDouble_hpet_clocktime"
IMG_DIR = "img"
CLOCKTIME_LABEL = "hpet"
SCENARIO_NAME = "LocalDouble"

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


def compute_ylim_per_ip_type(by_scenario, ip_types, time_labels, ylog, y_margin):
    """Compute y-axis limits separately for IPv4 and IPv6."""
    limits = {}
    for tl in time_labels:
        limits[tl] = {}
        for ip in ip_types:
            case = by_scenario.get((ip, tl), {})
            vals = []
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

            limits[tl][ip] = (ymin, ymax)
    return limits


# ================== PLOTS ==================
for ylog in [False, True]:
    # Pre-compute y-limits for each IP type separately
    ip_ylim = compute_ylim_per_ip_type(by_scenario, ip_types, time_labels, ylog, Y_MARGIN)

    # Create separate plots for each time label
    for time_label in time_labels:
        fig_width = 10
        fig_height = 5
        fig_thr, ax_left = plt.subplots(1, 1, figsize=(fig_width, fig_height))
        ax_right = ax_left.twinx()  # Create right y-axis
        
        plotted_any = False

        # Plot IPv6 (baseline) on left axis
        ipv6_case = by_scenario.get(("IPv6", time_label), {})
        legend_map_ipv6 = {
            "tundra-ns": "1 Hop",
            "jool-app-ns": "2 Hops",
        }
        
        for ns, (times, throughputs) in ipv6_case.items():
            # Skip tayga-ns for IPv6 baseline since it's redundant with tundra-ns
            if ns == "tayga-ns":
                continue
                
            color = namespace_colors.get(ns, None)
            # Make IPv6 baseline colors more distinct
            if color == "red":
                color = "orange"
            elif color == "green":
                color = "purple"

            if ylog:
                zipped = [
                    (t, th) for t, th in zip(times, throughputs)
                    if th is not None and t is not None and not np.isnan(th) and not np.isnan(t) and th > 0
                ]
            else:
                zipped = [
                    (t, th) for t, th in zip(times, throughputs)
                    if th is not None and t is not None and not np.isnan(th) and not np.isnan(t)
                ]
            if not zipped:
                continue

            times2, throughputs2 = zip(*zipped)

            # Plot on left axis
            ax_left.plot(times2, throughputs2, color=color, alpha=0.3, linewidth=1, zorder=1)
            ax_left.scatter(
                times2, throughputs2,
                label=legend_map_ipv6.get(ns, f"{ns} (IPv6)"),
                color=color, s=8, alpha=0.85, zorder=2, marker='x'
            )
            annotate_extrema(ax_left, list(times2), list(throughputs2), color)
            plotted_any = True

        # Plot IPv4 (transition) on right axis
        ipv4_case = by_scenario.get(("IPv4", time_label), {})
        legend_map_ipv4 = {
            "tundra-ns": "tundra",
            "jool-app-ns": "jool",
            "tayga-ns": "tayga",
        }
        
        for ns, (times, throughputs) in ipv4_case.items():
            color = namespace_colors.get(ns, None)

            if ylog:
                zipped = [
                    (t, th) for t, th in zip(times, throughputs)
                    if th is not None and t is not None and not np.isnan(th) and not np.isnan(t) and th > 0
                ]
            else:
                zipped = [
                    (t, th) for t, th in zip(times, throughputs)
                    if th is not None and t is not None and not np.isnan(th) and not np.isnan(t)
                ]
            if not zipped:
                continue

            times2, throughputs2 = zip(*zipped)

            # Plot on right axis
            ax_right.plot(times2, throughputs2, color=color, alpha=0.3, linewidth=1, zorder=1)
            ax_right.scatter(
                times2, throughputs2,
                label=legend_map_ipv4.get(ns, f"{ns} (IPv4)"),
                color=color, s=8, alpha=0.85, zorder=2, marker='o'
            )
            annotate_extrema(ax_right, list(times2), list(throughputs2), color)
            plotted_any = True

        # Configure axes
        ax_left.set_title(f"{time_label}")
        ax_left.set_xlabel("Time [s]")
        ax_left.set_ylabel("IPv6 Baseline", color='purple')
        ax_right.set_ylabel("IPv4 Transition", color='blue')
        
        ax_left.grid(True, alpha=0.3)
        
        if ylog:
            ax_left.set_yscale("log")
            ax_right.set_yscale("log")
        
        ax_left.margins(x=X_MARGIN)
        ax_right.margins(x=X_MARGIN)
        ax_left.set_xlim(left=0)

        # Apply separate y-limits
        if time_label in ip_ylim:
            if "IPv6" in ip_ylim[time_label]:
                ax_left.set_ylim(*ip_ylim[time_label]["IPv6"])
            elif not ylog:
                ax_left.set_ylim(bottom=0)
                
            if "IPv4" in ip_ylim[time_label]:
                ax_right.set_ylim(*ip_ylim[time_label]["IPv4"])
            elif not ylog:
                ax_right.set_ylim(bottom=0)

        # Color the y-axis labels to match the data
        ax_left.tick_params(axis='y', labelcolor='purple')
        ax_right.tick_params(axis='y', labelcolor='blue')

        if plotted_any:
            # Create combined legend
            lines_left, labels_left = ax_left.get_legend_handles_labels()
            lines_right, labels_right = ax_right.get_legend_handles_labels()
            
            # Main legend for the data - positioned outside the plot area
            legend1 = ax_left.legend(lines_left + lines_right, labels_left + labels_right, 
                                   fontsize=9, bbox_to_anchor=(1.15, 1), loc='upper left')
            
            # Add shape legend - positioned outside the plot area below the main legend
            shape_legend_elements = [
                Line2D([0], [0], marker='x', color='black', linestyle='None', 
                       markersize=8, label='IPv6 Baseline'),
                Line2D([0], [0], marker='o', color='black', linestyle='None', 
                       markersize=6, label='IPv4 Transition')
            ]
            legend2 = ax_left.legend(handles=shape_legend_elements, fontsize=9, 
                                   bbox_to_anchor=(1.15, 0.7), loc='upper left', title='Marker Types')

            # Add the first legend back
            ax_left.add_artist(legend1)

        else:
            ax_left.text(0.5, 0.5, f"No data for {time_label}", ha="center", va="center", transform=ax_left.transAxes)

        # Save individual plot
        yscale_name = "Log" if ylog else "Linear"
        yscale_name_file = yscale_name.lower()
        throughput_plot_path = os.path.join(
            IMG_DIR,
            f"{SCENARIO_NAME}_tcp_dualAxis_{CLOCKTIME_LABEL}_{time_label}_{yscale_name_file}.png"
        )
        
        plt.tight_layout()
        plt.savefig(throughput_plot_path, format='png', bbox_inches='tight')
        print(f"Throughput plot saved to {throughput_plot_path}")
        plt.close(fig_thr)

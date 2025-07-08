import os
import json
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np

FOLDER = "TCP_1/Messungen"
IMG_DIR = "img"  # Directory to save plot images
os.makedirs(IMG_DIR, exist_ok=True)  # Create if not exist

FILES = [f for f in os.listdir(FOLDER) if f.endswith(".json")]

by_scenario = defaultdict(dict)  # (ip_type, time_label) -> {ns: (times, throughput, rtt)}

namespace_colors = {
    "tundra-ns": "red",
    "jool-app-ns": "green",
    "tayga-ns": "blue"
}

for jsonfile in FILES:
    filename = os.path.join(FOLDER, jsonfile)
    try:
        namepart = os.path.splitext(jsonfile)[0]
        parts = namepart.split("_")
        namespace = parts[0]
        time_label = parts[-1]
        ip = "_".join(parts[1:-1])
    except Exception as e:
        print(f"Filename {jsonfile} could not be parsed: {e}, skipping.")
        continue

    ip_type = "IPv6" if ":" in ip.replace("_", ":") or "__" in ip else "IPv4"

    try:
        with open(filename, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to load {filename}: {e}")
        continue

    times, throughput, rtt = [], [], []
    for interval in data.get("intervals", []):
        t = interval["sum"].get("start", float('nan'))
        times.append(t)
        throughput.append(interval["sum"].get("bits_per_second", 0) / 1e9)
        streams = interval.get("streams", [])
        if streams:
            rtt.append(streams[0].get("rtt", float('nan')))
        else:
            rtt.append(float('nan'))

    key = (ip_type, time_label)
    by_scenario[key][namespace] = (times, throughput, rtt)

ip_types = ["IPv4", "IPv6"]
time_labels = ["30s", "2min"]

# ---- Throughput Plot ----
def moving_average(x, w=5):
    """Compute moving average using window w."""
    return np.convolve(x, np.ones(w)/w, mode='valid')

fig_thr, axs_thr = plt.subplots(2, 2, figsize=(14, 10))
axs_thr = axs_thr.flatten()

for i, ip_type in enumerate(ip_types):
    for j, time_label in enumerate(time_labels):
        idx = i*2 + j
        ax = axs_thr[idx]
        key = (ip_type, time_label)
        this_case = by_scenario.get(key, {})
        if not this_case:
            ax.set_title(f"No data: {ip_type}, {time_label}")
            continue
        for ns, (times, throughputs, _) in this_case.items():
            color = namespace_colors.get(ns, None)
            if not times or not throughputs:
                continue

            # Choose smoothing window for time label
            w = 10 if time_label == "2min" else 5
            w = min(w, len(throughputs))  # Ensure window isn't too big

            # ---- Plot smoothed line ----
            if len(throughputs) >= w and w > 1:
                sm_through = moving_average(throughputs, w)
                sm_times = moving_average(times, w)
                ax.plot(sm_times, sm_through, label=f"{ns} (smoothed)", color=color, linewidth=2)

                # Plot raw, but very faint and only as points (or line):
                ax.plot(times, throughputs, '.', alpha=0.15, color=color, markersize=1, zorder=1)
            else:
                # For very short series: plot only as-is
                ax.plot(times, throughputs, '-', marker='o', label=ns, color=color, markersize=3, linewidth=1)
            
            # Mean line across full data (for reference)
            if throughputs:
                mean_thr = sum(throughputs) / len(throughputs)
                ax.axhline(mean_thr, color=color, linestyle='--', alpha=0.5, linewidth=1)

        ax.set_title(f"Throughput: {ip_type}, {time_label}")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Throughput [Gbit/s]")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9)
        # Optionally: set lower y limit to zero for clarity
        ax.set_ylim(bottom=0)

fig_thr.suptitle("TCP Throughput Over Time for Each Scenario", fontsize=16)
plt.tight_layout(rect=[0, 0, 1, 0.96])

# ---- SAVE THROUGHOUT PLOT ----
throughput_plot_path = os.path.join(IMG_DIR, "tcp_throughput_over_time.png")
plt.savefig(throughput_plot_path, dpi=200)
print(f"Throughput plot saved to {throughput_plot_path}")
plt.show()


# ---- RTT Plot ----
fig_rtt, axs_rtt = plt.subplots(2, 2, figsize=(14, 10))
axs_rtt = axs_rtt.flatten()

for i, ip_type in enumerate(ip_types):
    for j, time_label in enumerate(time_labels):
        idx = i*2 + j
        ax = axs_rtt[idx]
        key = (ip_type, time_label)
        this_case = by_scenario.get(key, {})
        if not this_case:
            ax.set_title(f"No data: {ip_type}, {time_label}")
            continue
        for ns, (times, _, rtts) in this_case.items():
            color = namespace_colors.get(ns, None)
            ax.plot(times, rtts, marker='o', markersize=4, label=ns, color=color)
            if rtts:
                mean_rtt = sum(rtts) / len(rtts)
                ax.axhline(mean_rtt, color=color, linestyle='--', alpha=0.5)
        ax.set_title(f"RTT: {ip_type}, {time_label}")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("RTT [ms]")
        ax.grid(True)
        ax.legend()
fig_rtt.suptitle("TCP RTT Over Time for Each Scenario", fontsize=16)
plt.tight_layout(rect=[0, 0, 1, 0.96])

# ---- SAVE RTT PLOT ----
rtt_plot_path = os.path.join(IMG_DIR, "tcp_rtt_over_time.png")
#plt.savefig(rtt_plot_path, dpi=200)
print(f"RTT plot saved to {rtt_plot_path}")
plt.show()
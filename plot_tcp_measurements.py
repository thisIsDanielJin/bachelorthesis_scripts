import os
import json
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np

FOLDER = "RawMessungen/LocalSingle_tsc_clocktime"
IMG_DIR = "img"
CLOCKTIME_LABEL = "tsc"

os.makedirs(IMG_DIR, exist_ok=True)

FILES = [f for f in os.listdir(FOLDER) if f.endswith(".json")]

by_scenario = defaultdict(dict)

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
        ip_type = 'IPv4' if '.' in parts[1] else 'IPv6'

    except Exception as e:
        print(f"Filename {jsonfile} could not be parsed: {e}, skipping.")
        continue

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

def moving_average(x, w=5):
    return np.convolve(x, np.ones(w)/w, mode='valid')

# === Throughput plots ===
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
                continue
            for ns, (times, throughputs, _) in this_case.items():
                color = namespace_colors.get(ns, None)

                if ylog:
                    # Remove 0/nan/negative for log
                    zipped = [(t, th) for t, th in zip(times, throughputs) if th > 0 and not np.isnan(th) and not np.isnan(t)]
                else:
                    zipped = [(t, th) for t, th in zip(times, throughputs) if not np.isnan(th) and not np.isnan(t)]
                if not zipped:
                    continue
                times2, throughputs2 = zip(*zipped)

                w = 10 if time_label == "2min" else 5
                w = min(w, len(throughputs2))
                if len(throughputs2) >= w and w > 1:
                    sm_through = moving_average(throughputs2, w)
                    sm_times = moving_average(times2, w)
                    ax.plot(sm_times, sm_through, label=f"{ns} (smoothed)", color=color, linewidth=2)
                    ax.plot(times2, throughputs2, '.', alpha=0.15, color=color, markersize=1, zorder=1)
                else:
                    ax.plot(times2, throughputs2, '-', marker='o', label=ns, color=color, markersize=3, linewidth=1)
                if throughputs2:
                    mean_thr = sum(throughputs2) / len(throughputs2)
                    ax.axhline(mean_thr, color=color, linestyle='--', alpha=0.5, linewidth=1)

            ax.set_title(f"Throughput: {ip_type}, {time_label}")
            ax.set_xlabel("Time [s]")
            ax.set_ylabel("Throughput [Gbit/s]")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=9)
            if ylog:
                ax.set_yscale("log")

    fig_thr.suptitle(
    f"TCP Throughput Over Time for Each Scenario ({CLOCKTIME_LABEL}) (Y {'log' if ylog else 'linear'})",
    fontsize=16
)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    yscale_name = "log" if ylog else "linear"
    throughput_plot_path = os.path.join(IMG_DIR, f"tcp_throughput_over_time_{CLOCKTIME_LABEL}_{yscale_name}.png")
    plt.savefig(throughput_plot_path, dpi=200)
    print(f"Throughput plot saved to {throughput_plot_path}")
    plt.close(fig_thr)

# === RTT plots ===
for ylog in [False, True]:
    fig_rtt, axs_rtt = plt.subplots(2, 2, figsize=(14, 10))
    axs_rtt = axs_rtt.flatten()

    for i, ip_type in enumerate(ip_types):
        for j, time_label in enumerate(time_labels):
            idx = i * 2 + j
            ax = axs_rtt[idx]
            key = (ip_type, time_label)
            this_case = by_scenario.get(key, {})
            if not this_case:
                ax.set_title(f"No data: {ip_type}, {time_label}")
                continue
            for ns, (times, _, rtts) in this_case.items():
                color = namespace_colors.get(ns, None)
                if ylog:
                    zipped = [(t, r) for t, r in zip(times, rtts) if r > 0 and not np.isnan(r) and not np.isnan(t)]
                else:
                    zipped = [(t, r) for t, r in zip(times, rtts) if not np.isnan(r) and not np.isnan(t)]
                if not zipped:
                    continue
                times2, rtts2 = zip(*zipped)
                ax.plot(times2, rtts2, marker='o', markersize=4, label=ns, color=color)
                if rtts2:
                    mean_rtt = sum(rtts2) / len(rtts2)
                    ax.axhline(mean_rtt, color=color, linestyle='--', alpha=0.5)
            ax.set_title(f"RTT: {ip_type}, {time_label}")
            ax.set_xlabel("Time [s]")
            ax.set_ylabel("RTT [ms]")
            ax.grid(True)
            ax.legend()
            if ylog:
                ax.set_yscale("log")

    fig_rtt.suptitle(f"TCP RTT Over Time for Each Scenario ({CLOCKTIME_LABEL}) (Y {'log' if ylog else 'linear'})", fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    yscale_name = "log" if ylog else "linear"
    rtt_plot_path = os.path.join(IMG_DIR, f"tcp_rtt_over_time_{CLOCKTIME_LABEL}_{yscale_name}.png")
    plt.savefig(rtt_plot_path, dpi=200)
    print(f"RTT plot saved to {rtt_plot_path}")
    plt.close(fig_rtt)
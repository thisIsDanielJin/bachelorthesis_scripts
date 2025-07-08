import os
import json
import matplotlib.pyplot as plt
from collections import defaultdict

# Settings
FOLDER = "UDP_1/Messungen"
IMG_DIR = "img"
os.makedirs(IMG_DIR, exist_ok=True)
namespace_colors = {
    "tundra-ns": "red",
    "jool-app-ns": "green",
    "tayga-ns": "blue",
}

FILES = [f for f in os.listdir(FOLDER) if f.endswith(".json")]
by_scenario = defaultdict(dict)  # (ip_type, time_label) -> {namespace: (times, throughput, overall_loss_pct, overall_jitter)}

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

    times, throughput = [], []

    for interval in data.get("intervals", []):
        s = interval.get("sum", {})
        times.append(s.get("start", float('nan')))
        throughput.append(s.get("bits_per_second", 0) / 1e9)  # Gbit/s

    # Overall metrics
    overall_loss_pct = data.get("end", {}).get("sum", {}).get("lost_percent", None)
    overall_jitter = data.get("end", {}).get("sum", {}).get("jitter_ms", None)

    key = (ip_type, time_label)
    by_scenario[key][namespace] = (times, throughput, overall_loss_pct, overall_jitter)

ip_types = ["IPv4", "IPv6"]
time_labels = ["30s", "2min"]

# ---- Throughput plot ----
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
        for ns, (times, throughputs, overall_loss, overall_jitter) in this_case.items():
            color = namespace_colors.get(ns, None)
            ax.plot(times, throughputs, marker='o', markersize=4, label=ns, color=color)
            mean_thr = sum(throughputs) / len(throughputs) if throughputs else 0
            ax.axhline(mean_thr, color=color, linestyle='--', alpha=0.5)
            # Annotate overall loss%
            if overall_loss is not None and overall_loss > 0:
                ax.text(times[len(times)//2], mean_thr, f"{overall_loss:.3f}% loss", color=color, fontsize=8)
            # Annotate overall jitter
            if overall_jitter is not None and overall_jitter > 0:
                ax.text(times[len(times)//2], mean_thr*0.95, f"Jitter: {overall_jitter:.3f}ms", color=color, fontsize=8)
        ax.set_title(f"Throughput: {ip_type}, {time_label}")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Throughput [Gbit/s]")
        ax.grid(True)
        ax.legend()
fig_thr.suptitle("UDP Throughput Over Time for Each Scenario", fontsize=16)
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(os.path.join(IMG_DIR, "udp_throughput_over_time.png"), dpi=200)
plt.show()

# ---- Loss% plot (overall line only) ----
fig_loss, axs_loss = plt.subplots(2, 2, figsize=(14, 10))
axs_loss = axs_loss.flatten()
for i, ip_type in enumerate(ip_types):
    for j, time_label in enumerate(time_labels):
        idx = i*2 + j
        ax = axs_loss[idx]
        key = (ip_type, time_label)
        this_case = by_scenario.get(key, {})
        if not this_case:
            ax.set_title(f"No data: {ip_type}, {time_label}")
            continue
        for ns, (times, throughputs, overall_loss, _) in this_case.items():
            color = namespace_colors.get(ns, None)
            loss_line = [overall_loss]*len(times)
            ax.plot(times, loss_line, label=ns, color=color)
        ax.set_title(f"Loss %: {ip_type}, {time_label}")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Loss [%]")
        ax.grid(True)
        ax.legend()
fig_loss.suptitle("UDP Packet Loss (%) for Each Scenario (overall only)", fontsize=16)
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(os.path.join(IMG_DIR, "udp_loss_pct_over_time.png"), dpi=200)
plt.show()

# ---- Jitter plot (overall line only) ----
fig_jit, axs_jit = plt.subplots(2, 2, figsize=(14, 10))
axs_jit = axs_jit.flatten()
for i, ip_type in enumerate(ip_types):
    for j, time_label in enumerate(time_labels):
        idx = i*2 + j
        ax = axs_jit[idx]
        key = (ip_type, time_label)
        this_case = by_scenario.get(key, {})
        if not this_case:
            ax.set_title(f"No data: {ip_type}, {time_label}")
            continue
        for ns, (times, throughputs, _, overall_jitter) in this_case.items():
            color = namespace_colors.get(ns, None)
            jitter_line = [overall_jitter]*len(times)
            ax.plot(times, jitter_line, label=ns, color=color)
        ax.set_title(f"Jitter: {ip_type}, {time_label}")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Jitter [ms]")
        ax.grid(True)
        ax.legend()
fig_jit.suptitle("UDP Jitter for Each Scenario (overall only)", fontsize=16)
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(os.path.join(IMG_DIR, "udp_jitter_over_time.png"), dpi=200)
plt.show()

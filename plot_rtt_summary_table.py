import os
import re
import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np

# Configuration
FOLDERS = {
    "AWS": "RawMessungen/PingAWS",
    "Single": "RawMessungen/PingSingleMachineRTT", 
    "Double": "RawMessungen/PingDoubleMachineRTT"
}

OUTPUT_DIR = "img"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Regex patterns
RE_SEQ = re.compile(r"icmp[_-]seq=(\d+)", re.IGNORECASE)
RE_TIME = re.compile(r"time[=<]?([\d.]+)\s*ms", re.IGNORECASE)
RE_STATS = re.compile(r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms")

# IP label mappings
IP_LABEL_OVERRIDES = {
    "fd00_64_64_5f00_20d2__400": "fd00:64:64:5f00:20d2::400",
    "2a05_d014_144f_5f00_20d2__400": "2a05:d014:144f:5f00:20d2::400",
}

def normalize_ip_type(raw):
    """Convert IP version indicator to standard format"""
    s = (raw or "").strip().lower()
    if s in ("ipv4", "v4", "4"):
        return "IPv4"
    if s in ("ipv6", "v6", "6"):
        return "IPv6"
    return None

def reconstruct_ipv6_from_filename(ip_token_joined):
    """Reconstruct IPv6 address from filename encoding"""
    s = ip_token_joined.replace("", "::")
    s = s.replace("", ":")
    return s

def parse_ping_file(filepath):
    """Parse a ping file and extract RTT statistics"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        # Try to extract stats from the summary line first
        stats_match = RE_STATS.search(content)
        if stats_match:
            min_rtt = float(stats_match.group(1))
            avg_rtt = float(stats_match.group(2))
            max_rtt = float(stats_match.group(3))
            mdev_rtt = float(stats_match.group(4))
            
            # Also count packets and calculate additional metrics
            rtts = []
            lines = content.split('\n')
            for line in lines:
                if "icmp" in line.lower():
                    m_time = RE_TIME.search(line)
                    if m_time:
                        try:
                            rtt_ms = float(m_time.group(1))
                            rtts.append(rtt_ms)
                        except ValueError:
                            pass
            
            packet_count = len(rtts)
            std_dev = np.std(rtts) if rtts else 0
            percentile_95 = np.percentile(rtts, 95) if rtts else 0
            median_rtt = np.median(rtts) if rtts else 0
            
            return {
                'min': min_rtt,
                'avg': avg_rtt,
                'max': max_rtt,
                'mdev': mdev_rtt,
                'std_dev': std_dev,
                'median': median_rtt,
                'p95': percentile_95,
                'packet_count': packet_count,
                'raw_rtts': rtts
            }
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    
    return None

def collect_all_data():
    """Collect RTT data from all folders and files"""
    data = []
    
    for scenario, folder in FOLDERS.items():
        if not os.path.exists(folder):
            print(f"Warning: Folder {folder} not found, skipping {scenario}")
            continue
            
        files = [f for f in os.listdir(folder) if f.endswith("_30s.txt")]
        
        for fname in files:
            filepath = os.path.join(folder, fname)
            
            # Parse filename
            stem = os.path.splitext(fname)[0]
            parts = stem.split("_")
            
            if len(parts) < 4:
                print(f"Skipping {fname}: not enough parts")
                continue
            
            namespace = parts[0]
            ipvx_token = parts[-2]
            time_label = parts[-1]
            
            if time_label != "30s":
                continue
                
            ip_type = normalize_ip_type(ipvx_token)
            if not ip_type:
                print(f"Skipping {fname}: cannot determine IP type from '{ipvx_token}'")
                continue
            
            # Extract IP address
            ip_tokens = parts[1:-2]
            raw_ip_token_joined = "_".join(ip_tokens)
            
            if ip_type == "IPv4":
                ip_label = raw_ip_token_joined
            else:
                ip_label = IP_LABEL_OVERRIDES.get(
                    raw_ip_token_joined,
                    reconstruct_ipv6_from_filename(raw_ip_token_joined)
                )
            
            # Parse the file
            stats = parse_ping_file(filepath)
            if stats:
                data.append({
                    'scenario': scenario,
                    'namespace': namespace,
                    'ip_type': ip_type,
                    'ip_address': ip_label,
                    **stats
                })
    
    return data

def create_summary_table(data):
    """Create a formatted summary table"""
    df = pd.DataFrame(data)
    
    if df.empty:
        print("No data found!")
        return None
    
    # Create a pivot table for better visualization
    summary_data = []
    
    for scenario in df['scenario'].unique():
        for ip_type in ['IPv4', 'IPv6']:
            scenario_ip_data = df[(df['scenario'] == scenario) & (df['ip_type'] == ip_type)]
            
            if scenario_ip_data.empty:
                continue
                
            for _, row in scenario_ip_data.iterrows():
                # Clean up namespace names for display
                ns_display = row['namespace'].replace('-ns', '').replace('-app', '')
                
                summary_data.append({
                    'Scenario': scenario,
                    'IP Type': ip_type,
                    'Tool': ns_display,
                    'IP Address': row['ip_address'],
                    'Min (ms)': f"{row['min']:.3f}",
                    'Avg (ms)': f"{row['avg']:.3f}",
                    'Median (ms)': f"{row['median']:.3f}",
                    'Max (ms)': f"{row['max']:.3f}",
                    'Std Dev (ms)': f"{row['std_dev']:.3f}",
                    'P95 (ms)': f"{row['p95']:.3f}",
                    'Packets': row['packet_count']
                })
    
    summary_df = pd.DataFrame(summary_data)
    return summary_df

def create_comparison_plot(data):
    """Create a visual comparison plot of average RTTs
    
    This plot compares RTT performance across three scenarios:
    - AWS: Cloud environment with external routing
    - Single Local Host: Single machine setup with network namespaces
    - Dual Local Host: Two separate machines with network translation
    
    IPv4 Transition shows translation performance from IPv6 to IPv4.
    IPv6 Baseline shows native IPv6 performance without translation.
    
    Visual Elements Explained:
    - COLOR BARS represent different translation tools/configurations:
      IPv4 Transition (top row):
      * RED bars = Tundra (NAT64/DNS64 translator)
      * GREEN bars = Jool (Stateful NAT64 translator) 
      * BLUE bars = Tayga (Stateless NAT64 translator) - Single/Double scenarios only
      
      IPv6 Baseline (bottom row):
      * ORANGE bars = 1 Hop (Tundra configuration)
      * PURPLE bars = 2 Hops (Jool configuration)
      * Tayga is excluded from IPv6 baseline and AWS IPv4 transition
    
    - BLACK VERTICAL LINES (error bars) show the full range of RTT values:
      * Bottom of line = Minimum RTT observed
      * Top of line = Maximum RTT observed  
      * Bar height = Average RTT
      * This shows RTT variability/jitter for each tool
    
    - Numbers on top of bars = Average RTT in milliseconds
    """
    df = pd.DataFrame(data)
    
    if df.empty:
        return
    
    # Create comparison plots with explanatory title
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    

    # Updated scenario and IP type mappings
    scenarios = ['AWS', 'Single', 'Double']
    scenario_labels = {
        'AWS': 'AWS',
        'Single': 'Single Local Host', 
        'Double': 'Dual Local Host'
    }
    
    ip_types = ['IPv4', 'IPv6']
    ip_type_labels = {
        'IPv4': 'IPv4 Transition',
        'IPv6': 'IPv6 Baseline'
    }

    for i, ip_type in enumerate(ip_types):
        for j, scenario in enumerate(scenarios):
            ax = axes[i, j]
            
            scenario_data = df[(df['scenario'] == scenario) & (df['ip_type'] == ip_type)]
            
            # For IPv6 baseline, filter out tayga
            if ip_type == 'IPv6':
                scenario_data = scenario_data[~scenario_data['namespace'].str.contains('tayga')]
            
            # For AWS IPv4 transition, also filter out tayga
            if scenario == 'AWS' and ip_type == 'IPv4':
                scenario_data = scenario_data[~scenario_data['namespace'].str.contains('tayga')]
            
            if scenario_data.empty:
                ax.text(0.5, 0.5, 'No Data', ha='center', va='center', transform=ax.transAxes)
                ax.set_title(f'{scenario_labels[scenario]} - {ip_type_labels[ip_type]}')
                continue
            
            # Create bar plot with modified tool names for IPv6 baseline
            tools = []
            for ns in scenario_data['namespace']:
                clean_ns = ns.replace('-ns', '').replace('-app', '')
                if ip_type == 'IPv6':
                    if 'jool' in ns:
                        tools.append('2 Hops')
                    elif 'tundra' in ns:
                        tools.append('1 Hop')
                    else:
                        tools.append(clean_ns)
                else:
                    tools.append(clean_ns)
            
            avgs = scenario_data['avg']
            mins = scenario_data['min']
            maxs = scenario_data['max']
            
            # Color mapping
            colors = []
            for ns in scenario_data['namespace']:
                if ip_type == 'IPv6':
                    # IPv6 baseline colors
                    if 'tundra' in ns:
                        colors.append('orange')  # 1 Hop
                    elif 'jool' in ns:
                        colors.append('purple')  # 2 Hops
                    else:
                        colors.append('gray')
                else:
                    # IPv4 transition colors (keep original)
                    if 'tundra' in ns:
                        colors.append('red')
                    elif 'jool' in ns:
                        colors.append('green')
                    elif 'tayga' in ns:
                        colors.append('blue')
                    else:
                        colors.append('gray')
            
            x_pos = range(len(tools))
            bars = ax.bar(x_pos, avgs, alpha=0.7, color=colors)
            
            # Add error bars (min to max range)
            errors = [(avg - min_val, max_val - avg) for avg, min_val, max_val in zip(avgs, mins, maxs)]
            ax.errorbar(x_pos, avgs, yerr=list(zip(*errors)), fmt='none', capsize=3, color='black', alpha=0.6)
            
            # Add value labels on bars
            for idx, (bar, avg) in enumerate(zip(bars, avgs)):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.001, 
                       f'{avg:.3f}', ha='center', va='bottom', fontsize=8)
            
            ax.set_title(f'{scenario_labels[scenario]} - {ip_type_labels[ip_type]}')
            ax.set_ylabel('RTT (ms)')
            ax.set_xticks(x_pos)
            ax.set_xticklabels(tools, rotation=45)
            ax.grid(True, alpha=0.3)
            
            # Set y-axis to start from 0
            ax.set_ylim(bottom=0)
    
    # Add a color legend to explain the meaning of colors
    from matplotlib.patches import Patch
    legend_elements = [
        # IPv4 Transition colors
        Patch(facecolor='red', alpha=0.7, label='IPv4: Tundra (NAT64/DNS64)'),
        Patch(facecolor='green', alpha=0.7, label='IPv4: Jool (Stateful NAT64)'),
        Patch(facecolor='blue', alpha=0.7, label='IPv4: Tayga (Single/Double only)'),
        # IPv6 Baseline colors  
        Patch(facecolor='orange', alpha=0.7, label='IPv6: 1 Hop (Tundra)'),
        Patch(facecolor='purple', alpha=0.7, label='IPv6: 2 Hops (Jool)')
    ]
    #fig.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.92))
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'rtt_comparison_summary.png'), dpi=300, bbox_inches='tight')
    print(f"Comparison plot saved to {OUTPUT_DIR}/rtt_comparison_summary.png")
    print("  - IPv4 Transition: Red=Tundra, Green=Jool, Blue=Tayga (Single/Double only)")
    print("  - IPv6 Baseline: Orange=1 Hop (Tundra), Purple=2 Hops (Jool)")
    print("  - Black error bars show min-max RTT range for each measurement")
    print("  - Bar height shows average RTT, numbers on top show exact values")
    plt.close()

def create_latex_table(summary_df):
    """Create a LaTeX-formatted table from the summary data"""
    
    latex_output = []
    latex_output.append("% RTT Measurement Summary Table - LaTeX Format")
    latex_output.append("\\begin{table}[htbp]")
    latex_output.append("\\centering")
    latex_output.append("\\caption{RTT Performance Comparison Across Translation Tools and Scenarios}")
    latex_output.append("\\label{tab:rtt_comparison}")
    latex_output.append("\\footnotesize")
    latex_output.append("\\begin{tabular}{|l|l|l|l|r|r|r|r|r|r|r|}")
    latex_output.append("\\hline")
    latex_output.append("\\textbf{Scenario} & \\textbf{IP Type} & \\textbf{Tool} & \\textbf{IP Address} & " +
                       "\\textbf{Min (ms)} & \\textbf{Avg (ms)} & \\textbf{Median (ms)} & \\textbf{Max (ms)} & " +
                       "\\textbf{Std Dev (ms)} & \\textbf{P95 (ms)} & \\textbf{Packets} \\\\")
    latex_output.append("\\hline")
    
    # Group data by scenario and IP type for better organization
    current_scenario = ""
    current_ip_type = ""
    
    for _, row in summary_df.iterrows():
        # Add section dividers for readability
        if row['Scenario'] != current_scenario:
            if current_scenario != "":  # Not the first row
                latex_output.append("\\hline")
            current_scenario = row['Scenario']
            current_ip_type = ""
        
        if row['IP Type'] != current_ip_type:
            current_ip_type = row['IP Type']
        
        # Format IP address for LaTeX (handle special characters)
        ip_address = row['IP Address'].replace('_', '\\_')
        
        # Create table row
        row_data = f"{row['Scenario']} & {row['IP Type']} & {row['Tool']} & " + \
                  f"\\texttt{{{ip_address}}} & {row['Min (ms)']} & {row['Avg (ms)']} & " + \
                  f"{row['Median (ms)']} & {row['Max (ms)']} & {row['Std Dev (ms)']} & {row['P95 (ms)']} & {row['Packets']} \\\\"
        
        latex_output.append(row_data)
    
    latex_output.append("\\hline")
    latex_output.append("\\end{tabular}")
    latex_output.append("\\end{table}")
    latex_output.append("")
    latex_output.append("% Table Notes:")
    latex_output.append("% - Min/Avg/Median/Max: Minimum, Average, Median, and Maximum RTT values")
    latex_output.append("% - Std Dev: Standard deviation of RTT measurements")  
    latex_output.append("% - P95: 95th percentile RTT value")
    latex_output.append("% - Packets: Number of ping packets measured")
    latex_output.append("% - IPv4 Transition: Translation from IPv6 to IPv4")
    latex_output.append("% - IPv6 Baseline: Native IPv6 performance")
    
    return "\\n".join(latex_output)

def main():
    """Main execution function"""
    print("Collecting RTT data from all scenarios...")
    data = collect_all_data()
    
    if not data:
        print("No data collected!")
        return
    
    print(f"Collected {len(data)} measurements")
    
    # Create summary table
    summary_df = create_summary_table(data)
    
    if summary_df is not None:
        print("\n" + "="*120)
        print("RTT MEASUREMENT SUMMARY TABLE")
        print("="*120)
        print(summary_df.to_string(index=False))
        print("="*120)
        
        # Save to CSV
        csv_path = os.path.join(OUTPUT_DIR, "rtt_summary_table.csv")
        summary_df.to_csv(csv_path, index=False)
        print(f"\nSummary table saved to: {csv_path}")
        
        # Create LaTeX table
        latex_table = create_latex_table(summary_df)
        latex_path = os.path.join(OUTPUT_DIR, "rtt_summary_table.tex")
        with open(latex_path, 'w', encoding='utf-8') as f:
            f.write(latex_table)
        print(f"LaTeX table saved to: {latex_path}")
        
        # Create visualization
        print("\nGenerating comparison plot...")
        create_comparison_plot(data)
        
        # Print some insights
        print("\n" + "="*60)
        print("KEY INSIGHTS:")
        print("="*60)
        
        df = pd.DataFrame(data)
        
        # Find best and worst performers
        ipv4_data = df[df['ip_type'] == 'IPv4']
        ipv6_data = df[df['ip_type'] == 'IPv6']
        
        if not ipv4_data.empty:
            best_ipv4 = ipv4_data.loc[ipv4_data['avg'].idxmin()]
            worst_ipv4 = ipv4_data.loc[ipv4_data['avg'].idxmax()]
            print(f"IPv4 - Best: {best_ipv4['namespace']} in {best_ipv4['scenario']} ({best_ipv4['avg']:.3f}ms avg)")
            print(f"IPv4 - Worst: {worst_ipv4['namespace']} in {worst_ipv4['scenario']} ({worst_ipv4['avg']:.3f}ms avg)")
        
        if not ipv6_data.empty:
            best_ipv6 = ipv6_data.loc[ipv6_data['avg'].idxmin()]
            worst_ipv6 = ipv6_data.loc[ipv6_data['avg'].idxmax()]
            print(f"IPv6 - Best: {best_ipv6['namespace']} in {best_ipv6['scenario']} ({best_ipv6['avg']:.3f}ms avg)")
            print(f"IPv6 - Worst: {worst_ipv6['namespace']} in {worst_ipv6['scenario']} ({worst_ipv6['avg']:.3f}ms avg)")
        
        print("="*60)

if __name__ == "__main__":
    main()

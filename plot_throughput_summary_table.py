import os
import json
import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

# Configuration
FOLDERS = {
    "AWS_hpet": "RawMessungen/AWS_hpet_clocktime",
    "AWS_kvm": "RawMessungen/AWS_kvm-clock_clocktime",
    "LocalDouble_hpet": "RawMessungen/LocalDouble_hpet_clocktime",
    "LocalDouble_tsc": "RawMessungen/LocalDouble_tsc_clocktime",
    "LocalSingle_hpet": "RawMessungen/LocalSingle_hpet_clocktime",
    "LocalSingle_tsc": "RawMessungen/LocalSingle_tsc_clocktime"
}

OUTPUT_DIR = "img"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# IP label mappings
IP_LABEL_OVERRIDES = {
    "fd00_64_64_5f00_20d2__400": "fd00:64:64:5f00:20d2::400",
    "2a05_d014_144f_5f00_20d2__400": "2a05:d014:144f:5f00:20d2::400",
}

def normalize_ip_type(raw):
    """Convert IP version indicator to standard format"""
    if "." in raw:
        return "IPv4"
    elif ":" in raw or "_" in raw:  # Handle both full IPv6 and encoded format
        return "IPv6"
    return None

def reconstruct_ipv6_from_filename(ip_token_joined):
    """Reconstruct IPv6 address from filename encoding"""
    s = ip_token_joined.replace("", "::")
    s = s.replace("", ":")
    return s

def parse_iperf_file(filepath):
    """Parse an iperf3 JSON file and extract throughput statistics"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        
        # Extract summary statistics from the end section
        end_section = data.get("end", {})
        sum_sent = end_section.get("sum_sent", {})
        sum_received = end_section.get("sum_received", {})
        
        # Get overall throughput (prefer receiver data as it's more accurate)
        overall_throughput_bps = sum_received.get("bits_per_second", sum_sent.get("bits_per_second", 0))
        overall_throughput_gbps = overall_throughput_bps / 1e9
        
        # Extract interval data for detailed analysis
        intervals = data.get("intervals", [])
        interval_throughputs = []
        for interval in intervals:
            interval_sum = interval.get("sum", {})
            bps = interval_sum.get("bits_per_second", 0)
            interval_throughputs.append(bps / 1e9)  # Convert to Gbps
        
        if not interval_throughputs:
            return None
        
        # Calculate statistics
        min_throughput = min(interval_throughputs)
        max_throughput = max(interval_throughputs)
        avg_throughput = np.mean(interval_throughputs)
        std_dev = np.std(interval_throughputs)
        percentile_95 = np.percentile(interval_throughputs, 95)
        percentile_5 = np.percentile(interval_throughputs, 5)
        
        # Additional metrics
        duration_seconds = sum_sent.get("seconds", 0)
        total_bytes = sum_sent.get("bytes", 0)
        retransmits = sum_sent.get("retransmits", 0)
        
        return {
            'min': min_throughput,
            'avg': avg_throughput, 
            'max': max_throughput,
            'overall': overall_throughput_gbps,
            'std_dev': std_dev,
            'p95': percentile_95,
            'p5': percentile_5,
            'duration_seconds': duration_seconds,
            'total_gb': total_bytes / 1e9,
            'retransmits': retransmits,
            'sample_count': len(interval_throughputs),
            'raw_throughputs': interval_throughputs
        }
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    
    return None

def collect_all_data():
    """Collect throughput data from all folders and files"""
    data = []
    
    for scenario, folder in FOLDERS.items():
        if not os.path.exists(folder):
            print(f"Warning: Folder {folder} not found, skipping {scenario}")
            continue
            
        files = [f for f in os.listdir(folder) if f.endswith(".json") and ("_30s.json" in f or "_2min.json" in f)]
        
        for fname in files:
            filepath = os.path.join(folder, fname)
            
            # Parse filename: namespace_ip_tcp_duration.json
            stem = os.path.splitext(fname)[0]
            parts = stem.split("_")
            
            if len(parts) < 4:
                print(f"Skipping {fname}: not enough parts")
                continue
            
            namespace = parts[0]
            protocol = parts[-2]  # Should be "tcp"
            duration = parts[-1]   # "30s" or "2min"
            
            if protocol != "tcp":
                continue
                
            # Extract IP address parts
            ip_tokens = parts[1:-2]  # Everything between namespace and tcp_duration
            raw_ip_token_joined = "_".join(ip_tokens)
            
            ip_type = normalize_ip_type(raw_ip_token_joined)
            if not ip_type:
                print(f"Skipping {fname}: cannot determine IP type from '{raw_ip_token_joined}'")
                continue
            
            if ip_type == "IPv4":
                ip_label = raw_ip_token_joined
            else:
                ip_label = IP_LABEL_OVERRIDES.get(
                    raw_ip_token_joined,
                    reconstruct_ipv6_from_filename(raw_ip_token_joined)
                )
            
            # Parse the file
            stats = parse_iperf_file(filepath)
            if stats:
                data.append({
                    'scenario': scenario,
                    'namespace': namespace,
                    'ip_type': ip_type,
                    'ip_address': ip_label,
                    'duration': duration,
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
        for duration in ['30s', '2min']:
            for ip_type in ['IPv4', 'IPv6']:
                scenario_data = df[
                    (df['scenario'] == scenario) & 
                    (df['duration'] == duration) & 
                    (df['ip_type'] == ip_type)
                ]
                
                if scenario_data.empty:
                    continue
                    
                for _, row in scenario_data.iterrows():
                    # Clean up namespace names for display
                    ns_display = row['namespace'].replace('-ns', '').replace('-app', '')
                    
                    summary_data.append({
                        'Scenario': scenario,
                        'Duration': duration,
                        'IP Type': ip_type,
                        'Tool': ns_display,
                        'IP Address': row['ip_address'],
                        'Min (Gbps)': f"{row['min']:.3f}",
                        'Avg (Gbps)': f"{row['avg']:.3f}",
                        'Max (Gbps)': f"{row['max']:.3f}",
                        'Overall (Gbps)': f"{row['overall']:.3f}",
                        'Std Dev (Gbps)': f"{row['std_dev']:.3f}",
                        'P95 (Gbps)': f"{row['p95']:.3f}",
                        'Total (GB)': f"{row['total_gb']:.2f}",
                        'Retransmits': row['retransmits'],
                        'Samples': row['sample_count']
                    })
    
    summary_df = pd.DataFrame(summary_data)
    return summary_df

def create_comparison_plot(data):
    """Create a visual comparison plot of average throughput
    
    This plot compares throughput performance across different scenarios:
    - AWS environments with different clock sources (hpet vs kvm-clock)
    - Local environments (Single vs Double machine, hpet vs tsc)
    
    IPv4 Transition shows translation performance from IPv6 to IPv4.
    IPv6 Baseline shows native IPv6 performance without translation.
    
    Visual Elements Explained:
    - COLOR BARS represent different translation tools/configurations:
      IPv4 Transition (top row):
      * RED bars = Tundra (NAT64/DNS64 translator)
      * GREEN bars = Jool (Stateful NAT64 translator) 
      * BLUE bars = Tayga (Stateless NAT64 translator) - Local scenarios only
      
      IPv6 Baseline (bottom row):
      * ORANGE bars = 1 Hop (Tundra configuration)
      * PURPLE bars = 2 Hops (Jool configuration)
      * Tayga is excluded from IPv6 baseline and AWS IPv4 transition
    
    - BLACK VERTICAL LINES (error bars) show the full range of throughput values:
      * Bottom of line = Minimum throughput observed
      * Top of line = Maximum throughput observed  
      * Bar height = Average throughput
      * This shows throughput variability for each tool
    
    - Numbers on top of bars = Average throughput in Gbps
    """
    df = pd.DataFrame(data)
    
    if df.empty:
        return
    
    # Create separate plots for each duration
    for duration in ['30s', '2min']:
        duration_data = df[df['duration'] == duration]
        
        if duration_data.empty:
            continue
        
        # Get unique scenarios for this duration
        scenarios = sorted(duration_data['scenario'].unique())
        
        if not scenarios:
            continue
        
        # Create comparison plots with explanatory title
        fig, axes = plt.subplots(2, len(scenarios), figsize=(6*len(scenarios), 10))
        if len(scenarios) == 1:
            axes = axes.reshape(-1, 1)
        
        
        # Scenario labels for better display
        scenario_labels = {
            'AWS_hpet': 'AWS (HPET)',
            'AWS_kvm': 'AWS (KVM-Clock)', 
            'LocalDouble_hpet': 'Dual Local (HPET)',
            'LocalDouble_tsc': 'Dual Local (TSC)',
            'LocalSingle_hpet': 'Single Local (HPET)',
            'LocalSingle_tsc': 'Single Local (TSC)'
        }
        
        ip_types = ['IPv4', 'IPv6']
        ip_type_labels = {
            'IPv4': 'IPv4 Transition',
            'IPv6': 'IPv6 Baseline'
        }

        for i, ip_type in enumerate(ip_types):
            for j, scenario in enumerate(scenarios):
                ax = axes[i, j]
                
                scenario_data = duration_data[
                    (duration_data['scenario'] == scenario) & 
                    (duration_data['ip_type'] == ip_type)
                ]
                
                # For IPv6 baseline, filter out tayga
                if ip_type == 'IPv6':
                    scenario_data = scenario_data[~scenario_data['namespace'].str.contains('tayga')]
                
                # For AWS IPv4 transition, also filter out tayga
                if scenario.startswith('AWS') and ip_type == 'IPv4':
                    scenario_data = scenario_data[~scenario_data['namespace'].str.contains('tayga')]
                
                if scenario_data.empty:
                    ax.text(0.5, 0.5, 'No Data', ha='center', va='center', transform=ax.transAxes)
                    ax.set_title(f'{scenario_labels.get(scenario, scenario)} - {ip_type_labels[ip_type]}')
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
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, 
                           f'{avg:.2f}', ha='center', va='bottom', fontsize=8)
                
                ax.set_title(f'{scenario_labels.get(scenario, scenario)} - {ip_type_labels[ip_type]}')
                ax.set_xlabel('Translation Tool')
                ax.set_ylabel('Throughput (Gbps)')
                ax.set_xticks(x_pos)
                ax.set_xticklabels(tools, rotation=45)
                ax.grid(True, alpha=0.3)
                
                # Set y-axis to start from 0
                ax.set_ylim(bottom=0)
        
        # Add a color legend to explain the meaning of colors
        legend_elements = [
            # IPv4 Transition colors
            Patch(facecolor='red', alpha=0.7, label='IPv4: Tundra (NAT64/DNS64)'),
            Patch(facecolor='green', alpha=0.7, label='IPv4: Jool (Stateful NAT64)'),
            Patch(facecolor='blue', alpha=0.7, label='IPv4: Tayga (Local only)'),
            # IPv6 Baseline colors  
            Patch(facecolor='orange', alpha=0.7, label='IPv6: 1 Hop (Tundra)'),
            Patch(facecolor='purple', alpha=0.7, label='IPv6: 2 Hops (Jool)')
        ]
        #fig.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.92))
        
        plt.tight_layout()
        plot_path = os.path.join(OUTPUT_DIR, f'throughput_comparison_summary_{duration}.png')
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        print(f"Throughput comparison plot ({duration}) saved to {plot_path}")
        print("  - IPv4 Transition: Red=Tundra, Green=Jool, Blue=Tayga (Local scenarios only)")
        print("  - IPv6 Baseline: Orange=1 Hop (Tundra), Purple=2 Hops (Jool)")
        print("  - Black error bars show min-max throughput range for each measurement")
        print("  - Bar height shows average throughput, numbers on top show exact values")
        plt.close()

def create_latex_table(summary_df):
    """Create a LaTeX-formatted table from the summary data"""
    
    latex_output = []
    latex_output.append("% Throughput Measurement Summary Table - LaTeX Format")
    latex_output.append("\\begin{table}[htbp]")
    latex_output.append("\\centering")
    latex_output.append("\\caption{Throughput Performance Comparison Across Translation Tools and Scenarios}")
    latex_output.append("\\label{tab:throughput_comparison}")
    latex_output.append("\\footnotesize")
    latex_output.append("\\begin{tabular}{|l|l|l|l|l|r|r|r|r|r|r|r|r|}")
    latex_output.append("\\hline")
    latex_output.append("\\textbf{Scenario} & \\textbf{Duration} & \\textbf{IP Type} & \\textbf{Tool} & " +
                       "\\textbf{IP Address} & \\textbf{Min (Gbps)} & \\textbf{Avg (Gbps)} & " +
                       "\\textbf{Max (Gbps)} & \\textbf{Overall (Gbps)} & \\textbf{Std Dev (Gbps)} & " +
                       "\\textbf{P95 (Gbps)} & \\textbf{Total (GB)} & \\textbf{Retransmits} \\\\")
    latex_output.append("\\hline")
    
    # Group data by scenario and duration for better organization
    current_scenario = ""
    current_duration = ""
    
    for _, row in summary_df.iterrows():
        # Add section dividers for readability
        if row['Scenario'] != current_scenario:
            if current_scenario != "":  # Not the first row
                latex_output.append("\\hline")
            current_scenario = row['Scenario']
            current_duration = ""
        
        if row['Duration'] != current_duration:
            current_duration = row['Duration']
        
        # Format IP address for LaTeX (handle special characters)
        ip_address = row['IP Address'].replace('_', '\\_')
        
        # Create table row
        row_data = f"{row['Scenario']} & {row['Duration']} & {row['IP Type']} & {row['Tool']} & " + \
                  f"\\texttt{{{ip_address}}} & {row['Min (Gbps)']} & {row['Avg (Gbps)']} & " + \
                  f"{row['Max (Gbps)']} & {row['Overall (Gbps)']} & {row['Std Dev (Gbps)']} & " + \
                  f"{row['P95 (Gbps)']} & {row['Total (GB)']} & {row['Retransmits']} \\\\"
        
        latex_output.append(row_data)
    
    latex_output.append("\\hline")
    latex_output.append("\\end{tabular}")
    latex_output.append("\\end{table}")
    latex_output.append("")
    latex_output.append("% Table Notes:")
    latex_output.append("% - Min/Avg/Max: Minimum, Average, and Maximum throughput values from interval data")
    latex_output.append("% - Overall: End-to-end throughput from iperf3 summary") 
    latex_output.append("% - Std Dev: Standard deviation of throughput measurements")
    latex_output.append("% - P95: 95th percentile throughput value")
    latex_output.append("% - Total (GB): Total data transferred in gigabytes")
    latex_output.append("% - Retransmits: Number of TCP retransmissions")
    latex_output.append("% - IPv4 Transition: Translation from IPv6 to IPv4")
    latex_output.append("% - IPv6 Baseline: Native IPv6 performance")
    
    return "\\n".join(latex_output)

def main():
    """Main execution function"""
    print("Collecting throughput data from all scenarios...")
    data = collect_all_data()
    
    if not data:
        print("No data collected!")
        return
    
    print(f"Collected {len(data)} measurements")
    
    # Create summary table
    summary_df = create_summary_table(data)
    
    if summary_df is not None:
        print("\n" + "="*140)
        print("THROUGHPUT MEASUREMENT SUMMARY TABLE")
        print("="*140)
        print(summary_df.to_string(index=False))
        print("="*140)
        
        # Save to CSV
        csv_path = os.path.join(OUTPUT_DIR, "throughput_summary_table.csv")
        summary_df.to_csv(csv_path, index=False)
        print(f"\nSummary table saved to: {csv_path}")
        
        # Create LaTeX table
        latex_table = create_latex_table(summary_df)
        latex_path = os.path.join(OUTPUT_DIR, "throughput_summary_table.tex")
        with open(latex_path, 'w', encoding='utf-8') as f:
            f.write(latex_table)
        print(f"LaTeX table saved to: {latex_path}")
        
        # Create visualizations
        print("\nGenerating comparison plots...")
        create_comparison_plot(data)
        
        # Print some insights
        print("\n" + "="*60)
        print("KEY INSIGHTS:")
        print("="*60)
        
        df = pd.DataFrame(data)
        
        # Find best and worst performers for each duration
        for duration in ['30s', '2min']:
            print(f"\n{duration.upper()} DURATION:")
            duration_data = df[df['duration'] == duration]
            
            if duration_data.empty:
                continue
                
            ipv4_data = duration_data[duration_data['ip_type'] == 'IPv4']
            ipv6_data = duration_data[duration_data['ip_type'] == 'IPv6']
            
            if not ipv4_data.empty:
                best_ipv4 = ipv4_data.loc[ipv4_data['avg'].idxmax()]
                worst_ipv4 = ipv4_data.loc[ipv4_data['avg'].idxmin()]
                print(f"IPv4 - Best: {best_ipv4['namespace']} in {best_ipv4['scenario']} ({best_ipv4['avg']:.3f} Gbps avg)")
                print(f"IPv4 - Worst: {worst_ipv4['namespace']} in {worst_ipv4['scenario']} ({worst_ipv4['avg']:.3f} Gbps avg)")
            
            if not ipv6_data.empty:
                best_ipv6 = ipv6_data.loc[ipv6_data['avg'].idxmax()]
                worst_ipv6 = ipv6_data.loc[ipv6_data['avg'].idxmin()]
                print(f"IPv6 - Best: {best_ipv6['namespace']} in {best_ipv6['scenario']} ({best_ipv6['avg']:.3f} Gbps avg)")
                print(f"IPv6 - Worst: {worst_ipv6['namespace']} in {worst_ipv6['scenario']} ({worst_ipv6['avg']:.3f} Gbps avg)")
        
        print("="*60)

if __name__ == "__main__":
    main()

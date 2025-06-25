# constants
NS_IPERF="iperf-ns"

### Step 1 - Create Container and assure basic networking 

# 1.0 clean up
sudo ip netns del "$NS_IPERF" 2>/dev/null || true

# 1.1 Install iperf3
sudo apt-get update
sudo apt-get install iperf3

# 1.2 Create networking namespace
sudo ip netns add "$NS_IPERF"


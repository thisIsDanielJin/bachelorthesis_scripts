# constants
NS_IPERF="iperf-ns"
VETH_IPERF_HOST="veth-iperf-h"
VETH_IPERF_NS="veth-iperf-ns"


IPERF_NS_IPV6="2a05:d014:144f:5f00:20d2::400/124"     # Namespace side

IPERF_LINK_LOCAL_HOST="fe80::9"
IPERF_LINK_LOCAL_NS="fe80::10"

TESTING_IPERF_IPV4="192.0.0.171"


### Step 1 - Create Container and assure basic networking 

# 1.0 clean up
sudo ip netns del "$NS_IPERF" 2>/dev/null || true
sudo ip link del "$VETH_IPERF_HOST" 2>/dev/null || true

# 1.1 Create networking namespace and veth cable
sudo ip netns add "$NS_IPERF"
sudo ip link add "$VETH_IPERF_HOST" type veth peer name "$VETH_IPERF_NS"

# 1.2 Move veth cable to namespace
sudo ip link set "$VETH_IPERF_NS" netns "$NS_IPERF"

# 1.3 bring up interfaces 
sudo ip netns exec "$NS_IPERF" ip link set lo up
sudo ip link set "$VETH_IPERF_HOST" up
sudo ip netns exec "$NS_IPERF" ip link set "$VETH_IPERF_NS" up

# 1.4 assign link-local address to host veth cable
sudo ip addr add "$IPERF_LINK_LOCAL_HOST"/64 dev "$VETH_IPERF_HOST"
sudo ip netns exec "$NS_IPERF" ip addr add "$IPERF_LINK_LOCAL_NS"/64 dev "$VETH_IPERF_NS"

# 1.5 assign IPv6 to veth cable namespace
sudo ip netns exec "$NS_IPERF" ip addr add "$IPERF_NS_IPV6" dev "$VETH_IPERF_NS"

# 1.6 set route between link-local and veth cable namespace
sudo ip -6 route add "$IPERF_NS_IPV6" via "$IPERF_LINK_LOCAL_NS" dev "$VETH_IPERF_HOST"

# 1.7 set veth cable as default ipv6 route inside the namespace
sudo ip netns exec "$NS_IPERF" ip -6 route add default via "$IPERF_LINK_LOCAL_HOST" dev "$VETH_IPERF_NS"

# 1.8 Enable IP forwarding on the host
sudo sysctl -w net.ipv6.conf.all.forwarding=1

# ------------------------------------------------------------

# Step 2 - add routes from namespaces to host

# add routes for ipv6 addresses of the namespaces
sudo ip -6 route add 2a05:d014:144f:5f00:20d2::100/124 via "$IPERF_LINK_LOCAL_NS" dev "$VETH_IPERF_HOST"
sudo ip -6 route add 2a05:d014:144f:5f00:20d2::200/124 via "$IPERF_LINK_LOCAL_NS" dev "$VETH_IPERF_HOST"
sudo ip -6 route add 2a05:d014:144f:5f00:20d2::300/124 via "$IPERF_LINK_LOCAL_NS" dev "$VETH_IPERF_HOST"

# add route for translated testing ipv4 address
sudo ip route add 64:ff9b::"$TESTING_IPERF_IPV4" via "$IPERF_LINK_LOCAL_NS" dev "$VETH_IPERF_HOST"

# add route for translated testing ipv4 address to namespace
sudo ip netns exec "$NS_IPERF" ip addr add 64:ff9b::"$TESTING_IPERF_IPV4" dev "$VETH_IPERF_NS"


# 
echo "--------------------------------"
echo "iperf-ns setup complete!"
echo "--------------------------------"


# ------------------------------------------------------------


# Step 3 - Configure iperf3

# 3.1 Install iperf3
sudo ip netns exec "$NS_IPERF" apt-get update
sudo ip netns exec "$NS_IPERF" apt-get install iperf3


# 3.2 run iperf3 server
sudo ip netns exec "$NS_IPERF" iperf3 -s -V

# 3.3 run iperf3 client from tayga namespace
sudo ip netns exec tayga-ns iperf3 -c 2a05:d014:144f:5f00:20d2::400 -V


# ------------------------------------------------------------

# Full script for measurments

# Namespaces to test
NAMESPACES=(tayga-ns jool-app-ns tundra-ns)

# Target addresses (IPv4 and IPv6)
ADDRESSES=(192.0.0.171 2a05:d014:144f:5f00:20d2::400)

# Test durations (in seconds)
declare -A DURATIONS
DURATIONS=( ["30s"]=30 ["1min"]=60 ["2min"]=120 )

# Protocols: test both TCP and UDP
PROTOS=("tcp" "udp")

# Start the tests
for ns in "${NAMESPACES[@]}"; do
  for addr in "${ADDRESSES[@]}"; do
    # If address contains ':', treat as IPv6
    if [[ $addr == *:* ]]; then
      ipver="-6"
      safe_addr=${addr//:/_}
    else
      ipver=""
      safe_addr=$addr
    fi
    for label in "${!DURATIONS[@]}"; do
      duration=${DURATIONS[$label]}
      for proto in "${PROTOS[@]}"; do
        if [[ $proto == "tcp" ]]; then
          cmd="ip netns exec $ns iperf3 $ipver -c $addr -t $duration --json > ${ns}_${safe_addr}_$proto_$label.json"
        else
          # Specify bandwidth for UDP, e.g., 10 Mbps
          cmd="ip netns exec $ns iperf3 $ipver -c $addr -u -b 10M -t $duration --json > ${ns}_${safe_addr}_$proto_$label.json"
        fi
        echo "Running: $cmd"
        eval "$cmd"
      done
    done
  done
done

echo "All tests finished."




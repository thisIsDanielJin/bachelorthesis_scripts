# reset : destroy all artifacts
sudo ip netns del jool-app-ns 2>/dev/null || true
sudo ip link del j-app-host-h 2>/dev/null || true
sudo ip netns del jool-ns 2>/dev/null || true
sudo ip link del j-jool-host-h 2>/dev/null || true
sudo ip link del j-app-jool-j 2>/dev/null || true
sudo ip link del j-app-jool-a 2>/dev/null || true
sudo ip link del j-jool-host-j 2>/dev/null || true
sudo modprobe -r jool_siit || true
#sudo apt-get purge jool-dkms jool-tools || true

# ------------------------------------------------------------


### Step 1 - Create first container (Jool) and connect it with host

# constants
NS_JOOL="jool-ns" 
VETH_JOOL_HOST="j-jool-host-h" # jool to host - host side
VETH_HOST_JOOL="j-jool-host-j" # jool to host - jool side

JOOL_NS_IPV6="2a05:d014:144f:5f00:20d2::300/124" # 300s

JOOL_LINK_LOCAL_HOST="fe80::5"
JOOL_LINK_LOCAL_NS="fe80::6"


# 1.0 clean up
sudo ip netns del "$NS_JOOL" 2>/dev/null || true
sudo ip link del "$VETH_JOOL_HOST" 2>/dev/null || true

# 1.1 create networking namespace and veth cable
sudo ip netns add "$NS_JOOL"
sudo ip link add "$VETH_JOOL_HOST" type veth peer name "$VETH_HOST_JOOL"

# 1.2 move veth cable to namespace
sudo ip link set "$VETH_HOST_JOOL" netns "$NS_JOOL"

# 1.3 bring up interfaces
sudo ip netns exec "$NS_JOOL" ip link set lo up
sudo ip link set "$VETH_JOOL_HOST" up
sudo ip netns exec "$NS_JOOL" ip link set "$VETH_HOST_JOOL" up

# 1.4 assign link-local address to host veth cable
sudo ip addr add "$JOOL_LINK_LOCAL_HOST"/64 dev "$VETH_JOOL_HOST"
sudo ip netns exec "$NS_JOOL" ip addr add "$JOOL_LINK_LOCAL_NS"/64 dev "$VETH_HOST_JOOL"

# 1.5 assign IPv6 to veth cable namespace
sudo ip netns exec "$NS_JOOL" ip addr add "$JOOL_NS_IPV6" dev "$VETH_HOST_JOOL"

# 1.6 set route between link-local and veth cable namespace
sudo ip -6 route add "$JOOL_NS_IPV6" via "$JOOL_LINK_LOCAL_NS" dev "$VETH_JOOL_HOST"

# 1.7 set veth cable as default ipv6 route inside the namespace
sudo ip netns exec "$NS_JOOL" ip -6 route add default via "$JOOL_LINK_LOCAL_HOST" dev "$VETH_HOST_JOOL"

# 1.8 Enable IP forwarding on the host
sudo sysctl -w net.ipv6.conf.all.forwarding=1

# 1.9 Enable IP forwarding on the jool namespace
sudo ip netns exec "$NS_JOOL" sysctl -w net.ipv6.conf.all.forwarding=1

# ------------------------------------------------------------

### Step 2 - Create Jool App Container and assure basic network connectivity

# constants
NS_APP="jool-app-ns" 

JOOL_APP_SIDE_IPV6="2a05:d014:144f:5f00:20d2::301" 
JOOL_SIDE_APP_IPV6="2a05:d014:144f:5f00:20d2::302"

VETH_APP_JOOL="j-app-jool-j" # app to jool - jool side
VETH_JOOL_APP="j-app-jool-a" # app to jool - app side
IPV4_APP="192.0.0.2"
IPV4_JOOL="192.0.0.1"

# 2.0 clean up
sudo ip netns del "$NS_APP" 2>/dev/null || true
sudo ip link del "$VETH_JOOL_APP" 2>/dev/null || true

# 2.1 Create networking namespace and veth cable
sudo ip netns add "$NS_APP"
sudo ip link add "$VETH_APP_JOOL" type veth peer name "$VETH_JOOL_APP"

# 2.2 Move veth cable to namespace
sudo ip link set "$VETH_JOOL_APP" netns "$NS_APP"
sudo ip link set "$VETH_APP_JOOL" netns "$NS_JOOL"

# 2.3 bring up interfaces 
sudo ip netns exec "$NS_APP" ip link set lo up
sudo ip netns exec "$NS_JOOL" ip link set "$VETH_APP_JOOL" up
sudo ip netns exec "$NS_APP" ip link set "$VETH_JOOL_APP" up

# 2.4 assign IPv4 to veth cable namespace
sudo ip netns exec "$NS_APP" ip addr add "$IPV4_APP" peer "$IPV4_JOOL" dev "$VETH_JOOL_APP"
sudo ip netns exec "$NS_JOOL" ip addr add "$IPV4_JOOL" peer "$IPV4_APP" dev "$VETH_APP_JOOL"

# 2.5 assign IPv6 to veth cable namespace
sudo ip netns exec "$NS_APP" ip addr add "$JOOL_APP_SIDE_IPV6"/124 dev "$VETH_JOOL_APP"
sudo ip netns exec "$NS_JOOL" ip addr add "$JOOL_SIDE_APP_IPV6"/124 dev "$VETH_APP_JOOL"

# 2.6 set default route for app namespace
sudo ip netns exec "$NS_APP" ip route add default via "$IPV4_JOOL" dev "$VETH_JOOL_APP"
sudo ip netns exec "$NS_APP" ip -6 route add default via "$JOOL_SIDE_APP_IPV6" dev "$VETH_JOOL_APP"


# ------------------------------------------------------------

### Step 3 - Configure Jool

# constants
NAT64_PREFIX="64:ff9b::/96"

# 3.0 install jool
#sudo apt-get update
#sudo apt install jool-dkms jool-tools

# 3.1 load jool_siit module
sudo ip netns exec "$NS_JOOL" modprobe jool_siit

# 3.2 enable ipv6 forwarding in the jool namespace
sudo ip netns exec "$NS_JOOL" sysctl -w net.ipv6.conf.all.forwarding=1
sudo ip netns exec "$NS_JOOL" sysctl -w net.ipv4.conf.all.forwarding=1

# 3.3 create SIIT instance in namespace 
sudo ip netns exec "$NS_JOOL" jool_siit instance add --netfilter --pool6 "$NAT64_PREFIX"
sudo ip netns exec "$NS_JOOL" jool_siit eamt add "$IPV4_APP" "$JOOL_NS_IPV6"
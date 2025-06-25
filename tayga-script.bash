# reset : destroy all artifacts
sudo ip netns del tayga-ns 2>/dev/null || true
sudo ip link del veth-tayga-host 2>/dev/null || true
sudo pkill tayga || true
sudo rm -f /etc/tayga.conf

# ------------------------------------------------------------

# constants
NS="tayga-ns"
VETH_HOST="veth-tayga-host"
VETH_NS="veth-tayga-ns"

VETH_NS_IPV6="2a05:d014:144f:5f00:20d2::100/124" # 100s

LINK_LOCAL_HOST="fe80::1"
LINK_LOCAL_NS="fe80::2"

### Step 1 - Create Container and assure basic networking 

# 1.0 clean up
sudo ip netns del "$NS" 2>/dev/null || true
sudo ip link del "$VETH_HOST" 2>/dev/null || true

# 1.1 Create networking namespace and veth cable
sudo ip netns add "$NS"
sudo ip link add "$VETH_HOST" type veth peer name "$VETH_NS"

# 1.2 Move veth cable to namespace
sudo ip link set "$VETH_NS" netns "$NS"

# 1.3 bring up interfaces 
sudo ip netns exec "$NS" ip link set lo up
sudo ip link set "$VETH_HOST" up
sudo ip netns exec "$NS" ip link set "$VETH_NS" up

#1.4 assign link-local address to host veth cable
sudo ip addr add "$LINK_LOCAL_HOST"/64 dev "$VETH_HOST"
sudo ip netns exec "$NS" ip addr add "$LINK_LOCAL_NS"/64 dev "$VETH_NS"

# 1.5 assign IPv6 addresses to veth cables
sudo ip netns exec "$NS" ip addr add "$VETH_NS_IPV6" dev "$VETH_NS"

# 1.6 set route between link-local and veth cable namespace
sudo ip -6 route add "$VETH_NS_IPV6" via "$LINK_LOCAL_NS" dev "$VETH_HOST"

# 1.7 Enable IP forwarding on the host
sudo sysctl -w net.ipv6.conf.all.forwarding=1

# 1.8 set veth cable as default ipv6 route inside the namespace
sudo ip netns exec "$NS" ip -6 route add default via "$LINK_LOCAL_HOST" dev "$VETH_NS"


# ------------------------------------------------------------


### Step 2 - Configure Tayga

# constants
TAYGA_CONF="/etc/tayga.conf"
TAYGA_DYNAMIC_POOL="192.168.0.0/24"   # "192.0.1.0/24" ,private ipv4 range (docs)
CLAT_IPV6="2a05:d014:144f:5f00:20d2::101"
CLAT_IPV4="192.0.0.2"
TAYGA_IPV4="192.0.0.1"   #"192.0.2.10"
TAYGA_IPV6="2a05:d014:144f:5f00:20d2::102"


# 2.1 install tayga
sudo apt-get update
sudo apt-get install tayga

# 2.2 write tayga configuration file
sudo tee "$TAYGA_CONF" > /dev/null <<EOF
tun-device nat64 #change to clat
ipv4-addr $TAYGA_IPV4
prefix 64:ff9b::/96
ipv6-addr $TAYGA_IPV6
data-dir /var/db/tayga
map $CLAT_IPV4 $CLAT_IPV6
EOF

# 2.3 create the TUN device (nat64) inside the namespace
sudo ip netns exec "$NS" tayga --mktun

# 2.4 bring up NAT64 device
sudo ip netns exec "$NS" ip link set nat64 up

# 2.5 assign IP addresses to the nat64 device inside the namespace
sudo ip netns exec "$NS" ip addr add $CLAT_IPV4/32 dev nat64

# 2.6 add route to the nat64 device (for ipv6 traffic)
sudo ip netns exec "$NS" ip -6 route add "$CLAT_IPV6" dev nat64

# 2.7 add default ipv4 route to the namespace (for ipv4 traffic)
sudo ip netns exec "$NS" ip route add default via "$CLAT_IPV4" dev nat64

# 2.8 enable ipv6 forwarding inside the namespace
sudo ip netns exec "$NS" sysctl -w net.ipv6.conf.all.forwarding=1

# 2.9 start tayga inside the namespace
sudo ip netns exec "$NS" tayga 
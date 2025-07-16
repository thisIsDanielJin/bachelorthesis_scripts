# reset : destroy all artifacts
sudo ip netns del tundra-ns 2>/dev/null || true
sudo ip link del veth-tundra-host 2>/dev/null || true
sudo pkill tundra || true
sudo rm -f /etc/tundra.conf

# ------------------------------------------------------------

# constants
NS_TUNDRA="tundra-ns"
VETH_TUNDRA_HOST="veth-tundra-h"
VETH_TUNDRA_NS="veth-tundra-ns"

VETH_TUNDRA_NS_IPV6="2a05:d014:144f:5f00:20d2::200/124" # 200s

LINK_LOCAL_HOST="fe80::7"
LINK_LOCAL_NS="fe80::8"

### Step 1 - Create Container and assure basic networking 

# 1.0 clean up
sudo ip netns del "$NS_TUNDRA" 2>/dev/null || true
sudo ip link del "$VETH_TUNDRA_HOST" 2>/dev/null || true

# 1.1 Create networking namespace and veth cable
sudo ip netns add "$NS_TUNDRA"
sudo ip link add "$VETH_TUNDRA_HOST" type veth peer name "$VETH_TUNDRA_NS"

# 1.2 Move veth cable to namespace
sudo ip link set "$VETH_TUNDRA_NS" netns "$NS_TUNDRA"

# 1.3 bring up interfaces 
sudo ip netns exec "$NS_TUNDRA" ip link set lo up
sudo ip link set "$VETH_TUNDRA_HOST" up
sudo ip netns exec "$NS_TUNDRA" ip link set "$VETH_TUNDRA_NS" up

#1.4 assign link-local address to host veth cable
sudo ip addr add "$LINK_LOCAL_HOST"/64 dev "$VETH_TUNDRA_HOST"
sudo ip netns exec "$NS_TUNDRA" ip addr add "$LINK_LOCAL_NS"/64 dev "$VETH_TUNDRA_NS"

# 1.5 assign IPv6 addresses to veth cables
sudo ip netns exec "$NS_TUNDRA" ip addr add "$VETH_TUNDRA_NS_IPV6" dev "$VETH_TUNDRA_NS"

# 1.6 set route between link-local and veth cable namespace
sudo ip -6 route add "$VETH_TUNDRA_NS_IPV6" via "$LINK_LOCAL_NS" dev "$VETH_TUNDRA_HOST"

# 1.7 Enable IP forwarding on the host
sudo sysctl -w net.ipv6.conf.all.forwarding=1

# 1.8 set veth cable as default ipv6 route inside the namespace
sudo ip netns exec "$NS_TUNDRA" ip -6 route add default via "$LINK_LOCAL_HOST" dev "$VETH_TUNDRA_NS"


# ------------------------------------------------------------


### Step 2 - Setup Tundra

# constants
TUNDRA_CONF="/etc/tundra-clat.conf"
CLAT_IPV4="192.0.0.2"
CLAT_IPV6="2a05:d014:144f:5f00:20d2::201"
ROUTER_IPV4="192.0.0.1"
ROUTER_IPV6="2a05:d014:144f:5f00:20d2::202"
TUN_INTERFACE="clat"


# 2.0 build tundra
# 2.0.1 clone the repository
#git clone https://github.com/vitlabuda/tundra-nat64.git
cd /home/ubuntu/tundra-nat64
# 2.0.2 build the project
sudo apt install cmake
CC=gcc cmake -S. -Bbuild
make -Cbuild
cd /home/ubuntu/

# 2.1 write tundra configuration file
sudo tee "$TUNDRA_CONF" > /dev/null <<EOF
program.translator_threads = 4
program.privilege_drop_user = 
program.privilege_drop_group = 

io.mode = tun
io.tun.device_path = /dev/net/tun
io.tun.interface_name = $TUN_INTERFACE
io.tun.owner_user = 
io.tun.owner_group = 
io.tun.multi_queue = no

router.ipv4 = $ROUTER_IPV4
router.ipv6 = $ROUTER_IPV6
router.generated_packet_ttl = 224

addressing.mode = clat
addressing.nat64_clat.ipv4 = $CLAT_IPV4
addressing.nat64_clat.ipv6 = $CLAT_IPV6
addressing.nat64_clat_siit.prefix = 64:ff9b::
addressing.nat64_clat_siit.allow_translation_of_private_ips = yes

translator.ipv4.outbound_mtu = 1500
translator.ipv6.outbound_mtu = 1500

translator.6to4.copy_dscp_and_ecn = yes
translator.4to6.copy_dscp_and_ecn = yes
EOF

# 2.2 create the TUNDRA device (nat64) inside the namespace
sudo ip netns exec "$NS_TUNDRA" /home/ubuntu/tundra-nat64/build/tundra-nat64 --config-file="$TUNDRA_CONF" mktun

# 2.3 bring up CLAT device 
sudo ip netns exec "$NS_TUNDRA" ip link set "$TUN_INTERFACE" up

# 2.4 assign ip address to the clat device inside the namespace
sudo ip netns exec "$NS_TUNDRA" ip addr add "$CLAT_IPV4"/32 dev "$TUN_INTERFACE"

# 2.5 add route to the CLAT device (for ipv6 traffic)
sudo ip netns exec "$NS_TUNDRA" ip -6 route add "$CLAT_IPV6" dev "$TUN_INTERFACE"

# 2.6 add route to the CLAT device (for ipv4 traffic)
sudo ip netns exec "$NS_TUNDRA" ip route add default via "$CLAT_IPV4" dev "$TUN_INTERFACE"

# 2.7 add default ipv4 route to the namespace (for ipv4 traffic)
sudo ip netns exec "$NS_TUNDRA" ip route add default via "$CLAT_IPV4" dev "$TUN_INTERFACE"

# 2.8 enable ipv6 forwarding inside the namespace
sudo ip netns exec "$NS_TUNDRA" sysctl -w net.ipv6.conf.all.forwarding=1

# 2.9 start tundra
TUNDRA_CONF="/etc/tundra-clat.conf"
NS_TUNDRA="tundra-ns"

sudo ip netns exec "$NS_TUNDRA" /home/ubuntu/tundra-nat64/build/tundra-nat64 --config-file="$TUNDRA_CONF"

echo "--------------------------------"
echo "tundra-ns setup complete!"
echo "--------------------------------"
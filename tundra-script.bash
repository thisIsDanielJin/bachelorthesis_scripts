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

# 2.0 enable ipv6 forwarding in the namespace
sudo ip netns exec "$NS_TUNDRA" sysctl -w net.ipv6.conf.all.forwarding=1

# 2.1 clone the repository
git clone https://github.com/vitlabuda/tundra-nat64.git
cd tundra-nat64

# 2.2 build the project
sudo apt install cmake
CC=gcc cmake -S. -Bbuild
make -Cbuild

# 2.3 install the project
sudo cmake --install build

# 2.4 copy executable to /usr/local/sbin
sudo cp build/tundra-nat64 /usr/local/sbin/

# 2.4.1 set the right ownership 
sudo chown root:root /usr/local/sbin/tundra-nat64
sudo chmod 755 /usr/local/sbin/tundra-nat64

# 2.5.1 create the configuration directory
sudo mkdir -p /usr/local/etc/tundra-clat
cd ..
# 2.5.2 copy tundra configuration file 
sudo cp tundra-nat64/config_examples/debian_clat/tundra-clat.conf /usr/local/etc/tundra-clat/

# 2.5.3 copy the startup and stop script
sudo cp tundra-nat64/config_examples/debian_clat/start-tundra.sh  /usr/local/etc/tundra-clat/
sudo cp tundra-nat64/config_examples/debian_clat/stop-tundra.sh  /usr/local/etc/tundra-clat/

# 2.5.4 copy the systemd service file
sudo cp tundra-nat64/config_examples/debian_clat/tundra-clat.service /etc/systemd/system/

# 2.5.5 reload the systemd daemon
sudo systemctl daemon-reload

# 2.5.6 start the service
sudo systemctl start tundra-clat





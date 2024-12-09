from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel

class DataCenterTopo(Topo):
    def build(self):
        # Core Switch
        core = self.addSwitch('s1')

        # Aggregation switches
        agg1 = self.addSwitch('s2')
        agg2 = self.addSwitch('s3')

        # Access switches
        acc1 = self.addSwitch('s4')
        acc2 = self.addSwitch('s5')
        acc3 = self.addSwitch('s6')
        acc4 = self.addSwitch('s7')

        # Hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')
        h5 = self.addHost('h5')
        h6 = self.addHost('h6')
        h7 = self.addHost('h7')
        h8 = self.addHost('h8')

        # Links
        self.addLink(core, agg1)
        self.addLink(core, agg2)

        self.addLink(agg1, acc1)
        self.addLink(agg1, acc2)
        self.addLink(agg2, acc3)
        self.addLink(agg2, acc4)

        self.addLink(acc1, h1)
        self.addLink(acc1, h2)
        self.addLink(acc2, h3)
        self.addLink(acc2, h4)
        self.addLink(acc3, h5)
        self.addLink(acc3, h6)
        self.addLink(acc4, h7)
        self.addLink(acc4, h8)

if __name__ == '__main__':
    setLogLevel('info')
    topo = DataCenterTopo()
    controller = RemoteController('c1', ip='127.0.0.1', port=6633)
    net = Mininet(topo=topo, controller=controller, switch=OVSSwitch)
    net.start()
    CLI(net)
    net.stop()
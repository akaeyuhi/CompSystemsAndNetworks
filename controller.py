from datetime import datetime
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types


class ChannelControllerSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ChannelControllerSwitch, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.meter_id_counter = {}  # Track meter IDs per datapath (switch)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Initialize meter ID counter for this switch
        self.meter_id_counter.setdefault(datapath.id, 0)

        # Install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        # Configure meters dynamically based on time
        self.configure_meters(datapath)

    def get_next_meter_id(self, datapath_id):
        # Get the next available meter ID for a given datapath.
        self.meter_id_counter[datapath_id] += 1
        return self.meter_id_counter[datapath_id]

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    def configure_meters(self, datapath):
        """Set bandwidth limits dynamically based on day and time."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Time-based bandwidth policies
        now = datetime.now()
        day = now.strftime('%A')  # Get current day name
        hour = now.hour  # Get current hour

        # Example bandwidth settings (in kbps):
        if day in ['Saturday', 'Sunday']:
            if hour < 12:
                max_rate = 500  # Morning on weekends: 500 kbps
            else:
                max_rate = 1000  # Afternoon/Evening on weekends: 1000 kbps
        else:
            if hour < 9 or hour >= 18:
                max_rate = 1000  # Off-peak hours: 1000 kbps
            else:
                max_rate = 300  # Work hours: 300 kbps

        self.logger.info(f"Configuring meter with max rate: {max_rate} kbps")

        # Generate a unique meter ID
        meter_id = self.get_next_meter_id(datapath.id)

        # Add a meter to enforce bandwidth
        bands = [
            parser.OFPMeterBandDrop(rate=max_rate, burst_size=max_rate // 10)  # Drop excess traffic
        ]

        meter_mod = parser.OFPMeterMod(
            datapath=datapath,
            command=ofproto.OFPMC_ADD,
            flags=ofproto.OFPMF_KBPS,  # Rate in kilobits per second
            meter_id=meter_id,
            bands=bands,
        )

        try:
            datapath.send_msg(meter_mod)
            self.logger.info(f"Meter {meter_id} successfully configured.")
        except Exception as e:
            self.logger.error(f"Error adding meter {meter_id}: {e}")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                            ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # Ignore LLDP packets
            return
        dst = eth.dst
        src = eth.src

        dpid = format(datapath.id, "d").zfill(16)
        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        # Learn MAC address to avoid flooding next time
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Get a dynamically assigned meter ID
        if datapath.id in self.meter_id_counter.keys(): 
            meter_id = self.meter_id_counter[datapath.id]
        else: 
            meter_id = self.get_next_meter_id(datapath.id)  # Dynamically assign ID
            self.logger.info(f"Applying Meter ID: {meter_id} for datapath {dpid}")

        # Instructions with the dynamic meter ID
        instructions = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions),
            parser.OFPInstructionMeter(meter_id, ofproto.OFPIT_METER)
        ]

        # Install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            mod = parser.OFPFlowMod(datapath=datapath, priority=1, match=match,
                                    instructions=instructions)
            datapath.send_msg(mod)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

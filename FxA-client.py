import Queue
import hashlib
import random
import re
import socket
import struct
import sys
import threading


# TODO: Pack Header '!LLHLBLH'


def main(argv):
    global client_port
    global net_emu_ip_address
    global net_emu_port
    global net_emu_addr
    global client_window_size
    global client_state
    global client_seq_num
    global is_debug

    if len(argv) < 3 or len(argv) > 4:
        print("Correct usage: FxA-Client X A P [-debug]")
        sys.exit(1)

    client_port = argv[0]
    net_emu_ip_address = argv[1]
    net_emu_port = argv[2]
    is_debug_arg = ''
    if len(argv) == 4:
        is_debug_arg = argv[3]
    is_connected = False
    command_input = ''

    # Check that entered client port is an integer
    try:
        client_port = int(client_port)
    except ValueError:
        print('Invalid client port number %s' % argv[0])
        sys.exit(1)

    # Check that client port is odd so that NetEmu can tell the difference between client and server
    if client_port % 2 == 1:
        print('Client port number: %d was not even number' % client_port)
        sys.exit(1)

    # Check that entered NetEmu IP address is in correct format
    try:
        socket.inet_aton(net_emu_ip_address)
        p = re.compile('(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)')
        if not p.match(net_emu_ip_address):
            raise socket.error()
    except socket.error:
        print("Invalid IP notation: %s" % argv[1])
        sys.exit(1)
        # TODO check if port is open!

    # Check that entered NetEmu port is an integer
    try:
        net_emu_port = int(net_emu_port)
    except ValueError:
        print('Invalid NetEmu port number: %s' % argv[2])
        sys.exit(1)

    if len(argv) == 4:
        if is_debug_arg.lower() == '-debug':
            is_debug = True
            print('Debug mode activated')
        else:
            print('Could not parse argument: %s' % argv[3])
            sys.exit(1)

    # Create address for sending to NetEmu
    net_emu_addr = net_emu_ip_address, net_emu_port

    # Setup for Client Command Instructions
    print('Command Options:')
    print('connect\t\t|\tConnects to the FxA-server')
    print('get F\t\t|\tRetrieve file F from FxA-server')
    print('post F\t\t|\tPushes file F to the FxA-server')
    print("window W\t|\tSets the maximum receiver's window size")
    print("disconnect\t|\tDisconnect from the FxA-server\n")

    while command_input != 'disconnect':
        command_input = raw_input('Please enter command:')
        if command_input == 'connect':
            if not is_connected:
                is_connected = connect()
            else:
                print ("Client already connected to server")
        elif command_input == 'disconnect':
            # TODO disconnect() call
            break
        else:
            command_input_split = command_input.split(" ")
            if command_input_split[0] == 'get':
                if len(command_input_split) != 2:
                    print("Invalid command: get requires secondary parameter")
                    continue
                if is_connected:
                    # TODO get()
                    print('get')
                else:
                    print('get not valid without existing connection')
            elif command_input_split[0] == 'post':
                if len(command_input_split) != 2:
                    print("Invalid command: post requires secondary parameter")
                    continue
                if is_connected:
                    # TODO post()
                    print('post')
                else:
                    print('post not valid without existing connection')
            elif command_input_split[0] == 'window':
                if len(command_input_split) != 2:
                    print("Invalid command: window requires secondary parameter")
                    continue
                try:
                    window_size = int(command_input_split[1])
                except ValueError:
                    print('Invalid window size (not a number): %s' % command_input_split[1])
                    continue
                # TODO window()
                print('window')
            else:
                print("Command not recognized")


def connect():
    global client_state
    global server_window_size
    global client_port
    global server_seq_num
    global server_port

    if client_state == State.CLOSED:
        try:
            sock.bind(('', client_port))
        except socket.error, msg:
            print 'Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1]
            sys.exit()
    if client_state == State.CLOSED or client_state == State.SYN_SENT:
        # Send request to connect or if packet was corrupted, dropped, or etc; send again
        client_state = State.SYN_SENT
        send(client_seq_num, client_ack_num, 0, 1, 0, 0, '')
    if client_state == State.SYN_SENT:
        # Receive syn + ack + challenge back from server
        rtp_header, payload = recv()
        server_seq_num, server_ack_num, checksum, server_window_size, ack, syn, fin, nack, server_ip_address_long, \
            server_port = unpack_rtpheader(rtp_header)
        print ack, syn, fin, nack
        # Check checksum; if bad, drop packet and send nack
        if not check_checksum(checksum, rtp_header + payload):
            print "check sum bad"
            send(0, client_ack_num, 0, 0, 0, 1, None)
            return False
        # Checksum is good; send hash of hash to complete challenge
        else:
            client_state = State.SYN_SENT_HASH
            hashofhash = create_hash(payload)
            print "syn + ack + hash"
            send(client_seq_num, client_ack_num, 1, 1, 0, 0, hashofhash)
    if client_state == State.SYN_SENT_HASH:
        # Receive ack from hash challenge from server
        rtp_header, payload = recv()
        server_seq_num, server_ack_num, checksum, server_window_size, ack, syn, fin, nack, server_ip_address_long, \
            server_port = unpack_rtpheader(rtp_header)

        # Check checksum; if bad, drop packet and send nack
        if not check_checksum(checksum, rtp_header + payload):
            send(0, client_ack_num, 0, 0, 0, 1, None)
            return False
        # Checksum is good; done
        elif ack:
            print "ack"
            return True
        else:
            return False

    return False


    # Receive syn + ack + challenge
    ack_num, checksum, client_window_size, ack, syn, fin, nack, client_ip_address_long, client_port = recv()
    num_timeouts = 0
    timer = threading.Timer(10, connect_timeout)

    return True




def send(seq_num, ack_num, ack, syn, fin, nack, payload):

    checksum = 0
    rtp_header = pack_rtpheader(seq_num, ack_num, checksum, ack, syn, fin, nack)
    if payload is not None:
        packet = rtp_header + payload
    else:
        packet = rtp_header
    checksum = sum(bytearray(packet))
    print checksum
    #checksum_byte = struct.pack('!L', checksum)
    #checksum_increment = sum(bytearray(checksum_byte))
    #print checksum_increment
    #checksum += checksum_increment
    #print checksum
    #print
    rtp_header = pack_rtpheader(seq_num, ack_num, checksum, ack, syn, fin, nack)

    if payload is not None:
        packet = rtp_header + payload
    else:
        packet = rtp_header
    print len(packet)
    #print sum(bytearray(packet))
    sock.sendto(packet, net_emu_addr)

def recv():
    global server_seq_num
    global client_window_size

    recv_packet = sock.recvfrom(buff_size)
    packet = recv_packet[0]
    rtp_header = packet[0:21]
    payload = packet[21:]
    #print payload


    return rtp_header, payload

    #ip_address_old = struct.pack("!L", ip_address_long)



def pack_rtpheader(seq_num, ack_num, checksum, ack, syn, fin, nack):

    flags = pack_bits(ack, syn, fin, nack)
    rtp_header = struct.pack('!LLHLBLH', seq_num, ack_num, checksum, client_window_size, flags, CLIENT_IP_ADDRESS_LONG,
                             client_port)

    return rtp_header


def unpack_rtpheader(rtp_header):
    global server_window_size
    global server_seq_num

    rtp_header = struct.unpack('!LLHLBLH', rtp_header) # 21 bytes

    server_seq_num = rtp_header[0]
    server_ack_num = rtp_header[1]
    checksum = rtp_header[2]
    server_window_size = rtp_header[3]
    flags = rtp_header[4]
    ack, syn, fin, nack = unpack_bits(flags)
    server_ip_address_long = rtp_header[5]
    server_port = rtp_header[6]

    return server_seq_num, server_ack_num, checksum, server_window_size, ack, syn, fin, nack, server_ip_address_long, \
           server_port


def pack_bits(ack, syn, fin, nack):

    bit_string = str(ack) + str(syn) + str(fin) + str(nack)
    bit_string = '0000' + bit_string  # If you augment, it won't be correct, unless we want to put the flags in higher
    bit_string = int(bit_string, 2)

    return bit_string

def unpack_bits(bit_string):

    bit_string = format(bit_string, '08b')
    ack = int(bit_string[4])
    syn = int(bit_string[5])
    fin = int(bit_string[6])
    nack = int(bit_string[7])

    return ack, syn, fin, nack

def check_checksum(checksum, data):

    packed_checksum = struct.pack('!L',checksum)
    new_checksum = sum(bytearray(data))
    new_checksum -= sum(bytearray(packed_checksum))

    if checksum == new_checksum:
        return True
    else:
        return False

def connect_timeout(args):
    pass

def create_hash(hash_challenge):
    hashofhash = hashlib.sha224(hash_challenge).hexdigest()

    return hashofhash




class State:
    SYN_SENT = 1
    SYN_RECEIVED = 2
    SYN_SENT_HASH = 3
    ESTABLISHED = 4
    FIN_WAIT_1 = 5
    FIN_WAIT_2 = 6
    CLOSE_WAIT = 7
    CLOSING = 8
    LAST_ACK = 9
    TIME_WAIT = 10
    CLOSED = 11

    def __init__(self):
        pass


if __name__ == "__main__":

    client_window_size = 1
    buff_size = 1024
    client_port = ''
    CLIENT_IP_ADDRESS = socket.gethostbyname(socket.gethostname())
    CLIENT_IP_ADDRESS_LONG = struct.unpack("!L", socket.inet_aton(CLIENT_IP_ADDRESS))[0]
    net_emu_ip_address = ''
    net_emu_ip_address_long = ''
    net_emu_port = ''
    net_emu_addr = ''
    client_state = State.CLOSED
    client_seq_num = random.randint(0, 2**32-1)
    client_ack_num = client_seq_num
    server_seq_num = 0
    server_window_size = 1
    process_queue = Queue.Queue(maxsize=15000)
    is_debug = False

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except socket.error:
        print 'Failed to create socket'
        sys.exit()

    main(sys.argv[1:])

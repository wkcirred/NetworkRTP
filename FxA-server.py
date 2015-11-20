import Queue
import hashlib
import random
import re
import socket
import struct
import sys
import threading


# GET|FILENAME - CLIENT
# ACK - SERVER
# DATA - SERVER
# ACK - CLIENT
# ...
# ACK - CLIENT (PEACEFUL CLOSE)

# POST\FILENAME|FILESIZE(BYTES) - CLIENT
# ACK - SERVER
# DATA - CLIENT
# ACK - SERVER
# DATA - CLIENT
# ...
# ACK -SERVER


def main(argv):
    global server_port
    global net_emu_ip_address
    global net_emu_port
    global net_emu_addr
    global server_window_size
    global is_debug

    if len(argv) < 3 or len(argv) > 4:
        print("Correct usage: FxA-Server X A P [-debug]")
        sys.exit(1)

    # Save user input
    server_port = argv[0]
    net_emu_ip_address = argv[1]
    net_emu_port = argv[2]
    is_debug_arg = ''
    if len(argv) == 4:
        is_debug_arg = argv[3]

    # Check Port is an int
    try:
        server_port = int(server_port)
    except ValueError:
        print('Invalid server port number %s' % argv[0])
        sys.exit(1)

    # Check server port is even for correct interaction with NetEmu
    if server_port % 2 == 0:
        print('Server port number: %d was not an odd number' % server_port)
        sys.exit(1)

    # Check IP address is in correct notation
    try:
        socket.inet_aton(net_emu_ip_address)
        p = re.compile('(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)')
        if not p.match(net_emu_ip_address):
            raise socket.error()
    except socket.error:
        print("Invalid IP notation: %s" % argv[1])
        sys.exit(1)
        # TODO check if port is open!

    # Check port number is an int
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

    # Bind to server port
    try:
        sock.bind(('', server_port))
    except socket.error, msg:
        print 'Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1]
        sys.exit(1)


    # start packet collection and start processing queue
    try:
        t_recv = threading.Thread(target=recv_packet, args=())
        t_recv.daemon = True
        t_recv.start()
        t_proc = threading.Thread(target=proc_packet, args=())
        t_proc.daemon = True
        t_proc.start()
    except:
        print "Error"

    # Setup for Server Command Instructions
    print('Command Options:')
    print("window W\t|\tSets the maximum receiver's window size")
    print("terminate\t|\tShut-down FxA-Server gracefully\n")

    # Loop for commands from server user
    while True:
        command_input = str(raw_input('Please enter command:'))
        if command_input == 'terminate':
            # TODO terminate() call
            break
        else:
            parsed_command_input = command_input.split(" ")
            if parsed_command_input[0] == 'window':
                if len(parsed_command_input) != 2:
                    print("Invalid command: window requires secondary parameter")
                    continue
                try:
                    server_window_size = int(parsed_command_input[1])
                except ValueError:
                    print('Invalid window size (not a number): %s' % parsed_command_input[1])
                    continue
                # TODO window()
                print('window')
            else:
                print("Command not recognized")

    # Closing server and socket
    print("Server closing")
    sock.close()


def recv_packet():
    while True:
        try:
            packet = sock.recvfrom(BUFFER_SIZE)
            process_queue.put(packet)
        except socket.error, msg:
            continue


def proc_packet():
    while True:
        while not process_queue.empty():
            if is_debug:
                print 'Processing Received Data'
            recv_packet = process_queue.get()
            packet = recv_packet[0]
            rtp_header = packet[0:21]
            payload = packet[21:]

            # Unpack header
            client_seq_num, client_ack_num, checksum, client_window_size, ack, syn, fin, nack, client_ip_address_long, \
                client_port = unpack_rtpheader(rtp_header)

            # Check to see if client exists or needs to setup
            client_loc = check_client_list(client_ip_address_long, client_port)

            # Check checksum; if bad, drop packet and send nack; if good, proceed
            if not check_checksum(checksum, packet):
                if is_debug:
                    print 'Checksum Incorrect, sending NACK'
                send_nack()
                break # Don't allow to go further

            # Checksum is good; let's roll to client
            if is_debug:
                print 'Checksum Correct'
                print 'Received Payload:'
                print str(payload)


            # Special case where we nack a bad packet off the beginning
            if nack and client_loc is None:
                send_nack()


            # Client doesn't exist yet
            elif client_loc is None:
                client = Connection(client_ip_address_long, client_port, client_seq_num, client_ack_num)
                clientList.append(client)
                client.set_last_flags(ack, syn, fin, nack)
                client.update_on_receive()

            # Client exists
            elif client_loc is not None:
                # Receiving response to challenge
                if syn and ack:
                    clientList[client_loc].set_last_flags(ack, syn, fin, nack)
                    clientList[client_loc].set_hash_from_client(payload)
                    clientList[client_loc].update_on_receive()
                elif nack:
                    clientList[client_loc].update_on_receive()

            # Client is setup and ready to process command or files
            #else:
                # # Check client list for existing connection and then start get or post
                # if not syn and not ack and not fin:
                #     client = check_client_list(client_ip_address_long, client_port)
                #pass
                    # TODO - Look inside packet for command


def send(seq_num, ack_num, ack, syn, fin, nack, payload):

    checksum = 0
    rtp_header = pack_rtpheader(seq_num, ack_num, checksum, ack, syn, fin, nack)
    if payload is not None:
        packet = rtp_header + payload
    else:
        packet = rtp_header
    checksum = sum(bytearray(packet))
    rtp_header = pack_rtpheader(seq_num, ack_num, checksum, ack, syn, fin, nack)
    if payload is not None:
        packet = rtp_header + payload
    else:
        packet = rtp_header

    if is_debug:
        print "Sending:"
        print '\tServer Seq Num:\t' + str(seq_num)
        print '\tServer ACK Num:\t' + str(ack_num)
        print '\tChecksum:\t' + str(checksum)
        print '\tWindow:\t\t' + str(server_window_size)
        print '\tACK:\t\t' + str(ack)
        print '\tSYN:\t\t' + str(syn)
        print '\tFIN:\t\t' + str(fin)
        print '\tNACK:\t\t' + str(nack)
        print '\tServer IP Long:\t' + str(SERVER_IP_ADDRESS_LONG)
        print '\tServer Port:\t' + str(server_port)
        print '\tPayload:\t' + str(payload)

    sock.sendto(packet, net_emu_addr)


def pack_rtpheader(seq_num, ack_num, checksum, ack, syn, fin, nack):

    flags = pack_bits(ack, syn, fin, nack)
    rtp_header = struct.pack('!LLHLBLH', seq_num, ack_num, checksum, server_window_size, flags, SERVER_IP_ADDRESS_LONG,
                             server_port)

    return rtp_header


def check_checksum(checksum, data):

    packed_checksum = struct.pack('!L', checksum)
    new_checksum = sum(bytearray(data))
    new_checksum -= sum(bytearray(packed_checksum))

    if checksum == new_checksum:
        return True
    else:
        return False


def unpack_rtpheader(rtp_header):
    rtp_header = struct.unpack('!LLHLBLH', rtp_header)  # 21 bytes

    client_seq_num = rtp_header[0]
    client_ack_num = rtp_header[1]
    checksum = rtp_header[2]
    client_window_size = rtp_header[3]
    flags = rtp_header[4]
    ack, syn, fin, nack = unpack_bits(flags)
    client_ip_address_long = rtp_header[5]
    client_port = rtp_header[6]

    if is_debug:
        print "Unpacking Header:"
        print '\tClient Seq Num:\t' + str(client_seq_num)
        print '\tClient ACK Num:\t' + str(client_ack_num)
        print '\tChecksum:\t' + str(checksum)
        print '\tClient Window:\t' + str(client_window_size)
        print '\tACK:\t\t' + str(ack)
        print '\tSYN:\t\t' + str(syn)
        print '\tFIN:\t\t' + str(fin)
        print '\tNACK:\t\t' + str(nack)
        print '\tClient IP Long:\t' + str(client_ip_address_long)
        print '\tClient Port:\t' + str(server_port)

    return client_seq_num, client_ack_num, checksum, client_window_size, ack, syn, fin, nack, client_ip_address_long,\
        client_port


def pack_bits(ack, syn, fin, nack):

    bit_string = str(ack) + str(syn) + str(fin) + str(nack)
    bit_string = '0000' + bit_string
    bit_string = int(bit_string, 2)

    return bit_string


def unpack_bits(bit_string):

    bit_string = format(bit_string, '08b')
    ack = int(bit_string[4])
    syn = int(bit_string[5])
    fin = int(bit_string[6])
    nack = int(bit_string[7])

    return ack, syn, fin, nack


def check_client_list(client_ip_address, client_port):
    for i in range(len(clientList)):
        if clientList[i].get_sender_ip() == client_ip_address and clientList[i].get_sender_port() == client_port:
            if is_debug:
                print 'Client found in connection list'
            return i
    if is_debug:
        print 'Client not found in connection list'
    return None


def create_hash_int(random_int):
    random_string = str(random_int)
    hash_value = hashlib.sha224(random_string).hexdigest()

    return hash_value


def create_hash(hash_challenge):
    hash_of_hash = hashlib.sha224(hash_challenge).hexdigest()
    return hash_of_hash


def send_synack(payload):

    send(server_seq_num, server_ack_num, 1, 1, 0, 0, payload)


def send_nack():
    send(server_seq_num, server_ack_num, 0, 0, 0, 1, SERVER_EMPTY_PAYLOAD)


def send_ack():
    send(server_seq_num, server_ack_num, 1, 0, 0, 0, SERVER_EMPTY_PAYLOAD)


class Connection:

    def __init__(self, client_ip, client_port, seq_num, ack_num):
        self.state = State.LISTEN
        self.client_ip = client_ip
        self.client_port = client_port
        #self.timer = threading.Timer(10, dummy())
        #self.timer.start()
        self.hash = create_hash_int(random.randint(0, 2**64-1))
        self.hash_of_hash = create_hash(self.hash)
        self.seq_num = 0
        self.ack_num = ack_num
        self.window_size = 1
        self.last_ack = 0
        self.last_syn = 0
        self.last_fin = 0
        self.last_nack = 0
        self.hash_from_client = ''
        self.payload = ''

    def get_sender_ip(self):
        return self.client_ip

    def get_sender_port(self):
        return self.client_port

    def get_hash(self):
        return self.hash

    def get_hash_of_hash(self):
        return self.hash_of_hash

    def get_seq_num(self):
        return self.seq_num

    def get_ack_num(self):
        return self.ack_num

    def get_window_size(self):
        return self.get_window_size()

    # def restart_timer(self):
    #     self.timer = threading.Timer(10, timeout)
    #     self.timer.start()

    def get_client_state(self):
        return self.state

    def get_client_setup(self):
        # if client is not in either of these states; client is setup
        if self.state != State.SYN_RECEIVED and self.state != State.SYN_SENT_HASH and self.state != State.ESTABLISHED:
            return True
        return False

    def set_last_flags(self, ack, syn, fin, nack):
        self.last_ack = ack
        self.last_syn = syn
        self.last_fin = fin
        self.last_nack = nack

    def calc_seq_ack_nums(self):

        self.seq_num = self.ack_num

        if len(payload) == 0:
            client_ack_num = client_seq_num + 1
        else:
            client_ack_num = client_seq_num + len(payload)


    # def increase_seq_num(self, amount):
    #     self.seq_num += amount

    # def timeout(self):
    #     if self.state == State.SYN_RECEIVED:
    #         self.state = State.LISTEN
    #         self.update_on_receive()

    def get_last_ack(self):
        return self.last_ack

    def get_last_syn(self):
        return self.last_syn

    def get_last_fin(self):
        return self.last_fin

    def get_last_nack(self):
        return self.last_nack

    def set_hash_from_client(self, hash):
        self.hash_from_client = hash

    def update_on_receive(self):
        #self.timer.cancel()

        print self.state
        print self.last_ack, self.last_syn, self.last_fin, self.last_nack

        if self.state == State.ESTABLISHED:
            if self.last_syn and self.last_ack:
                self.state = State.SYN_RECEIVED
            else:
                print "&"*25

        elif self.state == State.SYN_RECEIVED:
            if self.last_syn and not self.last_ack:
                self.state = State.LISTEN
            elif self.last_syn and self.last_ack:
                # Hashes match; complete 4-way handshake
                if self.hash_from_client == self.hash_of_hash:
                    self.state = State.ESTABLISHED
                    send_ack()
                # Hashes don't match; send nack
                else:
                    send_nack()

        elif self.state == State.LISTEN:
            print "***********"
            if self.last_syn and not self.last_ack:
                self.state = State.SYN_RECEIVED
                send_synack(self.get_hash())




        # TODO 3 MINUTES






        #elif self.state == State.ESTABLISHED:
        #    if nack:
        #         pass
        #    if not syn and not ack and fin:
        #         self.state = State.CLOSE_WAIT
        #         ack()
        # elif self.state == State.LAST_ACK:
        #     if not syn and ack and not fin:
        #         self.state = State.CLOSED
        # elif self.state == State.FIN_WAIT_1:
        #     if not syn and not ack and fin:
        #         ack()
        #         self.state = State.CLOSING
        #     if not syn and ack and not fin:
        #         self.state = State.FIN_WAIT_2
        #     if not syn and ack and fin:
        #         ack()
        #         self.state = State.TIME_WAIT
        # elif self.state == State.FIN_WAIT_2:
        #     if not syn and not ack and fin:
        #         ack()
        #         self.state = State.TIME_WAIT
        # elif self.state == State.CLOSING:
        #     if not syn and ack and not fin:
        #         self.state = State.TIME_WAIT
        else:
            print('state not valid')



class State:
    LISTEN = 0
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
    # Misc Global variables
    BUFFER_SIZE = 1045  # 21 bytes for rtp_header and 1024 bytes for payload
    is_debug = False
    terminate = False

    # Server
    server_window_size = 0
    server_port = ''
    SERVER_IP_ADDRESS = socket.gethostbyname(socket.gethostname())
    SERVER_IP_ADDRESS_LONG = struct.unpack("!L", socket.inet_aton(SERVER_IP_ADDRESS))[0]
    server_seq_num = 0  # random.randint(0, 2**32-1)
    server_ack_num = server_seq_num
    TIMEOUT_MAX_LIMIT = 10
    process_queue = Queue.Queue(maxsize=15000)
    SERVER_EMPTY_PAYLOAD = ''

    # NetEmu
    net_emu_ip_address = ''
    net_emu_ip_address_long = ''
    net_emu_port = ''
    net_emu_addr = ''

    # Client
    clientList = []

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except socket.error:
        print 'Failed to create socket'
        sys.exit()

    main(sys.argv[1:])

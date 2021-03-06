import Queue
import datetime
import hashlib
import random
import re
import socket
import struct
import sys
import threading
import time

# GET PROTOCOL
# GET|FILENAME - CLIENT
#     Exists --- GET|FILENAME|<# of packets> ACK - SERVER
#     Not Exists --- GET|FILENOTFOUND|0 ACK - SERVER
# DATA - SERVER
# ACK - CLIENT
# ...
# ACK - CLIENT (PEACEFUL CLOSE)

# POST PROTOCOL
# POST|FILENAME|<# of packets> - CLIENT
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
    except RuntimeError:
        print "Error creating/starting client slave thread(s)"

    # Setup for Server Command Instructions
    print "*" * 80
    print('Command Options:')
    print("window W\t|\tSets the maximum receiver's window size")
    print("terminate\t|\tShut-down FxA-Server gracefully")
    print "*" * 80
    print

    # Loop for server user commands
    while True:
        command_input = str(raw_input('Please enter command: '))
        # TERMINATE
        if command_input == 'terminate':
            all_client_threads_dead = 0
            # Iterate through all clients and make sure they are all in State.CLOSED state
            for client in clientList:
                if client.state != State.CLOSED:
                    all_client_threads_dead += 1
            if not all_client_threads_dead:
                break
            else:
                print all_client_threads_dead
                # All client threads see termination call
                client_termination_flag.set()
        # WINDOW
        else:
            parsed_command_input = command_input.split(" ")
            if parsed_command_input[0] == 'window':
                if len(parsed_command_input) != 2:
                    print("Invalid command: window requires secondary parameter")
                    continue
                try:
                    window_size = int(parsed_command_input[1])
                except ValueError:
                    print('Invalid window size (not a number): %s' % parsed_command_input[1])
                    continue
                server_window_size_update(window_size)
            else:
                print("Command not recognized")

    # Closing server and socket
    print("Server closing")
    sock.close()

# Method to update server window size for sending out packets
def server_window_size_update(window_size):
    global server_window_size
    global process_queue
    global process_queue_lock

    if window_size < 1 or window_size > 2**32 - 1:
        print "Window size incorrect; please try a number between 1-4294967295"

    elif process_queue.qsize() > window_size:
        print "Window size too small for current jobs in queue."

    else:
        new_process_queue = Queue.Queue(maxsize=window_size)
        process_queue_lock.acquire(True)

        while not process_queue.empty():
            new_process_queue.put(process_queue.get(False))
        server_window_size = window_size - new_process_queue.qsize()
        process_queue = new_process_queue

        process_queue_lock.release()
        print "Window size has been adjusted"

# Method thread for receiving all packets for server
def recv_packet():
    global clientList
    global client_list_lock

    while True:
        try:
            # Obtain packet from buffer and process by breaking up into rtp_header and payload
            packet_recv = sock.recvfrom(BUFFER_SIZE)
            packet = packet_recv[0]
            rtp_header = packet[0:21]
            rtp_header = unpack_rtpheader(rtp_header)
            payload = packet[21:]

            if check_checksum(rtp_header.get_checksum(), rtp_header, payload):
                # Checksum is good
                if is_debug:
                    print 'Received Payload:'
                    print str(payload)

                # Check to see if client exists
                client_loc = check_client_list(rtp_header.get_ip(), rtp_header.get_port())

                # Update client window size
                if client_loc is not None:
                    with client_list_lock:
                        clientList[client_loc].window_size = rtp_header.get_window()
                # Enqueue packet to main buffer queue
                processed_packet = Packet(rtp_header, payload, 0)

                # process_queue_lock.acquire(True)
                process_queue.put(processed_packet)
                # process_queue_lock.release()

        except socket.error, msg:
            continue

# Method thread for processing packets
def proc_packet():
    global clientList
    global client_list_lock

    while True:
        while not process_queue.empty():

            if is_debug:
                print 'Processing Received Data'
            packet = process_queue.get()

            rtp_header = packet.get_header()
            payload = packet.get_payload()

            # Check to see if client exists or needs to setup
            client_loc = check_client_list(rtp_header.get_ip(), rtp_header.get_port())

            # Client doesn't exist; create client, append client to clientList, and start up client thread
            if client_loc is None:
                client = Connection(rtp_header.get_seq_num(), rtp_header.get_ack_num(), rtp_header.get_window(),
                                    rtp_header.get_ack(), rtp_header.get_syn(), rtp_header.get_fin(),
                                    rtp_header.get_nack(), rtp_header.get_ip(), rtp_header.get_port())

                client_ip_address = socket.inet_ntoa(struct.pack("!L", rtp_header.get_ip()))
                print "\nConnection with client %s %s is being established..." % (client_ip_address,
                                                                                  rtp_header.get_port())

                with client_list_lock:
                    clientList.append(client)
                client_loc = len(clientList) - 1

                client_t = threading.Thread(target=client_thread, args=(client_loc,))
                client_t.daemon = True
                client_t.start()

            with client_list_lock:
                clientList[client_loc].mailbox.put(packet)

# Method thread spawned for each client that is created
def client_thread(client_loc):
    global clientList
    timeout = 0

    while True:
        if client_termination_flag.isSet():
            server_disconnect_t = threading.Thread(target=server_initiated_disconnect, args=(client_loc,0,))
            server_disconnect_t.daemon = True
            server_disconnect_t.start()
            server_disconnect_t.join()
            if clientList[client_loc].state == State.CLOSED:
                break
            # client_termination_flag.clear()
            # Verify State has been closed for this client before breaking from this thread
        try:
            # Wait until the process queue has a packet, block for TIMEOUT_TIME seconds
            packet = clientList[client_loc].mailbox.get(True, TIMEOUT_TIME)
        # If this happens more than TIME_MAX, client has been idle for too long; let's disconnect
        # If no response from client, change state to CLOSED
        except Queue.Empty:  # If after blocking there still was not a packet in the queue
            if timeout > TIME_MAX:
                client_ip_address = socket.inet_ntoa(struct.pack("!L", clientList[client_loc].client_ip))
                client_port = clientList[client_loc].client_port
                server_disconnect_t = threading.Thread(target=server_initiated_disconnect, args=(client_loc,0,))
                server_disconnect_t.daemon = True
                server_disconnect_t.start()
                server_disconnect_t.join()
                if clientList[client_loc].state == State.CLOSED:
                    print "Client %s %s was inactive...disconnected" % (client_ip_address, client_port)
                    return
            elif clientList[client_loc].state == State.CLOSED:
                return
            else:
                timeout += TIMEOUT_TIME
                continue
        timeout = 0

        rtp_header = packet.get_header()
        payload = packet.get_payload()

        # Check for payload commands for GET or POST
        payload_split = check_for_get_or_post_request(payload)

        # Client calls a GET or POST command
        if payload_split is not None and clientList[client_loc].state == State.ESTABLISHED:

            # GET Command
            if payload_split[0] == 'GET':
                if is_debug:
                    print 'GET'
                get_t = threading.Thread(target=get, args=(payload_split[1], clientList[client_loc], packet, payload,))
                get_t.daemon = True
                get_t.start()
                get_t.join()

            # POST Command
            elif payload_split[0] == 'POST':
                if is_debug:
                    print 'POST'
                post_t = threading.Thread(target=post,
                                          args=(payload_split[1], int(payload_split[2]), clientList[client_loc], packet,))
                post_t.daemon = True
                post_t.start()
                post_t.join()

        else:
            with client_list_lock:
                # Connection setup in progress
                if rtp_header.get_syn() and not rtp_header.get_ack():
                    clientList[client_loc].client_ack_num = rtp_header.get_seq_num() + calc_payload_length(payload)
                    clientList[client_loc].state = State.SYN_RECEIVED
                    send_synack(clientList[client_loc].server_connect_seq_nums[0],
                                clientList[client_loc].client_ack_num, clientList[client_loc].hash)

                # Connection setup in progress
                elif rtp_header.get_syn() and rtp_header.get_ack():
                    if clientList[client_loc].server_connect_seq_nums[1] == rtp_header.get_ack_num():
                        # Hashes match; complete 4-way handshake
                        if payload == clientList[client_loc].hash_of_hash:
                            clientList[client_loc].state = State.ESTABLISHED
                            clientList[client_loc].client_ack_num = rtp_header.get_seq_num() + calc_payload_length(payload)
                            send_ack(clientList[client_loc].server_connect_seq_nums[1],
                                     clientList[client_loc].client_ack_num)
                            clientList[client_loc].server_seq_num = clientList[client_loc].server_connect_seq_nums[2]
                            client_ip_address = socket.inet_ntoa(struct.pack("!L", clientList[client_loc].client_ip))
                            print "Client %s %s supposedly is established." % \
                                  (client_ip_address, clientList[client_loc].client_port)
                        elif is_debug:
                            print "Dropping packet due to incorrect hash"
                    elif is_debug:
                        print "Dropping packet due to incorrect server acknowledgement numbers"

                # Disconnect is in operation
                elif rtp_header.get_fin() and not clientList[client_loc].disconnect_flag.isSet():
                    clientList[client_loc].server_disconnect_seq_nums = \
                        clientList[client_loc].create_server_disconnect_seq_nums(clientList[client_loc].server_seq_num)
                    if clientList[client_loc].server_disconnect_seq_nums[0] == rtp_header.get_ack_num():
                        clientList[client_loc].disconnect_flag.set()
                        clientList[client_loc].client_ack_num = rtp_header.get_seq_num() + calc_payload_length(payload)

                        disconnect_t = threading.Thread(target=client_initiated_disconnect, args=(client_loc, 0,))
                        disconnect_t.daemon = True
                        disconnect_t.start()
                        # disconnect_t.join() # Stops queue
                    elif is_debug:
                        print "Dropping packet due to incorrect server sequence and acknowledgement numbers"

                # Drop extra FIN packets
                elif rtp_header.get_fin():
                    pass
                # Put packet back into client mailbox; must be for GET, POST, or Disconnect
                else:
                    clientList[client_loc].mailbox.put(packet)

# Method wrapper for server initiated disconnect
def server_initiated_disconnect(client_loc, num_timeouts):

    global clientList

    saved_client_ack_num = clientList[client_loc].client_ack_num
    saved_server_seq_num = clientList[client_loc].server_seq_num

    # Input current client_seq_num to pre-populate our known seq_nums that we will be dealing with
    clientList[client_loc].server_disconnect_seq_nums = \
        clientList[client_loc].create_server_disconnect_seq_nums(clientList[client_loc].server_seq_num)

    begin_disconnect_success = begin_server_initiated_disconnect(client_loc, num_timeouts)

    # If it failed, client must be lost; disconnect; we gave a faithful try
    if not begin_disconnect_success:
        clientList[client_loc].client_ack_num = saved_client_ack_num
        clientList[client_loc].server_seq_num = saved_server_seq_num
        clientList[client_loc].state = State.CLOSED
        print "Termination failed, we gave a good try; disconnecting anyways."
    elif end_server_initiated_disconnect(client_loc, num_timeouts, 0):
        clientList[client_loc].state = State.CLOSED
        print "Client(s) is(are) disconnected."

# Method for server initiated disconnect - first part
def begin_server_initiated_disconnect(client_loc, num_timeouts):

    # Send out the FIN packet to initialize disconnect
    # Send pre-populated disconnect client seq_nums and current server_ack_num
    send_fin(clientList[client_loc].server_disconnect_seq_nums[0], clientList[client_loc].client_ack_num)
    try:
        # Wait until the process queue has a packet, block for TIMEOUT_TIME seconds
        packet = process_queue.get(True, TIMEOUT_TIME)
    except Queue.Empty:  # If after blocking there still was not a packet in the queue
        # If we have timed out TIMEOUT_MAX_LIMIT times, then cancel the operation
        if num_timeouts >= TIMEOUT_MAX_LIMIT:
            return False
        else:
            # If we have timed out less than TIMEOUT_MAX_LIMIT times, then try again with num_timeouts incremented
            print('.'),
            return begin_server_initiated_disconnect(client_loc, num_timeouts + 1)

    rtp_header = packet.get_header()
    payload = packet.get_payload()

    # Check client ack_num from recent packet received with pre-populated seq_nums
    # If bad, recurse
    if rtp_header.get_ack_num() != clientList[client_loc].server_disconnect_seq_nums[1]:
        if is_debug:
            print "Bad acknowledgement number"
        return begin_server_initiated_disconnect(client_loc, num_timeouts + 1)

    # If good, move onto receiving FIN from server and then sending ACK to complete disconnect
    elif rtp_header.get_ack():
        # Increment server_ack_num to account for recent recv packet from server
        clientList[client_loc].client_ack_num = rtp_header.get_seq_num() + calc_payload_length(payload)
        clientList[client_loc].state = State.FIN_WAIT_2
        return True

    else:
        return begin_server_initiated_disconnect(client_loc, num_timeouts + 1)

# Method for server initiated disconnect - second part
def end_server_initiated_disconnect(client_loc, num_timeouts, time_wait_counter):

    try:
        # Wait until the process queue has a packet, block for TIMEOUT_TIME seconds
        packet = process_queue.get(True, TIMEOUT_TIME)
    except Queue.Empty:  # If after blocking there still was not a packet in the queue
        # If we have timed out TIMEOUT_MAX_LIMIT times, then cancel the operation
        if num_timeouts >= TIMEOUT_MAX_LIMIT:
            return False
        # Wait 5 cycles before closing in case server never received ACK
        elif clientList[client_loc].state == State.TIME_WAIT and time_wait_counter == TIME_WAIT_MAX:
            return True
        elif clientList[client_loc].state == State.TIME_WAIT:
            return end_server_initiated_disconnect(client_loc, num_timeouts, time_wait_counter + 1)
        else:
            # If we have timed out less than TIMEOUT_MAX_LIMIT times, then try again with num_timeouts incremented
            print('.'),
            return end_server_initiated_disconnect(client_loc, num_timeouts + 1, time_wait_counter)

    rtp_header = packet.get_header()
    payload = packet.get_payload()

    # Check client ack_num from recent packet received with pre-populated seq_nums
    # If bad, recurse
    if rtp_header.get_ack_num() != clientList[client_loc].server_disconnect_seq_nums[1]:
        if is_debug:
            print "Bad acknowledgement number"
        return end_server_initiated_disconnect(client_loc, num_timeouts + 1, time_wait_counter)

    # We received a FIN; send ACK to complete disconnect
    # If server indeed receives an ACK, disconnect in complete, but if the client sends another FIN, then we need
    # to resend an ACK and wait again
    elif rtp_header.get_fin() or clientList[client_loc].state == State.TIME_WAIT:
        # Increment server_ack_num to account for recent recv packet from server
        clientList[client_loc].client_ack_num = rtp_header.get_seq_num() + calc_payload_length(payload)
        # Change sequence and acknowledge numbers to correct ones before sending to server
        # clientList[client_loc].client_ack_num = rtp_header.get_seq_num() + calc_payload_length(payload)
        clientList[client_loc].state = State.TIME_WAIT
        send_ack(clientList[client_loc].server_disconnect_seq_nums[1], clientList[client_loc].client_ack_num)
        clientList[client_loc].server_ack_num = clientList[client_loc].server_disconnect_seq_nums[2] + 1
        clientList[client_loc].server_seq_num = clientList[client_loc].server_ack_num
        return end_server_initiated_disconnect(client_loc, num_timeouts, time_wait_counter)

    # We received something else; lets recurse again
    else:
        return end_server_initiated_disconnect(client_loc, num_timeouts + 1, time_wait_counter)

# Method for client initiated disconenct
def client_initiated_disconnect(client_loc, num_timeouts):
    global clientList

    # Send out the ACK to match the FIN that was recv from the client
    send_ack(clientList[client_loc].server_disconnect_seq_nums[0], clientList[client_loc].client_ack_num)

    clientList[client_loc].state = State.CLOSE_WAIT

    # Send out the FIN packet to end connection
    send_fin(clientList[client_loc].server_disconnect_seq_nums[1], clientList[client_loc].client_ack_num)
    clientList[client_loc].state = State.LAST_ACK

    try:
        packet = clientList[client_loc].mailbox.get(True, TIMEOUT_TIME)
    except Queue.Empty:
        if num_timeouts >= TIMEOUT_MAX_LIMIT:
            clientList[client_loc].disconnect_flag.clear()
            clientList[client_loc].state = State.ESTABLISHED
            return False
        else:
            # If we have timed out less than TIMEOUT_MAX_LIMIT times, then try again with num_timeouts incremented
            print('.'),
            clientList[client_loc].state = State.ESTABLISHED
            return client_initiated_disconnect(client_loc, num_timeouts + 1)

    rtp_header = packet.get_header()
    payload = packet.get_payload()

    if rtp_header.get_ack_num() != clientList[client_loc].server_disconnect_seq_nums[2]:
        if is_debug:
            print "Bad acknowledgement number"
        return client_initiated_disconnect(client_loc, num_timeouts + 1)

    # Received an ACK from client.  Disconnect is complete
    elif rtp_header.get_ack():
        # Increment client_ack_num to account for recent recv packet from client
        clientList[client_loc].client_ack_num = rtp_header.get_seq_num() + calc_payload_length(payload)
        clientList[client_loc].server_seq_num = clientList[client_loc].server_disconnect_seq_nums[2]
        clientList[client_loc].state = State.CLOSED
        client_ip_address = socket.inet_ntoa(struct.pack("!L", clientList[client_loc].client_ip))
        print "Client %s %s has been disconnected." % (client_ip_address, clientList[client_loc].client_port)
        return True

    else:
        return client_initiated_disconnect(client_loc, num_timeouts + 1)

# Method to calculate payload length
def calc_payload_length(payload):

    if len(payload) == 0:
        return 1
    else:
        return len(payload)

# Method to check for GET or POST request
def check_for_get_or_post_request(payload):
    if len(payload) > 0:
        payload_split = payload.split('|')
        if payload_split[0] == 'GET' or payload_split[0] == 'POST':
            return payload_split
    return None

# Method to send packets to client
def send(server_seq_number, client_ack_num, ack, syn, fin, nack, payload):
    global server_window_size
    # Calculate checksum on rtp_header and payload with a blank checksum
    checksum = 0
    server_window_size = process_queue.maxsize - process_queue.qsize()
    rtp_header_obj = RTPHeader(server_seq_number, client_ack_num, checksum, server_window_size, ack, syn, fin, nack,
                               SERVER_IP_ADDRESS_LONG, server_port)
    packed_rtp_header = pack_rtpheader(rtp_header_obj)
    packet = packed_rtp_header + payload
    checksum = sum(bytearray(packet)) % 65535

    # Install checksum into rtp_header and package up with payload
    rtp_header_obj = RTPHeader(server_seq_number, client_ack_num, checksum, server_window_size, ack, syn, fin, nack,
                               SERVER_IP_ADDRESS_LONG, server_port)
    packed_rtp_header = pack_rtpheader(rtp_header_obj)
    packet = packed_rtp_header + payload

    if is_debug:
        print "Sending:"
        print '\tServer Seq Num:\t' + str(server_seq_number)
        print '\tClient ACK Num:\t' + str(client_ack_num)
        print '\tChecksum:\t' + str(checksum)
        print '\tServer Window:\t' + str(server_window_size)
        print '\tACK:\t\t' + str(ack)
        print '\tSYN:\t\t' + str(syn)
        print '\tFIN:\t\t' + str(fin)
        print '\tNACK:\t\t' + str(nack)
        print '\tServer IP Long:\t' + str(SERVER_IP_ADDRESS_LONG)
        print '\tServer Port:\t' + str(server_port)
        print '\tPayload:\t' + str(payload)
        print '\tSze-Pyld:\t' + str(len(payload))

    sock.sendto(packet, net_emu_addr)

# Method to pack up RTP header for sending
def pack_rtpheader(rtp_header):
    flags = pack_bits(rtp_header.get_ack(), rtp_header.get_syn(), rtp_header.get_fin(), rtp_header.get_nack())
    rtp_header_bin = struct.pack('!LLHLBLH', rtp_header.get_seq_num(), rtp_header.get_ack_num(),
                                 rtp_header.get_checksum(), rtp_header.get_window(), flags, rtp_header.get_ip(),
                                 rtp_header.get_port())

    return rtp_header_bin

# Method to check the checksum of each packet
def check_checksum(checksum, rtp_header, payload):
    flags = pack_bits(rtp_header.get_ack(), rtp_header.get_syn(), rtp_header.get_fin(), rtp_header.get_nack())
    packed_checksum = struct.pack('!L', checksum)
    packed_rtp_header = struct.pack('!LLHLBLH', rtp_header.get_seq_num(), rtp_header.get_ack_num(),
                                    0, rtp_header.get_window(), flags, rtp_header.get_ip(),
                                    rtp_header.get_port())

    data = packed_rtp_header + payload

    new_checksum = sum(bytearray(data)) % 65535
    # new_checksum -= sum(bytearray(packed_checksum))

    if checksum == new_checksum:
        if is_debug:
            print 'Checksum Correct'
        return True
    else:
        if is_debug:
            print 'Checksum Incorrect'
        return False

# Method to unpack RTP header to process
def unpack_rtpheader(packed_rtp_header):
    unpacked_rtp_header = struct.unpack('!LLHLBLH', packed_rtp_header)  # 21 bytes

    client_seq_num = unpacked_rtp_header[0]
    server_ack_num = unpacked_rtp_header[1]
    checksum = unpacked_rtp_header[2]
    client_window_size = unpacked_rtp_header[3]
    flags = unpacked_rtp_header[4]
    ack, syn, fin, nack = unpack_bits(flags)
    client_ip_address_long = unpacked_rtp_header[5]
    client_port = unpacked_rtp_header[6]
    rtp_header_obj = RTPHeader(client_seq_num, server_ack_num, checksum, client_window_size, ack, syn, fin, nack,
                               client_ip_address_long, client_port)

    if is_debug:
        print "Unpacking Header:"
        print '\tClient Seq Num:\t' + str(client_seq_num)
        print '\tServer ACK Num:\t' + str(server_ack_num)
        print '\tChecksum:\t' + str(checksum)
        print '\tClient Window:\t' + str(client_window_size)
        print '\tACK:\t\t' + str(ack)
        print '\tSYN:\t\t' + str(syn)
        print '\tFIN:\t\t' + str(fin)
        print '\tNACK:\t\t' + str(nack)
        print '\tClient IP Long:\t' + str(client_ip_address_long)
        print '\tClient Port:\t' + str(client_port)

    return rtp_header_obj

# Method to pack of flag into a 1 byte string
def pack_bits(ack, syn, fin, nack):
    bit_string = str(ack) + str(syn) + str(fin) + str(nack)
    bit_string = '0000' + bit_string
    bit_string = int(bit_string, 2)

    return bit_string

# Method to unpack the 1 byte string into the flags in the RTP header
def unpack_bits(bit_string):
    bit_string = format(bit_string, '08b')
    ack = int(bit_string[4])
    syn = int(bit_string[5])
    fin = int(bit_string[6])
    nack = int(bit_string[7])

    return ack, syn, fin, nack

# Method to allow the client to download a file from the server
def get(filename, conn_object, request_packet, payload):

    skip = False
    new_packet = None

    try:
        file_handle = open(filename, 'rb')
    except IOError:
        print "Could not open file: {0}".format(filename)
        conn_object.client_ack_num = request_packet.get_header().get_seq_num() + len(request_packet.get_payload())
        send(conn_object.server_seq_num, conn_object.client_ack_num, 1, 0, 0, 0, 'GET|FILENOTFOUND|0')
        #send(conn_object.server_seq_num, request_packet.get_header().get_seq_num() + len(request_packet.get_payload()),
        #     1, 0, 0, 0, 'GET|FILENOTFOUND|0')
        return
    packet_list = []  # clear out the list of packets
    while True:
        data = file_handle.read(1024)
        if not data:
            break
        packet_list.append(Packet(RTPHeader(0, 0, 0, 0, 0, 0, 0, 0, net_emu_ip_address_long, net_emu_port), data,
                                  False))
    file_handle.close()
    init_payload = 'GET|{0}|{1}'.format(filename, str(len(packet_list)))

    conn_object.client_ack_num = request_packet.get_header().get_seq_num() + len(request_packet.get_payload())
    send(conn_object.server_seq_num, conn_object.client_ack_num, 1, 0, 0, 0, init_payload)

    try:
        new_packet = conn_object.mailbox.get(True, 1)
    except Queue.Empty:
        skip = True
        # send(conn_object.server_seq_num, request_packet.get_header().get_seq_num() + len(request_packet.get_payload()),
        #      1, 0, 0, 0, init_payload)
        conn_object.server_seq_num += len(payload)
        for i in range(len(packet_list)):
            packet_list[i].header.seq_num = i * 1024 + conn_object.server_seq_num
            packet_list[i].header.ack_num = i * 1 + conn_object.client_ack_num
        next_packet_to_send = 0
        num_timeouts = 0
        total_packets_sent = 0
        # repeat infinitely if need be, will be broken out of if TIMEOUT_MAX_LIMIT timeouts are reached
        while True:
            print '{0:.1f}%'.format((total_packets_sent / float(len(packet_list))) * 100)
            if is_debug:
                print('\t\t'),
                for i in range(0, len(packet_list)):
                    print(i),
                print ''
                print 'ACK''ed:\t',
                for j in range(0, min(10, len(packet_list))):
                    if packet_list[j].get_acknowledged():
                        print('x'),
                    else:
                        print('.'),
                if len(packet_list) > 10:
                    for k in range(10, min(100, len(packet_list))):
                        if packet_list[k].get_acknowledged():
                            print(' x'),
                        else:
                            print(' .'),
                if len(packet_list) > 100:
                    for k in range(100, len(packet_list)):
                        if packet_list[k].get_acknowledged():
                            print('  x'),
                        else:
                            print('  .'),
                print ''
            # send (server window size) # of un-acknowledged packets in the packet list
            packets_sent_in_curr_window = 0
            for x in range(next_packet_to_send, len(packet_list)):
                if not packet_list[x].get_acknowledged():  # if it has not been acknowledged
                    send(packet_list[x].header.seq_num, packet_list[x].header.ack_num, 0, 0, 0, 0, packet_list[x].payload)
                    # send(packet_list[x].header.seq_num, 0, 0, 0, 0, 0, packet_list[x].payload)
                    conn_object.server_seq_num += len(packet_list[x].payload)
                    packets_sent_in_curr_window += 1
                    if packets_sent_in_curr_window == conn_object.window_size:
                        break

            # Use temp variable to see if we actually received any
            curr_num_packets_sent = total_packets_sent

            # wait_for_acks processes all the packets received in the 5 seconds after sending the window,
            # and sets the next packet to send
            next_packet_to_send, total_packets_sent = wait_for_acks(datetime.datetime.now(), next_packet_to_send,
                                                                    total_packets_sent, packet_list, conn_object)

            # if we have acknowledged all of the packets, then we are done
            if next_packet_to_send == -1:
                break
            # if we timeout then increment the number of timeouts
            if curr_num_packets_sent == next_packet_to_send:
                num_timeouts += 1
            else:
                # if we did receive reset timeouts
                num_timeouts = 0
            if num_timeouts == TIMEOUT_MAX_LIMIT:
                print 'Client Unresponsive, GET failed'
                break
        if len(packet_list) != 0:
            conn_object.server_seq_num = packet_list[len(packet_list)-1].header.seq_num + \
                                                     len(packet_list[len(packet_list)-1].payload)
            conn_object.client_ack_num = packet_list[len(packet_list)-1].header.ack_num + 1

    if not skip:
        # Check for payload commands for GET or POST
        # payload_split = check_for_get_or_post_request(payload)

        # currently, no checks
        get(filename, conn_object, new_packet, payload)


# Method to wait for acks from the client for data transfer
def wait_for_acks(time_of_calling, next_packet_to_send, packets_sent, list_of_packets, conn_object):
    to_return_packets_sent = packets_sent

    # Look at all the windows and sequence numbers received
    client_windows_received = []
    client_seq_num_received = [conn_object.client_seq_num]
    while True:
        # Stay in the loop for 5 seconds
        if datetime.datetime.now() > time_of_calling + datetime.timedelta(seconds=5):
            break
        # Try to pull something out of the Queue, block for a second, if there is nothing there, then go to the top
        try:
            new_packet = conn_object.mailbox.get(True, 1)
        except Queue.Empty:
            continue
        if not new_packet.header.ack:
            continue
        # Look through the packet list to find the packet that the ACK is referencing
        for i in list_of_packets:
            if i.get_header().seq_num + len(i.get_payload()) == new_packet.get_header().get_ack_num()\
                    and not i.acknowledged:
                i.acknowledged = True
                to_return_packets_sent += 1
                client_windows_received.append(new_packet.get_header().get_window())
                client_seq_num_received.append(new_packet.get_header().get_seq_num())
                break
    if not len(client_seq_num_received) == 0:
        conn_object.client_seq_num = max(client_seq_num_received)
    if not len(client_windows_received) == 0:
        conn_object.window_size = min(client_windows_received)
    else:
        conn_object.window_size = 10
    for i in range(next_packet_to_send, len(list_of_packets)):
        if not list_of_packets[i].get_acknowledged():
            return i, to_return_packets_sent
    return -1, to_return_packets_sent


# Method to upload a file from the client - incomplete
def post(filename, packets_in_file, conn_object, request_packet):
    global data
    global total_packets_rec

    # send acknowledgment of POST request
    send(conn_object.server_seq_num, conn_object.client_ack_num, 1, 0, 0, 0, '')
    data = []
    next_packet_to_rec = 0
    num_timeouts = 0
    total_packets_rec = 0
    for i in range(packets_in_file):
        data.append(Packet(
            RTPHeader((request_packet.get_header().get_seq_num() + len(request_packet.get_payload())) + i * 1024, 0, 0,
                      0, 0, 0, 0, 0, 0, 0), None, None))
    while True:
        print '{0:.1f}%'.format(total_packets_rec / packets_in_file)
        curr_num_packets_rec = total_packets_rec
        next_packet_to_rec = wait_for_data_and_acknowledge(datetime.datetime.now(), next_packet_to_rec, conn_object)

        if next_packet_to_rec == -1:
            break
        if curr_num_packets_rec == total_packets_rec:
            num_timeouts += 1
        else:
            # if we did receive reset timeouts
            num_timeouts = 0
        if num_timeouts == TIMEOUT_MAX_LIMIT:
            print 'Client Unresponsive, GET failed'
            return
    byte_data = []
    for packet in data:
        for i in range(0, len(packet.get_payload)):
            byte_data.append(packet.get_payload[i])
    file_byte_array = bytearray(byte_data)
    file_handle = open(filename, 'wb')
    file_handle.write(file_byte_array)
    file_handle.close()

# Method to wait for data from the client and send ACKs to the client - incomplete
def wait_for_data_and_acknowledge(time_of_calling, next_packet_to_rec, conn_object):
    global server_window_size
    global server_seq_num
    global total_packets_rec
    global data

    # Look at all the windows and sequence numbers received
    server_windows_received = []
    server_seq_num_received = []

    while True:
        # Stay in the loop for 5 seconds
        if datetime.datetime.now() > time_of_calling + datetime.timedelta(seconds=5):
            break

        # Try to pull something out of the Queue, block for a second, if there is nothing there, then go to the top
        try:
            new_packet = conn_object.mailbox.get(True, 1)
        except Queue.Empty:
            continue

        # Look through the packet list to find the packet that the ACK is referencing
        for i in data:
            if i.get_header().seq_num == new_packet.get_header().get_seq_num():
                if i.payload is None:
                    total_packets_rec += 1
                    i.payload = new_packet.get_payload()
                server_windows_received.append(new_packet.get_header().get_window())
                server_seq_num_received.append(new_packet.get_header().get_seq_num())
                i.payload = new_packet.get_payload()
                send(1, 0, 0, 0, 0, i.get_header().seq_num() + len(i.get_header()), '')
    if not len(server_seq_num_received) == 0:
        server_seq_num = max(server_seq_num_received)
    if not len(server_windows_received) == 0:
        server_window_size = min(server_windows_received)
    else:
        server_window_size = 10
    for i in range(next_packet_to_rec, len(data)):
        if not data[i].get_payload():
            return i
    return -1

# Method to check where a client is in the main client list
def check_client_list(client_ip_address, client_port):
    with client_list_lock:
        for i in range(len(clientList)):
            if clientList[i].client_ip == client_ip_address and clientList[i].client_port == client_port \
                    and clientList[i].state != State.CLOSED:
                if is_debug:
                    print 'Client found in connection list'
                return i

    if is_debug:
        print 'Client not found in connection list'
    return None

# Method to send SYN+ACK
def send_synack(server_seq_num, client_ack_num, payload):
    send(server_seq_num, client_ack_num, 1, 1, 0, 0, payload)

# Method to send a NACK
def send_nack(server_seq_num, client_ack_num):
    send(server_seq_num, client_ack_num, 0, 0, 0, 1, EMPTY_PAYLOAD)

# Method to send an ACK
def send_ack(server_seq_num, client_ack_num):
    send(server_seq_num, client_ack_num, 1, 0, 0, 0, EMPTY_PAYLOAD)

# Method to send a FIN
def send_fin(server_seq_num, client_ack_num):
    send(server_seq_num, client_ack_num, 0, 0, 1, 0, EMPTY_PAYLOAD)

# Connection class for storing all client important information
class Connection:
    def __init__(self, seq_num, ack_num, window_size, ack, syn, fin, nack, client_ip, client_port):
        self.state = State.LISTEN
        self.client_seq_num = seq_num
        self.client_ack_num = self.client_seq_num
        self.server_seq_num = ack_num
        self.server_ack_num = self.server_seq_num
        self.window_size = window_size
        self.last_ack = ack
        self.last_syn = syn
        self.last_fin = fin
        self.last_nack = nack
        self.client_ip = client_ip
        self.client_port = client_port
        self.timer = ''  # threading.Timer(10, dummy())
        self.hash = hashlib.sha224(str(random.randint(0, 2 ** 64 - 1))).hexdigest()
        self.hash_of_hash = hashlib.sha224(self.hash).hexdigest()
        self.hash_from_client = ''
        self.previous_payload_sent = ''
        self.server_connect_seq_nums = self.create_server_connect_seq_nums(self.server_ack_num)
        self.server_disconnect_seq_nums = None
        self.mailbox = Queue.Queue(maxsize=QUEUE_MAX_SIZE)
        self.mailbox_lock = threading.Lock()
        self.disconnect_flag = threading.Event()

    def is_client_setup(self):
        # if client is not in either of these states; client is setup
        if self.state != State.SYN_RECEIVED and self.state != State.SYN_SENT_HASH and self.state != State.LISTEN:
            return True
        return False

    def in_disconnect_state(self):
        if self.state == State.CLOSE_WAIT or self.state == State.LAST_ACK:
            return True
        return False

    def create_server_connect_seq_nums(self, syn_rcvd_seq_num):
        establish_seq_num = syn_rcvd_seq_num + len(self.hash)
        final_establish_seq_num = establish_seq_num + 1
        return syn_rcvd_seq_num, establish_seq_num, final_establish_seq_num

    def create_server_disconnect_seq_nums(self, established_seq_num):
        close_wait_seq_num = established_seq_num + 1
        closed_seq_num = close_wait_seq_num + 1
        return established_seq_num, close_wait_seq_num, closed_seq_num

    def create_server_initiated_disconnect_seq_nums(self, established_seq_num):
        fin_wait_2_seq_num = established_seq_num + 1
        time_wait_seq_num = fin_wait_2_seq_num + 1
        return (established_seq_num, fin_wait_2_seq_num, time_wait_seq_num)

    def update_on_receive(self, ack, syn, fin, nack, client_loc):
        pass

# State class for storing all the protocol states the client can be in
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

# RTP Header class for storing all important information for transporting data
class RTPHeader:
    def __init__(self, seq_num, ack_num, checksum, window, ack, syn, fin, nack, ip, port):
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.checksum = checksum
        self.window = window
        self.ack = ack
        self.syn = syn
        self.fin = fin
        self.nack = nack
        self.ip = ip
        self.port = port

    def get_seq_num(self):
        return self.seq_num

    def get_ack_num(self):
        return self.ack_num

    def get_checksum(self):
        return self.checksum

    def get_window(self):
        return self.window

    def get_ack(self):
        return self.ack

    def get_syn(self):
        return self.syn

    def get_fin(self):
        return self.fin

    def get_nack(self):
        return self.nack

    def get_ip(self):
        return self.ip

    def get_port(self):
        return self.port

# Packet class for storing RTP Header, payload, and ACKs
class Packet:
    def __init__(self, header, payload, acknowledged):
        self.header = header
        self.payload = payload
        self.acknowledged = acknowledged

    def get_header(self):
        return self.header

    def get_payload(self):
        return self.payload

    def get_acknowledged(self):
        return self.acknowledged


if __name__ == "__main__":
    # Misc Global variables
    BUFFER_SIZE = 1045  # 21 bytes for rtp_header and 1024 bytes for payload
    is_debug = False
    terminate = False
    EMPTY_PAYLOAD = ''
    TIMEOUT_MAX_LIMIT = 20
    TIMEOUT_TIME = 2
    TIME_MAX = 60  # 1 minute
    QUEUE_MAX_SIZE = 10
    TIME_WAIT_MAX = 2

    # Server
    server_window_size = 1
    server_port = ''
    SERVER_IP_ADDRESS = socket.gethostbyname(socket.gethostname())
    SERVER_IP_ADDRESS_LONG = struct.unpack("!L", socket.inet_aton(SERVER_IP_ADDRESS))[0]
    process_queue = Queue.Queue(maxsize=QUEUE_MAX_SIZE)
    process_queue_lock = threading.Lock()
    total_packets_rec = 0
    data = []

    # NetEmu
    net_emu_ip_address = ''
    net_emu_ip_address_long = ''
    net_emu_port = ''
    net_emu_addr = ''

    # Client
    clientList = []
    client_list_lock = threading.Lock()
    client_termination_flag = threading.Event()

    # Create global socket for server
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except socket.error:
        print 'Failed to create socket'
        sys.exit()

    main(sys.argv[1:])

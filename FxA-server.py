import Queue
import socket
import sys
from threading import Timer


def main(argv):
    if len(argv) != 3:
        print("Correct usage: FxA-Client X A P")
        sys.exit(1)

    server_port = argv[0]
    ip_address = argv[1]
    net_emu_port = argv[2]
    x = ''
    window = 0
    max_connections = 1000


    try:
        server_port = int(server_port)
    except ValueError:
        print('Invalid server port number %s' % argv[0])
        sys.exit(1)

    if server_port % 2 == 0:
        print('Server port number: %d was not an odd number' % server_port)
        sys.exit(1)

    try:
        ip_address = socket.inet_aton(ip_address)
    except socket.error:
        print("Invalid IP notation: %s" % argv[1])
        sys.exit(1)
        # TODO check if port is open!

    try:
        net_emu_port = int(net_emu_port)
    except ValueError:
        print('Invalid NetEmu port number: %s' % argv[2])
        sys.exit(1)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('', server_port))
    q = Queue.Queue(max_connections)

    print('Command Options:')
    print("window W\t|\tSets the maximum receiver's window size")
    print("terminate\t|\tShut-down FxA-Server gracefully\n")

    while x != 'terminate':
        x = raw_input('Please enter command:')
        if x == 'terminate':
            # TODO terminate() call
            break
        else:
            y = x.split(" ")
            if y[0] == 'window':
                if len(y) != 2:
                    print("Invalid command: window requires secondary parameter")
                    continue
                try:
                    window = int(y[1])
                except ValueError:
                    print('Invalid window size (not a number): %s' % y[1])
                    continue
                # TODO window()
                print('window')
            else:
                print("Command not recognized")


def send(param, param1, param2):
    pass


def timeout(args):
    pass


def acknowledge():
    pass


def checkhash():
    pass


class Connection:

    def __init__(self, sender_ip, sender_port):
        self.state = State.SYN_RECEIVED
        self.sender_ip = sender_ip
        self.sender_port = sender_port
        self.timer = Timer(10, timeout)
        self.timer.start()

    def update_on_receive(self, syn, ack, fin):
        self.timer.cancel()

        if self.state == State.SYN_RECEIVED:
            if syn and ack and not fin:
                if checkhash():
                    self.state = State.ESTABLISHED
                    acknowledge()
                else:
                    self.state = State.CLOSED
        elif self.state == State.ESTABLISHED:
            if not syn and not ack and fin:
                self.state = State.CLOSE_WAIT
                acknowledge()
        elif self.state == State.LAST_ACK:
            if not syn and ack and not fin:
                self.state = State.CLOSED
        elif self.state == State.FIN_WAIT_1:
            if not syn and not ack and fin:
                acknowledge()
                self.state = State.CLOSING
            if not syn and ack and not fin:
                self.state = State.FIN_WAIT_2
            if not syn and ack and fin:
                acknowledge()
                self.state = State.TIME_WAIT
        elif self.state == State.FIN_WAIT_2:
            if not syn and not ack and fin:
                acknowledge()
                self.state = State.TIME_WAIT
        elif self.state == State.CLOSING:
            if not syn and ack and not fin:
                self.state = State.TIME_WAIT
        else:
            print('state not valid')

        self.timer = Timer(10, timeout)
        self.timer.start()


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
    main(sys.argv[1:])

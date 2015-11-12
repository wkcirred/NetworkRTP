import socket
import sys


def main(argv):
    if len(argv) != 3:
        print("Correct usage: FxA-Client X A P")
        sys.exit(1)

    client_port = argv[0]
    ip_address = argv[1]
    net_emu_port = argv[2]
    is_connected = False
    x = ''
    window = 0

    try:
        client_port = int(client_port)
    except ValueError:
        print('Invalid client port number %s' % argv[0])
        sys.exit(1)

    if client_port % 2 == 1:
        print('Client port number: %d was not even number' % client_port)
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

    print('Command Options:')
    print('connect\t\t|\tConnects to the FxA-server')
    print('get F\t\t|\tRetrieve file F from FxA-server')
    print('post F\t\t|\tPushes file F to the FxA-server')
    print("window W\t|\tSets the maximum receiver's window size")
    print("disconnect\t|\tDisconnect from the FxA-server\n")

    while x != 'disconnect':
        x = raw_input('Please enter command:')
        if x == 'connect':
            # TODO connect() call
            is_connected = True
        elif x == 'disconnect':
            if is_connected:
                # TODO disconnect() call
                break
            else:
                print('post not valid without existing connection')
        else:
            y = x.split(" ")
            if y[0] == 'get':
                if len(y) != 2:
                    print("Invalid command: get requires secondary parameter")
                    continue
                if is_connected:
                    # TODO get()
                    print('get')
                else:
                    print('get not valid without existing connection')
            elif y[0] == 'post':
                if len(y) != 2:
                    print("Invalid command: post requires secondary parameter")
                    continue
                if is_connected:
                    # TODO post()
                    print('post')
                else:
                    print('post not valid without existing connection')
            elif y[0] == 'window':
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

if __name__ == "__main__":
    main(sys.argv[1:])
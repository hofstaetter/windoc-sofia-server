
import socket
from time import sleep
from astm.constants import ENQ, STX, ETX, EOT, ACK, LF, NAK
import sys, os

f = open(sys.argv[1] if len(sys.argv) > 1 else 'out.dat.4', 'rb')

s = socket.socket()
s.connect(('localhost', int(os.environ["PORT"] if 'PORT' in os.environ else 15200)))

frame = b''

b = f.read(1)
while b != b'':
    frame += b
    if b in [ ENQ, LF ]:
        s.send(frame)
        print("Just sent %s, waiting for ACK" % repr(frame))
        frame = b''
        r = s.recv(1)
        if r == ACK:
            print('ACK')
        elif r == NAK:
            print('NAK')
            break
        else:
            print(r)
    elif b == EOT:
        s.send(b)
        frame = b''
        print("EOT")
        sleep(1)
    b = f.read(1)

s.close()
f.close()

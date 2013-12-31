import socket
import time
import hashlib
import select
import sys
import tty
import termios
import hashlib

class GameConnector(object):
    def __init__(self, host, port, game_name):
        self.host = host
        self.port  = port

        self.game_name = game_name.replace(" ","_")
        self.socket = None

        self.sendbuffer = []
        self.writebuffer = []
        self.recvbuffer = ""

        self.token = None

        self.playing = False

        self.reading = []

    def start(self):
        self.socket = socket.socket()
        try:
            self.socket.connect((self.host, self.port))
            self.reading.append(self.socket)
            return True
        except Exception, e:
            print e
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

    def start_termios(self):
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)

        tty.setraw(sys.stdin.fileno())

        self.playing = True
        self.reading.append(sys.stdin)

    def mainloop(self):
        try:
            self._mainloop()
        except KeyboardInterrupt:
            self.socket.close()
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


    def recv_sock(self, sock):
        data = sock.recv(1024)
        if not data:
            self.socket.close()
            self.socket = None
        data = data.split("\r\n")
        data[0] = self.recvbuffer + data[0]
        if data[-1] == "":
            self.recvbuffer = data.pop()
        else:
            self.recvbuffer = ""
        for item in data:
            self.parse_sock(item)

    def recv_stdin(self, fd):
        char = fd.read(1)
        self.parse_stdin(char)

    def send(self, opcode, values):
        m = "{0} {1} {2}\r\n".format(opcode, values, self.token)
        self.sendbuffer.append(m)

    def write(self, message):
        self.writebuffer.append(message + "\n")

    def _mainloop(self):
        while self.socket:
            writing = []
            if self.sendbuffer != []:
                writing.append(self.socket)
            r, w, e = select.select(self.reading, writing, [self.socket], 5)
            if r:
                for sock in r:
                    if sock == self.socket:
                        self.recv_sock(sock)
                    if sock == sys.stdin:
                       self.recv_stdin(sock)
            if w:
                for sock in w:
                    if sock == self.socket:
                        for item in self.sendbuffer:
                            self.socket.send(item)
                        self.sendbuffer = []
            if e:
                print "ERROR"
                self.socket.close()
                self.socket = None

    def do_auth(self):
        username = raw_input("Username: ")
        password = hashlib.md5(raw_input("Password: ")).hexdigest()[::-1]
        self.send("002","{0}-{1}-{2}".format(username, password, self.game_name))

    def parse_sock(self, message):
        try:
            opcode, values, source = message.split()
            if opcode == "005" and source == "*HOST*":
                self.token = values
                self.send("001",time.time())
            if opcode == "007":
                if values == "REQUIRE_AUTH":
                    self.do_auth()
                else:
                    self.send("002","x-x-{0}".format(self.game_name))
            if opcode == "008":
                if values == "LOGGED_IN":
                    print "We are logged in, beginning game!"
                    self.start_termios()
                else:
                    self.do_auth
            if opcode == "248":
                for i in range(2):
                    print "\a"
                    time.sleep(.3)
        except Exception, e:
            print "Error:", e

    def parse_stdin(self, char):
        if self.playing:
            if char == " ":
                self.send("004","{0} {1}".format(time.time(), self.token))


if __name__ == "__main__":
    game = GameConnector("",8000, "Cameron Wrigley_2")
    if game.start():
        game.mainloop()
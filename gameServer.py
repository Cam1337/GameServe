import time
import socket
import select
import uuid
import hashlib

# player1 = AuthenticatedPlayerModel("Charles","charles123",None,False)

class AuthenticatedPlayerModel(object):
    def __init__(self, user, password, ip_limit, admin):
        self.user = user
        self.password = hashlib.md5(password).hexdigest()[::-1]
        self.ip_limit = ip_limit
        self.admin = admin

class GamePlayer(object):
    def __init__(self, accepted_socket, addr):
        self.socket = accepted_socket
        self.addr = addr
        self.name = None
        self.authed = None

        self.token = uuid.uuid1()

        self.send_buffer = []
        self.recv_buffer = ""

        self.send("005 {0} *HOST*".format(self.token))

    def fileno(self):
        return self.socket.fileno()

    def send(self, message):
        self.send_buffer.append(message + "\r\n")

    def __repr__(self):
        return self.name or str(self.token)

class GameListener(object):
    def __init__(self, host, port, use_auth):
        self.host = host
        self.port = port

        self.authentication = use_auth
        self.authenticated_players = []

        self.is_running = False
        self.players = []

        self.socket = None

        self.statistics = {}

    def add_model(self, model):
        self.authenticated_players.append(model)

    def start(self):
        self.command_center = CommandCenter(self, self.authentication, self.authenticated_players)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)

        self.is_running = True

    def accept_player(self, read):
        client_sock, addr = read.accept()

        new_player = GamePlayer(client_sock, addr[0])
        self.players.append(new_player)

        print "New connection - unauthorized player"

    def delete(self, player):
        print "Disconnecting Player {0}".format(player)
        self.players.remove(player)

    def recv(self, player):
        data = player.socket.recv(1024)
        if not data: return self.delete(player)
        data = data.split("\r\n")
        data[0] = player.recv_buffer + data[0]
        if data[-1] == "":
            player.recv_buffer = data.pop()
        else:
            player.recv_buffer = ""
        for item in data:
                self.command_center.parse(player, item)

    def mainloop(self):
        try:
            self._mainloop()
        except KeyboardInterrupt:
            for player in self.players:
                player.socket.close()
            self.socket.close()

    def _mainloop(self):
        while self.is_running:
            read_sockets = self.players + [self.socket]
            playable_sockets = [player for player in self.players if player.send_buffer != []]

            _r, _w, _e = select.select(read_sockets, playable_sockets, self.players, 5)
            if _r:
                for player in _r:
                    if player == self.socket:
                        self.accept_player(player)
                    else:
                        self.recv(player)
            if _w:
                for player in _w:
                    for item in player.send_buffer:
                        player.socket.send(item)
                    player.send_buffer = []
            if _e:
                for player in _e:
                    print "Error in user {0}".format(player)
            else:
                # timeout
                pass
            self.command_center.garbage()
            # print "Garbage Collection || Players: {0}".format(len(self.players))
            # for player in self.players:
            #     print "\t {0} => {1}".format(player.name, player.token)

# CommandCenter(self, self.authentication, self.authenticated_players)

class MessageObject(object):
    def __init__(self, data):
        self.data = data.strip()
        self.args = data.split(" ")
        self.valid = True
        try:
            self.define(self.args)
        except Exception, e:
            print e
            self.valid = False

    def define(self, args):
        self.opcode = args[0]
        self.values = [i.replace("_"," ") for i in args[1].split("-")]
        self.vlen = len(self.values)
        self.token = args[2]

    def __repr__(self):
        return "<{0}:{1}>".format(self.name, self.data)

class CommandCenter(object):
    def __init__(self, glist, auth_b, auth_a):
        self.listener = glist
        self.use_auth = auth_b
        self.auth_models = auth_a
        self.opcodes = {
                    "001": (self.op_auth_req,1,False),
                    "002": (self.op_auth,3,False),
                    "003": (self.op_ping,1,False),
                    "004": (self.op_spacebar,1,True)
        }
        
        self.current_user = None
        self.current_user_c = 0
        self.current_user_t = time.time()

    def garbage(self):
        if time.time() - self.current_user_c > 30:
            self.current_user_c = (self.current_user_c + 1) % len(self.listener.players)
            self.current_user = self.listener.players[int(self.current_user_c)]
            self.current_user_t = time.time()
            

    def parse(self, player, incoming_message):
        message = MessageObject(incoming_message)
        if message.valid:
            if message.token == str(player.token):
                self.valid_parse(player, message)
            else:
                player.send("000 BAD_TOKEN *HOST*")
                print "Unauthorized token for message: {0}".format(message.data)
                # authed socket, unauthed token
        else:
            # message wasn't formatted correctly
            player.send("000 BAD_MSG *HOST*")
            print "Malformed message for message: {0}".format(message.data)
            # user isn't authed

    def valid_parse(self, player, message):
        opvl = self.opcodes.get(message.opcode)
        if opvl:
            if message.vlen == opvl[1] and (player.authed or not opvl[2]):
                opvl[0](player, message.values)
        else:
            player.send("000 BAD_OPCODE *HOST*")

    def op_auth(self, player, values):
        if self.use_auth:
            username, password, game_name = values
            for user in self.auth_models:
                if username == user.user and password == user.password:
                    player.name = game_name
                    player.authed = True
                    break
        else:
            player.name = values[2]
            player.authed = True
        if player.authed:
            player.send("008 LOGGED_IN *HOST*")
        else:
            player.send("008 NOT_LOGGED_IN *HOST*")


    def op_auth_req(self, player, values):
        player.send("007 REQUIRE_AUTH *HOST*")

    def op_ping(self, player, values):
        pass

    def op_spacebar(self, player, values):
        o = self.current_user_c
        if self.current_user == None:
            self.current_user = self.listener.players[0]
            self.current_user_c = time.time()
        if self.current_user == player:
            self.current_user_c = (self.current_user_c + 1) % len(self.listener.players)
            self.current_user = self.listener.players[int(self.current_user_c)]
            self.current_user_t = time.time()
        else:
            if time.time() - self.current_user_t > 30:
                self.current_user_c = (self.current_user_c + 1) % len(self.listener.players)
                self.current_user = self.listener.players[int(self.current_user_c)]
                self.current_user_t = time.time()
        if o != self.current_user_c:
            self.current_user.send("248 BELL *HOST*")
        print "{0}'s turn, {1} seconds remaining".format(self.current_user, 30-(time.time() -self.current_user_t))


if __name__ == "__main__":
    player1 = AuthenticatedPlayerModel("charles","charles123",None,False)
    player2 = AuthenticatedPlayerModel("cam","cam123",None,True)

    gameListener = GameListener("",8000, use_auth=True)

    gameListener.add_model(player1)
    gameListener.add_model(player2)

    gameListener.start()
    gameListener.mainloop()
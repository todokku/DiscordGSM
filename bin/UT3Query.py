# more info: https://wiki.unrealadmin.org/UT3_query_protocol
# author: TatLead

import socket
import time
import struct
import sys

class UT3Query(object):
    def __init__(self, addr, port=19132, timeout=5.0):
        self.ip, self.port, self.timeout = socket.gethostbyname(addr), port, timeout
        self.sock = False

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = False

    def connect(self):
        self.disconnect()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.ip, self.port))

    def getInfo(self):
        self.connect()

        # initial request
        self.sock.send(b'\xFE\xFD\x09\x10\x20\x30\x40')
        try:
            response = self.sock.recv(4096)
        except:
            return False

        # second request
        try:
            token = int(response[5:].decode('ascii').strip('\x00')).to_bytes(4, byteorder='big', signed=True)
        except:
            return False
        
        self.sock.send(b'\xFE\xFD\x00\x10\x20\x30\x40'+token+b'\xFF\xFF\xFF\x01')
        try:
            response = self.sock.recv(4096)
        except:
            return False

        response = response[16:].decode('utf8').split('\x00\x00\x01player_\x00\x00')
        # print(response) # useful output
        kv = response[0].split('\x00')
        
        result = {}
        for i in range(0, len(kv), 2):
            result[kv[i]] = kv[i+1]

        return result
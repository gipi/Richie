"""This was brutally ripped out of twisted"""

from include.utils import Base
import socket
from threading import Thread
from select import select
import os
import struct
import md5
import string
import random
import types

class Protocol(Base):

    def __init__(self, host, port, timeout=60, bufsize=60):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.bufsize = bufsize
        self.socket = self.fd = None
        self.connected = False

    def start(self):
        self.connect()

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        self.fd = self.socket.fileno()
        self.connected = True
        self.connectionMade()
        thread = Thread(target=self.poll, name=self.__class__.__name__)
        thread.setDaemon(True)
        thread.start()

    def stop(self):
        self.disconnect()
        self.connected = False
        self.socket.close()
        self.socket = self.fd = None

    close = stop

    def disconnect(self):
        pass

    def poll(self):
        while self.connected:
            try:
                if self.fd in select([self.fd], [], [], self.timeout)[0]:
                    data = os.read(self.fd, self.bufsize)
                    if len(data):
                        self.dataReceived(data)
            except:
                self.connected = False

    def connectionMade(self):
        pass

    def dataReceived(self, data):
        pass

    def send(self, data):
        self.socket.send(data)

    write = send


class OSCARUser:

    def __init__(self, name, warn, tlvs):
        self.name = name
        self.warning = warn
        self.flags = []
        self.caps = []
        for k,v in tlvs.items():
            if k == 1:
                v=struct.unpack('!H',v)[0]
                for o, f in [(1,'trial'),
                             (2,'unknown bit 2'),
                             (4,'aol'),
                             (8,'unknown bit 4'),
                             (16,'aim'),
                             (32,'away'),
                             (1024,'activebuddy')]:
                    if v&o: self.flags.append(f)
            elif k == 2:
                self.memberSince = struct.unpack('!L',v)[0]
            elif k == 3:
                self.onSince = struct.unpack('!L',v)[0]
            elif k == 4:
                self.idleTime = struct.unpack('!H',v)[0]
            elif k == 5:
                pass
            elif k == 6:
                if v[2] == '\x00':
                    self.icqStatus = 'online'
                elif v[2] == '\x01':
                    self.icqStatus = 'away'
                elif v[2] == '\x02':
                    self.icqStatus = 'dnd'
                elif v[2] == '\x04':
                    self.icqStatus = 'out'
                elif v[2] == '\x10':
                    self.icqStatus = 'busy'
                else:
                    self.icqStatus = 'unknown'
            elif k == 10:
                self.icqIPaddy = socket.inet_ntoa(v)
            elif k == 12:
                self.icqRandom = v
            elif k == 13:
                caps=[]
                while v:
                    c=v[:16]
                    if c==CAP_ICON: caps.append("icon")
                    elif c==CAP_IMAGE: caps.append("image")
                    elif c==CAP_VOICE: caps.append("voice")
                    elif c==CAP_CHAT: caps.append("chat")
                    elif c==CAP_GET_FILE: caps.append("getfile")
                    elif c==CAP_SEND_FILE: caps.append("sendfile")
                    elif c==CAP_SEND_LIST: caps.append("sendlist")
                    elif c==CAP_GAMES: caps.append("games")
                    else: caps.append(("unknown",c))
                    v=v[16:]
                caps.sort()
                self.caps=caps
            elif k == 14: pass
            elif k == 15:
                self.sessionLength = struct.unpack('!L',v)[0]
            elif k == 16:
                self.sessionLength = struct.unpack('!L',v)[0]
            elif k == 30:
                pass
            else:
                pass

    def __str__(self):
        s = '<OSCARUser %s' % self.name
        o = []
        if self.warning!=0: o.append('warning level %s'%self.warning)
        if hasattr(self, 'flags'): o.append('flags %s'%self.flags)
        if hasattr(self, 'sessionLength'): o.append('online for %i minutes' % (self.sessionLength/60,))
        if hasattr(self, 'idleTime'): o.append('idle for %i minutes' % self.idleTime)
        if self.caps: o.append('caps %s'%self.caps)
        if o:
            s=s+', '+', '.join(o)
        s=s+'>'
        return s


class SSIGroup:

    def __init__(self, name, tlvs = {}):
        self.name = name
        self.usersToID = {}
        self.users = []

    def findIDFor(self, user):
        return self.usersToID[user]

    def addUser(self, buddyID, user):
        self.usersToID[user] = buddyID
        self.users.append(user)
        user.group = self

    def oscarRep(self, groupID, buddyID):
        tlvData = TLV(0xc8, reduce(lambda x,y:x+y, [struct.pack('!H',self.usersToID[x]) for x in self.users]))
        return struct.pack('!H', len(self.name)) + self.name + struct.pack('!HH', groupID, buddyID) + '\000\001' + tlvData


class SSIBuddy:

    def __init__(self, name, tlvs = {}):
        self.name = name
        self.tlvs = tlvs
        for k,v in tlvs.items():
            if k == 0x013c:
                self.buddyComment = v
            elif k == 0x013d:
                actionFlag = ord(v[0])
                whenFlag = ord(v[1])
                self.alertActions = []
                self.alertWhen = []
                if actionFlag&1:
                    self.alertActions.append('popup')
                if actionFlag&2:
                    self.alertActions.append('sound')
                if whenFlag&1:
                    self.alertWhen.append('online')
                if whenFlag&2:
                    self.alertWhen.append('unidle')
                if whenFlag&4:
                    self.alertWhen.append('unaway')
            elif k == 0x013e:
                self.alertSound = v

    def oscarRep(self, groupID, buddyID):
        tlvData = reduce(lambda x,y: x+y, map(lambda (k,v):TLV(k,v), self.tlvs.items())) or '\000\000'
        return struct.pack('!H', len(self.name)) + self.name + struct.pack('!HH', groupID, buddyID) + '\000\000' + tlvData


class OscarConnection(Protocol):

    def connectionMade(self):
        self.state=""
        self.seqnum=0
        self.buf=''
        self.stopKeepAliveID = None
        self.setKeepAlive(4*60)

    def connectionLost(self, reason):
        self.stopKeepAlive()

    def sendFLAP(self,data,channel = 0x02):
        header="!cBHH"
        self.seqnum=(self.seqnum+1)%0xFFFF
        seqnum=self.seqnum
        head=struct.pack(header,'*', channel,
                         seqnum, len(data))
        self.write(head+str(data))

    def readFlap(self):
        header="!cBHH"
        if len(self.buf)<6: return
        flap=struct.unpack(header,self.buf[:6])
        if len(self.buf)<6+flap[3]: return
        data,self.buf=self.buf[6:6+flap[3]],self.buf[6+flap[3]:]
        return [flap[1],data]

    def dataReceived(self,data):
        self.buf=self.buf+data
        flap=self.readFlap()
        while flap:
            func=getattr(self,"oscar_%s"%self.state,None)
            state=func(flap)
            if state:
                self.state=state
            flap=self.readFlap()

    def setKeepAlive(self,t):
        self.keepAliveDelay=t
        self.stopKeepAlive()

    def sendKeepAlive(self):
        self.sendFLAP("",0x05)
        #self.stopKeepAliveID = reactor.callLater(self.keepAliveDelay, self.sendKeepAlive)

    def stopKeepAlive(self):
        if self.stopKeepAliveID:
            self.stopKeepAliveID.cancel()
            self.stopKeepAliveID = None

    def disconnect(self):
        self.sendFLAP('', 0x04)


class SNACBased(OscarConnection):
    snacFamilies = {
    }

    def __init__(self,cookie):
        self.cookie=cookie
        self.lastID=0
        self.supportedFamilies = ()
        self.requestCallbacks={}

    def sendSNAC(self,fam,sub,data,flags=[0,0]):
        reqid=self.lastID
        self.lastID=reqid+1
        self.sendFLAP(SNAC(fam,sub,reqid,data))

    def _ebDeferredError(self, error, fam, sub, data):
        pass

    def sendSNACnr(self,fam,sub,data,flags=[0,0]):
        self.sendFLAP(SNAC(fam,sub,0x10000*fam+sub,data))

    def oscar_(self,data):
        self.sendFLAP("\000\000\000\001"+TLV(6,self.cookie), 0x01)
        return "Data"

    def oscar_Data(self,data):
        snac=readSNAC(data[1])
        if self.requestCallbacks.has_key(snac[4]):
            d = self.requestCallbacks[snac[4]]
            del self.requestCallbacks[snac[4]]
            if snac[1]!=1:
                d.callback(snac)
            else:
                d.errback(snac)
            return
        func=getattr(self,'oscar_%02X_%02X'%(snac[0],snac[1]),None)
        if not func:
            self.oscar_unknown(snac)
        else:
            func(snac[2:])
        return "Data"

    def oscar_unknown(self,snac):
        pass

    def oscar_01_03(self, snac):
        numFamilies = len(snac[3])/2
        self.supportedFamilies = struct.unpack("!"+str(numFamilies)+'H', snac[3])
        d = ''
        for fam in self.supportedFamilies:
            if self.snacFamilies.has_key(fam):
                d=d+struct.pack('!2H',fam,self.snacFamilies[fam][0])
        self.sendSNACnr(0x01,0x17, d)

    def oscar_01_0A(self,snac):
        pass

    def oscar_01_18(self,snac):
        self.sendSNACnr(0x01,0x06,"")

    def clientReady(self):
        d = ''
        for fam in self.supportedFamilies:
            if self.snacFamilies.has_key(fam):
                version, toolID, toolVersion = self.snacFamilies[fam]
                d = d + struct.pack('!4H',fam,version,toolID,toolVersion)
        self.sendSNACnr(0x01,0x02,d)


class BOSConnection(SNACBased):
    snacFamilies = {
        0x01:(3, 0x0110, 0x059b),
        0x13:(3, 0x0110, 0x059b),
        0x02:(1, 0x0110, 0x059b),
        0x03:(1, 0x0110, 0x059b),
        0x04:(1, 0x0110, 0x059b),
        0x06:(1, 0x0110, 0x059b),
        0x08:(1, 0x0104, 0x0001),
        0x09:(1, 0x0110, 0x059b),
        0x0a:(1, 0x0110, 0x059b),
        0x0b:(1, 0x0104, 0x0001),
        0x0c:(1, 0x0104, 0x0001)
    }
    capabilities = None

    def __init__(self,server,port,username,cookie):
        SNACBased.__init__(self,cookie)
        self.username=username
        self.profile = None
        self.awayMessage = None
        self.services = {}
        Protocol.__init__(self, server, port)
        if not self.capabilities:
            self.capabilities = [CAP_CHAT]

    def parseUser(self,data,count=None):
        l=ord(data[0])
        name=data[1:1+l]
        warn,foo=struct.unpack("!HH",data[1+l:5+l])
        warn=int(warn/10)
        tlvs=data[5+l:]
        if count:
            tlvs,rest = readTLVs(tlvs,foo)
        else:
            tlvs,rest = readTLVs(tlvs), None
        u = OSCARUser(name, warn, tlvs)
        if rest == None:
            return u
        else:
            return u, rest

    def oscar_01_05(self, snac, d = None):
        tlvs = readTLVs(snac[3][2:])
        service = struct.unpack('!H',tlvs[0x0d])[0]
        ip = tlvs[5]
        cookie = tlvs[6]
        #c = protocol.ClientCreator(reactor, serviceClasses[service], self, cookie, d)

        def addService(x):
            self.services[service] = x
        c.connectTCP(ip, 5190)

    def oscar_01_07(self,snac):
        self.sendSNACnr(0x01,0x08,"\x00\x01\x00\x02\x00\x03\x00\x04\x00\x05")
        self.initDone()
        self.sendSNACnr(0x13,0x02,'')
        self.sendSNACnr(0x02,0x02,'')
        self.sendSNACnr(0x03,0x02,'')
        self.sendSNACnr(0x04,0x04,'')
        self.sendSNACnr(0x09,0x02,'')

    def oscar_01_10(self,snac):
        skip = struct.unpack('!H',snac[3][:2])[0]
        newLevel = struct.unpack('!H',snac[3][2+skip:4+skip])[0]/10
        if len(snac[3])>4+skip:
            by = self.parseUser(snac[3][4+skip:])
        else:
            by = None
        self.receiveWarning(newLevel, by)

    def oscar_01_13(self,snac):
        pass

    def oscar_02_03(self, snac):
        tlvs = readTLVs(snac[3])
        self.maxProfileLength = tlvs[1]

    def oscar_03_03(self, snac):
        tlvs = readTLVs(snac[3])
        self.maxBuddies = tlvs[1]
        self.maxWatchers = tlvs[2]

    def oscar_03_0B(self, snac):
        self.updateBuddy(self.parseUser(snac[3]))

    def oscar_03_0C(self, snac):
        self.offlineBuddy(self.parseUser(snac[3]))

    def oscar_04_05(self, snac):
        self.sendSNACnr(0x04,0x02,'\x00\x00\x00\x00\x00\x0b\x1f@\x03\xe7\x03\xe7\x00\x00\x00\x00')

    def oscar_04_07(self, snac):
        data = snac[3]
        cookie, data = data[:8], data[8:]
        channel = struct.unpack('!H',data[:2])[0]
        data = data[2:]
        user, data = self.parseUser(data, 1)
        tlvs = readTLVs(data)
        if channel == 1:
            flags = []
            multiparts = []
            for k, v in tlvs.items():
                if k == 2:
                    while v:
                        v = v[2:]
                        messageLength, charSet, charSubSet = struct.unpack('!3H', v[:6])
                        messageLength -= 4
                        message = [v[6:6+messageLength]]
                        if charSet == 0:
                            pass
                        elif charSet == 2:
                            message.append('unicode')
                        elif charSet == 3:
                            message.append('iso-8859-1')
                        elif charSet == 0xffff:
                            message.append('none')
                        if charSubSet == 0xb:
                            message.append('macintosh')
                        if messageLength > 0: multiparts.append(tuple(message))
                        v = v[6+messageLength:]
                elif k == 3:
                    flags.append('acknowledge')
                elif k == 4:
                    flags.append('auto')
                elif k == 6:
                    flags.append('offline')
                elif k == 8:
                    iconLength, foo, iconSum, iconStamp = struct.unpack('!LHHL',v)
                    if iconLength:
                        flags.append('icon')
                        flags.append((iconLength, iconSum, iconStamp))
                elif k == 9:
                    flags.append('buddyrequest')
                elif k == 0xb:
                    pass
                elif k == 0x17:
                    flags.append('extradata')
                    flags.append(v)
                else:
                    pass
            self.receiveMessage(user, multiparts, flags)
        elif channel == 2:
            status = struct.unpack('!H',tlvs[5][:2])[0]
            requestClass = tlvs[5][10:26]
            moreTLVs = readTLVs(tlvs[5][26:])
            if requestClass == CAP_CHAT:
                exchange = struct.unpack('!H',moreTLVs[10001][:2])[0]
                name = moreTLVs[10001][3:-2]
                instance = struct.unpack('!H',moreTLVs[10001][-2:])[0]
                if not self.services.has_key(SERVICE_CHATNAV):
                    self.connectService(SERVICE_CHATNAV,1)
                else:
                    self.services[SERVICE_CHATNAV].getChatInfo(exchange, name, instance)
            elif requestClass == CAP_SEND_FILE:
                if moreTLVs.has_key(11):
                    return
                name = moreTLVs[10001][9:-7]
                desc = moreTLVs[12]
                self.receiveSendFileRequest(user, name, desc, cookie)
            else:
                pass
        else:
            pass

    def _cbGetChatInfoForInvite(self, info, user, message):
        apply(self.receiveChatInvite, (user,message)+info)

    def oscar_09_03(self, snac):
        tlvs = readTLVs(snac[3])
        self.maxPermitList = tlvs[1]
        self.maxDenyList = tlvs[2]

    def oscar_0B_02(self, snac):
        self.reportingInterval = struct.unpack('!H',snac[3][:2])[0]

    def oscar_13_03(self, snac):
        pass

    def requestSelfInfo(self):
        self.sendSNAC(0x01, 0x0E, '')

    def _cbRequestSelfInfo(self, snac, d):
        d.callback(self.parseUser(snac[5]))

    def initSSI(self):
        return self.sendSNAC(0x13, 0x02, '')

    def _cbInitSSI(self, snac, d):
        return {}

    def requestSSI(self, timestamp = 0, revision = 0):
        return self.sendSNAC(0x13, 0x05,
            struct.pack('!LH',timestamp,revision))

    def _cbRequestSSI(self, snac, args = ()):
        if snac[1] == 0x0f:
            return
        itemdata = snac[5][3:]
        if args:
            revision, groups, permit, deny, permitMode, visibility = args
        else:
            version, revision = struct.unpack('!BH', snac[5][:3])
            groups = {}
            permit = []
            deny = []
            permitMode = None
            visibility = None
        while len(itemdata)>4:
            nameLength = struct.unpack('!H', itemdata[:2])[0]
            name = itemdata[2:2+nameLength]
            groupID, buddyID, itemType, restLength = struct.unpack('!4H', itemdata[2+nameLength:10+nameLength])
            tlvs = readTLVs(itemdata[10+nameLength:10+nameLength+restLength])
            itemdata = itemdata[10+nameLength+restLength:]
            if itemType == 0:
                groups[groupID].addUser(buddyID, SSIBuddy(name, tlvs))
            elif itemType == 1:
                g = SSIGroup(name, tlvs)
                if groups.has_key(0): groups[0].addUser(groupID, g)
                groups[groupID] = g
            elif itemType == 2:
                permit.append(name)
            elif itemType == 3:
                deny.append(name)
            elif itemType == 4:
                if not tlvs.has_key(0xcb):
                    continue
                permitMode = {1:'permitall',2:'denyall',3:'permitsome',4:'denysome',5:'permitbuddies'}[ord(tlvs[0xca])]
                visibility = {'\xff\xff\xff\xff':'all','\x00\x00\x00\x04':'notaim'}[tlvs[0xcb]]
            elif itemType == 5:
                pass
            else:
                pass
        timestamp = struct.unpack('!L',itemdata)[0]
        if not timestamp:
            pass
        return (groups[0].users,permit,deny,permitMode,visibility,timestamp,revision)

    def activateSSI(self):
        self.sendSNACnr(0x13,0x07,'')

    def startModifySSI(self):
        """
        tell the OSCAR server to be on the lookout for SSI modifications
        """
        self.sendSNACnr(0x13,0x11,'')

    def addItemSSI(self, item, groupID = None, buddyID = None):
        """
        add an item to the SSI server.  if buddyID == 0, then this should be a group.
        this gets a callback when it's finished, but you can probably ignore it.
        """
        if not groupID:
            groupID = item.group.group.findIDFor(item.group)
        if not buddyID:
            buddyID = item.group.findIDFor(item)
        return self.sendSNAC(0x13,0x08, item.oscarRep(groupID, buddyID))

    def modifyItemSSI(self, item, groupID = None, buddyID = None):
        if not groupID:
            groupID = item.group.group.findIDFor(item.group)
        if not buddyID:
            buddyID = item.group.findIDFor(item)
        return self.sendSNAC(0x13,0x09, item.oscarRep(groupID, buddyID))

    def delItemSSI(self, item, groupID = None, buddyID = None):
        if not groupID:
            groupID = item.group.group.findIDFor(item.group)
        if not buddyID:
            buddyID = item.group.findIDFor(item)
        return self.sendSNAC(0x13,0x0A, item.oscarRep(groupID, buddyID))

    def endModifySSI(self):
        self.sendSNACnr(0x13,0x12,'')

    def setProfile(self, profile):
        """
        set the profile.
        send None to not set a profile (different from '' for a blank one)
        """
        self.profile = profile
        tlvs = ''
        if self.profile:
            tlvs =  TLV(1,'text/aolrtf; charset="us-ascii"') + TLV(2,self.profile)
        tlvs = tlvs + TLV(5, ''.join(self.capabilities))
        self.sendSNACnr(0x02, 0x04, tlvs)

    def setAway(self, away = None):
        self.awayMessage = away
        tlvs = TLV(3,'text/aolrtf; charset="us-ascii"') + TLV(4,away or '')
        self.sendSNACnr(0x02, 0x04, tlvs)

    def setIdleTime(self, idleTime):
        self.sendSNACnr(0x01, 0x11, struct.pack('!L',idleTime))

    def sendMessage(self, user, message, wantAck = 0, autoResponse = 0, offline = 0 ):
        data = ''.join([chr(random.randrange(0, 127)) for i in range(8)])
        data = data + '\x00\x01' + chr(len(user)) + user
        if not type(message) in (types.TupleType, types.ListType):
            message = [[message,]]
            if type(message[0][0]) == types.UnicodeType:
                message[0].append('unicode')
        messageData = ''
        for part in message:
            charSet = 0
            if 'unicode' in part[1:]:
                charSet = 2
            elif 'iso-8859-1' in part[1:]:
                charSet = 3
            elif 'none' in part[1:]:
                charSet = 0xffff
            if 'macintosh' in part[1:]:
                charSubSet = 0xb
            else:
                charSubSet = 0
            messageData = messageData + '\x01\x01' + struct.pack('!3H',len(part[0])+4,charSet,charSubSet)
            messageData = messageData + part[0]
        data = data + TLV(2, '\x05\x01\x00\x03\x01\x01\x02'+messageData)
        if wantAck:
            data = data + TLV(3,'')
        if autoResponse:
            data = data + TLV(4,'')
        if offline:
            data = data + TLV(6,'')
        if wantAck:
            return self.sendSNAC(0x04, 0x06, data)
        self.sendSNACnr(0x04, 0x06, data)

    def _cbSendMessageAck(self, snac, user, message):
        return user, message

    def connectService(self, service, wantCallback = 0, extraData = ''):
        if wantCallback:
            self.sendSNAC(0x01,0x04,struct.pack('!H',service) + extraData)
        else:
            self.sendSNACnr(0x01,0x04,struct.pack('!H',service))

    def _cbConnectService(self, snac, d):
        d.arm()
        self.oscar_01_05(snac[2:], d)

    def createChat(self, shortName):
        if self.services.has_key(SERVICE_CHATNAV):
            return self.services[SERVICE_CHATNAV].createChat(shortName)
        else:
            pass

    def joinChat(self, exchange, fullName, instance):
        return self.connectService(0x0e, 1, TLV(0x01, struct.pack('!HB',exchange, len(fullName)) + fullName +
                          struct.pack('!H', instance)))

    def _cbJoinChat(self, chat):
        del self.services[SERVICE_CHAT]
        return chat

    def warnUser(self, user, anon = 0):
        return self.sendSNAC(0x04, 0x08, '\x00'+chr(anon)+chr(len(user))+user)

    def _cbWarnUser(self, snac):
        oldLevel, newLevel = struct.unpack('!2H', snac[5])
        return oldLevel, newLevel

    def getInfo(self, user):
        return self.sendSNAC(0x02, 0x05, '\x00\x01'+chr(len(user))+user)

    def _cbGetInfo(self, snac):
        user, rest = self.parseUser(snac[5],1)
        tlvs = readTLVs(rest)
        return tlvs.get(0x02,None)

    def getAway(self, user):
        return self.sendSNAC(0x02, 0x05, '\x00\x03'+chr(len(user))+user)

    def _cbGetAway(self, snac):
        user, rest = self.parseUser(snac[5],1)
        tlvs = readTLVs(rest)
        return tlvs.get(0x04,None)

    def initDone(self):
        pass

    def updateBuddy(self, user):
        pass

    def offlineBuddy(self, user):
        pass

    def receiveMessage(self, user, multiparts, flags):
        pass

    def receiveWarning(self, newLevel, user):
        pass

    def receiveChatInvite(self, user, message, exchange, fullName, instance, shortName, inviteTime):
        pass

    def chatReceiveMessage(self, chat, user, message):
        pass

    def chatMemberJoined(self, chat, member):
        pass

    def chatMemberLeft(self, chat, member):
        pass

    def receiveSendFileRequest(self, user, file, description, cookie):
        pass


class OSCARService(SNACBased):

    def __init__(self, bos, cookie, d = None):
        SNACBased.__init__(self, cookie)
        self.bos = bos
        self.d = d

    def connectionLost(self, reason):
        for k,v in self.bos.services.items():
            if v == self:
                del self.bos.services[k]
                return

    def clientReady(self):
        SNACBased.clientReady(self)
        if self.d:
            self.d.callback(self)
            self.d = None


class ChatNavService(OSCARService):
    snacFamilies = {
        0x01:(3, 0x0010, 0x059b),
        0x0d:(1, 0x0010, 0x059b)
    }

    def oscar_01_07(self, snac):
        self.sendSNACnr(0x01, 0x08, '\000\001\000\002\000\003\000\004\000\005')
        self.sendSNACnr(0x0d, 0x02, '')

    def oscar_0D_09(self, snac):
        self.clientReady()

    def getChatInfo(self, exchange, name, instance):
        self.sendSNAC(0x0d,0x04,struct.pack('!HB',exchange,len(name)) + name + struct.pack('!HB',instance,2))

    def _cbGetChatInfo(self, snac, d):
        data = snac[5][4:]
        exchange, length = struct.unpack('!HB',data[:3])
        fullName = data[3:3+length]
        instance = struct.unpack('!H',data[3+length:5+length])[0]
        tlvs = readTLVs(data[8+length:])
        shortName = tlvs[0x6a]
        inviteTime = struct.unpack('!L',tlvs[0xca])[0]
        info = (exchange,fullName,instance,shortName,inviteTime)
        d.callback(info)

    def createChat(self, shortName):
        data = '\x00\x04\x06create\xff\xff\x01\x00\x03'
        data = data + TLV(0xd7, 'en')
        data = data + TLV(0xd6, 'us-ascii')
        data = data + TLV(0xd3, shortName)
        return self.sendSNAC(0x0d, 0x08, data)

    def _cbCreateChat(self, snac):
        exchange, length = struct.unpack('!HB',snac[5][4:7])
        fullName = snac[5][7:7+length]
        instance = struct.unpack('!H',snac[5][7+length:9+length])[0]
        return exchange, fullName, instance


class ChatService(OSCARService):
    snacFamilies = {
        0x01:(3, 0x0010, 0x059b),
        0x0E:(1, 0x0010, 0x059b)
    }

    def __init__(self,bos,cookie, d = None):
        OSCARService.__init__(self,bos,cookie,d)
        self.exchange = None
        self.fullName = None
        self.instance = None
        self.name = None
        self.members = None
    clientReady = SNACBased.clientReady

    def oscar_01_07(self,snac):
        self.sendSNAC(0x01,0x08,"\000\001\000\002\000\003\000\004\000\005")
        self.clientReady()

    def oscar_0E_02(self, snac):
        data = snac[3]
        self.exchange, length = struct.unpack('!HB',data[:3])
        self.fullName = data[3:3+length]
        self.instance = struct.unpack('!H',data[3+length:5+length])[0]
        tlvs = readTLVs(data[8+length:])
        self.name = tlvs[0xd3]
        self.d.callback(self)

    def oscar_0E_03(self,snac):
        users=[]
        rest=snac[3]
        while rest:
            user, rest = self.bos.parseUser(rest, 1)
            users.append(user)
        if not self.fullName:
            self.members = users
        else:
            self.members.append(users[0])
            self.bos.chatMemberJoined(self,users[0])

    def oscar_0E_04(self,snac):
        user=self.bos.parseUser(snac[3])
        for u in self.members:
            if u.name == user.name:
                self.members.remove(u)
        self.bos.chatMemberLeft(self,user)

    def oscar_0E_06(self,snac):
        data = snac[3]
        user,rest=self.bos.parseUser(snac[3][14:],1)
        tlvs = readTLVs(rest[8:])
        message=tlvs[1]
        self.bos.chatReceiveMessage(self,user,message)

    def sendMessage(self,message):
        tlvs=TLV(0x02,"us-ascii")+TLV(0x03,"en")+TLV(0x01,message)
        self.sendSNAC(0x0e,0x05,
                      "\x46\x30\x38\x30\x44\x00\x63\x00\x00\x03\x00\x01\x00\x00\x00\x06\x00\x00\x00\x05"+
                      struct.pack("!H",len(tlvs))+
                      tlvs)

    def leaveChat(self):
        self.stop()


class OscarAuthenticator(OscarConnection):
    host = 'login.oscar.aol.com'
    port = 5190
    BOSClass = BOSConnection

    def __init__(self,username,password,deferred=None,icq=0):
        self.username=username
        self.password=password
        self.deferred=deferred
        self.icq=icq
        Protocol.__init__(self, self.host, self.port)

    def oscar_(self,flap):
        if not self.icq:
            self.sendFLAP("\000\000\000\001", 0x01)
            self.sendFLAP(SNAC(0x17,0x06,0,
                               TLV(TLV_USERNAME,self.username)+
                               TLV(0x004B,'')))
            self.state="Key"
        else:
            encpass=encryptPasswordICQ(self.password)
            self.sendFLAP('\000\000\000\001'+
                          TLV(0x01,self.username)+
                          TLV(0x02,encpass)+
                          TLV(0x03,'ICQ Inc. - Product of ICQ (TM).2001b.5.18.1.3659.85')+
                          TLV(0x16,"\x01\x0a")+
                          TLV(0x17,"\x00\x05")+
                          TLV(0x18,"\x00\x12")+
                          TLV(0x19,"\000\001")+
                          TLV(0x1a,"\x0eK")+
                          TLV(0x14,"\x00\x00\x00U")+
                          TLV(0x0f,"en")+
                          TLV(0x0e,"us"),0x01)
            self.state="Cookie"

    def oscar_Key(self,data):
        snac=readSNAC(data[1])
        key=snac[5][2:]
        encpass=encryptPasswordMD5(self.password,key)
        self.sendFLAP(SNAC(0x17,0x02,0,
                           TLV(TLV_USERNAME,self.username)+
                           TLV(TLV_PASSWORD,encpass)+
                           TLV(0x004C, '')+
                           TLV(TLV_CLIENTNAME,"AOL Instant Messenger (SM), version 4.8.2790/WIN32")+
                           TLV(0x0016,"\x01\x09")+
                           TLV(TLV_CLIENTMAJOR,"\000\004")+
                           TLV(TLV_CLIENTMINOR,"\000\010")+
                           TLV(0x0019,"\000\000")+
                           TLV(TLV_CLIENTSUB,"\x0A\xE6")+
                           TLV(0x0014,"\x00\x00\x00\xBB")+
                           TLV(TLV_LANG,"en")+
                           TLV(TLV_COUNTRY,"us")+
                           TLV(TLV_USESSI,"\001")))
        return "Cookie"

    def oscar_Cookie(self,data):
        snac=readSNAC(data[1])
        if self.icq:
            i=snac[5].find("\000")
            snac[5]=snac[5][i:]
        tlvs=readTLVs(snac[5])
        if tlvs.has_key(6):
            self.cookie=tlvs[6]
            server,port=string.split(tlvs[5],":")
            self.connectToBOS(server, int(port))
        elif tlvs.has_key(8):
            errorcode=tlvs[8]
            errorurl=tlvs[4]
            if errorcode=='\000\030':
                error="You are attempting to sign on again too soon.  Please try again later."
            elif errorcode=='\000\005':
                error="Invalid Username or Password."
            else: error=repr(errorcode)
            self.error(error,errorurl)
        else:
            pass
        return "None"

    def oscar_None(self,data):
        pass

    def connectToBOS(self, server, port):
        self.proto = self.BOSClass(server, port, self.username, self.cookie)
        self.proto.bot = self.bot
        self.proto.start()
        self.stop()

    def error(self,error,url):
        if self.deferred: self.deferred.errback((error,url))
        print 'stopping because of error()'
        self.stop()


FLAP_CHANNEL_NEW_CONNECTION = 0x01
FLAP_CHANNEL_DATA = 0x02
FLAP_CHANNEL_ERROR = 0x03
FLAP_CHANNEL_CLOSE_CONNECTION = 0x04
SERVICE_CHATNAV = 0x0d
SERVICE_CHAT = 0x0e
serviceClasses = {
    SERVICE_CHATNAV:ChatNavService,
    SERVICE_CHAT:ChatService
}
TLV_USERNAME = 0x0001
TLV_CLIENTNAME = 0x0003
TLV_COUNTRY = 0x000E
TLV_LANG = 0x000F
TLV_CLIENTMAJOR = 0x0017
TLV_CLIENTMINOR = 0x0018
TLV_CLIENTSUB = 0x001A
TLV_PASSWORD = 0x0025
TLV_USESSI = 0x004A
CAP_ICON = '\011F\023FL\177\021\321\202"DEST\000\000'
CAP_VOICE = '\011F\023AL\177\021\321\202"DEST\000\000'
CAP_IMAGE = '\011F\023EL\177\021\321\202"DEST\000\000'
CAP_CHAT = 't\217$ b\207\021\321\202"DEST\000\000'
CAP_GET_FILE = '\011F\023HL\177\021\321\202"DEST\000\000'
CAP_SEND_FILE = '\011F\023CL\177\021\321\202"DEST\000\000'
CAP_GAMES = '\011F\023GL\177\021\321\202"DEST\000\000'
CAP_SEND_LIST = '\011F\023KL\177\021\321\202"DEST\000\000'
CAP_SERV_REL = '\011F\023IL\177\021\321\202"DEST\000\000'


def logPacketData(data):
    lines = len(data)/16
    if lines*16 != len(data): lines=lines+1
    for i in range(lines):
        d = tuple(data[16*i:16*i+16])
        hex = map(lambda x: "%02X"%ord(x),d)
        text = map(lambda x: (len(repr(x))>3 and '.') or x, d)

def SNAC(fam,sub,id,data,flags=[0,0]):
    header="!HHBBL"
    head=struct.pack(header,fam,sub,
                     flags[0],flags[1],
                     id)
    return head+str(data)

def readSNAC(data):
    header="!HHBBL"
    head=list(struct.unpack(header,data[:10]))
    return head+[data[10:]]

def TLV(type,value):
    header="!HH"
    head=struct.pack(header,type,len(value))
    return head+str(value)

def readTLVs(data,count=None):
    header="!HH"
    dict={}
    while data and len(dict)!=count:
        head=struct.unpack(header,data[:4])
        dict[head[0]]=data[4:4+head[1]]
        data=data[4+head[1]:]
    if not count:
        return dict
    return dict,data

def encryptPasswordMD5(password,key):
    m=md5.new()
    m.update(key)
    m.update(md5.new(password).digest())
    m.update("AOL Instant Messenger (SM)")
    return m.digest()

def encryptPasswordICQ(password):
    key=[0xF3,0x26,0x81,0xC4,0x39,0x86,0xDB,0x92,0x71,0xA3,0xB9,0xE6,0x53,0x7A,0x95,0x7C]
    bytes=map(ord,password)
    r=""
    for i in range(len(bytes)):
        r=r+chr(bytes[i]^key[i%len(key)])
    return r


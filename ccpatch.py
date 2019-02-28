#!/usr/bin/python3
from collections import defaultdict
import collections
import os
import sys
import mido
import pickle
import json
import time
import re

# TODO: Add additional editable property to values defaultdict with default value of False
# TODO: On channel change, set all values to editable and freeze all encoders
# TODO: Set value in channel to editable, and indicate LED, once relevant encoder has been tweaked
# TODO: Once all encoders corresponding to stored values have been tweaked
# TODO: Progress bar and tracking of synced encoders
# TODO: recall and store buttons should, if there are values for that channel,
#       lock encoders to new values, request user input on encoders, show progress bar.  
# TODO: As soon as all values are synced unlock all encoders
# TODO: Light up pads to indicate which encoders are still to be synced
# TODO: Light up pads to indicate encoder values as they are turned (e.g. 8-15: 1 pad lit, 16-23: 2 pads lit...)

#########################################################################################
#                                                                                       #
#   CCPatch - A command line tool to create, save, and load patches of Midi CC Vals     #
#                                                                                       #
#   Create a patch:     Execute ccpatch.py and tweak knobs                              #
#   Save a patch:       Send a sysex [7F,7F,06,01] message to ccpatch.py                #
#   Load a patch:       Pass filename to ccpatch.py:                                    #
#                           - Load values into memory                                   #
#                           - Broadcast the values to synths etc                        #
#                           - Set the values as current for the controller via sysex    #
#                                                                                       #
#   Stop:     0x58      Start:  0x59      Cntrl/Seq:   0x5A       ExtSync:   0x5B       #
#   Recall:   0x5C      Store:  0x5D      Shift:       0x5E       Chan:      0x5F       #
#                                                                                       #
#########################################################################################

CONTROLLER_DEVICE    =   "BeatStep"
INSTRUMENT_DEVICE    =   "in_from_ccpatch"
BLUE     =   0x10
MAGENTA  =   0x11

class CCPatch:
    curChan = 0x00 
    curCCMessage = None
    lastCCMessage = None
    controllerPort = None
    instrumentPort = None
    values = defaultdict(dict)
    pending = set()
    controlToEncoder = lambda self,c:c+20
    encoderToPosition = lambda self,c:c-31
    encoderToPad = lambda self,c:c+0x50
    sysexListeners = {}
    ccListeners = {}

    def configure(self):
        mido.set_backend('mido.backends.rtmidi')
        self.connectController()
        self.connectInstrument()

        # Listen for current global chan which will be requested next
        self.addSysexListener((0xF0,0x00, 0x20, 0x6b, 0x7F, 0x42, 0x02, 0x00, 0x40, 0x06, 0xF7),self.setCurChan)
        hexGetGlobalChan = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x01, 0x00, 0x40, 0x06]
        self.sendSysexToController(hexGetGlobalChan)

        # Beatstep transport stop
        self.addSysexListener((0xF0,0x7F,0x7F,0x06,0x01,0xF7), self.save)
        # Beatstep transport play
        #self.addSysexListener((0xF0,0x7F,0x7F,0x06,0x02,0xF7), self.getUserTweakage)

        # Listen for CC 0x34 from recall button to decrement,
        # set global midi channel, and then get some user tweaks to sync
        self.addCCListener((0x34), self.decrementChan)

        # Listen for CC 0x35 from store button to increment,
        # set global midi channel, and then get some user tweaks to sync
        self.addCCListener((0x35), self.incrementChan)

        # Set Beatstep recall button to CC switch mode
        hexSetRecallMMC = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x01, 0x5C, 0x08]
        self.sendSysexToController(hexSetRecallMMC)

        # Set Beatstep store button to CC switch mode
        hexSetRecallMMC = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x01, 0x5D, 0x08]
        self.sendSysexToController(hexSetRecallMMC)

        # Set Beatstep recall button CC control # to 0x34 
        hexSetRecallMMCx34 = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x03, 0x5C, 0x34]
        self.sendSysexToController(hexSetRecallMMCx34)

        # Set Beatstep store button CC control # to 0x35 
        hexSetStoreMMCx35 = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x03, 0x5D, 0x35]
        self.sendSysexToController(hexSetStoreMMCx35)

        hexGetGlobalChan = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x01, 0x00, 0x40, 0x06]
        self.sendSysexToController(hexGetGlobalChan)
        
    def sendSysexToController(self,sysex):
        try:
            self.controllerPort.send(mido.Message('sysex', data=sysex))
        except Exception as e:
            print("Error sending sysex to device")

    def setCurChan(self,value) :
        print("Setting channel to: "+str(value))
        self.curChan = value[0]

    def decrementChan(self,value):
        if self.curChan > 0: self.curChan -= 1 
        else: self.curChan = 15 

        hexSetGlobalChan = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x40, 0x06, self.curChan]
        self.sendSysexToController(hexSetGlobalChan)
        hexSetChanIndicator = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x10, 0x70+self.curChan, 0x11]
        self.sendSysexToController(hexSetChanIndicator)

        print("Decrementing global channel " + str(self.curChan+1))
        self.queueEncoders()

    def incrementChan(self,value):
        if self.curChan < 15:
            self.curChan += 1
        else:
            self.curChan = 0
        hexSetGlobalChan = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x40, 0x06, self.curChan]
        self.sendSysexToController(hexSetGlobalChan)
        hexSetChanIndicator = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x10, 0x70+self.curChan, 0x11]
        self.sendSysexToController(hexSetChanIndicator)
        print("Incrementing global channel " + str(self.curChan+1))
        self.queueEncoders()

    
    # Compares sysex commands. Returns either False, or with an array of remaining unmatched bytes from sysex2
    # In the case of an exact match, returns an empty list
    def compareSysex(self,sysex_listener,sysex_message):
        # results array for return values in sysex message
        result = []

        # either sysex_listener or sysex_message could be longer than the other
        # if the listener is longer than the message then it won't match
        # so we may as well return false
        if len(sysex_listener) > len(sysex_message): return False

        # if we have an exact match then return an empty list for return vals
        if sysex_listener == sysex_message: return []

        # remove the trailing 0xF7 from sysex_listener, or else it may try to compare it
        sysex_listener = list(sysex_listener)
        sysex_listener.remove(0xF7)
        sysex_listener = tuple(sysex_listener)

        # if any bytes don't match now up to the length of sysex_listener then it's not a match
        for i in range(0,len(sysex_listener)):
            if sysex_listener[i] != sysex_message[i]: return False
      
        # loop through any remaining message bytes (except the trailing 0xF7), which don't appear in sysex_listener
        # These are result bytes
        for i in range(len(sysex_listener),len(sysex_message)):
            if (sysex_message[i] != 0xF7):
                result.append(sysex_message[i])

        return result

    def processCCListeners(self,message):
        for cc in self.ccListeners:
            if cc == message.control: 
                self.ccListeners[cc](message.value)

    def processSysexListeners(self,message):
        for sysex in self.sysexListeners:
            values = self.compareSysex(sysex,message.bytes())
            if values != False :
                if len(values) > 0:
                    self.sysexListeners[sysex](values)
                else:
                    self.sysexListeners[sysex]()

    def addSysexListener(self,message,function):
        print("resistering "+str(message))
        self.sysexListeners[message] = function

    def addCCListener(self,control,function):
        print("resistering "+str(control))
        self.ccListeners[control] = function

    def keyExists(self,key):
        return key in self.values.keys()

    def getPortName(self,pattern):
        for portName in mido.get_input_names()+mido.get_output_names():
            if re.search(pattern,portName):
                return portName

    def cleanName(self,name):
        return name[:name.rfind(' ')]

    def connectController(self):
        print("Attempting to connect to " + CONTROLLER_DEVICE + "...")
        try:
            device = self.getPortName(CONTROLLER_DEVICE)
            self.controllerPort = mido.open_ioport(device, callback=lambda m, cn=self.cleanName(device): self.onMessage(cn, m))
            print("Successfully connected to " + device)
        except Exception as e:
            print('Unable to open MIDI ports: {}'.format(CONTROLLER_DEVICE), file=sys.stderr)

    def connectInstrument(self):
        print("Attempting to connect to " + INSTRUMENT_DEVICE + "...")
        try:
            device = self.getPortName(INSTRUMENT_DEVICE)
            self.instrumentPort = mido.open_output(device)
            print("Successfully connected to " + device)
        except Exception as e:
            print('Unable to open MIDI output: {}'.format(INSTRUMENT_DEVICE), file=sys.stderr)

    def freezeEncoder(self,encoder,value):
        print("Freezing encoder: "+str(encoder)+", value: "+str(value))
        hexSetMin = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x04, encoder, value]
        hexSetMax = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x05, encoder, value]
        try:
            self.controllerPort.send(mido.Message('sysex', data=hexSetMin))
            self.controllerPort.send(mido.Message('sysex', data=hexSetMax))
        except Exception as e:
            print("Error sending sysex to device")

    def unfreezeEncoder(self,encoder):
        print("Unfreezing controller: "+str(encoder))
        hexSetMin = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x04, encoder, 0]
        hexSetMax = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x05, encoder, 127]
        try:
            self.controllerPort.send(mido.Message('sysex', data=hexSetMin))
            self.controllerPort.send(mido.Message('sysex', data=hexSetMax))
        except Exception as e:
            print("Error sending sysex to device")

    def freezeEncoders(self):
        for channeldata in self.values.items():
            for controldata in channeldata[1].items():
                channel = int(channeldata[0])
                control = int(controldata[0])
                value = int(controldata[1])
                encoder = self.controlToEncoder(control)
                self.freezeEncoder(encoder,value)
                print("Encoder values locked")
        self.getUserTweakage()

    def unfreezeEncoders(self):
        for channeldata in self.values.items():
            for controldata in channeldata[1].items():
                channel = int(channeldata[0])
                control = int(controldata[0])
                value = int(controldata[1])
                encoder = self.controlToEncoder(control)
                self.freezeEncoder(encoder,value)
                print("Encoder values locked")

    def queueEncoders(self):
        time.sleep(0.5)
        for channeldata in self.values.items():
            if channeldata[0] == self.curChan:
                print("cunt")
                for controldata in channeldata[1].items():
                    targetControl = int(controldata[0])
                    targetValue = int(controldata[1])
                    targetEncoder = self.controlToEncoder(targetControl)
                    targetEncoderPosition = self.encoderToPosition(targetEncoder)
                    targetIndicatorPad = self.encoderToPad(targetEncoder)
                    print("target indicator pad "+str(targetIndicatorPad))
                    self.pending.add(targetEncoder)
                    self.padLEDOn(targetIndicatorPad,BLUE)

        #while len(self.pending) > 0:
        #    print("waiting...")
            
    def padLEDOn(self, targetPad, color):
        hexSetEncoderIndicator = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x10, targetPad, color]
        self.sendSysexToController(hexSetEncoderIndicator)
        self.sendSysexToController(hexSetEncoderIndicator)


    def load(self,filename):
        print("Loading patch file "+filename)
        success = False
        if os.path.isfile(filename):
            try:
                with open(filename) as json_file:
                    dict = json.load(json_file)
                    self.values = defaultdict(defaultdict,dict)
                    success = True
            except:
                print("Error loading patch file: "+filename)
        else:
            print("Patch file "+filename+" does not exist")
        if (success):
            self.freezeEncoders()

    def save(self):
        filename = "patch-"+time.strftime("%Y%m%d%H%M")+".json"
        try:
            with open(filename, 'w') as f:
                json.dump(self.values, f)
        except:
            print("Error saving patch file")
            return
        print("Saved patch file "+filename+" to file...")

    def onMessage(self, name, message):
        if message.type == 'control_change':
            self.processCCListeners(message)
            self.lastCCMessage = None
            self.curCCMessage = (name, message.channel, message.control, message.value)
            if  self.curCCMessage != self.lastCCMessage and message.channel == self.curChan:
                self.values[self.curChan][message.control] = message.value
                self.lastCCMessage = self.curCCMessage
        elif message.type == 'sysex':         
            self.processSysexListeners(message)
        else:
            print(message)

patch = CCPatch()
patch.configure()

if len(sys.argv) > 1:
    patch.load(sys.argv[1])

while True:
    continue
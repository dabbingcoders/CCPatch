#!/usr/bin/python3
from collections import defaultdict
from threading import Thread
import collections
import os
import sys
import mido
import pickle
import json
import time
import re

# TODO: turn off LED, once relevant encoder has been tweaked
# TODO: In queueEncoders() freeze ALL encoders until out of tweak mode to prevent unwanted vals being stored
# TODO: Un-light pad LEDs once corresponding encoder has been set to lock value
# TODO: Create unfreezeAllEncoders() method
# TODO: Once all encoders corresponding to stored values have been tweaked, unfreeze all encoders
# TODO: Light up pads to indicate which encoders are still to be synced
# TODO: (nice to have) Light up pads to indicate encoder values as they are turned (e.g. 8-15: 1 pad lit, 16-23: 2 pads lit...)
# TODO: Leave LEDs corresponding to active encoders lit in blue while in 'play mode' (e.g. nothing frozen - something in pending) 
# TODO: When in calibration mode light up all active (and frozen) encoders in magenta
# TODO: What do we do when the encoder happens to already have the right value?
# TODO: Configure defaults to be helpful values - e.g. filter cutoff all the way open etc

# 29/03:

# recap:

# the encoders still need to be frozen for channels with pending values to be sync-ed
# We can't easily add an 'editable' property to the defaultdict of cc values
# so instead perhaps we need a list of pending encoders to be tweaked


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
RED      =  0x01
BLUE     =  0x10
MAGENTA  =  0x11
OFF      =  0x00
STOP     =  0x58
START    =  0x59
CTRLSEQ  =  0x5A
EXTSYNC  =  0x5B
RECALL   =  0x5C
STORE    =  0x5D
SHIFT    =  0x5E
CHAN     =  0x5F

class CCPatch:
    curChan = 0x00 
    curCCMessage = None
    lastCCMessage = None
    controllerPort = None
    instrumentPort = None
    values = defaultdict(dict)
    defaultValue = 64
    pending = set()
    controlMap =   {0x20:0x0C,0x21:0x0D,0x22:0x0E, 
                    0x24:0x0F,0x25:0x10,0x26:0x11,
                    0x28:0x12,0x29:0x13,0x2A:0x14,
                    0x2C:0x15,0x2D:0x16,0x2E:0x17}
    #print(list(mydict.keys())[list(mydict.values()).index(16)]) # Prints george
    #controlToEncoder = lambda self,c:c+20
    controlToEncoder = lambda self,c:list(self.controlMap.keys())[list(self.controlMap.values()).index(c)]
    #encoderToControl = lambda self,c:c-20
    encoderToControl = lambda self,e:self.controlMap[e]
    encoderToPad = lambda self,c:c+0x50
    #encoders = range(0x20, 0x30)
    encoders = (0x20,0x21,0x22, 0x24,0x25,0x26, 0x28,0x29,0x2a, 0x2c,0x2d,0x2e)
    channels = range(0,15)
    encodersFrozen = False
    defaultEncoderVal = 0x40
    sysexListeners = {}
    ccListeners = {}
    reservedCCs = range(0x34,0x41)
    defaultVals = { 0x20:64,0x21:127,0x22:0,0x23:0,
                    0x24:64,0x25:127,0x26:0,0x27:0,
                    0x28:64,0x29:127,0x2a:0,0x2b:0,
                    0x2c:64,0x2d:127,0x2e:0,0x2f:0 }
    padFuncs = {}

    def initVals(self):
        for channel in self.channels:
            for encoder in self.encoders:
                self.setCCVal(channel,self.encoderToControl(encoder),self.defaultVals[encoder])

    def doInit(self,val):
        self.init()

    def init(self):
        self.initVals()
        self.queueEncoders()
        self.freezeAllEncoders()

    def configure(self):
        self.padFuncs    = { #CTRLSEQ:self.doSomething,
                             EXTSYNC:self.doInit,
                             #RECALL:self.doSomething,
                             STORE:self.toggleFreezeEncoders,
                             SHIFT:self.decrementChan,
                             CHAN:self.incrementChan}

        mido.set_backend('mido.backends.rtmidi')
        self.connectController()
        self.connectInstrument()

        # Listen for current global chan which will be requested next
        self.addSysexListener((0xF0,0x00, 0x20, 0x6b, 0x7F, 0x42, 0x02, 0x00, 0x40, 0x06, 0xF7),self.setCurChan)
        hexGetGlobalChan = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x01, 0x00, 0x40, 0x06]
        self.sendSysexToController(hexGetGlobalChan)

        # Beatstep transport stop
        self.addSysexListener((0xF0,0x7F,0x7F,0x06,0x01,0xF7), self.save)

        self.assignPadFunctions()

        hexGetGlobalChan = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x01, 0x00, 0x40, 0x06]
        self.sendSysexToController(hexGetGlobalChan)

    def assignPadFunctions(self):
        i = 0
        for padData in self.padFuncs.items():
            self.setPadToSwitchMode(padData[0])
            self.assignControlToPad(padData[0],self.reservedCCs[i])
            self.addCCListener((self.reservedCCs[i]),padData[1])
            i=i+1

    def setPadToSwitchMode(self,pad):
        self.sendSysexToController([0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x01, pad, 0x08])

    def assignControlToPad(self,pad,control):
        self.sendSysexToController([0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x03, pad, control])

    def sendSysexToController(self,sysex):
        #print(str(sysex))
        #try:
        self.controllerPort.send(mido.Message('sysex', data=sysex))
       #except Exception as e:
        #    print("Error sending sysex to device")

    def setCurChan(self,value) :
        print("Setting channel to: "+str(value))
        self.curChan = value[0]

    def decrementChan(self,value):
        self.emptyPending()
        if self.curChan > 0: self.curChan -= 1 

        hexSetGlobalChan = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x40, 0x06, self.curChan]
        self.sendSysexToController(hexSetGlobalChan)
        hexSetChanIndicator = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x10, 0x70+self.curChan, 0x11]
        self.sendSysexToController(hexSetChanIndicator)

        print("Decrementing global channel " + str(self.curChan+1))
        if self.hasCCVals(self.curChan):
            self.queueEncoders()
            self.freezeAllEncoders()

    def incrementChan(self,value):
        self.emptyPending()
        if self.curChan < 15: self.curChan += 1
        #else: self.curChan = 0

        hexSetGlobalChan = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x40, 0x06, self.curChan]
        self.sendSysexToController(hexSetGlobalChan)
        hexSetChanIndicator = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x10, 0x70+self.curChan, 0x11]
        self.sendSysexToController(hexSetChanIndicator)
        print("Incrementing global channel " + str(self.curChan+1))
        if self.hasCCVals(self.curChan):
            self.queueEncoders()
            self.freezeAllEncoders()

    
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
        #print("registering "+str(message))
        self.sysexListeners[message] = function

    def addCCListener(self,control,function):
        #print("registering "+str(control))
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
        #print("Freezing encoder: "+str(encoder)+", value: "+str(value))
        minVal = value
        maxVal = value
        if value < 127:
            minVal = value
            maxVal = value+1
        else:
           minVal = value-1
           maxVal = value

        hexSetMin = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x04, encoder, minVal]
        hexSetMax = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x05, encoder, maxVal]
        try:
            self.controllerPort.send(mido.Message('sysex', data=hexSetMin))
            self.controllerPort.send(mido.Message('sysex', data=hexSetMax))
        except Exception as e:
            print(str(hexSetMin))
            print(str(hexSetMax))
            print("Error sending sysex to device")

    def unfreezeEncoder(self,encoder):
        #print("Unfreezing controller: "+str(encoder))
        hexSetMin = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x04, encoder, 0]
        hexSetMax = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x05, encoder, 127]
        try:
            self.controllerPort.send(mido.Message('sysex', data=hexSetMin))
            self.controllerPort.send(mido.Message('sysex', data=hexSetMax))
        except Exception as e:
            print("Error sending sysex to device")

    def toggleFreezeEncoders(self,val):
        if self.encodersFrozen:
            self.unfreezeAllEncoders()
        else:
            self.queueEncoders()
            self.freezeAllEncoders()

    # freeze all encoders, regardless of whether the corresponding control has a stored value
    def freezeAllEncoders(self):
        print("Freezing all encoders")
        for encoder in self.encoders:
            control = self.encoderToControl(encoder)
            value = self.getCCVal(self.curChan, control)
            pad = self.encoderToPad(encoder)
            self.freezeEncoder(encoder,value)
        self.encodersFrozen = True
        self.refreshLEDs()

    def unfreezeAllEncoders(self):
        print("Unfreezing all encoders")
        for encoder in self.encoders:
            self.unfreezeEncoder(encoder)
        self.encodersFrozen = False
        self.emptyPending()
        self.refreshLEDs()

    def emptyPending(self):
        self.pending = set()

    def queueEncoders(self):
        for channeldata in self.values.items():
            #print(channeldata)
            # get the values for current (probably new) channel
            if channeldata[0] == self.curChan:
                for controldata in channeldata[1].items():
                    targetControl = int(controldata[0])
                    targetValue = int(controldata[1])
                    targetEncoder = self.controlToEncoder(targetControl)
                    targetIndicatorPad = self.encoderToPad(targetEncoder)
                    self.pending.add(targetEncoder)

    def padLED(self, targetPad, color):
        hexSetEncoderIndicator = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x10, targetPad, color]
        self.sendSysexToController(hexSetEncoderIndicator)
        #self.sendSysexToController(hexSetEncoderIndicator)

    def load(self,filename):
        print("Loading patch file "+filename)
        success = False
        if os.path.isfile(filename):
            #try:
            with open(filename) as json_file:
                dict = json.load(json_file)
                self.values = defaultdict(defaultdict,dict)
                success = True
            #except:
            #    print("Error loading patch file: "+filename)
        else:
            print("Patch file "+filename+" does not exist")
        if (success):
            self.queueEncoders()
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
        if message.type not in ['control_change','sysex']:
           return 
        if message.type == 'control_change':
            self.processCCListeners(message)
            self.lastCCMessage = None
            self.curCCMessage = (name, message.channel, message.control, message.value)
            # only listen to new, unreserved CCs on the current channel
            if self.curCCMessage != self.lastCCMessage and message.channel == self.curChan and message.control not in self.reservedCCs:
                print(message)
                if len(self.pending) == 0:
                    #print("setting value to: "+str(message.value))
                    self.setCCVal(self.curChan,message.control,message.value)
                    self.lastCCMessage = self.curCCMessage
                else:
                    encoder = self.controlToEncoder(message.control)
                    print(str(encoder))
                    self.removeFromPendingIfCalibrated(encoder, message.value)
                    #self.removeFromPendingIfCalibrated(self.controlToEncoder(message.control), message.value)
        elif message.type == 'sysex':         
            self.processSysexListeners(message)
        else:
            print(message)
        thread = Thread(target = self.refreshLEDs)
        thread.start()    
        #self.refreshLEDs()

    # Check to see if control is pending calibration, if it's value has been correctly calibrated
    # and if so, remove it from the pending list and turn off the corresponding pad LED.
    def removeFromPendingIfCalibrated(self, encoder, value):
        if encoder in self.pending:
            if value == self.getCCVal(self.curChan, self.encoderToControl(encoder)):
                self.pending.remove(encoder)
                indicatorPad = self.encoderToPad(encoder)
                return True
        return False
                
    def hasCCVal(self, channel, control):
        return control in self.values[channel]

    def hasCCVals(self, channel):
        return len(self.values[channel])

    def getCCVal(self, channel, control):
        if control in self.values[channel]:
            return self.values[self.curChan][control]
        else:
            return self.defaultEncoderVal

    def setCCVal(self, channel, control, value):
        self.values[channel][control] = value

    def refreshLEDs(self):
        # sleep 1 sec, or else indicator pads won't stay lit
        time.sleep(0.25)
        for encoder in self.encoders:
            control = self.encoderToControl(encoder)
            value = self.getCCVal(self.curChan, control)
            pad = self.encoderToPad(encoder)
            if encoder in self.pending:
                self.padLED(pad,MAGENTA)
            elif self.hasCCVal(self.curChan,control):
                if self.encodersFrozen:
                    self.padLED(pad,BLUE)
                else:
                    self.padLED(pad,OFF)

            else:
                self.padLED(pad,OFF)

patch = CCPatch()
patch.configure()

patch.init()

if len(sys.argv) > 1:
    patch.load(sys.argv[1])

while True:
    continue

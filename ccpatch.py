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

# idea: Store a dictionary of midi commands to listen for and callback functions
# to execute

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
#########################################################################################

CONTROLLER_DEVICE    =   "BeatStep"
INSTRUMENT_DEVICE    =   "in_from_ccpatch"


class CCPatch:
    currCCMessage = None
    lastCCMessage = None
    controllerPort = None
    instrumentPort = None
    values = defaultdict(dict)
    pending = None
    controlToEncoder = lambda self,c:c+20
    encoderToPosition = lambda self,c:c-31
    sysexListeners = {}

    def cleanName(self,name):
        return name[:name.rfind(' ')]

    def configure(self):
        mido.set_backend('mido.backends.rtmidi')
        self.connectController()
        self.connectInstrument()
        # Beatstep transport stop
        self.addSysexListener((0xF0,0x7F,0x7F,0x06,0x01,0xF7), self.save)
        # Beatstep transport play
        self.addSysexListener((0xF0,0x7F,0x7F,0x06,0x02,0xF7), self.getUserTweakage)

    # Compares sysex commands. Returns either False, or with an array of remaining unmatched bytes from sysex2
    # In the case of an exact match, returns an empty list
    def compareSysex(self,sysex1,sysex2):
        print(str(sysex1))
        print(str(sysex2))
        result = []
        for i in range(0,len(sysex1)):
            if sysex1[i] != sysex2[i]:
                return False
        if len(sysex2) > len(sysex1):
            for i in range(len(sysex1),len(sysex2)):
                result[i] = sysex2[i]
        return result


    # we need to compare tuples, identify an exact match, and in the event of a partial match,
    # get the values of the remaining bytes
    def processSysexListeners(self,message):
        for sysex in self.sysexListeners:
            print(str(sysex))
            print("-->"+str(self.compareSysex(sysex,message.bytes())))
            print(str(message.bytes()))

            #if set(sysex) == message.bytes():
            #if self.compareSysex(sysex,message.bytes())
            #    print("Exact sysex command identified. Executing "+str(self.sysexListeners[sysex]))
            #elif set(sysex).issubset(message.bytes()):
            #    print("Sysex command identified. Executing with args: "+str(self.sysexListeners[sysex]))
                
    def addSysexListener(self,message,function):
        print("resistering "+str(message))
        self.sysexListeners[message] = function

    def keyExists(self,key):
        return key in self.values.keys()

    def getPortName(self,pattern):
        for portName in mido.get_input_names()+mido.get_output_names():
            if re.search(pattern,portName):
                return portName

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

    def makePending(self):
        # Copy self.values to self.pending
        self.pending = self.values
        return self.pending

    def getPending(self):
        if (self.pending != None):
            return self.pending
        else:
            return makePending()

    def unpendCC(self,channel,control):
        print("Unpending channel: "+channel+" control:"+control)
        #remove channel/control pair from self.pending

    def getCurrentChannel(self):
        hexGetChan = [0x00, 0x20, 0x6B, 0x7F, 0x42, 0x01, 0x00, 0x50, 0x0B]
        try:
            self.controllerPort.send(mido.Message('sysex', data=hexGetChan))
        except Exception as e:
            print("Error sending sysex to device")


    def getUserTweakage(self):
        channel = input("Which channel?:")
#        print("Please tweak the following controllers")
#        for channeldata in self.values.items():
#            for controldata in channeldata[1].items():
#                targetChannel = int(channeldata[0])
#                targetControl = int(controldata[0])
#                targetValue = int(controldata[1])
#                targetEncoder = self.controlToEncoder(targetControl)
#                targetEncoderPosition = self.encoderToPosition(targetEncoder)

        print(str(self.getPending()))
        while (self.getPending()):
            if self.currCCMessage != self.lastCCMessage:
                if (self.mapVal(self.currCCMessage[1],self.currCCMessage[2],self.currCCMessage[3])):
                    self.unpendCC(self.currCCMessage[1],self.currCCMessage[2])
                    print("Channel: "+currCCMessage[1]+" Control: "+currCCMessage[2]+" Value: "+currCCMessage[3])
                    print(str(self.getPending()))


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
            self.lastCCMessage = None
            self.currCCMessage = (name, message.channel, message.control, message.value)
            if  self.currCCMessage != self.lastCCMessage:
                self.values[message.channel-1][message.control] = message.value
                self.lastCCMessage = self.currCCMessage
        # listen for save and broadcast commands from beatstep stop and play buttons

        elif message.type == 'sysex':         
            self.processSysexListeners(message)
        #elif message.type == 'sysex' and message.bytes()[3]==6:
           # if (message.bytes()[4]==1):
           #     self.save()
           # elif (message.bytes()[4]==2):
           #     self.getCurrentChannel()
        else:
            print(message)

patch = CCPatch()
patch.configure()

if len(sys.argv) > 1:
    patch.load(sys.argv[1])

while True:
    continue


#        for channeldata in self.values.items():
#            for controldata in channeldata[1].items():
#                channel = int(channeldata[0])
#                control = int(controldata[0])
#                value = int(controldata[1])
#                encoder = self.controlToEncoder(control)
#
#                setMinSyx=self.cmdBeatstep(0x02,channel,encoder,value)
#                setMaxSyx=self.cmdBeatstep(0x02,channel,encoder,value)

                # need to listen for CC messages from beatstep
                # maybe this process should be executed in the load method
                # yup i think it should

                #while True:
                #    for msg in self.controllerPort.iter_pending():
                #        print(msg)

                #print("\nPlease tweak encoder #: "+str(self.controlToEncoder(control)))

                # We're going to need to wait and listen for CC messages

#                while (self.currMessage is not None
#                        and self.currMessage.type is not "control_change"
#                        and self.currMessage.channel is not channel and
#                        self.currMessage.control is not control):
#                       x = 1
#               print("\nThank you!")
                #self.controllerPort.send(mido.Message('sysex', data=setMinSyx))
                #self.controllerPort.send(mido.Message('sysex', data=setMinSyx))

# Set minimum val of encoders F0 00 20 6B 7F 42 02 00 04 20 23 F7
#        print("Broadcasting current patch...")
#        for channeldata in self.values.items():
#            for controldata in channeldata[1].items():
#                self.instrumentPort.send(mido.Message('control_change', channel=int(channeldata[0]),control=int(controldata[0]),value=int(controldata[1])))

                #F0 00 20 6B 7F 42 02 00 00 2x vv F7
                #240 00, 32, 107, 127, 66, 02, 00, 00, 20, 127
                #self.controllerPort.send(mido.Message('sysex', data=[0,32,107,127,66,2,0,0,20,127]))
                #self.controllerPort.send(mido.Message('sysex', data=[1,2,3]))
                #self.controllerPort.send(mido.Message.from_bytes([0xF0, 0x00, 0x20, 0x6B, 0x7F,
                #                                 0x42, 0x02, 0x00, 000, 0x20, 0x7F, 0xF7]))
                #F0 00 20 6B 7F 42 02 00 50 0B nn F7
                #self.controllerPort.send(mido.Message('sysex', data=[0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x50, 0x0B, 0x04, 0xF7]))
                #self.controllerPort.send(mido.Message('sysex', data=[0x00, 0x20, 0x6B, 0x7F, 0x42, 0x02, 0x00, 0x50, 0x0B, 0x04, 0x7F]))

                #self.controllerPort.send(mido.Message('note_on', note=0, velocity=56, time=6.2))

#        print("Please tweak the following controllers")
#        for channeldata in self.values.items():
#            for controldata in channeldata[1].items():
#                targetChannel = int(channeldata[0])
#                targetControl = int(controldata[0])
#                targetValue = int(controldata[1])
#                targetEncoder = self.controlToEncoder(targetControl)
#                targetEncoderPosition = self.encoderToPosition(targetEncoder)

    # This method needs to wait for the user to tweak each encoder associated with
    # each channel and control stored in self.values
    # self.values = [[chan > [control > value]]
    # If we are not to request each encoder on each channel, in order
    # then we need a way to track that each required [chan/controller] has been tweaked
    # We also need to indicate to the user which [chan/contoller]s still need to be tweaked

    # OK so thinking about this...
    # the beatstep is channel-agnostic when it comes to setting encoder values
    # so we need to set the values each time we change channel
    # We're also going to need to tell ccpatch each time, which channel we want
    # to sync the values for. This could be done with user input from input()

    # How are we going to kick getUserTweakage off?
    # Should the whole app just listen for some kind of midi event, and then
    # check the last played channel? Ooh no, wait... We can query the beatstep for the
    # current channel, and listen for the answer!
    # The script should then validate midi cc input to make sure the user
    # doesn't switch the channel mid-process
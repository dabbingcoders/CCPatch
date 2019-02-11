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
    controllerPort = None
    instrumentPort = None
    lastMessage = None
    currMessage = None
    values = defaultdict(dict)
    ccMap = {}
    for control in range(12,27):
        ccMap[control] = control+8
        
    def cleanName(self,name):
        return name[:name.rfind(' ')]

    def configure(self):
        mido.set_backend('mido.backends.rtmidi')
        self.connectController()
        self.connectInstrument()

    def getCurrentChannel(self):
        if self.currMessage == None: return 0
        return self.currMessage[1]
    
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

    def load(self,filename):
        print("Loading patch file "+filename)
        if os.path.isfile(filename):
            try:
                with open(filename) as json_file:  
                    dict = json.load(json_file)
                    self.values = defaultdict(defaultdict,dict)
            except:
                print("Error loading patch file: "+filename)
        else:
            print("Patch file "+filename+" does not exist")

    def save(self):
        filename = "patch-"+time.strftime("%Y%m%d%H%M")+".json" 
        try:
            with open(filename, 'w') as f:
                json.dump(self.values, f)
        except:
            print("Error saving patch file")
            return
        print("Saved patch file "+filename+" to file...")

    def cmdBeatstep(getset,param,controller,value):
        return self.controllerPort.send(mido.Message('sysex', data=[0xF0,0x00,0x20,0x6B,0x7F,0x42,getset,0x00,param,controller,value,0xF7]))

    def broadcast(self):
    
        # loop through patch values for each control on each channel
            # set the beatstep encoder min and max to the value in the patch
            # prompt the user to tweak the encoder
            # set the encoder min and max back to 0 and 127
            # prompt for the next encoder

        for channeldata in self.values.items():
            for controldata in channeldata[1].items():
                channel = int(channeldata[0])
                control = int(controldata[0])
                value = int(controldata[1])
                setMinSyx=cmdBeatstep(0x01,0x04,this.ccMap[control],value)
                setMaxSyx=cmdBeatstep(0x01,0x05,this.ccMap[control],value)


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


    def onMessage(self, name, message):
        if message.type == 'control_change': 
            self.lastCCMessage = None
            self.currCCMessage = (name, message.channel, message.control, message.value)
            if  self.currCCMessage != self.lastCCMessage:
                self.values[message.channel-1][message.control] = message.value
                self.lastCCMessage = self.currCCMessage
        elif message.type == 'sysex' and message.bytes()[3]==6:
            if (message.bytes()[4]==1):
                self.save()
            elif (message.bytes()[4]==2):
                patch.broadcast()
        else:
            print(message)

patch = CCPatch()
patch.configure()

if len(sys.argv) > 1:
    patch.load(sys.argv[1])

while True:
    continue

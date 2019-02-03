from collections import defaultdict
import os
import sys
import mido
import pickle
import json
import time


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

MIDI_CC_NUMS = range(12,28)

class CCPatch:
    lastMessage = None
    currMessage = None
    values = defaultdict(dict)

    def configure(self):
        self.connect()

    def getCurrentChannel(self):
        if self.currMessage == None: return 0
        return self.currMessage[1]
    
    def keyExists(self,key):
        return key in self.values.keys()
    
    def connect(self):
        print('Connecting MIDI devices')
        mido.set_backend('mido.backends.rtmidi')
        controllerNames = mido.get_input_names()

        if not controllerNames: return

        for name in controllerNames:
            try:
                cleanName = name[:name.rfind(' ')]
                print("Connecting " + cleanName)
                mido.open_input(name, callback=lambda m, cn=cleanName: self.onMessage(cn, m))
            except Exception as e:
                print('Unable to open MIDI input: {}'.format(name), file=sys.stderr)

    def load(self,filename):
        print("Loading patch file "+filename)
        if os.path.isfile(filename):
            try:
                with open(filename) as json_file:  
                    self.values = json.load(json_file)
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

    def broadcast(self):
        print("Broadcasting current patch...")

    def onMessage(self, name, message):
        if message.type == 'control_change': 
            self.lastCCMessage = None
            self.currCCMessage = (name, message.channel, message.control, message.value)
            if  self.currCCMessage != self.lastCCMessage:
                print("CH: %03d CC: %03d VL: %03d" % (message.channel,message.control,message.value))
                self.values[message.channel][message.control] = message.value
                self.lastCCMessage = self.currCCMessage
        elif message.type == 'sysex' and message.bytes()[3]==6:
            if (message.bytes()[4]==1):
                self.save()
            elif (message.bytes()[4]==2):
                print("Transmitting CC vals...")
        else:
            print(message)

patch = CCPatch()
patch.configure()

if len(sys.argv) > 1:
    patch.load(sys.argv[1])

while True:
    continue
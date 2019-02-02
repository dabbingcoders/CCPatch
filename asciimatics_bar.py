import sys
import mido
import pickle
import json

MIDI_CC_NUMS = range(12,28)

class CCPatch:
    lastMessage = None
    currMessage = None
    deviceInfo = {}
    values = dict()

    def configure(self):
        self.connect()
        self.save()

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

    def save(self):
        with open('deviceinfo.json', 'w') as f:
            json.dump(self.deviceInfo, f)
        print('Done!')

    def onMessage(self, name, message):
        if message.type != 'control_change': return 
        self.lastMessage = None
        self.currMessage = (name, message.channel, message.control, message.value)
        if  self.currMessage != self.lastMessage:
            self.values[message.channel,message.control] = message.value
            self.lastMessage = self.currMessage

patch = CCPatch()
patch.configure()
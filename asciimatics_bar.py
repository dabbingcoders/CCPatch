from asciimatics.effects import Print
from asciimatics.renderers import BarChart, FigletText
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.exceptions import ResizeScreenError
import sys
import math
import time
from random import randint
import mido
import sys
import pickle
import json

MIDI_CC_NUMS = range(12,28)

def getCCValFuncs():
    funcs = []
    for control in MIDI_CC_NUMS:
       # print(control)
        if patch.keyExists((patch.getCurrentChannel(),control)):
            print("bingo")
            funcs.append(lambda: patch.values[patch.getCurrentChannel(),control])
        else:
            funcs.append(lambda: 0)
    return funcs

def demo(screen):
    scenes = []
    
    effects = [
        Print(screen,
              BarChart(
                      18, 64,
                      getCCValFuncs(),
                      colour=[c for c in range(1, 8)],
                      bg=[c for c in range(1, 8)],
                      scale=128.0,
                      axes=BarChart.X_AXIS,
                      intervals=8,
                      labels=True,
                      border=False),
                  x=2, y=3, transparent=False, speed=2)
    ]

    scenes.append(Scene(effects, -1))
    screen.play(scenes, stop_on_resize=True)


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
            #pickle.dump(self.deviceInfo, f)

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

while True:
    #print(patch.values)
    #x = 1
    try:
        Screen.wrapper(demo)
        sys.exit(0)
    except ResizeScreenError:
        pass
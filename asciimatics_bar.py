from asciimatics.effects import Print
from asciimatics.renderers import BarChart, FigletText
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.exceptions import ResizeScreenError
import sys
import math
import time
from random import randint

MIDI_CC_NUMS = range(12,28)

def getLastCCVal(ccNum):
    return lambda: ccNum*4

def getCCValFuncs():
    funcs = []
    for i in MIDI_CC_NUMS:
        funcs.append(getLastCCVal(i))
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


while True:
    try:
        Screen.wrapper(demo)
        sys.exit(0)
    except ResizeScreenError:
        pass

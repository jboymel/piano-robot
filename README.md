# Robotic Piano Actuator System
Northwestern University SURG 2026 — Jordan Boymel\
Advisor: Dr. Brenna Argall

## Overview
A modular robotic actuation platform targeting one octave of piano keys
(13 keys, C to C) using 24V solenoid actuators mounted on an 80/20
T-slot aluminum frame with 3D-printed PLA brackets. Designed for
millisecond-scale timing precision and repeatable force-controllable
keypresses, with architecture scalable to 88 keys.

## Research question
How can a modular robotic actuation system be designed and controlled
to achieve millisecond-scale timing precision and repeatable,
force-controllable keypresses across multiple piano keys?

## System overview
- Actuators: 24V push solenoids (JF-1039B), one per key
- Controller: Arduino Mega 2560, C++ firmware
- Drive circuit: IRLB8721 MOSFETs with FR307 flyback protection
- Sensing: FSR 402 (force) + TCST2103 photointerrupter (timing onset)
- Frame: 80/20 1010 T-slot aluminum + 3D-printed PLA brackets
- Power: 24V 1500W switching supply (62.5A)

## Performance targets
- Mean onset error < 10ms, standard deviation < 5ms (50 trials/key)
- Force coefficient of variation < 15% across all keys at fixed dynamic level

## Repository structure
- /firmware — Arduino C++ sketches
- /matlab — characterization and analysis scripts
- /cad — SolidWorks/Fusion 360 files and exported STLs
- /data — processed trial datasets and summary CSVs
- /docs — bill of materials, wiring documentation
- /media — photos and demo videos

## Status
Week 1 — bench fixture assembly and single-channel characterization

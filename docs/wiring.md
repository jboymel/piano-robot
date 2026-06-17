# Wiring documentation

## Single-channel bench test circuit

### Arduino Mega pin assignments
- Pin 2: PWM output to 100 ohm gate resistor to MOSFET gate
- Pin 18: photointerrupter onset interrupt (RISING)
- Pin A0: FSR analog voltage input
- 5V pin: sensor power rail
- GND pin: common ground rail

### Power rail (fully in series)
PSU positive to inline 10A fuse to e-stop (NC) to +24V rail
PSU negative to common GND rail

### MOSFET channel (IRLZ44N, flat face: G·D·S = left·middle·right)
- Gate (left): 100 ohm from pin 2, 10k pull-down to GND, expose header pin for probe access
- Drain (middle): solenoid bottom wire, FR307 diode anode
- Source (right): GND rail

### Solenoid
- Top wire: +24V rail
- Bottom wire: MOSFET drain

### FR307 flyback diode
- Cathode (stripe): +24V rail
- Anode: MOSFET drain
- Spans solenoid: cathode at top node, anode at bottom/drain node

### FSR 402 voltage divider (5V circuit)
5V to FSR to junction node to A0
Junction node to 10k to GND
Starting value 10k, calibrate with 4.7k/22k/47k as needed

### Photointerrupter TCST2103 (verify pinout against datasheet)
- Pin 1 LED anode: 270 ohm to 5V
- Pin 2 LED cathode: GND
- Pin 3 collector: pin 18 + 10k pull-up to 5V
- Pin 4 emitter: GND
- Beam broken = HIGH = onset detected

### Decoupling capacitors
- 100uF electrolytic (35V+): across +24V/GND near MOSFET cluster
- 470-1000uF electrolytic (35V+): across +24V/GND near PSU connection
- 0.1uF ceramic: across Arduino 5V/GND near sensors

## Full 13-key array pin assignments
- PWM channels: pins 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 44
- Interrupt pins: 18, 19
- FSR inputs: A0, A1 (1-2 sensors moved between keys)

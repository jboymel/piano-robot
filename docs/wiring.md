# Wiring

This page covers the final 84-key system: seven identical octave boards, driven by an Arduino Mega. Part values and designators match the [BOM](bom.md).

## Overview

The laptop connects to the Arduino over USB, which carries both serial data and 5 V power. The Arduino drives Board 1, and two separate chains run from each board to the next:
- **Signal chain:** 5-conductor ribbon between the 1×5 headers (J13 in, J14 out).
- **Power chain:** heavy wire between the 2-position power screw terminals (J15 in, J16 out). The 24 V supply connects to Board 1's J15.

## Arduino Mega → Board 1

| Arduino pin | Signal | Notes |
|---|---|---|
| 51 (MOSI) | DATA | Hardware SPI |
| 52 (SCK) | CLOCK | Hardware SPI |
| 8 | LATCH | 74HC595 RCLK |
| 5V | 5 V logic | Powers the shift registers on all 7 boards |
| GND | GND | Common with the 24 V supply ground |

The 5 V logic rail for the entire chain comes from the laptop's USB through the Arduino. No separate 5 V supply is used.

## Shift-register chain (per board)

- **U1 → U2:** U1's serial out (QH′) feeds U2's serial in (SER).
- **Board → board:** U2's QH′ leaves on the DATA line of the outgoing ribbon and feeds U1 SER on the next board. CLOCK and LATCH are shared by every board.
- **SRCLR** is tied to +5 V (never cleared). **OE** is tied to GND (outputs always enabled).
- 12 of U1/U2's 16 outputs drive MOSFET gates. The other 4 are unused.
- Both 74HC595s sit in DIP-16 sockets. Check the pin-1 notch when you insert them (see [the chain-failure write-up](power-debugging.md)).

Across 7 boards this forms one 112-bit shift chain. 84 of those bits are keys.

## Solenoid channel (×12 per board)

- **Gate:** 220 Ω series resistor from the 74HC595 output, and a 10 kΩ pull-down to GND that holds the MOSFET off while the logic is unpowered or floating.
- **Drain:** one side of the solenoid (through its screw terminal) and the FR307 anode.
- **Source:** GND.
- **Solenoid:** the other side goes to +24 V.
- **FR307 flyback diode:** cathode (stripe) at +24 V, anode at the drain. It clamps the inductive kick when the MOSFET turns off.
- **IRLZ44N pinout** (TO-220, flat face toward you): Gate · Drain · Source, left to right.

## Power

- A single 24 V, 1500 W (62.5 A) switching supply feeds Board 1's J15. Each board's J16 feeds the next board's J15.
- Each solenoid draws about 400 mA. Firmware caps simultaneous keys at 20, which is about 8 A on the bus.
- Common ground: the 24 V supply ground, the board grounds, and the Arduino ground are all tied together.
- On-board protection and bulk capacitance: SMBJ28A TVS diode (D1), 1000 µF (C2) and 10 µF (C1) electrolytic, and 0.1 µF ceramic (C3, C4). See the KiCad schematic for placement.

---

## Prototype (superseded)

Before the octave boards, a single-key bench circuit drove one IRLZ44N directly from an Arduino PWM pin (100 Ω gate resistor, 10 kΩ pull-down). The flyback arrangement was the same as above. The bench also included an FSR 402 and a TCST2103 photointerrupter for planned force and timing measurements. These were not used in the final build, and no data was collected with them. The direct-drive approach needed one Arduino pin per key, which is why the design moved to the shift-register chain.

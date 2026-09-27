# Debugging the 7-board chain failure

## Symptom
Three octave boards chained together worked as expected: shift-register outputs were verified with indicator LEDs. With all seven boards connected, the system stopped working reliably. The 5 V logic rail sagged along the chain, from 5.0 V at the first board to about 4 V or lower at the far end, and the Arduino browned out.

## First hypothesis: power budget (wrong)
The symptoms pointed to an undersized logic supply. The 5 V rail came from the laptop through the Arduino's USB port, which supplies about 500 mA, and it was daisy-chained to every board through the 1×5 signal headers. The theory was that 7 boards' worth of logic load, plus the voltage drop across six header connections, exceeded what USB could supply.

I planned a fix to match: a dedicated external 5 V supply for the shift registers, with the Arduino's USB powering only the Mega. Before building that, I worked through a diagnostic checklist:

1. Confirm the Arduino still uploads and runs over USB with nothing attached.
2. Check continuity pin-to-pin across the 1×5 headers, and from VCC/GND to each shift register's pins.
3. Measure the 5 V rail at each board with the chain connected.

## Actual cause: one reversed 74HC595
One of the shift registers had been put in upside down. After it was reinstalled in the correct orientation, the problem went away. The full 7-board chain now runs from the laptop's USB 5 V, with no separate supply.

A CMOS IC installed backwards has its supply pins swapped with signal pins, and it can conduct heavily through its internal protection structures. That loads the rail, which matches the sag and brownouts seen here.

## Takeaways
- **Rule out assembly errors before redesigning.** The symptoms fit a power-budget story well enough that I nearly added a supply the system didn't need.
- **Scaling in steps localized the fault.** Three boards worked and seven didn't, which narrowed where to look.
- **Visual inspection is a cheap first check.** IC orientation (the pin-1 dot and notch against the silkscreen) takes seconds to verify on every board.

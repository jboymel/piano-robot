/* ============================================================================
 * piano_driver.ino
 * 84-key (C1..B7) solenoid piano actuator
 *
 * Hardware: Arduino Mega 2560
 *           7 octave PCBs daisy-chained, 2x 74HC595 per board
 *           74HC595 outputs -> IRLZ44N gate (logic HIGH = solenoid energized)
 *           24 V solenoid rail, 400 mA/solenoid, ~65 A supply
 *
 * The Mega does no musical work. It receives a full 84-bit keyboard state from
 * the host over USB serial, applies safety limits, and clocks the chain.
 * All scheduling, tempo, and voice allocation happen in midi_player.py.
 * ========================================================================== */

#include <SPI.h>
#include <string.h>

/* ---------------------------------------------------------------------------
 * PIN MAP (Arduino Mega 2560)
 * ------------------------------------------------------------------------ */
const uint8_t PIN_DATA = 51;  // MOSI. Hardware SPI data out. Fixed by the
                              // ATmega2560 -- cannot be reassigned.
                              // Wire to DATA_IN (SER of U1 on the FIRST board).
const uint8_t PIN_CLOCK = 52; // SCK. Hardware SPI clock. Also fixed.
                              // Wire to CLOCK (SRCLK), bussed to all 14 registers.
const uint8_t PIN_LATCH = 8;  // Plain digital output (no PWM needed).
                              // Wire to LATCH (RCLK), bussed to all 14 registers.
const uint8_t PIN_SS = 53;    // SPI slave-select. NOT wired to anything, but it
                              // must be configured as an output or the AVR SPI
                              // peripheral silently drops out of master mode.
const uint8_t PIN_LED = 13;   // Onboard LED (PWM-capable, used as plain digital).
                              // Lit whenever any solenoid is energized.

/* ---------------------------------------------------------------------------
 * KEYBOARD GEOMETRY
 * ------------------------------------------------------------------------ */
const uint8_t N_BOARDS = 7;                // one PCB per octave
const uint8_t N_KEYS = N_BOARDS * 12;      // C1 (MIDI 24) .. B7 (MIDI 107)
const uint8_t CHAIN_BYTES = N_BOARDS * 2;  // 14 bytes = 112 clocked bits
                                           // (12 notes + 4 dead bits per board)

// the board receiving DATA_IN directly from the Mega drives octave 1 (C1..B1)


/* ---------------------------------------------------------------------------
 * SAFETY LIMITS
 * ------------------------------------------------------------------------ */
const uint8_t  MAX_SIMULTANEOUS = 20;    // hard cap. 20 * 400 mA = 8 A of the 65 A.
                                         // The host applies a musical version of this
                                         // cap; this one is a dumb backstop that keeps
                                         // a buggy or malicious host from browning out
                                         // the rail. It keeps the lowest 20 keys.
const uint32_t MAX_ON_MS = 5000;         // per-key continuous energize limit. Set this
                                         // from your solenoid's duty-cycle rating.
                                         // A key that trips it is locked off until the
                                         // host releases it.
const uint32_t LINK_TIMEOUT_MS = 500;    // if the host goes quiet this long, drop
                                         // everything to prevemt a python crash
                                         // mid-chord leaving solenoids energized forever.

/* ---------------------------------------------------------------------------
 * WIRE PROTOCOL   0xAA 0x55 <11 payload bytes> <XOR checksum>
 * payload bit i (LSB-first within each byte) = key i, 0 = C1 ... 83 = B7
 * ------------------------------------------------------------------------ */
const uint8_t SYNC0 = 0xAA;
const uint8_t SYNC1 = 0x55;
const uint8_t PAYLOAD_BYTES = 11;  // ceil(84 / 8)
const uint32_t BAUD = 250000;      // exact on a 16 MHz AVR (0% error, unlike 115200)

/* ---------------------------------------------------------------------------
 * STATE
 * ------------------------------------------------------------------------ */
bool requested[N_KEYS];    // what keys were asked for
bool energized[N_KEYS];    // what is actually being driven after safety limits
uint32_t onsetMs[N_KEYS];  // when each key was energized, for MAX_ON_MS
bool thermalLock[N_KEYS];  // key exceeded MAX_ON_MS, held off until released
uint32_t lastFrameMs = 0;
bool linkUp = false;

/* ---------------------------------------------------------------------------
 * pushChain()
 *
 * Shift-register bit order:
 *
 *   A 74HC595 moves SER -> QA -> QB -> ... -> QH -> QH'. The FIRST bit clocked
 *   out therefore travels FURTHEST down the chain. With U1.QH' feeding U2.SER,
 *   the first 8 bits sent land in U2 and the last 8 land in U1.
 *
 *   Per board, transmit order (first sent -> last sent) maps to:
 *     U2.QH U2.QG U2.QF U2.QE  U2.QD U2.QC U2.QB U2.QA
 *     U1.QH U1.QG U1.QF U1.QE  U1.QD U1.QC U1.QB U1.QA
 *
 *   From the schematic, U1.QA..QH = C C# D D# E F F# G
 *                       U2.QA..QD = G# A A# B, and U2.QE..QH are unconnected.
 *
 *   So the first byte out of each board pair is:
 *     bit7..bit4 = pad (the 4 unused outputs), bit3..bit0 = B A# A G#
 *   and the second byte is:
 *     bit7..bit0 = G F# F E D# D C# C
 *
 *   Equivalently: semitone s (0=C..11=B) occupies bit s of the low byte for
 *   s < 8, and bit (s-8) of the high byte for s >= 8.
 *
 *   Across boards, the same "first sent travels furthest" rule means the board
 *   physically LAST in the chain must be transmitted FIRST.
 * ------------------------------------------------------------------------ */
void pushChain() {
  uint8_t frame[CHAIN_BYTES];
  uint8_t idx = 0;

  for (uint8_t k = 0; k < N_BOARDS; k++) {
    uint8_t board = N_BOARDS - 1 - k;
    

    uint8_t hi = 0;  // U2: pad, pad, pad, pad, B, A#, A, G#
    uint8_t lo = 0;  // U1: G, F#, F, E, D#, D, C#, C

    for (uint8_t s = 0; s < 12; s++) {
      if (!energized[board * 12 + s]) {
        continue;
      }

      if (s < 8) {
        lo |= (uint8_t)(1 << s);
      } else  {
        hi |= (uint8_t)(1 << (s - 8));
      }
    }

    frame[idx++] = hi;   // must go out before lo
    frame[idx++] = lo;
  }

  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0)); // 1 MHz is conservative for ribbon-cabled 74HC595s; could go higher

  for (uint8_t i = 0; i < CHAIN_BYTES; i++) {
    SPI.transfer(frame[i]);
  }
  SPI.endTransaction();

  digitalWrite(PIN_LATCH, HIGH); // RCLK is rising-edge triggered
  digitalWrite(PIN_LATCH, LOW);
}

/* ---------------------------------------------------------------------------
 * applySafety() -- turns `requested` into `energized`
 * ------------------------------------------------------------------------ */
void applySafety() {
  uint32_t now = millis();

  bool linkOk = linkUp && (now - lastFrameMs < LINK_TIMEOUT_MS);

  if (!linkOk) {
    memset(energized, 0, sizeof(energized));
    memset(thermalLock, 0, sizeof(thermalLock));
    return;
  }

  // A key that tripped MAX_ON_MS stays locked until the host actually releases it,
  // so it cannot turn back on immediately.
  for (uint8_t i = 0; i < N_KEYS; i++) {
    if (!requested[i]) {
      thermalLock[i] = false;
      onsetMs[i] = 0;
    }
  }

  uint8_t count = 0;
  for (uint8_t i = 0; i < N_KEYS; i++) {
    bool want = requested[i] && !thermalLock[i];

    if (want && count >= MAX_SIMULTANEOUS) {
      want = false;                       // backstop cap, bass-first
    } else if (want) {
      if (!energized[i]) {
        onsetMs[i] = now;                 // rising edge, start the clock
      } else if (now - onsetMs[i] > MAX_ON_MS) {
        thermalLock[i] = true;
        want = false;
      }
    }

    energized[i] = want;
    if (want) count++;
  }
}

/* ---------------------------------------------------------------------------
 * readSerial() -- non-blocking frame parser
 * ------------------------------------------------------------------------ */
void readSerial() {
  static uint8_t state = 0;
  static uint8_t buf[PAYLOAD_BYTES];
  static uint8_t n = 0;

  while (Serial.available()) {
    uint8_t b = Serial.read();

    switch (state) {
      case 0:
        if (b == SYNC0) {
          state = 1;
        }
        break;

      case 1:
        if (b == SYNC1) { 
          state = 2; 
          n = 0; 
        } else if (b == SYNC0) {
          state = 1; 
        } else { 
          state = 0; 
        }
        break;

      case 2:
        buf[n++] = b;
        if (n == PAYLOAD_BYTES) {
          state = 3;
        }
        break;

      case 3: {
        uint8_t sum = 0;
        for (uint8_t i = 0; i < PAYLOAD_BYTES; i++) {
          sum ^= buf[i];
        }

        if (sum == b) {
          for (uint8_t i = 0; i < N_KEYS; i++) {
            uint8_t byteIndex = i / 8;
            uint8_t bitIndex = i % 8;
            requested[i] = (buf[byteIndex] >> bitIndex) & 1;
          }
          lastFrameMs = millis();
          linkUp = true;
        }

        state = 0; // bad checksum: drop the frame, resync
        break;
      }
    }
  }
}

/* ------------------------------------------------------------------------ */
void setup() {
  pinMode(PIN_LATCH, OUTPUT);
  digitalWrite(PIN_LATCH, LOW);
  pinMode(PIN_SS, OUTPUT);
  pinMode(PIN_LED, OUTPUT);

  memset(requested, 0, sizeof(requested));
  memset(energized, 0, sizeof(energized));
  memset(onsetMs, 0, sizeof(onsetMs));
  memset(thermalLock, 0, sizeof(thermalLock));

  SPI.begin();
  pushChain();                            // flush power-up garbage out of the registers

  Serial.begin(BAUD);
}

void loop() {
  readSerial();
  applySafety();
  pushChain();   // ~112 us. Rewriting every pass is self-healing: a bit corrupted
                 // by noise on the ribbon cable is corrected within one loop.

  uint8_t on = 0;
  for (uint8_t i = 0; i < N_KEYS; i++) {
    if (energized[i]) {
      on++;
    }
  }
  digitalWrite(PIN_LED, on > 0 ? HIGH : LOW);
}

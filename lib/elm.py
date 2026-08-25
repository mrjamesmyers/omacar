"""A minimal, strictly read-only ELM327 client.

python-obd is the right tool for known PIDs. Prospecting is different: it
needs to set arbitrary headers, send raw service requests, and — crucially —
*see* negative responses. `7F 22 31` (requestOutOfRange) means "that PID does
not exist on this ECU", which is a completely different fact from silence,
which means "wrong header". python-obd collapses both to null.

Read-only is enforced here, at the bottom of the stack, rather than trusted
to callers.
"""
import time

import serial

# Services this client will ever emit. Everything else — 0x2E write, 0x2F
# input/output control, 0x31 routine control, 0x11 ECU reset, 0x14 clear
# diagnostic information, 0x85 control DTC setting — can change vehicle state
# or erase data, and has no place in a discovery tool.
READ_ONLY_SERVICES = {0x01, 0x02, 0x03, 0x06, 0x07, 0x09, 0x21, 0x22}

NRC = {
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x22: "conditionsNotCorrect",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x78: "responsePending",
}


class WriteAttempted(Exception):
    """Raised when something asks for a service that could change state."""


class Elm:
    def __init__(self, port, baudrate=38400, timeout=1.0):
        self.ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        self.header = None
        time.sleep(0.2)

    # -- transport ---------------------------------------------------------

    def raw(self, line, wait=0.0):
        """Send one line, read to the ELM prompt, return the reply lines."""
        self.ser.reset_input_buffer()
        self.ser.write((line + "\r").encode())
        self.ser.flush()
        buf, deadline = b"", time.time() + 5.0
        while time.time() < deadline:
            chunk = self.ser.read(256)
            if chunk:
                buf += chunk
                if b">" in buf:
                    break
            elif buf:
                break
        if wait:
            time.sleep(wait)
        text = buf.decode("ascii", "replace").replace("\r", "\n")
        return [ln.strip() for ln in text.split("\n") if ln.strip() and ln.strip() != ">"]

    def at(self, cmd):
        return self.raw("AT" + cmd)

    def init(self, protocol="6"):
        self.at("Z")
        time.sleep(0.5)
        self.at("E0")     # no echo
        self.at("L0")     # no linefeeds
        self.at("S0")     # no spaces
        self.at("H1")     # headers on — we need to know who answered
        self.at("SP" + protocol)
        return self.raw("0100")

    def set_header(self, header):
        if header != self.header:
            self.at("SH" + header)
            self.header = header

    # -- requests ----------------------------------------------------------

    def request(self, payload_hex):
        """Send a raw service request. Refuses anything that could write."""
        service = int(payload_hex[:2], 16)
        if service not in READ_ONLY_SERVICES:
            raise WriteAttempted(
                f"service 0x{service:02X} is not read-only; refusing to send it")
        return self.raw(payload_hex)

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


def classify(lines, service):
    """(kind, detail, data_hex) for a reply.

    kind is 'positive', 'negative', 'silent' or 'error'.
    """
    if not lines:
        return "silent", "", ""
    joined = "".join(lines).upper()
    if "NODATA" in joined.replace(" ", ""):
        return "silent", "NO DATA", ""
    if any(w in joined for w in ("BUSINIT", "CANERROR", "BUFFERFULL",
                                 "UNABLETOCONNECT", "STOPPED", "ERROR")):
        return "error", joined[:40], ""

    positive = f"{service + 0x40:02X}"
    for ln in lines:
        body = ln.replace(" ", "").upper()
        # With headers on, the reply is <header><pci?><data>. Find the
        # service echo rather than assuming a fixed offset.
        i = body.find("7F")
        if i >= 0 and len(body) >= i + 6 and body[i + 2:i + 4] == f"{service:02X}":
            code = int(body[i + 4:i + 6], 16)
            return "negative", NRC.get(code, f"NRC 0x{code:02X}"), ""
        j = body.find(positive)
        if j >= 0:
            return "positive", ln, body[j:]
    return "silent", lines[0][:40], ""

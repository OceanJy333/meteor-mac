# input: supplied CD key; output: installer-format registry value; pos: InstallUtil.dll compatibility.
import hashlib

def installed_serial(cd_key: bytes) -> bytes:
    # REA InstallUtil.dll HashCDKey 0x100011e0: normalize, omit region prefix,
    # hash the remainder, then replace the latter half with a second digest slice.
    normalized = bytes(c for c in cd_key[:127].lower() if 48 <= c <= 57 or 97 <= c <= 122)[2:]
    length = len(normalized)
    first = hashlib.md5(normalized).hexdigest().encode('ascii')
    half = length // 2
    second = hashlib.md5(first[:half]).hexdigest().encode('ascii')
    return first[:half] + second[half:length]

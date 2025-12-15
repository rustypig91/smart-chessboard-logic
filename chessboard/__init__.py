import os
import io

is_raspberrypi = False
if os.name != 'posix':
    is_raspberrypi = False
try:
    with io.open('/proc/cpuinfo', 'r') as cpuinfo:
        for line in cpuinfo:
            if line.startswith('Model') and 'Raspberry Pi' in line:
                is_raspberrypi = True

except Exception:
    is_raspberrypi = False

"""Helper: print APP_VERSION from constants.py (used by build.bat / pack_release.bat)"""
import re
with open('core/constants.py', encoding='utf-8') as f:
    m = re.search(r'APP_VERSION\s*=\s*"(.+?)"', f.read())
    print(m.group(1) if m else '0.0.0')

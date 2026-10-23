"""Contributor source boundaries. Platform mechanisms belong to the SDK."""
import re

from .formats import require



def validate_source_boundary(source, name='<engine>'):
    # This is an architectural lint, not a C++ parser or a security sandbox.
    # Strip comments so explanatory text does not count as an implementation.
    code = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    require(not re.search(r'^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b', code, re.M),
            name + ': conditional compilation belongs in SDK support code')
    require(not re.search(r'\b(_WIN32|__bfin__|__asm__|asm)\b', code),
            name + ': platform/compiler primitives belong in SDK support code')
    require(not re.search(r'#\s*include\s*[<"](?:windows\.h|io\.h|fcntl\.h)[>"]', code),
            name + ': OS headers belong in SDK support code')

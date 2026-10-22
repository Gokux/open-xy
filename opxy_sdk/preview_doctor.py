"""Check browser-preview prerequisites by compiling and running a WASM probe."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from .formats import require


def run(command):
    try:
        result = subprocess.run([str(value) for value in command], capture_output=True,
                                text=True, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as error:
        raise ValueError('Prerequisite probe timed out: ' + str(command[0])) from error
    require(result.returncode == 0, result.stdout + result.stderr)
    return result.stdout.strip()


def check(compiler='clang++'):
    require(sys.version_info >= (3, 11), 'Use Python 3.11 or newer.')
    print('Python: ' + sys.version.split()[0])
    try:
        numpy = version('numpy')
    except PackageNotFoundError:
        raise ValueError('Install the preview dependency: python -m pip install numpy==2.3.5') from None
    require(numpy == '2.3.5', 'Install the pinned preview dependency: python -m pip install numpy==2.3.5')
    print('NumPy: ' + numpy)
    node = shutil.which('node')
    require(node, 'Install Node 22 or newer and make node available on PATH.')
    node_version = run([node, '--version'])
    require(int(node_version.lstrip('v').split('.')[0]) >= 22, 'Use Node 22 or newer.')
    print('Node: ' + node_version)
    executable = shutil.which(str(compiler))
    require(executable, 'Install LLVM with wasm32/wasm-ld; pass its clang++ path with --cxx.')
    executable = Path(executable).resolve()
    try:
        with tempfile.TemporaryDirectory(prefix='opxy-preview-doctor-') as temporary:
            directory = Path(temporary).resolve()
            source = directory / 'probe.cpp'
            module = directory / 'probe.wasm'
            source.write_text('extern "C" int opxy_probe() { return 42; }\n', encoding='utf-8')
            run([executable, '--target=wasm32', '-nostdlib', source, '-o', module,
                 '-Wl,--no-entry', '-Wl,--export=opxy_probe'])
            run([node, '--input-type=module', '-e',
                 "import{readFileSync}from'node:fs';"
                 "const{instance}=await WebAssembly.instantiate(readFileSync(process.argv[1]));"
                 "if(instance.exports.opxy_probe()!==42)throw Error('WASM probe failed');", module])
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise ValueError('This compiler could not build and run WebAssembly. '
                         'Choose LLVM with wasm32 and wasm-ld using --cxx.\n' + str(error)) from error
    print('Clang: ' + str(executable))
    print('PASS: WebAssembly compilation, linking and execution. No firmware or device required.')
    return 0

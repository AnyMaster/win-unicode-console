
from ctypes import byref, windll, c_ulong

from win_unicode_console.buffer import get_buffer

import io
import sys
import time


kernel32 = windll.kernel32
GetStdHandle = kernel32.GetStdHandle
ReadConsoleW = kernel32.ReadConsoleW
WriteConsoleW = kernel32.WriteConsoleW
GetLastError = kernel32.GetLastError


ERROR_SUCCESS = 0
ERROR_NOT_ENOUGH_MEMORY = 8
ERROR_OPERATION_ABORTED = 995

STDIN_HANDLE = GetStdHandle(-10)
STDOUT_HANDLE = GetStdHandle(-11)
STDERR_HANDLE = GetStdHandle(-12)

STDIN_FILENO = 0
STDOUT_FILENO = 1
STDERR_FILENO = 2

EOF = b"\x1a"

MAX_BYTES_WRITTEN = 32767	# arbitrary because WriteConsoleW ability to write big buffers depends on heap usage


class WindowsConsoleRawIOBase(io.RawIOBase):
	def __init__(self, name, handle):
		self.name = name
		self.handle = handle
	
	def __repr__(self):
		return "<{} {}>".format(self.__class__.__name__, repr(self.name))

class WindowsConsoleRawReader(WindowsConsoleRawIOBase):
	def readable(self):
		return True
	
	def readinto(self, b):
		bytes_to_be_read = len(b)
		if not bytes_to_be_read:
			return 0
		elif bytes_to_be_read % 2:
			raise ValueError("cannot read odd number of bytes from UTF-16-LE encoded console")
		
		buffer = get_buffer(b, writable=True)
		code_units_to_be_read = bytes_to_be_read // 2
		code_units_read = c_ulong()
		
		retval = ReadConsoleW(self.handle, buffer, code_units_to_be_read, byref(code_units_read), None)
		if GetLastError() == ERROR_OPERATION_ABORTED:
			time.sleep(0.1)	# wait for KeyboardInterrupt
		if not retval:
			raise OSError("Windows error {}".format(GetLastError()))
		
		if buffer[0] == EOF:
			return 0
		else:
			return 2 * code_units_read.value

class WindowsConsoleRawWriter(WindowsConsoleRawIOBase):
	def writable(self):
		return True
	
	@staticmethod
	def _error_message(errno):
		if errno == ERROR_SUCCESS:
			return "Windows error {} (ERROR_SUCCESS); zero bytes written on nonzero input, probably just one byte given".format(errno)
		elif errno == ERROR_NOT_ENOUGH_MEMORY:
			return "Windows error {} (ERROR_NOT_ENOUGH_MEMORY); try to lower `win_unicode_console.streams.MAX_BYTES_WRITTEN`".format(errno)
		else:
			return "Windows error {}".format(errno)
	
	def write(self, b):
		bytes_to_be_written = len(b)
		buffer = get_buffer(b)
		code_units_to_be_written = min(bytes_to_be_written, MAX_BYTES_WRITTEN) // 2
		code_units_written = c_ulong()
		
		retval = WriteConsoleW(self.handle, buffer, code_units_to_be_written, byref(code_units_written), None)
		bytes_written = 2 * code_units_written.value
		
		# fixes both infinite loop of io.BufferedWriter.flush() on when the buffer has odd length
		#	and situation when WriteConsoleW refuses to write lesser that MAX_BYTES_WRITTEN bytes
		if bytes_written == 0 != bytes_to_be_written:
			raise OSError(self._error_message(GetLastError()))
		else:
			return bytes_written


stdin = io.TextIOWrapper(
	io.BufferedReader(
		WindowsConsoleRawReader("<stdin>", STDIN_HANDLE)),
	encoding="utf-16-le",
	line_buffering=True)

stdout = io.TextIOWrapper(
	io.BufferedWriter(
		WindowsConsoleRawWriter("<stdout>", STDOUT_HANDLE)),
	encoding = "utf-16-le",
	line_buffering = True)

stderr = io.TextIOWrapper(
	io.BufferedWriter(
		WindowsConsoleRawWriter("<stderr>", STDERR_HANDLE)),
	encoding="utf-16-le",
	line_buffering=True)


def disable():
	sys.stdin.flush()
	sys.stdout.flush()
	sys.stderr.flush()
	sys.stdin = sys.__stdin__
	sys.stdout = sys.__stdout__
	sys.stderr = sys.__stderr__

def check_stream(stream, fileno):
	try:
		_fileno = stream.fileno()
	except io.UnsupportedOperation:
		return False
	else:
		if _fileno == fileno and stream.isatty():
			stream.flush()
			return True
		else:
			return False
	
def enable_reader():
	if check_stream(sys.stdin, STDIN_FILENO):
		sys.stdin = stdin

def enable_writer():
	if check_stream(sys.stdout, STDOUT_FILENO):
		sys.stdout = stdout

def enable_error_writer():
	if check_stream(sys.stderr, STDERR_FILENO):
		sys.stderr = stderr

def enable():
	enable_reader()
	enable_writer()
	enable_error_writer()


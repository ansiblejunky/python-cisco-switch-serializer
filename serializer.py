import time
import sys
import glob

# Dependency - pyserial
# python -m pip install pyserial
# https://pyserial.readthedocs.io/en/latest/pyserial.html
import serial

# Handle Python 2 (raw_input) and Python 3 (input)
from builtins import input

DEFAULT_RETURN = '\r'
DEFAULT_COMMAND_QUIT = 'exitnow'
DEFAULT_BLANK_COMMAND = " "
CISCO_VERSION = "16.3.2"

# TODO: handle when "invalid command" is returned from Cisco - end everything but ONLY in config mode, not interactive mode!

class SerialWrapper(object):

    serialConn = None
    serialPort = "UNDEFINED"

    def getSerialPorts(self):
        """ Lists serial port names

            :raises EnvironmentError:
                On unsupported or unknown platforms
            :returns:
                A list of the serial ports available on the system
        """
        if sys.platform.startswith('win'):
            ports = ['COM%s' % (i + 1) for i in range(256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            # this excludes your current terminal "/dev/tty"
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/tty.*')
        else:
            raise EnvironmentError('Unsupported platform')

        result = []
        for port in ports:
            try:
                s = serial.Serial(port)
                s.close()
                result.append(port)
            except (OSError, serial.SerialException):
                pass
        return result

    def getOutput(self, serialConn, printOutput=None):
        if printOutput == None:
            printOutput = True
        time.sleep(1)
        out = ''
        while True:
            chr = serialConn.read(1)
            out += chr
            if chr=='':
                break
        if out != '' and printOutput:
            print(out)
        return out

    def getInput(self):
        # get keyboard input
        ret = input("switch>> ")
        return ret

    def sendCommand(self, serialConn, cmd):
        serialConn.write(cmd + DEFAULT_RETURN)

    def sendCommandAndGetOutput(self, serialConn, cmd, printOutput=None):
        self.sendCommand(serialConn, cmd)
        return self.getOutput(serialConn, printOutput)

    def interactiveMode(self, serialConn=None):
        # allow temporary serial connection
        if serialConn == None:
            serialConn = self.serialConn
        
        # initialize prompt
        self.sendCommand(serialConn, "")
        resultString = self.getOutput(serialConn)
        while True:
            print('Enter your commands below - use \'' + DEFAULT_COMMAND_QUIT + '\' to quit the application')
            inputString = self.getInput()
            # force program to do non-graceful quit
            if inputString == DEFAULT_COMMAND_QUIT:
                serialConn.close()
                exit()
            self.sendCommand(serialConn, inputString)
            self.getOutput(serialConn)


class CiscoSerialWrapper(SerialWrapper):

    DEFAULT_CISCO_CONFIG = "Would you like to enter the initial configuration dialog?"
    DEFAULT_CISCO_KEYWORD = "Switch"
    DEFAULT_CISCO_KEYWORD_MORE = "--More--"
    DEFAULT_CISCO_PROMPT1 = ">"
    DEFAULT_CISCO_PROMPT2 = "#"
    DEFAULT_CISCO_PASSWORD = "Password"
    DEFAULT_PASSWORD = "mysecretpassword"
    DEFAULT_CISCO_INVALID_INPUT = "Invalid input detected"
    serialPortExists = False

    def __init__(self):
        self.availableSerialPorts = self.getSerialPorts()
        print("Found the following serial ports:")
        print(self.availableSerialPorts)
        print("Searching for Cisco switch software...")
        self.findCiscoPrompt()
        if not self.serialPortExists:
            print("WARNING: No Cisco switch was found on any serial port. Make sure it is properly connected!")
        else:
            print("Found Cisco switch software on port " + self.serialPort)
            print("Preparing default Cisco switch software...")
            self.prepareCiscoPrompt()
            print("Ready to begin...")
            print("")

    def debug(self, msg):
        print(msg)

    def findCiscoPrompt(self):
        self.serialPortExists = False
        for port in self.availableSerialPorts:
            try:
                print("Testing port " + port + " ...")
                s = serial.Serial(port=port, baudrate=9600, parity='N', stopbits=1, bytesize=8, timeout=1, xonxoff=0, rtscts=0)
                self.sendCommand(s, "")
                resultString = self.getOutput(s, False)
                #self.debug("resultString = '" + resultString + "'")
                if (resultString.endswith(self.DEFAULT_CISCO_PROMPT1)) or (resultString.endswith(self.DEFAULT_CISCO_PROMPT2)) or (self.DEFAULT_CISCO_CONFIG in resultString) or (self.DEFAULT_CISCO_KEYWORD_MORE in resultString):
                    self.serialPort = port
                    self.serialConn = s
                    self.serialPortExists = True
                    return
                s.close()
            except (OSError, serial.SerialException):
                pass
        return ""

    def getCiscoVersion(self):
        resultString = self.sendCommandAndGetOutput(self.serialConn, "show ver | begin SW Ver", False)


    def prepareCiscoPrompt(self):
        # skip initial cisco config or exit from special modes
        resultString = self.sendCommandAndGetOutput(self.serialConn, DEFAULT_BLANK_COMMAND, False)
        while not resultString.endswith(self.DEFAULT_CISCO_PROMPT1):
            # skip initial configuration
            if self.DEFAULT_CISCO_CONFIG in resultString:
                self.sendCommand(self.serialConn, "no")
                resultString = self.getOutput(self.serialConn, False)
                self.sendCommand(self.serialConn, "yes")
                resultString = self.getOutput(self.serialConn, False)
                self.sendCommand(self.serialConn, "")
                resultString = self.getOutput(self.serialConn, False)
            else:
                self.sendCommand(self.serialConn, "exit")
                resultString = self.getOutput(self.serialConn, False)
            resultString = self.sendCommandAndGetOutput(self.serialConn, DEFAULT_BLANK_COMMAND, False)            

    def configureSwitchUsingFile(self, fileName):
        f = open(fileName, "r")
        lines = f.read().splitlines()
        f.close()

        for cmd in lines:
            if cmd.strip() == "":
                continue
            if cmd[0] == "#":
                continue
            if cmd == "!":
                resultString = self.sendCommandAndGetOutput(self.serialConn, DEFAULT_BLANK_COMMAND, True)
            else:
                resultString = self.sendCommandAndGetOutput(self.serialConn, cmd, True)
                if self.DEFAULT_CISCO_INVALID_INPUT in resultString:
                    print("Last command failed... ending session.")
                    exit()
        print("")
        print("Configuration completed.")

    def configureSwitch(self):
        # disable cisco initial configuration
        self.sendCommand(self.serialConn, "")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "enable")
        resultString = self.getOutput(self.serialConn)
        if self.DEFAULT_CISCO_PASSWORD in resultString:
            self.sendCommand(self.serialConn, self.DEFAULT_PASSWORD)
            resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "configure terminal")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "enable secret " + self.DEFAULT_PASSWORD)
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "int gig 0/0")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "ip add 192.168.8.104 255.255.255.0")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "no shut")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "exit")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "exit")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "exit")
        resultString = self.getOutput(self.serialConn)

    def resetSwitch(self):
        self.sendCommand(self.serialConn, "enable")
        resultString = self.getOutput(self.serialConn)
        if "Password" in resultString:
            self.sendCommand(self.serialConn, self.DEFAULT_PASSWORD)
            resultString = self.getOutput(self.serialConn)  
        self.sendCommand(self.serialConn, "write erase")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "reload")
        resultString = self.getOutput(self.serialConn)  
        self.sendCommand(self.serialConn, "no")
        resultString = self.getOutput(self.serialConn)
        self.sendCommand(self.serialConn, "")
        resultString = self.getOutput(self.serialConn)


def showHeader():
    print("Welcome to the Serializer to manage Cisco Switch")
    print("")

def showHelp():
    print("Select operation for Cisco Switch:")
    print("")
    print("reset               - reset the switch to default configuration")
    print("config <configfile> - load initial configuration")
    print("inter               - interactive mode (run other commands)")
    print("")
    print("Configuration files <configfile> should be written as line-by-line commands. It handles the following")
    print("special commands:")
    print("")
    print("!  = ENTER")
    print("#  = any line starting with # are considered a commented line (ignored)")
    print("")

if __name__ == '__main__':

    showHeader()

    if len(sys.argv) == 1:
        showHelp()
        exit()

    # verify cisco connection exists
    ser = CiscoSerialWrapper()
    # exit if no connection was found
    if not ser.serialPortExists:
        exit()

    if sys.argv[1] == "inter":
        ser.interactiveMode()
    elif sys.argv[1] == "reset":
        ser.resetSwitch()
    elif sys.argv[1] == "config":
        if len(sys.argv) < 3:
            print("Provide a configuration file as a parameter.")
            showHelp()
            exit()
        fileName = sys.argv[2]
        ser.configureSwitchUsingFile(fileName)
        #ser.configureSwitch()

